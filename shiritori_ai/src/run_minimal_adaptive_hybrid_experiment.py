"""Short D10000 screening for score-gap Beam and selective exact proofs."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import statistics
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable

from adaptive_hybrid import (
    AdaptiveHybridConfig,
    ScoreGapDynamicBeamAlphaBetaAgent,
    SelectiveProofAlphaBetaAgent,
    position_scale,
)
from agents import BeamAlphaBetaAgent
from exact_solver import AnalysisLimitExceeded, ShiritoriSolver
from match import simulate_runtime_match
from run_graph_control_comparison import append_jsonl, read_jsonl, write_csv
from run_search_parameter_tuning import restore_position
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "data/dictionaries"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/minimal_adaptive_hybrid/D10000"
DEFAULT_FIXED = (
    PROJECT_ROOT
    / "results/search_parameter_tuning/f5a877380b91/fixed_positions.json"
)
FORMAT_VERSION = "minimal_adaptive_hybrid_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("prepare", "benchmark", "matches", "analyze", "all"),
        default="all",
    )
    parser.add_argument("--source-log", type=Path)
    parser.add_argument("--fixed-positions", type=Path, default=DEFAULT_FIXED)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--position-limit", type=int, default=50)
    parser.add_argument("--truth-target", type=int, default=30)
    parser.add_argument("--truth-time-sec", type=float, default=0.6)
    parser.add_argument("--decision-time-sec", type=float, default=0.3)
    parser.add_argument("--reference-time-sec", type=float, default=1.0)
    parser.add_argument("--match-seeds", default="0,1,2,3,4")
    parser.add_argument(
        "--match-profiles",
        default="",
        help=(
            "comma-separated profiles to match even when screening rejected "
            "them; empty uses accepted profiles only"
        ),
    )
    parser.add_argument(
        "--match-plan",
        choices=("baseline", "round_robin"),
        default="baseline",
        help="baseline pairs each profile with fixed; round_robin compares all",
    )
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--max-match-time-sec", type=float, default=90.0)
    parser.add_argument("--confirm-d10000", action="store_true")
    args = parser.parse_args()
    if not args.confirm_d10000:
        parser.error("D10000の実験には --confirm-d10000 が必要です")
    if args.position_limit < 1 or not 20 <= args.truth_target <= 50:
        parser.error("position-limit must be positive and truth-target must be 20..50")
    return args


def latest_source_log() -> Path:
    paths = list(
        (
            PROJECT_ROOT
            / "results/position_adaptive_hybrid_v2/tune/D10000"
        ).glob("*/raw_matches.jsonl")
    )
    if not paths:
        paths = list(PROJECT_ROOT.glob("results/**/raw_matches.jsonl"))
    candidates = [
        path
        for path in paths
        if path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        raise FileNotFoundError("D10000 raw_matches.jsonl was not found")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _position_key(position: dict[str, Any]) -> tuple[str, tuple[tuple[int, int], ...]]:
    return (
        str(position["runtime"]),
        tuple(tuple(edge) for edge in position["edge_history"]),
    )


def _position_record(
    *,
    row: dict[str, Any],
    state: AIEdgeState,
    history: list[list[int]],
    turn: int,
) -> dict[str, Any]:
    scale = position_scale(state, 1_000_000)
    return {
        "position_id": f"log_seed{row['dictionary_seed']}_{row['match_id']}_t{turn}",
        "runtime": str(Path(row["runtime"]).resolve()),
        "seed": int(row["dictionary_seed"]),
        "source_match_id": str(row["match_id"]),
        "turn": turn,
        "edge_history": [list(edge) for edge in history],
        "legal_edge_count": scale.legal_edge_types,
        "remaining_word_count": sum(state.edge_counts),
        "position_scale": asdict(scale),
        "category": "exact_candidate" if scale.reachable_word_count <= 40 else "late",
        "categories": ["D10000", "saved_match", "late"],
    }


def extract_saved_positions(
    source_log: Path,
    *,
    max_candidates: int = 500,
) -> list[dict[str, Any]]:
    runtimes: dict[str, RuntimeDictionary] = {}
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[int, int], ...]]] = set()
    with source_log.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if int(row.get("dict_size", 0)) != 10_000:
                continue
            runtime_path = str(Path(row["runtime"]).resolve())
            runtime = runtimes.get(runtime_path)
            if runtime is None:
                runtime = RuntimeDictionary.load(Path(runtime_path))
                runtimes[runtime_path] = runtime
            state = AIEdgeState.initial(runtime)
            history: list[list[int]] = []
            moves = row.get("history", [])
            late_start = max(1, len(moves) - 35)
            for turn, move in enumerate(moves):
                if turn >= late_start and len(state.available_edges()) >= 2:
                    position = _position_record(
                        row=row, state=state, history=history, turn=turn
                    )
                    key = _position_key(position)
                    if key not in seen:
                        seen.add(key)
                        candidates.append(position)
                edge = [int(move["start_id"]), int(move["end_id"])]
                state.apply_edge(edge[0], edge[1])
                history = [*history, edge]
            if len(candidates) >= max_candidates:
                break
    candidates.sort(
        key=lambda item: (
            int(item["position_scale"]["reachable_word_count"]),
            int(item["position_scale"]["reachable_edge_types"]),
            int(item["legal_edge_count"]),
            str(item["position_id"]),
        )
    )
    return candidates


def exact_root_outcomes(
    position: dict[str, Any],
    *,
    timeout_sec: float,
    max_states: int = 200_000,
) -> dict[str, Any] | None:
    _runtime, state = restore_position(position)
    edges = state.available_edges()
    if len(edges) < 2:
        return None
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    n_id = state.edge_dictionary.char_to_id.get("ん")
    for edge in edges:
        remaining = timeout_sec - (time.perf_counter() - started)
        if remaining <= 0:
            return None
        state.apply_edge(*edge)
        try:
            if edge[1] == n_id:
                events.append(
                    {
                        "edge": list(edge),
                        "result": "loss",
                        "searched_states": 0,
                        "trivial": True,
                    }
                )
                continue
            assert state.required_char_id is not None
            residual = state.edge_dictionary.__class__(
                dictionary_hash=state.edge_dictionary.dictionary_hash,
                normalization_version=state.edge_dictionary.normalization_version,
                char_to_id=dict(state.edge_dictionary.char_to_id),
                id_to_char=state.edge_dictionary.id_to_char,
                char_count=state.edge_dictionary.char_count,
                edge_instance_count=sum(state.edge_counts),
                initial_edge_counts=tuple(state.edge_counts),
                initial_active_end_masks=tuple(state.active_end_masks),
            )
            solver = ShiritoriSolver(
                residual,
                max_states=max_states,
                timeout_sec=remaining,
            )
            try:
                opponent_wins = solver.solve(state.required_char_id)
            except (AnalysisLimitExceeded, RecursionError):
                return None
            events.append(
                {
                    "edge": list(edge),
                    "result": "loss" if opponent_wins else "win",
                    "searched_states": solver.count_states(),
                    "trivial": solver.count_states() <= 1,
                }
            )
        finally:
            state.undo_edge()
    wins = [event["edge"] for event in events if event["result"] == "win"]
    losses = [event["edge"] for event in events if event["result"] == "loss"]
    return {
        "position_id": position["position_id"],
        "winning_edges": wins,
        "losing_edges": losses,
        "mixed_outcomes": bool(wins and losses),
        "candidate_count": len(events),
        "searched_state_count": sum(
            int(event["searched_states"]) for event in events
        ),
        "elapsed_time_sec": time.perf_counter() - started,
        "events": events,
    }


def prepare(args: argparse.Namespace) -> tuple[Path, Path]:
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.source_log.resolve() if args.source_log else latest_source_log()
    print(f"source log: {source}", flush=True)
    extracted = extract_saved_positions(source)
    truth_rows: list[dict[str, Any]] = []
    truth_positions: list[dict[str, Any]] = []
    truth_attempts = sorted(
        extracted,
        key=lambda item: (
            int(item["legal_edge_count"]),
            int(item["position_scale"]["reachable_word_count"]),
            str(item["position_id"]),
        ),
    )[: max(20, args.truth_target)]
    incomplete_truth_count = 0
    for index, position in enumerate(truth_attempts, start=1):
        truth = exact_root_outcomes(
            position, timeout_sec=args.truth_time_sec
        )
        status = "complete" if truth is not None else "incomplete"
        print(
            f"[truth {index}/{len(truth_attempts)}] "
            f"{position['position_id']}: {status}",
            flush=True,
        )
        if truth is None:
            incomplete_truth_count += 1
            continue
        truth_rows.append(truth)
        truth_positions.append(position)
        if len(truth_rows) >= args.truth_target:
            break

    fixed_data = _load_json(args.fixed_positions)
    fixed = fixed_data if isinstance(fixed_data, list) else fixed_data["positions"]
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[int, int], ...]]] = set()
    for position in [*truth_positions, *fixed, *extracted]:
        key = _position_key(position)
        if key in seen:
            continue
        seen.add(key)
        selected.append(position)
        if len(selected) >= args.position_limit:
            break
    positions_path = args.output / "positions.json"
    truth_path = args.output / "exact_truth.json"
    _write_json(positions_path, selected)
    _write_json(truth_path, truth_rows)
    _write_json(
        args.output / "prepare_summary.json",
        {
            "format_version": FORMAT_VERSION,
            "source_log": str(source),
            "extracted_candidate_count": len(extracted),
            "exact_truth_attempt_count": len(truth_attempts),
            "exact_truth_incomplete_count": incomplete_truth_count,
            "saved_position_count": len(selected),
            "exact_truth_count": len(truth_rows),
            "mixed_exact_truth_count": sum(
                bool(row["mixed_outcomes"]) for row in truth_rows
            ),
        },
    )
    return positions_path, truth_path


def profiles() -> dict[str, tuple[str, AdaptiveHybridConfig | None]]:
    base = AdaptiveHybridConfig()
    return {
        "fixed_beam_alpha_beta": ("baseline", None),
        "gap_conservative": (
            "gap",
            replace(
                base,
                score_gap_wide_threshold=3.0,
                score_gap_narrow_threshold=16.0,
                score_gap_min_widths=(8, 6, 3, 2),
                score_gap_max_widths=(16, 10, 5, 2),
            ),
        ),
        "gap_responsive": (
            "gap",
            replace(
                base,
                score_gap_wide_threshold=6.0,
                score_gap_narrow_threshold=12.0,
                score_gap_min_widths=(6, 4, 2, 1),
                score_gap_max_widths=(18, 12, 6, 3),
            ),
        ),
        "proof_strict": (
            "proof",
            replace(
                base,
                exact_max_reachable_words=18,
                exact_max_edge_types=12,
                exact_max_vertices=10,
                exact_max_state_estimate=50_000,
                exact_max_states=50_000,
                exact_time_fraction=0.15,
                exact_time_cap_sec=0.045,
                exact_normal_time_reserve_sec=0.0,
                selective_proof_score_margin=4.0,
                selective_proof_candidate_limit=3,
                selective_proof_max_calls=3,
            ),
        ),
        "proof_moderate": (
            "proof",
            replace(
                base,
                exact_max_reachable_words=28,
                exact_max_edge_types=18,
                exact_max_vertices=12,
                exact_max_state_estimate=100_000,
                exact_max_states=100_000,
                exact_time_fraction=0.20,
                exact_time_cap_sec=0.060,
                exact_normal_time_reserve_sec=0.0,
                selective_proof_score_margin=8.0,
                selective_proof_candidate_limit=3,
                selective_proof_max_calls=3,
            ),
        ),
    }


def build_screening_agent(
    profile: str,
    *,
    time_limit_sec: float,
    fixed_depth: bool,
    random_seed: int = 0,
):
    kind, config = profiles()[profile]
    common = {
        "depth": 8,
        "max_depth": 8 if fixed_depth else 9,
        "time_limit_sec": time_limit_sec,
        "adaptive_depth": not fixed_depth,
        "min_depth": 1,
        "depth_recovery_turns": 2,
        "depth_decrease_ratio": 0.95,
        "depth_recovery_ratio": 0.6,
        "depth_step": 1,
        "timeout_decreases_depth": True,
        "target_time_sec": None if fixed_depth else time_limit_sec * 0.6,
        "beam_widths": (12, 8, 4, 2),
        "random_seed": random_seed,
    }
    if kind == "baseline":
        return BeamAlphaBetaAgent(**common)
    assert config is not None
    if kind == "gap":
        return ScoreGapDynamicBeamAlphaBetaAgent(
            **common, adaptive_config=config
        )
    return SelectiveProofAlphaBetaAgent(
        **common, adaptive_config=config
    )


def _edge(decision: Any) -> list[int] | None:
    if decision.start_id is None or decision.end_id is None:
        return None
    return [int(decision.start_id), int(decision.end_id)]


def benchmark(args: argparse.Namespace) -> Path:
    positions = _load_json(args.output / "positions.json")
    truth = {
        row["position_id"]: row
        for row in _load_json(args.output / "exact_truth.json")
    }
    raw_path = args.output / "benchmark_runs.jsonl"
    completed = {
        (row["profile"], row["position_id"]) for row in read_jsonl(raw_path)
    }
    jobs = [
        (profile, position)
        for profile in ("reference", *profiles())
        for position in positions
    ]
    for index, (profile, position) in enumerate(jobs, start=1):
        key = (profile, position["position_id"])
        if key in completed:
            continue
        _runtime, state = restore_position(position)
        if profile == "reference":
            agent = BeamAlphaBetaAgent(
                depth=10,
                max_depth=10,
                time_limit_sec=args.reference_time_sec,
                adaptive_depth=False,
                beam_widths=(12, 8, 4, 2),
                random_seed=0,
            )
        else:
            agent = build_screening_agent(
                profile,
                time_limit_sec=args.decision_time_sec,
                fixed_depth=True,
            )
        decision = agent.choose_edge(state)
        state.assert_aggregates_consistent()
        extra = decision.extra
        exact = truth.get(position["position_id"])
        row = {
            "profile": profile,
            "position_id": position["position_id"],
            "selected_edge": _edge(decision),
            "elapsed_time_sec": decision.elapsed_time_sec,
            "timed_out": decision.timed_out,
            "score": decision.score,
            "nodes_searched": int(extra.get("nodes_searched", 0)),
            "effective_depth": int(extra.get("effective_depth", 0)),
            "completed_root_moves": int(extra.get("completed_root_moves", 0)),
            "selected_root_candidate_count": int(
                extra.get("selected_root_candidate_count", 0)
            ),
            "root_search_scores": extra.get("root_search_scores", []),
            "beam_widths_used": extra.get("beam_widths_used", {}),
            "beam_candidate_counts_by_ply": extra.get(
                "beam_candidate_counts_by_ply", {}
            ),
            "beam_selected_counts_by_ply": extra.get(
                "beam_selected_counts_by_ply", {}
            ),
            "beam_pruned_counts_by_ply": extra.get(
                "beam_pruned_counts_by_ply", {}
            ),
            "beam_score_gap_sums_by_ply": extra.get(
                "beam_score_gap_sums_by_ply", {}
            ),
            "beam_score_gap_counts_by_ply": extra.get(
                "beam_score_gap_counts_by_ply", {}
            ),
            "dynamic_beam_width_counts": extra.get(
                "dynamic_beam_width_counts", {}
            ),
            "exact_attempt_count": int(extra.get("exact_attempt_count", 0)),
            "exact_success_count": int(extra.get("exact_success_count", 0)),
            "exact_nontrivial_success_count": int(
                extra.get("exact_nontrivial_success_count", 0)
            ),
            "exact_total_time_sec": float(
                extra.get("exact_total_time_sec", 0.0)
            ),
            "root_choice_changed_by_exact": bool(
                extra.get("root_choice_changed_by_exact", False)
            ),
            "exact_call_events": extra.get("exact_call_events", []),
            "has_exact_truth": exact is not None,
            "mixed_exact_truth": bool(
                exact and exact.get("mixed_outcomes")
            ),
        }
        append_jsonl(raw_path, row)
        completed.add(key)
        print(
            f"[benchmark {len(completed)}/{len(jobs)}] "
            f"{profile} {position['position_id']}: "
            f"{decision.elapsed_time_sec:.3f}s",
            flush=True,
        )
    analyze_benchmark(args.output)
    return raw_path


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return statistics.fmean(rows) if rows else 0.0


def analyze_benchmark(output: Path) -> dict[str, Any]:
    rows = read_jsonl(output / "benchmark_runs.jsonl")
    truth = {
        row["position_id"]: row
        for row in _load_json(output / "exact_truth.json")
    }
    by_key = {
        (row["profile"], row["position_id"]): row for row in rows
    }
    position_ids = sorted({row["position_id"] for row in rows})
    reference_edges = {
        position_id: by_key[("reference", position_id)]["selected_edge"]
        for position_id in position_ids
        if ("reference", position_id) in by_key
        and not by_key[("reference", position_id)]["timed_out"]
        and by_key[("reference", position_id)]["completed_root_moves"]
        == by_key[("reference", position_id)][
            "selected_root_candidate_count"
        ]
    }

    def correctness(profile: str, position_id: str) -> bool | None:
        row = by_key.get((profile, position_id))
        if row is None or row["selected_edge"] is None:
            return None
        exact = truth.get(position_id)
        if exact and exact["mixed_outcomes"]:
            return row["selected_edge"] in exact["winning_edges"]
        reference = reference_edges.get(position_id)
        return None if reference is None else row["selected_edge"] == reference

    metrics: list[dict[str, Any]] = []
    baseline_changes: dict[str, dict[str, int]] = {}
    for profile in profiles():
        profile_rows = [
            by_key[(profile, position_id)]
            for position_id in position_ids
            if (profile, position_id) in by_key
        ]
        outcomes = [
            correctness(profile, position_id)
            for position_id in position_ids
        ]
        resolved = [value for value in outcomes if value is not None]
        changes = improvements = regressions = unknown = 0
        if profile != "fixed_beam_alpha_beta":
            for position_id in position_ids:
                row = by_key.get((profile, position_id))
                base = by_key.get(("fixed_beam_alpha_beta", position_id))
                if not row or not base or row["selected_edge"] == base["selected_edge"]:
                    continue
                changes += 1
                new_ok = correctness(profile, position_id)
                base_ok = correctness("fixed_beam_alpha_beta", position_id)
                if new_ok is True and base_ok is False:
                    improvements += 1
                elif new_ok is False and base_ok is True:
                    regressions += 1
                else:
                    unknown += 1
        baseline_changes[profile] = {
            "changes": changes,
            "improvements": improvements,
            "regressions": regressions,
            "unknown": unknown,
        }
        metrics.append(
            {
                "profile": profile,
                "position_count": len(profile_rows),
                "reference_denominator": len(resolved),
                "reference_match_rate": (
                    sum(resolved) / len(resolved) if resolved else 0.0
                ),
                "mean_elapsed_time_sec": _mean(
                    float(row["elapsed_time_sec"]) for row in profile_rows
                ),
                "mean_nodes_searched": _mean(
                    float(row["nodes_searched"]) for row in profile_rows
                ),
                "mean_effective_depth": _mean(
                    float(row["effective_depth"]) for row in profile_rows
                ),
                "timeout_rate": _mean(
                    bool(row["timed_out"]) for row in profile_rows
                ),
                "choice_change_count": changes,
                "improvement_count": improvements,
                "regression_count": regressions,
                "unknown_change_count": unknown,
                "exact_attempt_count": sum(
                    int(row["exact_attempt_count"]) for row in profile_rows
                ),
                "exact_success_count": sum(
                    int(row["exact_success_count"]) for row in profile_rows
                ),
                "exact_nontrivial_success_count": sum(
                    int(row["exact_nontrivial_success_count"])
                    for row in profile_rows
                ),
                "exact_choice_change_count": sum(
                    bool(row["root_choice_changed_by_exact"])
                    for row in profile_rows
                ),
            }
        )
    baseline = next(
        row for row in metrics if row["profile"] == "fixed_beam_alpha_beta"
    )
    accepted: dict[str, bool] = {}
    for row in metrics:
        profile = row["profile"]
        if profile.startswith("gap_"):
            accuracy_ok = (
                row["reference_match_rate"] + 0.01
                >= baseline["reference_match_rate"]
            )
            reduction = min(
                row["mean_elapsed_time_sec"]
                / max(baseline["mean_elapsed_time_sec"], 1e-12),
                row["mean_nodes_searched"]
                / max(baseline["mean_nodes_searched"], 1e-12),
            )
            accepted[profile] = accuracy_ok and reduction <= 0.90
        elif profile.startswith("proof_"):
            accepted[profile] = (
                row["exact_nontrivial_success_count"] > 0
                and row["exact_choice_change_count"] >= 2
                and row["improvement_count"] > row["regression_count"]
                and row["mean_elapsed_time_sec"]
                <= baseline["mean_elapsed_time_sec"] * 1.25
            )
    best_by_kind: dict[str, str] = {}
    for kind, prefix in (("gap", "gap_"), ("proof", "proof_")):
        passing = [
            row
            for row in metrics
            if row["profile"].startswith(prefix)
            and accepted.get(row["profile"], False)
        ]
        if passing:
            passing.sort(
                key=lambda row: (
                    -row["reference_match_rate"],
                    row["mean_elapsed_time_sec"],
                )
            )
            best_by_kind[kind] = passing[0]["profile"]
    summary = {
        "format_version": FORMAT_VERSION,
        "metrics": metrics,
        "accepted_profiles": accepted,
        "selected_profiles": best_by_kind,
        "stable_reference_position_count": len(reference_edges),
        "exact_truth_position_count": len(truth),
        "mixed_exact_truth_position_count": sum(
            bool(row["mixed_outcomes"]) for row in truth.values()
        ),
    }
    _write_json(output / "benchmark_summary.json", summary)
    write_csv(output / "benchmark_summary.csv", metrics)
    width_rows: list[dict[str, Any]] = []
    proof_event_rows: list[dict[str, Any]] = []
    for row in rows:
        for key, count in row.get(
            "dynamic_beam_width_counts", {}
        ).items():
            if ":" not in str(key):
                continue
            ply, width = str(key).split(":", 1)
            gap_count = float(
                row.get("beam_score_gap_counts_by_ply", {}).get(
                    ply,
                    row.get("beam_score_gap_counts_by_ply", {}).get(
                        int(ply), 0
                    ),
                )
            )
            gap_sum = float(
                row.get("beam_score_gap_sums_by_ply", {}).get(
                    ply,
                    row.get("beam_score_gap_sums_by_ply", {}).get(
                        int(ply), 0.0
                    ),
                )
            )
            width_rows.append(
                {
                    "profile": row["profile"],
                    "position_id": row["position_id"],
                    "ply": int(ply),
                    "beam_width": int(width),
                    "ordering_call_count": int(count),
                    "mean_top_score_gap_at_ply": (
                        gap_sum / gap_count if gap_count else 0.0
                    ),
                }
            )
        for event in row.get("exact_call_events", []):
            proof_event_rows.append(
                {
                    "profile": row["profile"],
                    "position_id": row["position_id"],
                    "location": event.get("location", ""),
                    "ply": event.get("ply", ""),
                    "target_candidate": event.get("target_candidate", ""),
                    "status": event.get("status", ""),
                    "result": event.get("result", ""),
                    "reachable_word_count": event.get(
                        "reachable_word_count", ""
                    ),
                    "reachable_edge_types": event.get(
                        "reachable_edge_types", ""
                    ),
                    "reachable_vertices": event.get(
                        "reachable_vertices", ""
                    ),
                    "legal_edge_types": event.get(
                        "legal_edge_types", ""
                    ),
                    "searched_states": event.get("searched_states", ""),
                    "elapsed_time_sec": event.get(
                        "elapsed_time_sec", ""
                    ),
                    "normal_score": event.get("normal_score", ""),
                    "exact_score": event.get("exact_score", ""),
                    "score_difference": event.get(
                        "score_difference", ""
                    ),
                    "trivial": event.get("trivial", ""),
                }
            )
    write_csv(output / "dynamic_beam_width_events.csv", width_rows)
    write_csv(output / "selective_proof_events.csv", proof_event_rows)
    make_plots(output, metrics)
    return summary


def make_plots(output: Path, metrics: list[dict[str, Any]]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    labels = [row["profile"].replace("_", "\n") for row in metrics]
    figures = (
        (
            "reference_match_rate",
            "Reference/exact move match rate",
            "reference_match_rate.png",
            lambda value: f"{value:.1%}",
        ),
        (
            "mean_elapsed_time_sec",
            "Mean decision time (sec)",
            "mean_decision_time.png",
            lambda value: f"{value:.3f}",
        ),
        (
            "mean_nodes_searched",
            "Mean searched nodes",
            "mean_nodes.png",
            lambda value: f"{value:.0f}",
        ),
    )
    for field, title, filename, formatter in figures:
        values = [float(row[field]) for row in metrics]
        fig, axis = plt.subplots(figsize=(11, 5))
        bars = axis.bar(labels, values)
        axis.set_title(title)
        axis.tick_params(axis="x", labelsize=8)
        top = max(values, default=1.0)
        axis.set_ylim(0, top * 1.18 if top else 1.0)
        for bar, value in zip(bars, values):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + top * 0.02,
                formatter(value),
                ha="center",
                va="bottom",
                fontsize=8,
            )
        fig.tight_layout()
        fig.savefig(output / filename, dpi=160)
        plt.close(fig)


def run_matches(args: argparse.Namespace) -> Path:
    summary = _load_json(args.output / "benchmark_summary.json")
    selected = summary["selected_profiles"]
    requested = [
        value.strip()
        for value in args.match_profiles.split(",")
        if value.strip()
    ]
    unknown = sorted(set(requested) - set(profiles()))
    if unknown:
        raise ValueError(
            "unknown match profile(s): " + ", ".join(unknown)
        )
    profiles_to_run = requested or list(selected.values())
    if args.match_plan == "round_robin":
        return run_round_robin_matches(args, profiles_to_run)
    raw_path = args.output / "short_matches.jsonl"
    seeds = tuple(
        int(value.strip())
        for value in args.match_seeds.split(",")
        if value.strip()
    )
    jobs = [
        (profile, seed, candidate_first)
        for profile in profiles_to_run
        for seed in seeds
        for candidate_first in (True, False)
    ]
    completed = {row["match_id"] for row in read_jsonl(raw_path)}
    for index, (profile, seed, candidate_first) in enumerate(jobs, start=1):
        first_name = profile if candidate_first else "fixed_beam_alpha_beta"
        second_name = "fixed_beam_alpha_beta" if candidate_first else profile
        match_id = f"D10000_seed{seed}_{first_name}_vs_{second_name}"
        if match_id in completed:
            continue
        runtime_path = (
            args.runtime_dir / f"D10000_L2-12_seed{seed}.runtime.json"
        )
        runtime = RuntimeDictionary.load(runtime_path)
        first = build_screening_agent(
            first_name,
            time_limit_sec=args.decision_time_sec,
            fixed_depth=False,
            random_seed=seed * 1000 + 1,
        )
        second = build_screening_agent(
            second_name,
            time_limit_sec=args.decision_time_sec,
            fixed_depth=False,
            random_seed=seed * 1000 + 2,
        )
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            first,
            second,
            max_moves=min(args.max_moves, runtime.word_count),
            max_match_time_sec=args.max_match_time_sec,
            match_id=match_id,
        )
        append_jsonl(
            raw_path,
            {
                "match_id": match_id,
                "profile": profile,
                "dictionary_seed": seed,
                "candidate_player": "first" if candidate_first else "second",
                "first_agent": first_name,
                "second_agent": second_name,
                "winner": result.winner,
                "turn_count": result.turn_count,
                "loss_reason": result.loss_reason,
                "invalid_move_count": int(
                    result.loss_reason == "invalid_ai_move"
                ),
                "match_elapsed_time_sec": result.match_elapsed_time_sec,
                "max_match_time_sec": result.max_match_time_sec,
                "dictionary_size": 10000,
                "decision_time_sec": args.decision_time_sec,
                "max_moves": min(args.max_moves, runtime.word_count),
                "candidate_depth": 8,
                "candidate_max_depth": 9,
                "adaptive_depth": True,
                "beam_widths": [12, 8, 4, 2],
                "first_timeout_count": result.first_timeout_count,
                "second_timeout_count": result.second_timeout_count,
            },
        )
        completed.add(match_id)
        print(
            f"[match {len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )
    analyze_matches(args.output)
    return raw_path


def run_round_robin_matches(
    args: argparse.Namespace,
    profiles_to_run: list[str],
) -> Path:
    agents = ["fixed_beam_alpha_beta", *profiles_to_run]
    if len(agents) != len(set(agents)):
        raise ValueError("round-robin agents must be unique")
    raw_path = args.output / "round_robin_matches.jsonl"
    completed_rows = read_jsonl(raw_path)
    completed = {row["match_id"] for row in completed_rows}

    baseline_path = args.output / "short_matches.jsonl"
    for row in read_jsonl(baseline_path):
        if {
            row.get("first_agent"),
            row.get("second_agent"),
        }.issubset(set(agents)) and row["match_id"] not in completed:
            append_jsonl(raw_path, {**row, "match_plan": "round_robin"})
            completed.add(row["match_id"])

    seeds = tuple(
        int(value.strip())
        for value in args.match_seeds.split(",")
        if value.strip()
    )
    jobs = [
        (left, right, seed, left_first)
        for left, right in itertools.combinations(agents, 2)
        for seed in seeds
        for left_first in (True, False)
    ]
    for left, right, seed, left_first in jobs:
        first_name = left if left_first else right
        second_name = right if left_first else left
        match_id = f"D10000_seed{seed}_{first_name}_vs_{second_name}"
        if match_id in completed:
            continue
        runtime_path = (
            args.runtime_dir / f"D10000_L2-12_seed{seed}.runtime.json"
        )
        runtime = RuntimeDictionary.load(runtime_path)
        first = build_screening_agent(
            first_name,
            time_limit_sec=args.decision_time_sec,
            fixed_depth=False,
            random_seed=seed * 1000 + 1,
        )
        second = build_screening_agent(
            second_name,
            time_limit_sec=args.decision_time_sec,
            fixed_depth=False,
            random_seed=seed * 1000 + 2,
        )
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            first,
            second,
            max_moves=min(args.max_moves, runtime.word_count),
            max_match_time_sec=args.max_match_time_sec,
            match_id=match_id,
        )
        append_jsonl(
            raw_path,
            {
                "match_id": match_id,
                "match_plan": "round_robin",
                "dictionary_seed": seed,
                "first_agent": first_name,
                "second_agent": second_name,
                "winner": result.winner,
                "turn_count": result.turn_count,
                "loss_reason": result.loss_reason,
                "invalid_move_count": int(
                    result.loss_reason == "invalid_ai_move"
                ),
                "match_elapsed_time_sec": result.match_elapsed_time_sec,
                "max_match_time_sec": result.max_match_time_sec,
                "dictionary_size": 10000,
                "decision_time_sec": args.decision_time_sec,
                "max_moves": min(args.max_moves, runtime.word_count),
                "candidate_depth": 8,
                "candidate_max_depth": 9,
                "adaptive_depth": True,
                "beam_widths": [12, 8, 4, 2],
                "first_timeout_count": result.first_timeout_count,
                "second_timeout_count": result.second_timeout_count,
            },
        )
        completed.add(match_id)
        print(
            f"[round-robin {len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )
    analyze_round_robin_matches(args.output)
    return raw_path


def analyze_round_robin_matches(output: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(output / "round_robin_matches.jsonl")
    agents = sorted(
        {
            str(row[side])
            for row in rows
            for side in ("first_agent", "second_agent")
        }
    )
    summary = []
    for agent in agents:
        selected = [
            row
            for row in rows
            if agent in {row["first_agent"], row["second_agent"]}
        ]
        wins = sum(
            (
                row["winner"] == "first"
                and row["first_agent"] == agent
            )
            or (
                row["winner"] == "second"
                and row["second_agent"] == agent
            )
            for row in selected
        )
        draws = sum(row["winner"] == "draw" for row in selected)
        losses = len(selected) - wins - draws
        first_rows = [
            row for row in selected if row["first_agent"] == agent
        ]
        second_rows = [
            row for row in selected if row["second_agent"] == agent
        ]
        summary.append(
            {
                "agent": agent,
                "match_count": len(selected),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": wins / len(selected) if selected else 0.0,
                "first_match_count": len(first_rows),
                "first_wins": sum(
                    row["winner"] == "first" for row in first_rows
                ),
                "second_match_count": len(second_rows),
                "second_wins": sum(
                    row["winner"] == "second" for row in second_rows
                ),
                "internal_timeout_count": sum(
                    int(row["first_timeout_count"])
                    + int(row["second_timeout_count"])
                    for row in selected
                ),
                "match_timeout_count": sum(
                    row["loss_reason"] == "match_timeout"
                    for row in selected
                ),
                "invalid_move_count": sum(
                    int(row["invalid_move_count"]) for row in selected
                ),
            }
        )
    _write_csv_lf(output / "round_robin_summary.csv", summary)
    _write_json(output / "round_robin_summary.json", summary)
    return summary


def analyze_matches(output: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(output / "short_matches.jsonl")
    summary: list[dict[str, Any]] = []
    for profile in sorted({row["profile"] for row in rows}):
        selected = [row for row in rows if row["profile"] == profile]
        wins = losses = draws = 0
        for row in selected:
            candidate = row["candidate_player"]
            if row["winner"] == candidate:
                wins += 1
            elif row["winner"] in {"first", "second"}:
                losses += 1
            else:
                draws += 1
        summary.append(
            {
                "profile": profile,
                "match_count": len(selected),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": wins / len(selected) if selected else 0.0,
                "internal_timeout_count": sum(
                    int(row["first_timeout_count"])
                    + int(row["second_timeout_count"])
                    for row in selected
                ),
                "match_timeout_count": sum(
                    row["loss_reason"] == "match_timeout"
                    for row in selected
                ),
                "invalid_move_count": sum(
                    int(row["invalid_move_count"]) for row in selected
                ),
            }
        )
    _write_csv_lf(output / "short_match_summary.csv", summary)
    _write_json(output / "short_match_summary.json", summary)
    return summary


def _write_csv_lf(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_report(output: Path) -> Path:
    benchmark_summary = _load_json(output / "benchmark_summary.json")
    match_summary = (
        _load_json(output / "short_match_summary.json")
        if (output / "short_match_summary.json").is_file()
        else []
    )
    round_robin_summary = (
        _load_json(output / "round_robin_summary.json")
        if (output / "round_robin_summary.json").is_file()
        else []
    )
    prepare_summary = _load_json(output / "prepare_summary.json")
    lines = [
        "# Minimal D10000 adaptive-hybrid experiment",
        "",
        "## Data",
        "",
        f"- Saved positions: {prepare_summary['saved_position_count']}",
        f"- Exact-complete positions: {prepare_summary['exact_truth_count']}",
        f"- Mixed win/loss exact positions: {prepare_summary['mixed_exact_truth_count']}",
        f"- Stable deep-reference positions: {benchmark_summary['stable_reference_position_count']}",
        "",
        "## Fixed-position screening",
        "",
        "| profile | match rate | time (s) | nodes | depth | timeout | exact nontrivial | changes | improve | regress | accepted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    accepted = benchmark_summary["accepted_profiles"]
    for row in benchmark_summary["metrics"]:
        lines.append(
            "| {profile} | {rate:.1%} | {time:.4f} | {nodes:.0f} | "
            "{depth:.2f} | {timeout:.1%} | {proof} | {changes} | "
            "{improve} | {regress} | {accepted} |".format(
                profile=row["profile"],
                rate=row["reference_match_rate"],
                time=row["mean_elapsed_time_sec"],
                nodes=row["mean_nodes_searched"],
                depth=row["mean_effective_depth"],
                timeout=row["timeout_rate"],
                proof=row["exact_nontrivial_success_count"],
                changes=row["choice_change_count"],
                improve=row["improvement_count"],
                regress=row["regression_count"],
                accepted=(
                    "yes"
                    if accepted.get(row["profile"], False)
                    else "no"
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Selection",
            "",
            f"- Accepted profiles: {benchmark_summary['selected_profiles'] or 'none'}",
            "- Dynamic Beam acceptance: accuracy not degraded and time or nodes reduced by at least 10%.",
            "- Selective proof acceptance: nontrivial proofs, at least two choice changes, improvements exceed regressions, and time stays within 125% of baseline.",
            "",
            "## Short matches",
            "",
        ]
    )
    if not match_summary:
        lines.append("- No method passed screening, so matches were skipped.")
    else:
        for row in match_summary:
            lines.append(
                f"- {row['profile']}: {row['wins']}-{row['losses']}-"
                f"{row['draws']} ({row['win_rate']:.1%}), "
                f"internal timeouts {row['internal_timeout_count']}, "
                f"match timeouts {row['match_timeout_count']}, "
                f"invalid moves {row['invalid_move_count']}"
            )
    if round_robin_summary:
        lines.extend(
            [
                "",
                "## Explicit five-agent round robin",
                "",
            ]
        )
        for row in round_robin_summary:
            lines.append(
                f"- {row['agent']}: {row['wins']}-{row['losses']}-"
                f"{row['draws']} ({row['win_rate']:.1%}), "
                f"n={row['match_count']}, first "
                f"{row['first_match_count']}, second "
                f"{row['second_match_count']}"
            )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            ".venv/bin/python -u src/run_minimal_adaptive_hybrid_experiment.py \\",
            "  --stage all --truth-time-sec 0.3 --confirm-d10000 \\",
            "  --output results/minimal_adaptive_hybrid/D10000_rerun",
            "```",
            "",
            "The combined DynamicSelectiveProof agent was intentionally not "
            "implemented unless both mechanisms passed the independent screen.",
        ]
    )
    path = output / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    try:
        args = parse_args()
        if args.stage in {"prepare", "all"}:
            prepare(args)
        if args.stage in {"benchmark", "all"}:
            benchmark(args)
        if args.stage in {"matches", "all"}:
            run_matches(args)
        if args.stage in {"analyze", "all"}:
            if (args.output / "benchmark_runs.jsonl").is_file():
                analyze_benchmark(args.output)
            if (args.output / "short_matches.jsonl").is_file():
                analyze_matches(args.output)
            if (args.output / "round_robin_matches.jsonl").is_file():
                analyze_round_robin_matches(args.output)
            print(write_report(args.output))
    except (FileNotFoundError, ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
