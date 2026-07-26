"""Run resumable edge-native agent comparisons."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from agents import BaseAgent, EdgeMoveDecision, GraphControlAgent, build_agent
from match import MatchResult, simulate_runtime_match
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "results/agent_comparison"
AGENTS = (
    "random",
    "greedy",
    "monte_carlo",
    "minimax",
    "alpha_beta",
    "pvs",
    "beam_negamax",
    "graph_control",
    "graph_pvs",
    "beam_alpha_beta",
    "beam_pvs",
    "branch_switch_alpha_beta",
    "dynamic_beam_alpha_beta",
    "dynamic_beam_pvs",
    "research_adaptive_beam",
    "endgame_exact_hybrid",
    "proof_extension_beam_alpha_beta",
    "dynamic_proof_extension_beam_alpha_beta",
    "integrated_adaptive_hybrid",
)
DEFAULT_AGENTS = (
    "random",
    "greedy",
    "monte_carlo",
    "minimax",
    "alpha_beta",
    "pvs",
    "beam_negamax",
    "graph_control",
)
ADAPTIVE_COMPARISON_AGENTS = (
    "alpha_beta",
    "pvs",
    "beam_negamax",
    "graph_pvs",
    "beam_alpha_beta",
    "beam_pvs",
)
STOCHASTIC_AGENTS = frozenset({"random", "monte_carlo"})
FULL_SIZES = (1000, 3000, 5000, 10000, 20000)
FULL_SEEDS = (0, 1, 2)


def stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((PROJECT_ROOT / "src").glob("*.py")):
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()


def percentile(values: list[float], rate: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * rate) - 1)]


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def _parse_int_csv(value: str, *, allow_zero: bool) -> tuple[int, ...]:
    try:
        values = tuple(
            dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip())
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "values must be comma-separated integers"
        ) from exc
    minimum = 0 if allow_zero else 1
    if not values or any(item < minimum for item in values):
        label = "non-negative" if allow_zero else "positive"
        raise argparse.ArgumentTypeError(f"values must be {label} integers")
    return values


def parse_positive_int_csv(value: str) -> tuple[int, ...]:
    return _parse_int_csv(value, allow_zero=False)


def parse_nonnegative_int_csv(value: str) -> tuple[int, ...]:
    return _parse_int_csv(value, allow_zero=True)


def parse_agent_csv(value: str) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(item.strip() for item in value.split(",") if item.strip())
    )
    unknown = sorted(set(values) - set(AGENTS))
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown agents: {','.join(unknown)}; choices={','.join(AGENTS)}"
        )
    if len(values) < 2:
        raise argparse.ArgumentTypeError("--agents requires at least two agents")
    return values


def runtime_path(runtime_dir: Path, size: int, seed: int) -> Path:
    return runtime_dir / f"D{size}_L2-12_seed{seed}.runtime.json"


def experiment_config(
    quick: bool,
    time_limit_sec: float,
    *,
    sizes: tuple[int, ...] | None = None,
    seeds: tuple[int, ...] | None = None,
    agents: tuple[str, ...] | None = None,
    stochastic_repetitions: int | None = None,
    adaptive_depth: bool = False,
) -> dict[str, Any]:
    selected_sizes = sizes or ((1000,) if quick else FULL_SIZES)
    selected_seeds = seeds or ((0,) if quick else FULL_SEEDS)
    selected_agents = agents or (
        ADAPTIVE_COMPARISON_AGENTS if adaptive_depth else DEFAULT_AGENTS
    )
    if sizes is not None and len(selected_sizes) == 1:
        output_scope = f"D{selected_sizes[0]}"
    elif sizes is not None or seeds is not None or agents is not None:
        output_scope = "custom"
    else:
        output_scope = "quick" if quick else "full"
    if adaptive_depth:
        output_scope += "_adaptive"
    fixed_settings = {
        "minimax": {"depth": 3, "branch_limit": 8, "adaptive_depth": False},
        "alpha_beta": {"depth": 5, "branch_limit": 8, "adaptive_depth": False},
        "pvs": {"depth": 5, "branch_limit": 8, "adaptive_depth": False},
        "beam_negamax": {
            "depth": 5,
            "beam_widths": [8, 6, 4, 2],
            "adaptive_depth": False,
        },
        "monte_carlo": {
            "candidate_limit": 20,
            "playouts_per_move": 10,
            "max_playout_moves": 200,
        },
        "graph_control": {
            "search": "none",
            "simulation": "none",
            "tie_break": "score,start_id,end_id",
        },
        "graph_pvs": {
            "depth": 5,
            "branch_limit": 8,
            "ordering": "lightweight_graph_control",
            "adaptive_depth": False,
        },
        "beam_alpha_beta": {
            "depth": 5,
            "beam_widths": [8, 6, 4, 2],
            "adaptive_depth": False,
        },
        "beam_pvs": {
            "depth": 5,
            "beam_widths": [8, 6, 4, 2],
            "adaptive_depth": False,
        },
    }
    for adaptive_name in (
        "branch_switch_alpha_beta",
        "dynamic_beam_alpha_beta",
        "dynamic_beam_pvs",
        "research_adaptive_beam",
        "endgame_exact_hybrid",
        "proof_extension_beam_alpha_beta",
        "dynamic_proof_extension_beam_alpha_beta",
        "integrated_adaptive_hybrid",
    ):
        fixed_settings[adaptive_name] = {
            "depth": 8,
            "beam_widths": [12, 8, 4, 2],
            "adaptive_depth": False,
        }
    if adaptive_depth:
        adaptive_common = {
            "adaptive_depth": True,
            "min_depth": 1,
            "depth_decrease_ratio": 0.95,
            "depth_recovery_ratio": 0.6,
            "depth_recovery_turns": 2,
            "depth_step": 1,
            "timeout_decreases_depth": True,
            "target_time_ratio": 0.6,
        }
        fixed_settings.update(
            {
                # Reuse the selected D10000 search-parameter-tuning settings.
                "alpha_beta": {
                    **adaptive_common,
                    "initial_depth": 5,
                    "max_depth": 7,
                    "branch_limit": 8,
                    "selection_source": (
                        "results/search_parameter_tuning/f5a877380b91/"
                        "adaptive/selected.json"
                    ),
                },
                "pvs": {
                    **adaptive_common,
                    "initial_depth": 5,
                    "max_depth": 7,
                    "branch_limit": 8,
                    "selection_source": (
                        "results/search_parameter_tuning/f5a877380b91/"
                        "adaptive/selected.json"
                    ),
                },
                "beam_negamax": {
                    **adaptive_common,
                    "initial_depth": 6,
                    "max_depth": 8,
                    "beam_widths": [8, 6, 4, 2],
                    "selection_source": (
                        "results/search_parameter_tuning/f5a877380b91/"
                        "adaptive/selected.json"
                    ),
                },
                # D5 timed out often in matches, so GraphPVS starts one ply
                # lower and may recover only to the measured D5 setting.
                "graph_pvs": {
                    **adaptive_common,
                    "initial_depth": 4,
                    "max_depth": 5,
                    "branch_limit": 8,
                    "ordering": "lightweight_graph_control",
                    "selection_basis": "D10000 fixed-D5 and match results",
                },
                # Promoted after the D10000 10-seed follow-up: this setting
                # beat the AlphaBeta reference 16-4 while remaining faster.
                "beam_alpha_beta": {
                    **adaptive_common,
                    "initial_depth": 8,
                    "max_depth": 9,
                    "beam_widths": [12, 8, 4, 2],
                    "selection_basis": (
                        "results/beam_hybrid_followup/D10000/"
                        "c86fc7661da6"
                    ),
                },
                "beam_pvs": {
                    **adaptive_common,
                    "initial_depth": 8,
                    "max_depth": 9,
                    "beam_widths": [12, 8, 4, 2],
                    "selection_basis": (
                        "results/beam_hybrid_followup/D10000/"
                        "c86fc7661da6"
                    ),
                },
            }
        )
        for adaptive_name in (
            "branch_switch_alpha_beta",
            "dynamic_beam_alpha_beta",
            "dynamic_beam_pvs",
            "research_adaptive_beam",
            "endgame_exact_hybrid",
            "proof_extension_beam_alpha_beta",
            "dynamic_proof_extension_beam_alpha_beta",
            "integrated_adaptive_hybrid",
        ):
            fixed_settings[adaptive_name] = {
                **adaptive_common,
                "initial_depth": 8,
                "max_depth": 9,
                "beam_widths": [12, 8, 4, 2],
                "selection_basis": "position_adaptive_hybrid_stage2",
            }
    return {
        "format_version": "graph_control_comparison_v1",
        "mode": "quick" if quick else "full",
        "depth_profile": "adaptive" if adaptive_depth else "fixed",
        "output_scope": output_scope,
        "agents": list(selected_agents),
        "dictionary_sizes": list(selected_sizes),
        "dictionary_seeds": list(selected_seeds),
        "stochastic_repetitions": (
            stochastic_repetitions
            if stochastic_repetitions is not None
            else 2
            if quick
            else 5
        ),
        "time_limit_sec": time_limit_sec,
        "max_moves": 100 if quick else 1000,
        "max_match_time_sec": 30.0 if quick else 300.0,
        "settings": fixed_settings,
        "candidate_unit": "directed_edge_type_with_multiplicity",
    }


def build_comparison_agent(
    name: str, config: dict[str, Any], random_seed: int
) -> BaseAgent:
    settings = config["settings"]
    agent_settings = settings.get(name, {})
    fallback_depth = int(agent_settings.get("depth", 3))
    initial_depth = int(agent_settings.get("initial_depth", fallback_depth))
    max_depth = int(agent_settings.get("max_depth", initial_depth))
    target_time_ratio = float(agent_settings.get("target_time_ratio", 1.0))
    beam_widths = tuple(
        agent_settings.get(
            "beam_widths",
            settings["beam_negamax"]["beam_widths"],
        )
    )
    common = {
        "agent_name": name,
        "time_limit_sec": float(config["time_limit_sec"]),
        "random_seed": random_seed,
        "adaptive_depth": bool(agent_settings.get("adaptive_depth", False)),
        "branch_limit": agent_settings.get("branch_limit", 8),
        "minimax_depth": initial_depth,
        "alpha_beta_depth": initial_depth,
        "aggressive_pvs_depth": initial_depth,
        "beam_negamax_depth": initial_depth,
        "beam_widths": beam_widths,
        "hybrid_depth": initial_depth,
        "min_depth": int(agent_settings.get("min_depth", 1)),
        "depth_recovery_turns": int(
            agent_settings.get("depth_recovery_turns", 5)
        ),
        "depth_decrease_ratio": float(
            agent_settings.get("depth_decrease_ratio", 0.9)
        ),
        "depth_recovery_ratio": float(
            agent_settings.get("depth_recovery_ratio", 0.5)
        ),
        "depth_step": int(agent_settings.get("depth_step", 1)),
        "timeout_decreases_depth": bool(
            agent_settings.get("timeout_decreases_depth", True)
        ),
        "adaptive_max_depth_increment": max_depth - initial_depth,
        "target_time_sec": (
            float(config["time_limit_sec"]) * target_time_ratio
            if bool(agent_settings.get("adaptive_depth", False))
            else None
        ),
        "monte_carlo_candidates": int(settings["monte_carlo"]["candidate_limit"]),
        "monte_carlo_playouts": int(settings["monte_carlo"]["playouts_per_move"]),
        "monte_carlo_max_moves": int(settings["monte_carlo"]["max_playout_moves"]),
    }
    return build_agent(**common)


def repetitions(first: str, second: str, config: dict[str, Any]) -> int:
    if first in STOCHASTIC_AGENTS or second in STOCHASTIC_AGENTS:
        return int(config["stochastic_repetitions"])
    return 1


def expected_jobs(config: dict[str, Any]) -> list[tuple[int, int, str, str, int]]:
    jobs = []
    for size in config["dictionary_sizes"]:
        for dictionary_seed in config["dictionary_seeds"]:
            for first, second in itertools.permutations(config["agents"], 2):
                if (
                    config["mode"] == "quick"
                    and "graph_control" in config["agents"]
                    and "graph_control" not in {first, second}
                ):
                    continue
                for repetition in range(repetitions(first, second, config)):
                    jobs.append((size, dictionary_seed, first, second, repetition))
    return jobs


def _turn_times(result: MatchResult, side: str) -> list[float]:
    return [
        float(turn["elapsed_time_sec"])
        for turn in result.history
        if turn["player"] == side
    ]


def _turn_stat_sum(result: MatchResult, side: str, field: str) -> float:
    values = []
    for turn in result.history:
        if turn["player"] != side:
            continue
        value = turn.get(field, "")
        if value not in ("", None):
            values.append(float(value))
    return sum(values)


def result_record(
    result: MatchResult,
    *,
    match_id: str,
    runtime_path_value: Path,
    dictionary_seed: int,
    match_seed: int,
    repetition: int,
    commit_id: str,
    source_hash: str,
    config_hash: str,
    dictionary_file_hash: str,
    dictionary_hash: str,
) -> dict[str, Any]:
    row = result.to_csv_row()
    row["history"] = result.history
    row.update(
        {
            "match_id": match_id,
            "runtime": str(runtime_path_value),
            "dictionary_seed": dictionary_seed,
            "match_seed": match_seed,
            "repetition": repetition,
            "commit_id": commit_id,
            "source_fingerprint": source_hash,
            "experiment_config_hash": config_hash,
            "dictionary_file_sha256": dictionary_file_hash,
            "dictionary_hash": dictionary_hash,
            "invalid_move_count": int(result.loss_reason == "invalid_ai_move"),
        }
    )
    for side in ("first", "second"):
        values = _turn_times(result, side)
        row[f"{side}_median_time_sec"] = statistics.median(values) if values else 0.0
        row[f"{side}_p95_time_sec"] = percentile(values, 0.95)
        row[f"{side}_nodes_searched"] = _turn_stat_sum(
            result, side, "nodes_searched"
        )
        row[f"{side}_candidate_evaluations"] = _turn_stat_sum(
            result, side, "ordering_evaluations"
        )
        row[f"{side}_leaf_evaluations"] = _turn_stat_sum(
            result, side, "leaf_evaluations"
        )
        for field in (
            "cutoff_count",
            "beam_pruned_move_count",
            "null_window_search_count",
            "research_count",
            "graph_ordering_evaluations",
            "graph_ordering_calls",
            "graph_ordering_changed_first_count",
            "graph_ordering_time_sec",
        ):
            row[f"{side}_{field}"] = _turn_stat_sum(result, side, field)
        side_turns = [
            turn for turn in result.history if turn["player"] == side
        ]
        depths = [
            float(turn["effective_depth"])
            for turn in side_turns
            if turn.get("effective_depth") not in ("", None)
        ]
        row[f"{side}_mean_effective_depth"] = (
            statistics.fmean(depths) if depths else 0.0
        )
        row[f"{side}_depth_change_count"] = sum(
            bool(turn.get("depth_changed")) for turn in side_turns
        )
    return row


def graph_turn_observer(
    destination: list[dict[str, Any]],
    *,
    match_id: str,
    dict_size: int,
    dictionary_seed: int,
    match_seed: int,
    initial_words: int,
):
    def observe(
        turn_index: int,
        player_index: int,
        agent: BaseAgent,
        decision: EdgeMoveDecision,
        state: AIEdgeState,
    ) -> None:
        if not isinstance(agent, GraphControlAgent):
            return
        edge_dictionary = state.edge_dictionary
        remaining = sum(state.remaining_word_counts)
        candidates = deepcopy(agent.last_candidate_details)
        for candidate in candidates:
            start_id = int(candidate["start_id"])
            end_id = int(candidate["end_id"])
            candidate.update(
                {
                    "candidate_unit": "edge_type",
                    "candidate_edge": (
                        f"{edge_dictionary.id_to_char[start_id]}→"
                        f"{edge_dictionary.id_to_char[end_id]}"
                    ),
                    "start_char": edge_dictionary.id_to_char[start_id],
                    "end_char": edge_dictionary.id_to_char[end_id],
                    "selected": (
                        start_id == decision.start_id and end_id == decision.end_id
                    ),
                }
            )
        destination.append(
            {
                "match_id": match_id,
                "dict_size": dict_size,
                "dictionary_seed": dictionary_seed,
                "match_seed": match_seed,
                "turn": turn_index + 1,
                "seat": "first" if player_index == 0 else "second",
                "remaining_word_count": remaining,
                "remaining_word_rate": remaining / initial_words,
                "legal_candidate_count": len(state.available_edges()),
                "candidate_unit": "edge_type_with_multiplicity",
                "word_display_note": (
                    "AI対AI状態は単語IDを保持しないため、候補は辺種別と"
                    "残存多重度で記録する"
                ),
                "summary": deepcopy(agent.last_evaluation_summary),
                "candidates": candidates,
            }
        )

    return observe


def run(args: argparse.Namespace) -> Path:
    config = experiment_config(
        bool(args.quick),
        float(args.time_limit_sec),
        sizes=args.sizes,
        seeds=args.seeds,
        agents=args.agents,
        stochastic_repetitions=args.stochastic_repetitions,
        adaptive_depth=args.adaptive_depth,
    )
    config_hash = stable_hash(config)
    commit_id = git_commit()
    source_hash = source_fingerprint()
    run_hash = stable_hash(
        {
            "commit_id": commit_id,
            "source_fingerprint": source_hash,
            "experiment_config_hash": config_hash,
        }
    )
    output = args.output_root / config["output_scope"] / run_hash[:12]
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "commit_id": commit_id,
        "source_fingerprint": source_hash,
        "experiment_config_hash": config_hash,
        "run_hash": run_hash,
        "config": config,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    raw_path = output / "raw_matches.jsonl"
    graph_path = output / "graph_control_candidate_details.jsonl"
    rows = read_jsonl(raw_path)
    duplicate_existing = len(rows) - len({row["match_id"] for row in rows})
    if duplicate_existing:
        raise ValueError(f"raw result contains {duplicate_existing} duplicate match IDs")
    completed = {
        row["match_id"]
        for row in rows
        if row.get("commit_id") == commit_id
        and row.get("source_fingerprint") == source_hash
        and row.get("experiment_config_hash") == config_hash
    }

    jobs = expected_jobs(config)
    for job_index, (size, dictionary_seed, first, second, repetition) in enumerate(
        jobs, 1
    ):
        match_id = (
            f"D{size}_seed{dictionary_seed}_{first}_vs_{second}_rep{repetition}"
        )
        if match_id in completed:
            continue
        path = runtime_path(args.runtime_dir, size, dictionary_seed)
        if not path.is_file():
            raise FileNotFoundError(
                f"runtime dictionary not found: {path}\n"
                "先に experiment_dictionary.py で同じsize/seedを生成してください。"
            )
        runtime = RuntimeDictionary.load(path)
        dictionary_file_hash = file_sha256(path)
        match_seed = dictionary_seed * 1_000_000 + repetition * 10_000 + job_index
        first_agent = build_comparison_agent(first, config, match_seed * 2 + 1)
        second_agent = build_comparison_agent(second, config, match_seed * 2 + 2)
        graph_details: list[dict[str, Any]] = []
        observer = graph_turn_observer(
            graph_details,
            match_id=match_id,
            dict_size=size,
            dictionary_seed=dictionary_seed,
            match_seed=match_seed,
            initial_words=runtime.word_count,
        )
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            first_agent,
            second_agent,
            max_moves=int(config["max_moves"]),
            max_match_time_sec=float(config["max_match_time_sec"]),
            match_id=match_id,
            turn_observer=observer,
        )
        record = result_record(
            result,
            match_id=match_id,
            runtime_path_value=path,
            dictionary_seed=dictionary_seed,
            match_seed=match_seed,
            repetition=repetition,
            commit_id=commit_id,
            source_hash=source_hash,
            config_hash=config_hash,
            dictionary_file_hash=dictionary_file_hash,
            dictionary_hash=runtime.dictionary_hash,
        )
        append_jsonl(raw_path, record)
        graph_won = (
            result.winner == "first" and first == "graph_control"
        ) or (result.winner == "second" and second == "graph_control")
        for detail in graph_details:
            detail.update(
                {
                    "winner": result.winner,
                    "graph_control_won": graph_won,
                    "loss_reason": result.loss_reason,
                    "experiment_config_hash": config_hash,
                    "dictionary_hash": runtime.dictionary_hash,
                }
            )
            append_jsonl(graph_path, detail)
        rows.append(record)
        completed.add(match_id)
        print(
            f"[{len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )

    rows = read_jsonl(raw_path)
    flat_rows = [{k: v for k, v in row.items() if k != "history"} for row in rows]
    write_csv(output / "raw_matches.csv", flat_rows)
    completion = {
        "expected_match_count": len(jobs),
        "completed_match_count": len(rows),
        "unique_match_count": len({row["match_id"] for row in rows}),
        "duplicate_match_count": len(rows)
        - len({row["match_id"] for row in rows}),
        "complete": len(rows) == len(jobs),
    }
    (output / "completion.json").write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=PROJECT_ROOT / "data/dictionaries",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--sizes",
        type=parse_positive_int_csv,
        help="dictionary sizes, for example 5000 or 5000,10000",
    )
    parser.add_argument(
        "--seeds",
        type=parse_nonnegative_int_csv,
        help="dictionary seeds, for example 0,1,2",
    )
    parser.add_argument(
        "--agents",
        type=parse_agent_csv,
        help="comma-separated subset; default is all official agents",
    )
    parser.add_argument(
        "--stochastic-repetitions",
        type=int,
        default=None,
        help="default: quick=2, full=5",
    )
    parser.add_argument(
        "--time-limit-sec",
        type=float,
        default=None,
        help="default: quick=0.2, full=1.0 (same final settings as existing analysis)",
    )
    parser.add_argument(
        "--adaptive-depth",
        action="store_true",
        help=(
            "use the selected adaptive D10000 settings; defaults to "
            "AlphaBeta, PVS, BeamNegamax, GraphPVS, BeamAlphaBeta, and BeamPVS "
            "(standalone GraphControl is excluded)"
        ),
    )
    args = parser.parse_args(argv)
    if args.time_limit_sec is None:
        args.time_limit_sec = 0.2 if args.quick else 1.0
    if args.time_limit_sec <= 0:
        parser.error("--time-limit-sec must be positive")
    if (
        args.stochastic_repetitions is not None
        and args.stochastic_repetitions <= 0
    ):
        parser.error("--stochastic-repetitions must be positive")
    return args


def main() -> None:
    try:
        run(parse_args())
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
