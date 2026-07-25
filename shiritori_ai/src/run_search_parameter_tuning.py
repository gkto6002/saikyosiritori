"""Tune fixed-depth search settings, adaptive depth, matches, plots, and report."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import itertools
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agents import AlphaBetaAgent, BeamNegamaxAgent, PVSAgent, _edge_sort_key
from match import simulate_runtime_match
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState
from search_common import edge_position_metrics, evaluate_ordering_score, risk_level_for_metrics
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_LOG = (
    PROJECT_ROOT
    / "results/agent_comparison/D5000/bd3c4f60037c/raw_matches.jsonl"
)
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "data/dictionaries"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/search_parameter_tuning"
FORMAT_VERSION = "search_parameter_tuning_v2"
SEARCH_AGENTS = ("alpha_beta", "pvs", "beam_negamax")
BASELINES = {
    "alpha_beta": {
        "config_id": "alpha_beta_d5_b8",
        "agent": "alpha_beta",
        "depth": 5,
        "branch_limit": 8,
    },
    "pvs": {
        "config_id": "pvs_d5_b8",
        "agent": "pvs",
        "depth": 5,
        "branch_limit": 8,
    },
    "beam_negamax": {
        "config_id": "beam_negamax_d5_w8-6-4-2",
        "agent": "beam_negamax",
        "depth": 5,
        "beam_widths": (8, 6, 4, 2),
    },
}
ADAPTIVE_PROFILES = {
    "fixed": {
        "adaptive_depth": False,
        "max_depth_increment": 0,
        "target_time_ratio": 1.0,
        "depth_decrease_ratio": 0.9,
        "depth_recovery_ratio": 0.5,
        "depth_recovery_turns": 5,
    },
    "conservative": {
        "adaptive_depth": True,
        "max_depth_increment": 1,
        "target_time_ratio": 0.25,
        "depth_decrease_ratio": 0.8,
        "depth_recovery_ratio": 0.4,
        "depth_recovery_turns": 3,
    },
    "standard": {
        "adaptive_depth": True,
        "max_depth_increment": 2,
        "target_time_ratio": 0.4,
        "depth_decrease_ratio": 0.9,
        "depth_recovery_ratio": 0.5,
        "depth_recovery_turns": 3,
    },
    "aggressive": {
        "adaptive_depth": True,
        "max_depth_increment": 2,
        "target_time_ratio": 0.6,
        "depth_decrease_ratio": 0.95,
        "depth_recovery_ratio": 0.6,
        "depth_recovery_turns": 2,
    },
}


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()


def stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for directory in ("src", "benchmarks"):
        for path in sorted((PROJECT_ROOT / directory).glob("*.py")):
            digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: Iterable[float], rate: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(len(ordered) * rate) - 1)]


def clone_state(state: AIEdgeState) -> AIEdgeState:
    return AIEdgeState(
        edge_dictionary=state.edge_dictionary,
        required_char_id=state.required_char_id,
        edge_counts=list(state.edge_counts),
        active_end_masks=list(state.active_end_masks),
    )


def restore_position(position: dict[str, Any]) -> tuple[RuntimeDictionary, AIEdgeState]:
    runtime = RuntimeDictionary.load(Path(position["runtime"]))
    state = AIEdgeState.initial(runtime)
    for start_id, end_id in position["edge_history"]:
        state.apply_edge(int(start_id), int(end_id))
    state.assert_aggregates_consistent()
    return runtime, state


def runtime_paths(
    runtime_dir: Path,
    dictionary_size: int = 5000,
    seeds: Iterable[int] = (0, 1, 2),
) -> list[Path]:
    paths = [
        runtime_dir / f"D{dictionary_size}_L2-12_seed{seed}.runtime.json"
        for seed in seeds
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"missing D{dictionary_size} runtimes: " + ", ".join(missing)
        )
    return paths


def load_selection_source(
    source: Path,
    output: Path,
) -> dict[str, dict[str, Any]]:
    source = source.resolve()
    selected_path = source / "fixed_depth/selected.json"
    adaptive_path = source / "adaptive/selected.json"
    if not selected_path.is_file():
        raise FileNotFoundError(f"selection source not found: {selected_path}")
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    missing_agents = [agent for agent in SEARCH_AGENTS if agent not in selected]
    if missing_agents:
        raise ValueError(
            "selection source is missing agents: " + ", ".join(missing_agents)
        )
    write_json(output / "selection_source/fixed_selected.json", selected)
    if adaptive_path.is_file():
        write_json(
            output / "selection_source/adaptive_selected.json",
            json.loads(adaptive_path.read_text(encoding="utf-8")),
        )
    write_json(
        output / "selection_source/metadata.json",
        {
            "source_run": str(source),
            "fixed_selected_file": str(selected_path),
            "adaptive_selected_file": (
                str(adaptive_path) if adaptive_path.is_file() else None
            ),
        },
    )
    return selected


def reuse_fixed_stage(
    source: Path,
    output: Path,
    config: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    source = source.resolve()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"fixed-stage source manifest not found: {manifest_path}")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_config = source_manifest.get("config", {})
    comparable_keys = (
        "time_limit_sec",
        "positions_per_seed",
        "runtime_paths",
        "reference_log",
        "fixed_configs",
        "depth7_gate",
    )
    mismatched = [
        key
        for key in comparable_keys
        if stable_hash(source_config.get(key)) != stable_hash(config.get(key))
    ]
    if mismatched:
        raise ValueError(
            "fixed-stage source is incompatible for: " + ", ".join(mismatched)
        )

    fixed_rows_path = source / "fixed_depth/runs.json"
    fixed_summary_path = source / "fixed_depth/summary.json"
    exclusions_path = source / "fixed_depth/exclusions.json"
    selected_path = source / "fixed_depth/selected.json"
    required = (
        fixed_rows_path,
        fixed_summary_path,
        exclusions_path,
        selected_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "fixed-stage source is incomplete: " + ", ".join(missing)
        )

    fixed_rows = json.loads(fixed_rows_path.read_text(encoding="utf-8"))
    fixed_summary = json.loads(fixed_summary_path.read_text(encoding="utf-8"))
    exclusions = json.loads(exclusions_path.read_text(encoding="utf-8"))
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    write_jsonl(output / "fixed_depth/runs.jsonl", fixed_rows)
    write_json(output / "fixed_depth/runs.json", fixed_rows)
    write_csv(output / "fixed_depth/runs.csv", fixed_rows)
    write_json(output / "fixed_depth/summary.json", fixed_summary)
    write_csv(output / "fixed_depth/summary.csv", fixed_summary)
    write_json(output / "fixed_depth/exclusions.json", exclusions)
    write_json(output / "fixed_depth/selected.json", selected)

    validation_rows_path = source / "validation/runs.jsonl"
    if validation_rows_path.is_file():
        validation_rows = read_jsonl(validation_rows_path)
        write_jsonl(output / "validation/runs.jsonl", validation_rows)
        write_csv(output / "validation/runs.csv", validation_rows)
    validation_summary_path = source / "validation/summary.json"
    if validation_summary_path.is_file():
        write_json(
            output / "validation/summary.json",
            json.loads(validation_summary_path.read_text(encoding="utf-8")),
        )
    return fixed_rows, fixed_summary, exclusions, selected


def _reference_match(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if int(row["dictionary_seed"]) == seed
        and row["first_agent"] in SEARCH_AGENTS
        and row["second_agent"] in SEARCH_AGENTS
    ]
    if not candidates:
        raise ValueError(f"no deterministic search-agent reference match for seed {seed}")
    return max(candidates, key=lambda row: (int(row["turn_count"]), row["match_id"]))


def collect_positions(
    runtimes: list[Path],
    reference_log: Path,
    positions_per_seed: int,
) -> list[dict[str, Any]]:
    """Select phase, branching, close-score, pruning, and slow snapshots."""

    match_rows = read_jsonl(reference_log)
    output: list[dict[str, Any]] = []
    for seed, runtime_path in enumerate(runtimes):
        runtime = RuntimeDictionary.load(runtime_path)
        reference = _reference_match(match_rows, seed)
        state = AIEdgeState.initial(runtime)
        snapshots: list[dict[str, Any]] = []
        history = reference["history"]
        for turn_index, turn in enumerate(history):
            edges = state.available_edges()
            if not edges:
                break
            scores = sorted(
                (
                    evaluate_ordering_score(state, edge[0], edge[1]).total_score
                    for edge in edges
                ),
                reverse=True,
            )
            margin = scores[0] - scores[1] if len(scores) > 1 else math.inf
            metrics = edge_position_metrics(state)
            snapshots.append(
                {
                    "turn": turn_index,
                    "remaining_word_count": state.legal_word_count(),
                    "legal_edge_count": len(edges),
                    "risk_level": risk_level_for_metrics(metrics).value,
                    "ordering_score_margin": margin,
                    "recorded_elapsed_time_sec": float(
                        turn.get("elapsed_time_sec", 0.0) or 0.0
                    ),
                    "recorded_cutoff_count": int(
                        turn.get("cutoff_count", 0) or 0
                    ),
                    "edge_history": [
                        [int(item["start_id"]), int(item["end_id"])]
                        for item in history[:turn_index]
                    ],
                }
            )
            state.apply_edge(int(turn["start_id"]), int(turn["end_id"]))

        if not snapshots:
            raise ValueError(f"reference match has no usable positions: {reference['match_id']}")
        choices = [
            ("early", snapshots[0]),
            ("middle", snapshots[len(snapshots) // 2]),
            ("late", snapshots[max(0, len(snapshots) - 5)]),
            ("many_legal", max(snapshots, key=lambda row: row["legal_edge_count"])),
            (
                "few_legal",
                min(
                    (row for row in snapshots if row["legal_edge_count"] > 1),
                    key=lambda row: row["legal_edge_count"],
                    default=snapshots[-1],
                ),
            ),
            (
                "close_evaluation",
                min(snapshots, key=lambda row: row["ordering_score_margin"]),
            ),
            (
                "early_pruning",
                max(snapshots, key=lambda row: row["recorded_cutoff_count"]),
            ),
            (
                "slow_recorded",
                max(snapshots, key=lambda row: row["recorded_elapsed_time_sec"]),
            ),
        ]
        selected_by_turn: dict[int, tuple[dict[str, Any], list[str]]] = {}
        for category, snapshot in choices:
            turn = int(snapshot["turn"])
            if turn in selected_by_turn:
                selected_by_turn[turn][1].append(category)
            else:
                selected_by_turn[turn] = (snapshot, [category])
        for selection_index, (turn, (snapshot, categories)) in enumerate(
            selected_by_turn.items()
        ):
            output.append(
                {
                    **snapshot,
                    "position_id": f"seed{seed}_{categories[0]}_t{turn}",
                    "seed": seed,
                    "split": "tuning" if seed in (0, 1) else "validation",
                    "category": categories[0],
                    "categories": categories,
                    "runtime": str(runtime_path.resolve()),
                    "source_match_id": reference["match_id"],
                }
            )
            if selection_index + 1 >= positions_per_seed:
                break
    return output


def fixed_configs() -> list[dict[str, Any]]:
    configs = [
        {
            "config_id": f"{agent}_d{depth}_b{branch}",
            "agent": agent,
            "depth": depth,
            "branch_limit": branch,
        }
        for agent in ("alpha_beta", "pvs")
        for depth in (5, 6, 7)
        for branch in (8, 12, 16)
    ]
    widths = ((8, 6, 4, 2), (12, 8, 4, 2), (12, 8, 6, 4), (16, 12, 8, 4))
    configs.extend(
        {
            "config_id": f"beam_negamax_d{depth}_w{'-'.join(map(str, width))}",
            "agent": "beam_negamax",
            "depth": depth,
            "beam_widths": width,
        }
        for depth in (5, 6, 7)
        for width in widths
    )
    return configs


def build_agent(
    config: dict[str, Any],
    time_limit_sec: float,
    profile: dict[str, Any] | None = None,
):
    adaptive = profile or ADAPTIVE_PROFILES["fixed"]
    common = {
        "time_limit_sec": time_limit_sec,
        "depth": int(config["depth"]),
        "max_depth": int(config["depth"])
        + int(adaptive.get("max_depth_increment", 0)),
        "target_time_sec": time_limit_sec
        * float(adaptive.get("target_time_ratio", 1.0)),
        "adaptive_depth": bool(adaptive["adaptive_depth"]),
        "min_depth": max(1, int(config["depth"]) - 2),
        "depth_recovery_turns": int(adaptive["depth_recovery_turns"]),
        "depth_decrease_ratio": float(adaptive["depth_decrease_ratio"]),
        "depth_recovery_ratio": float(adaptive["depth_recovery_ratio"]),
        "depth_step": 1,
        "timeout_decreases_depth": True,
    }
    if config["agent"] == "alpha_beta":
        return AlphaBetaAgent(
            **common, branch_limit=int(config["branch_limit"])
        )
    if config["agent"] == "pvs":
        return PVSAgent(**common, branch_limit=int(config["branch_limit"]))
    return BeamNegamaxAgent(
        **common, beam_widths=tuple(config["beam_widths"])
    )


def decision_row(
    config: dict[str, Any],
    position: dict[str, Any],
    decision,
    *,
    profile_name: str,
    sequence_index: int | None = None,
) -> dict[str, Any]:
    extra = decision.extra
    root_count = int(extra.get("root_candidate_count", 0) or 0)
    selected_root_count = int(
        extra.get("selected_root_candidate_count", root_count) or 0
    )
    completed = int(extra.get("searched_root_candidate_count", 0) or 0)
    total = float(decision.elapsed_time_sec)
    ordering = float(extra.get("ordering_time_sec", 0.0) or 0.0)
    root_ordering = float(extra.get("root_ordering_time_sec", 0.0) or 0.0)
    recursive_ordering = max(0.0, ordering - root_ordering)
    search = float(extra.get("search_time_sec", 0.0) or 0.0)
    leaf_evaluation = float(extra.get("evaluation_time_sec", 0.0) or 0.0)
    recursive_other = max(0.0, search - recursive_ordering - leaf_evaluation)
    legal = float(extra.get("legal_move_generation_time_sec", 0.0) or 0.0)
    other = max(0.0, total - legal - root_ordering - search)
    return {
        "config_id": config["config_id"],
        "agent": config["agent"],
        "depth": config["depth"],
        "initial_depth": int(extra.get("initial_depth", config["depth"]) or config["depth"]),
        "max_depth": int(extra.get("max_depth", config["depth"]) or config["depth"]),
        "target_time_sec": float(extra.get("target_time_sec", 0.0) or 0.0),
        "branch_limit": config.get("branch_limit", ""),
        "beam_widths": "-".join(map(str, config.get("beam_widths", ()))),
        "profile": profile_name,
        "position_id": position["position_id"],
        "seed": position["seed"],
        "split": position["split"],
        "category": position["category"],
        "turn": position["turn"],
        "sequence_index": "" if sequence_index is None else sequence_index,
        "remaining_word_count": position["remaining_word_count"],
        "legal_edge_count": position["legal_edge_count"],
        "risk_level": position["risk_level"],
        "selected_edge": f"{decision.start_id}→{decision.end_id}",
        "start_id": decision.start_id,
        "end_id": decision.end_id,
        "score": decision.score,
        "elapsed_time_sec": total,
        "elapsed_ratio": float(extra.get("elapsed_ratio", 0.0) or 0.0),
        "target_elapsed_ratio": float(
            extra.get("target_elapsed_ratio", 0.0) or 0.0
        ),
        "timed_out": decision.timed_out,
        "nodes_searched": int(extra.get("nodes_searched", 0) or 0),
        "leaf_evaluations": int(extra.get("leaf_evaluations", 0) or 0),
        "ordering_evaluations": int(extra.get("ordering_evaluations", 0) or 0),
        "root_candidate_count": root_count,
        "selected_root_candidate_count": selected_root_count,
        "completed_root_moves": completed,
        "root_completion_rate": (
            completed / selected_root_count if selected_root_count else 1.0
        ),
        "effective_depth": int(extra.get("effective_depth", config["depth"]) or config["depth"]),
        "depth_before": int(extra.get("depth_before", config["depth"]) or config["depth"]),
        "depth_after": int(extra.get("depth_after", config["depth"]) or config["depth"]),
        "depth_changed": bool(extra.get("depth_changed", False)),
        "depth_change_reason": extra.get("depth_change_reason", ""),
        "recovery_streak": int(extra.get("recovery_streak", 0) or 0),
        "cutoff_count": int(extra.get("cutoff_count", 0) or 0),
        "pruned_move_count": int(extra.get("pruned_move_count", 0) or 0),
        "beam_pruned_move_count": int(extra.get("beam_pruned_move_count", 0) or 0),
        "null_window_searches": int(extra.get("null_window_searches", 0) or 0),
        "research_count": int(extra.get("research_count", 0) or 0),
        "research_rate": float(extra.get("research_rate", 0.0) or 0.0),
        "beam_widths_used": json.dumps(extra.get("beam_widths_used", {}), sort_keys=True),
        "legal_move_generation_time_sec": legal,
        "candidate_evaluation_time_sec": float(
            extra.get("candidate_evaluation_time_sec", 0.0) or 0.0
        ),
        "candidate_sort_time_sec": float(
            extra.get("candidate_sort_time_sec", 0.0) or 0.0
        ),
        "root_ordering_time_sec": root_ordering,
        "recursive_ordering_time_sec": recursive_ordering,
        "leaf_evaluation_time_sec": leaf_evaluation,
        "recursive_other_time_sec": recursive_other,
        "other_time_sec": other,
    }


def summarize_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["config_id"]), str(row["profile"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (config_id, profile), values in sorted(groups.items()):
        elapsed = [float(row["elapsed_time_sec"]) for row in values]
        node_values = [int(row["nodes_searched"]) for row in values]
        summary = {
            "config_id": config_id,
            "agent": values[0]["agent"],
            "depth": values[0]["depth"],
            "initial_depth": values[0]["initial_depth"],
            "max_depth": values[0]["max_depth"],
            "target_time_sec": values[0]["target_time_sec"],
            "branch_limit": values[0]["branch_limit"],
            "beam_widths": values[0]["beam_widths"],
            "profile": profile,
            "run_count": len(values),
            "mean_time_sec": statistics.fmean(elapsed),
            "median_time_sec": statistics.median(elapsed),
            "p90_time_sec": percentile(elapsed, 0.90),
            "p95_time_sec": percentile(elapsed, 0.95),
            "p99_time_sec": percentile(elapsed, 0.99),
            "max_time_sec": max(elapsed),
            "timeout_count": sum(bool(row["timed_out"]) for row in values),
            "timeout_rate": statistics.fmean(bool(row["timed_out"]) for row in values),
            "mean_nodes": statistics.fmean(node_values),
            "median_nodes": statistics.median(node_values),
            "max_nodes": max(node_values),
            "mean_effective_depth": statistics.fmean(
                int(row["effective_depth"]) for row in values
            ),
            "mean_root_candidate_count": statistics.fmean(
                int(row["root_candidate_count"]) for row in values
            ),
            "mean_completed_root_moves": statistics.fmean(
                int(row["completed_root_moves"]) for row in values
            ),
            "mean_root_completion_rate": statistics.fmean(
                float(row["root_completion_rate"]) for row in values
            ),
            "depth_change_count": sum(bool(row["depth_changed"]) for row in values),
            "mean_research_rate": statistics.fmean(
                float(row["research_rate"]) for row in values
            ),
        }
        summaries.append(summary)
    return summaries


def depth_six_is_safe(summary: dict[str, Any], time_limit_sec: float) -> bool:
    return (
        float(summary["timeout_rate"]) <= 0.2
        and float(summary["p95_time_sec"]) <= time_limit_sec * 0.9
        and float(summary["mean_root_completion_rate"]) >= 0.5
    )


def matching_depth_six(config: dict[str, Any]) -> str:
    if config["agent"] == "beam_negamax":
        widths = "-".join(map(str, config["beam_widths"]))
        return f"beam_negamax_d6_w{widths}"
    return f"{config['agent']}_d6_b{config['branch_limit']}"


def run_fixed_benchmark(
    positions: list[dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    path = output / "fixed_depth/runs.jsonl"
    rows = read_jsonl(path)
    completed = {(row["config_id"], row["position_id"]) for row in rows}
    tuning_positions = [row for row in positions if row["split"] == "tuning"]
    configs = fixed_configs()
    phase_one = [config for config in configs if int(config["depth"]) in (5, 6)]
    for config in phase_one:
        for position in tuning_positions:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_agent(config, time_limit_sec).choose_edge(state)
            row = decision_row(config, position, decision, profile_name="fixed")
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
    phase_one_summary = summarize_runs(rows)
    summary_map = {row["config_id"]: row for row in phase_one_summary}
    exclusions: list[dict[str, Any]] = []
    for config in (row for row in configs if int(row["depth"]) == 7):
        parent = summary_map[matching_depth_six(config)]
        if not depth_six_is_safe(parent, time_limit_sec):
            exclusions.append(
                {
                    "config_id": config["config_id"],
                    "status": "excluded",
                    "reason": (
                        "corresponding depth-6 setting failed safety gate: "
                        f"timeout={parent['timeout_rate']:.3f}, "
                        f"p95={parent['p95_time_sec']:.3f}, "
                        f"root_completion={parent['mean_root_completion_rate']:.3f}"
                    ),
                    "parent_config_id": parent["config_id"],
                }
            )
            continue
        for position in tuning_positions:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_agent(config, time_limit_sec).choose_edge(state)
            row = decision_row(config, position, decision, profile_name="fixed")
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
    summaries = summarize_runs(rows)
    config_map = {config["config_id"]: config for config in configs}
    row_map = {(row["config_id"], row["position_id"]): row for row in rows}
    for row in rows:
        baseline = row_map.get(
            (BASELINES[str(row["agent"])]["config_id"], row["position_id"])
        )
        row["baseline_move_agreement"] = (
            baseline is not None and row["selected_edge"] == baseline["selected_edge"]
        )
        if row["agent"] == "pvs":
            alpha_id = f"alpha_beta_d{row['depth']}_b{row['branch_limit']}"
        elif row["agent"] == "beam_negamax":
            alpha_id = f"alpha_beta_d{row['depth']}_b16"
        else:
            alpha_id = row["config_id"]
        alpha = row_map.get((alpha_id, row["position_id"]))
        row["alpha_beta_reference_config"] = alpha_id
        row["alpha_beta_move_agreement"] = (
            alpha is not None and row["selected_edge"] == alpha["selected_edge"]
        )
        row["alpha_beta_score_agreement"] = (
            alpha is not None
            and math.isclose(
                float(row["score"]), float(alpha["score"]), rel_tol=0.0, abs_tol=1e-9
            )
        )
        if row["agent"] == "beam_negamax" and alpha is not None:
            _runtime, state = restore_position(
                next(item for item in positions if item["position_id"] == row["position_id"])
            )
            evaluations = {
                edge: evaluate_ordering_score(state, *edge)
                for edge in state.available_edges()
            }
            ordered = sorted(
                evaluations,
                key=lambda edge: _edge_sort_key(edge, evaluations[edge], False),
            )
            reference = (int(alpha["start_id"]), int(alpha["end_id"]))
            rank = ordered.index(reference) + 1 if reference in ordered else len(ordered) + 1
            row["alpha_beta_reference_rank"] = rank
            row["alpha_beta_reference_retained_at_root"] = (
                rank <= int(tuple(config_map[row["config_id"]]["beam_widths"])[0])
            )
    summaries = summarize_runs(rows)
    for summary in summaries:
        values = [row for row in rows if row["config_id"] == summary["config_id"]]
        summary["baseline_move_agreement_rate"] = statistics.fmean(
            bool(row["baseline_move_agreement"]) for row in values
        )
        agreements = [
            row for row in values if row.get("alpha_beta_reference_config")
        ]
        summary["alpha_beta_move_agreement_rate"] = statistics.fmean(
            bool(row["alpha_beta_move_agreement"]) for row in agreements
        )
        summary["alpha_beta_score_agreement_rate"] = statistics.fmean(
            bool(row["alpha_beta_score_agreement"]) for row in agreements
        )
        paired = []
        for row in values:
            reference = row_map.get(
                (str(row["alpha_beta_reference_config"]), row["position_id"])
            )
            if reference is not None:
                paired.append((row, reference))
        summary["alpha_beta_reference_pair_count"] = len(paired)
        summary["faster_than_alpha_beta_rate"] = (
            statistics.fmean(
                float(row["elapsed_time_sec"])
                < float(reference["elapsed_time_sec"])
                for row, reference in paired
            )
            if paired
            else None
        )
        summary["slower_than_alpha_beta_rate"] = (
            statistics.fmean(
                float(row["elapsed_time_sec"])
                > float(reference["elapsed_time_sec"])
                for row, reference in paired
            )
            if paired
            else None
        )
        summary["mean_time_difference_from_alpha_beta_sec"] = (
            statistics.fmean(
                float(row["elapsed_time_sec"])
                - float(reference["elapsed_time_sec"])
                for row, reference in paired
            )
            if paired
            else None
        )
        summary["mean_absolute_score_difference_from_alpha_beta"] = (
            statistics.fmean(
                abs(float(row["score"]) - float(reference["score"]))
                for row, reference in paired
            )
            if paired
            else None
        )
        if summary["agent"] == "beam_negamax":
            summary["alpha_beta_root_retention_rate"] = statistics.fmean(
                bool(row.get("alpha_beta_reference_retained_at_root")) for row in values
            )
    write_csv(output / "fixed_depth/runs.csv", rows)
    write_json(output / "fixed_depth/runs.json", rows)
    write_csv(output / "fixed_depth/summary.csv", summaries)
    write_json(output / "fixed_depth/summary.json", summaries)
    write_json(output / "fixed_depth/exclusions.json", exclusions)
    return rows, summaries, exclusions


def select_fixed_settings(
    summaries: list[dict[str, Any]], time_limit_sec: float
) -> dict[str, dict[str, Any]]:
    configs = {row["config_id"]: row for row in fixed_configs()}
    selected: dict[str, dict[str, Any]] = {}
    for agent in SEARCH_AGENTS:
        candidates = [row for row in summaries if row["agent"] == agent]
        viable = [
            row
            for row in candidates
            if row["timeout_rate"] <= 0.2
            and row["p95_time_sec"] <= time_limit_sec * 0.9
            and row["mean_root_completion_rate"] >= 0.5
            and (
                agent != "beam_negamax"
                or row.get("alpha_beta_root_retention_rate", 0.0) >= 0.75
            )
        ]
        if viable:
            winner = min(
                viable,
                key=lambda row: (
                    -int(row["depth"]),
                    -float(row.get("alpha_beta_move_agreement_rate", 0.0)),
                    float(row["p95_time_sec"]),
                    float(row["mean_time_sec"]),
                ),
            )
        else:
            winner = min(
                candidates,
                key=lambda row: (
                    float(row["timeout_rate"]),
                    float(row["p95_time_sec"]),
                    -float(row["mean_root_completion_rate"]),
                    -float(row.get("alpha_beta_move_agreement_rate", 0.0)),
                    float(row["mean_time_sec"]),
                    -int(row["depth"]),
                ),
            )
        selected[agent] = {
            **configs[winner["config_id"]],
            "selection_metrics": winner,
        }
    return selected


def run_validation(
    positions: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> list[dict[str, Any]]:
    path = output / "validation/runs.jsonl"
    rows = read_jsonl(path)
    completed = {(row["config_id"], row["position_id"]) for row in rows}
    validation = [row for row in positions if row["split"] == "validation"]
    configs = [BASELINES[agent] for agent in SEARCH_AGENTS] + [
        {key: value for key, value in selected[agent].items() if key != "selection_metrics"}
        for agent in SEARCH_AGENTS
    ]
    unique = {config["config_id"]: config for config in configs}
    for config in unique.values():
        for position in validation:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_agent(config, time_limit_sec).choose_edge(state)
            row = decision_row(config, position, decision, profile_name="fixed")
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
    write_csv(output / "validation/runs.csv", rows)
    write_json(output / "validation/summary.json", summarize_runs(rows))
    return rows


def run_selected_fixed_benchmark(
    positions: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Revalidate imported fixed settings on another dictionary size."""

    path = output / "fixed_depth/runs.jsonl"
    rows = read_jsonl(path)
    completed = {(row["config_id"], row["position_id"]) for row in rows}
    tuning = [row for row in positions if row["split"] == "tuning"]
    configs = [
        {
            key: value
            for key, value in selected[agent].items()
            if key != "selection_metrics"
        }
        for agent in SEARCH_AGENTS
    ]
    for config in configs:
        for position in tuning:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_agent(config, time_limit_sec).choose_edge(state)
            row = decision_row(config, position, decision, profile_name="fixed")
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
    summaries = summarize_runs(rows)
    write_csv(output / "fixed_depth/runs.csv", rows)
    write_json(output / "fixed_depth/runs.json", rows)
    write_csv(output / "fixed_depth/summary.csv", summaries)
    write_json(output / "fixed_depth/summary.json", summaries)
    write_json(output / "fixed_depth/selected.json", selected)
    write_json(output / "fixed_depth/exclusions.json", [])
    return rows, summaries


def run_adaptive_benchmark(
    positions: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    fixed_rows: list[dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = output / "adaptive/runs.jsonl"
    rows = read_jsonl(path)
    completed = {
        (row["config_id"], row["profile"], row["seed"], row["position_id"])
        for row in rows
    }
    tuning = [row for row in positions if row["split"] == "tuning"]
    for agent_name, selected_config in selected.items():
        config = {
            key: value
            for key, value in selected_config.items()
            if key != "selection_metrics"
        }
        for profile_name, profile in ADAPTIVE_PROFILES.items():
            adaptive_config = {
                **config,
                "config_id": f"{config['config_id']}__{profile_name}",
            }
            for seed in (0, 1):
                sequence = sorted(
                    (row for row in tuning if int(row["seed"]) == seed),
                    key=lambda row: int(row["turn"]),
                )
                agent = build_agent(adaptive_config, time_limit_sec, profile)
                for index, position in enumerate(sequence):
                    key = (
                        adaptive_config["config_id"],
                        profile_name,
                        seed,
                        position["position_id"],
                    )
                    if key in completed:
                        # Reconstruct controller state deterministically when resuming.
                        _runtime, replay_state = restore_position(position)
                        agent.choose_edge(replay_state)
                        continue
                    _runtime, state = restore_position(position)
                    decision = agent.choose_edge(state)
                    row = decision_row(
                        adaptive_config,
                        position,
                        decision,
                        profile_name=profile_name,
                        sequence_index=index,
                    )
                    append_jsonl(path, row)
                    rows.append(row)
                    completed.add(key)
    fixed_map = {
        (row["config_id"], row["position_id"]): row for row in fixed_rows
    }
    for row in rows:
        base_config_id = selected[str(row["agent"])]["config_id"]
        reference = fixed_map.get((base_config_id, row["position_id"]))
        row["max_depth_fixed_move_agreement"] = (
            reference is not None
            and row["selected_edge"] == reference["selected_edge"]
        )
        row["max_depth_fixed_score_agreement"] = (
            reference is not None
            and math.isclose(
                float(row["score"]),
                float(reference["score"]),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
    summaries = summarize_runs(rows)
    for summary in summaries:
        values = [
            row
            for row in rows
            if row["config_id"] == summary["config_id"]
            and row["profile"] == summary["profile"]
        ]
        summary["max_depth_fixed_move_agreement_rate"] = statistics.fmean(
            bool(row["max_depth_fixed_move_agreement"]) for row in values
        )
        summary["max_depth_fixed_score_agreement_rate"] = statistics.fmean(
            bool(row["max_depth_fixed_score_agreement"]) for row in values
        )
    write_csv(output / "adaptive/runs.csv", rows)
    write_json(output / "adaptive/runs.json", rows)
    write_csv(output / "adaptive/summary.csv", summaries)
    write_json(output / "adaptive/summary.json", summaries)
    return rows, summaries


def select_adaptive_profiles(
    selected: dict[str, dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for agent in SEARCH_AGENTS:
        base_id = selected[agent]["config_id"]
        candidates = [
            row
            for row in summaries
            if row["agent"] == agent and row["profile"] != "fixed"
        ]
        winner = min(
            candidates,
            key=lambda row: (
                float(row["timeout_rate"]),
                -float(row["mean_effective_depth"]),
                float(row["p95_time_sec"]),
            ),
        )
        output[agent] = {
            "profile": winner["profile"],
            "config_id": f"{base_id}__{winner['profile']}",
            "initial_depth": int(winner["initial_depth"]),
            "max_depth": int(winner["max_depth"]),
            "target_time_sec": float(winner["target_time_sec"]),
            "metrics": winner,
            **ADAPTIVE_PROFILES[str(winner["profile"])],
        }
    return output


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def analyze_adaptive_behavior(
    rows: list[dict[str, Any]],
    fixed_rows: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    output: Path,
) -> list[dict[str, Any]]:
    fixed_map = {
        (row["config_id"], row["position_id"]): row for row in fixed_rows
    }
    diagnostics: list[dict[str, Any]] = []
    for agent in SEARCH_AGENTS:
        for profile in ADAPTIVE_PROFILES:
            values = [
                row
                for row in rows
                if row["agent"] == agent and row["profile"] == profile
            ]
            lowered = [
                row
                for row in values
                if int(row["effective_depth"]) < int(row["initial_depth"])
            ]
            raised = [
                row
                for row in values
                if int(row["effective_depth"]) > int(row["initial_depth"])
            ]
            previous_times: list[float] = []
            next_fixed_times: list[float] = []
            oscillations = 0
            for seed in (0, 1):
                sequence = sorted(
                    (row for row in values if int(row["seed"]) == seed),
                    key=lambda row: int(row["turn"]),
                )
                previous_direction = 0
                for previous, current in zip(sequence, sequence[1:]):
                    reference = fixed_map.get(
                        (selected[agent]["config_id"], current["position_id"])
                    )
                    if reference is not None:
                        previous_times.append(float(previous["elapsed_time_sec"]))
                        next_fixed_times.append(float(reference["elapsed_time_sec"]))
                for row in sequence:
                    direction = int(row["depth_after"]) - int(row["depth_before"])
                    if direction and previous_direction and direction != previous_direction:
                        oscillations += 1
                    if direction:
                        previous_direction = direction
            diagnostics.append(
                {
                    "agent": agent,
                    "profile": profile,
                    "position_count": len(values),
                    "lowered_depth_count": len(lowered),
                    "lowered_depth_rate": len(lowered) / len(values) if values else 0.0,
                    "raised_depth_count": len(raised),
                    "raised_depth_rate": len(raised) / len(values) if values else 0.0,
                    "max_effective_depth": (
                        max(int(row["effective_depth"]) for row in values)
                        if values
                        else 0
                    ),
                    "move_change_when_lowered_rate": (
                        statistics.fmean(
                            not bool(row["max_depth_fixed_move_agreement"])
                            for row in lowered
                        )
                        if lowered
                        else 0.0
                    ),
                    "previous_time_next_fixed_time_correlation": _correlation(
                        previous_times, next_fixed_times
                    ),
                    "legal_edges_effective_depth_correlation": _correlation(
                        [float(row["legal_edge_count"]) for row in values],
                        [float(row["effective_depth"]) for row in values],
                    ),
                    "remaining_words_effective_depth_correlation": _correlation(
                        [float(row["remaining_word_count"]) for row in values],
                        [float(row["effective_depth"]) for row in values],
                    ),
                    "depth_change_count": sum(
                        bool(row["depth_changed"]) for row in values
                    ),
                    "depth_oscillation_count": oscillations,
                }
            )
    write_csv(output / "adaptive/diagnostics.csv", diagnostics)
    write_json(output / "adaptive/diagnostics.json", diagnostics)
    return diagnostics


def build_match_jobs(
    selected: dict[str, dict[str, Any]],
    adaptive: dict[str, dict[str, Any]],
    quick: bool = False,
    plan: str = "full",
) -> list[tuple[str, str]]:
    jobs: set[tuple[str, str]] = set()
    for agent in SEARCH_AGENTS:
        baseline = f"baseline_{agent}"
        fixed = f"improved_fixed_{agent}"
        adapted = f"improved_adaptive_{agent}"
        if quick:
            jobs.update(((baseline, adapted), (adapted, baseline)))
        elif plan == "pilot":
            jobs.update(((fixed, adapted), (adapted, fixed)))
        else:
            jobs.update(
                (
                    (baseline, fixed),
                    (fixed, baseline),
                    (fixed, adapted),
                    (adapted, fixed),
                )
            )
    best = [f"improved_adaptive_{agent}" for agent in SEARCH_AGENTS]
    jobs.update(itertools.permutations(best, 2))
    return sorted(jobs)


def match_target(
    target: str,
    selected: dict[str, dict[str, Any]],
    adaptive: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = next(name for name in SEARCH_AGENTS if target.endswith(name))
    if target.startswith("baseline_"):
        return BASELINES[agent], ADAPTIVE_PROFILES["fixed"]
    config = {
        key: value
        for key, value in selected[agent].items()
        if key != "selection_metrics"
    }
    if target.startswith("improved_adaptive_"):
        return config, adaptive[agent]
    return config, ADAPTIVE_PROFILES["fixed"]


def run_matches(
    runtimes: list[Path],
    selected: dict[str, dict[str, Any]],
    adaptive: dict[str, dict[str, Any]],
    output: Path,
    time_limit_sec: float,
    max_moves: int,
    max_match_time_sec: float,
    quick: bool = False,
    match_plan: str = "full",
    match_seeds: set[int] | None = None,
    match_limit: int | None = None,
) -> list[dict[str, Any]]:
    path = output / "matches/results.jsonl"
    rows = read_jsonl(path)
    ids = [row["match_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(
            f"duplicate match IDs in checkpoint: {len(ids) - len(set(ids))}"
        )
    completed = {row["match_id"] for row in rows}
    jobs = build_match_jobs(
        selected,
        adaptive,
        quick=quick,
        plan=match_plan,
    )
    requested_seeds = {0} if quick else (match_seeds or set(range(len(runtimes))))
    selected_runtimes = [
        (seed, runtime_path, RuntimeDictionary.load(runtime_path).word_count)
        for seed, runtime_path in enumerate(runtimes)
        if seed in requested_seeds
    ]
    expected_ids = {
        f"D{dictionary_size}_seed{seed}_{first}_vs_{second}"
        for seed, _runtime_path, dictionary_size in selected_runtimes
        for first, second in jobs
    }
    total = len(expected_ids)
    done = len(expected_ids & completed)
    new_match_count = 0
    for seed, runtime_path, dictionary_size in selected_runtimes:
        runtime = RuntimeDictionary.load(runtime_path)
        for first_target, second_target in jobs:
            if match_limit is not None and new_match_count >= match_limit:
                break
            match_id = (
                f"D{dictionary_size}_seed{seed}_"
                f"{first_target}_vs_{second_target}"
            )
            if match_id in completed:
                continue
            first_config, first_profile = match_target(first_target, selected, adaptive)
            second_config, second_profile = match_target(second_target, selected, adaptive)
            try:
                result = simulate_runtime_match(
                    runtime.to_edge_dictionary(),
                    build_agent(first_config, time_limit_sec, first_profile),
                    build_agent(second_config, time_limit_sec, second_profile),
                    max_moves=min(dictionary_size, max_moves),
                    max_match_time_sec=max_match_time_sec,
                    match_id=match_id,
                )
                row = {
                    "match_id": match_id,
                    "seed": seed,
                    "dictionary_size": dictionary_size,
                    "runtime": str(runtime_path.resolve()),
                    "first_target": first_target,
                    "second_target": second_target,
                    "first_agent": first_config["agent"],
                    "second_agent": second_config["agent"],
                    "winner": result.winner,
                    "loss_reason": result.loss_reason,
                    "turn_count": result.turn_count,
                    "first_avg_time_sec": result.first_avg_time_sec,
                    "second_avg_time_sec": result.second_avg_time_sec,
                    "first_timeout_count": result.first_timeout_count,
                    "second_timeout_count": result.second_timeout_count,
                    "invalid_move": result.loss_reason == "invalid_ai_move",
                    "exception": "",
                    "history": result.history,
                }
            except Exception as exc:  # noqa: BLE001 - experiment must record failures
                row = {
                    "match_id": match_id,
                    "seed": seed,
                    "dictionary_size": dictionary_size,
                    "runtime": str(runtime_path.resolve()),
                    "first_target": first_target,
                    "second_target": second_target,
                    "first_agent": first_config["agent"],
                    "second_agent": second_config["agent"],
                    "winner": "error",
                    "loss_reason": "exception",
                    "turn_count": 0,
                    "first_avg_time_sec": 0.0,
                    "second_avg_time_sec": 0.0,
                    "first_timeout_count": 0,
                    "second_timeout_count": 0,
                    "invalid_move": False,
                    "exception": f"{type(exc).__name__}: {exc}",
                    "history": [],
                }
            append_jsonl(path, row)
            rows.append(row)
            completed.add(match_id)
            done += 1
            new_match_count += 1
            print(f"[{done}/{total}] {match_id}: {row['winner']}, {row['turn_count']} turns")
        if match_limit is not None and new_match_count >= match_limit:
            break
    flat = [{key: value for key, value in row.items() if key != "history"} for row in rows]
    write_csv(output / "matches/results.csv", flat)
    return rows


def appearance_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in matches:
        if match["winner"] not in {"first", "second", "draw"}:
            continue
        for seat in ("first", "second"):
            target = match[f"{seat}_target"]
            won = match["winner"] == seat
            rows.append(
                {
                    "target": target,
                    "agent": match[f"{seat}_agent"],
                    "seed": match["seed"],
                    "seat": seat,
                    "won": won,
                    "draw": match["winner"] == "draw",
                    "elapsed_time_sec": match[f"{seat}_avg_time_sec"],
                    "timeout_count": match[f"{seat}_timeout_count"],
                }
            )
    return rows


def summarize_matches(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    appearances = appearance_rows(matches)

    def grouped(fields: tuple[str, ...]) -> list[dict[str, Any]]:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in appearances:
            groups[tuple(row[field] for field in fields)].append(row)
        result = []
        for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
            wins = sum(bool(row["won"]) for row in values)
            draws = sum(bool(row["draw"]) for row in values)
            result.append(
                {
                    **dict(zip(fields, key)),
                    "games": len(values),
                    "wins": wins,
                    "losses": len(values) - wins - draws,
                    "draws": draws,
                    "win_rate": wins / len(values),
                    "mean_time_sec": statistics.fmean(
                        float(row["elapsed_time_sec"]) for row in values
                    ),
                    "timeout_count": sum(int(row["timeout_count"]) for row in values),
                }
            )
        return result

    return {
        "overall": grouped(("target", "agent")),
        "by_seed": grouped(("seed", "target", "agent")),
        "by_seat": grouped(("seat", "target", "agent")),
    }


def _value_label(value: float, rate: bool = False) -> str:
    if rate:
        return f"{value:.1%}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:.3f}"


def _bar(plt, path: Path, labels, values, title: str, ylabel: str, rate: bool = False) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, values, color="#4c78a8")
    ax.bar_label(
        bars,
        labels=[_value_label(float(value), rate) for value in values],
        padding=3,
        fontsize=8,
    )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", alpha=0.25)
    ax.margins(y=0.15)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def generate_plots(
    output: Path,
    dictionary_size: int,
    fixed_rows: list[dict[str, Any]],
    fixed_summary: list[dict[str, Any]],
    adaptive_rows: list[dict[str, Any]],
    adaptive_summary: list[dict[str, Any]],
    match_summary: dict[str, list[dict[str, Any]]],
) -> list[str]:
    plt = ensure_matplotlib()
    plots = output / "analysis/plots"
    plots.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def bar(name, rows, metric, title, ylabel, rate=False):
        path = plots / f"{name}.png"
        _bar(
            plt,
            path,
            [str(row["config_id"]) for row in rows],
            [float(row[metric]) for row in rows],
            title,
            ylabel,
            rate,
        )
        created.append(str(path))

    bar("fixed_mean_time", fixed_summary, "mean_time_sec", "Fixed setting mean decision time", "Seconds")
    bar("fixed_p95_time", fixed_summary, "p95_time_sec", "Fixed setting p95 decision time", "Seconds")
    bar("fixed_mean_nodes", fixed_summary, "mean_nodes", "Fixed setting mean searched nodes", "Nodes")

    for x_field, filename, xlabel in (
        ("depth", "depth_vs_time", "Maximum depth"),
        ("branch_limit", "branch_limit_vs_time", "Branch limit"),
    ):
        fig, ax = plt.subplots(figsize=(10, 6))
        for agent in ("alpha_beta", "pvs"):
            rows = [
                row
                for row in fixed_summary
                if row["agent"] == agent and row[x_field] != ""
            ]
            ax.scatter(
                [float(row[x_field]) for row in rows],
                [float(row["mean_time_sec"]) for row in rows],
                label=agent,
                alpha=0.8,
            )
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Mean seconds")
        ax.set_title(f"{xlabel} and decision time")
        ax.legend()
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = plots / f"{filename}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    beam = [row for row in fixed_summary if row["agent"] == "beam_negamax"]
    bar("beam_width_vs_time", beam, "mean_time_sec", "Beam widths and mean decision time", "Seconds")
    retention = [row for row in beam if "alpha_beta_root_retention_rate" in row]
    bar(
        "beam_width_vs_reference_retention",
        retention,
        "alpha_beta_root_retention_rate",
        "Beam widths and AlphaBeta root-reference retention",
        "Retention rate",
        True,
    )

    depth_counts: dict[str, int] = defaultdict(int)
    for row in adaptive_rows:
        depth_counts[f"{row['agent']} {row['profile']} D{row['effective_depth']}"] += 1
    depth_rows = [
        {"config_id": key, "count": value} for key, value in sorted(depth_counts.items())
    ]
    bar("adaptive_depth_distribution", depth_rows, "count", "Adaptive effective-depth distribution", "Positions")

    for x_field, filename, xlabel in (
        ("turn", "turn_vs_effective_depth", "Turn"),
        ("legal_edge_count", "legal_edges_vs_effective_depth", "Legal edge types"),
    ):
        fig, ax = plt.subplots(figsize=(10, 6))
        for agent in SEARCH_AGENTS:
            rows = [row for row in adaptive_rows if row["agent"] == agent]
            ax.scatter(
                [float(row[x_field]) for row in rows],
                [float(row["effective_depth"]) for row in rows],
                label=agent,
                alpha=0.6,
            )
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Effective depth")
        ax.set_title(f"{xlabel} and adaptive effective depth")
        ax.legend()
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = plots / f"{filename}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    bar(
        "adaptive_profile_p95_time",
        adaptive_summary,
        "p95_time_sec",
        "Fixed and adaptive profile p95 decision time",
        "Seconds",
    )
    overall = match_summary["overall"]
    path = plots / "fixed_adaptive_win_rate.png"
    _bar(
        plt,
        path,
        [row["target"] for row in overall],
        [row["win_rate"] for row in overall],
        f"Fixed and adaptive D{dictionary_size} match win rate",
        "Win rate",
        True,
    )
    created.append(str(path))

    best_targets = [row for row in overall if row["target"].startswith("improved_adaptive")]
    path = plots / "agent_final_win_rate.png"
    _bar(
        plt,
        path,
        [row["agent"] for row in best_targets],
        [row["win_rate"] for row in best_targets],
        "Final AlphaBeta, PVS, and Beam win rate",
        "Win rate",
        True,
    )
    created.append(str(path))

    fixed_map = {(row["position_id"], row["config_id"]): row for row in fixed_rows}
    for other, filename in (
        ("pvs", "alpha_beta_vs_pvs_position_time"),
        ("beam_negamax", "alpha_beta_vs_beam_position_time"),
    ):
        pairs = []
        for row in fixed_rows:
            if row["agent"] != other:
                continue
            if other == "pvs":
                alpha_id = f"alpha_beta_d{row['depth']}_b{row['branch_limit']}"
            else:
                alpha_id = f"alpha_beta_d{row['depth']}_b16"
            alpha = fixed_map.get((row["position_id"], alpha_id))
            if alpha is not None:
                pairs.append((alpha, row))
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.scatter(
            [float(left["elapsed_time_sec"]) for left, _right in pairs],
            [float(right["elapsed_time_sec"]) for _left, right in pairs],
            alpha=0.65,
        )
        maximum = max(
            [float(item["elapsed_time_sec"]) for pair in pairs for item in pair],
            default=1.0,
        )
        ax.plot([0, maximum], [0, maximum], linestyle="--", color="gray")
        ax.set_xlabel("AlphaBeta seconds")
        ax.set_ylabel(f"{other} seconds")
        ax.set_title(f"Position-level AlphaBeta vs {other} time")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = plots / f"{filename}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    for group_name, filename, title in (
        ("by_seed", "win_rate_by_seed", "Win rate by dictionary seed"),
        ("by_seat", "win_rate_by_seat", "Win rate by seat"),
    ):
        rows = match_summary[group_name]
        path = plots / f"{filename}.png"
        _bar(
            plt,
            path,
            [
                f"{row.get('seed', row.get('seat'))} {row['target']}"
                for row in rows
            ],
            [row["win_rate"] for row in rows],
            title,
            "Win rate",
            True,
        )
        created.append(str(path))
    return created


def generate_report(
    output: Path,
    manifest: dict[str, Any],
    positions: list[dict[str, Any]],
    fixed_summary: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    adaptive_summary: list[dict[str, Any]],
    adaptive_diagnostics: list[dict[str, Any]],
    selected_adaptive: dict[str, dict[str, Any]],
    matches: list[dict[str, Any]],
    match_summary: dict[str, list[dict[str, Any]]],
    plots: list[str],
) -> Path:
    dictionary_size = int(manifest["config"].get("dictionary_size", 5000))
    selection_source = manifest["config"].get("selection_source_run")
    diagnostic_lines = [
        (
            f"- {row['agent']} {row['profile']}: 深度低下"
            f"{row['lowered_depth_count']}/{row['position_count']}、"
            f"低下時の手変更率{row['move_change_when_lowered_rate']:.1%}、"
            f"上下反転{row['depth_oscillation_count']}回"
        )
        for row in adaptive_diagnostics
    ]
    lines = [
        "# AlphaBeta・PVS・Beamパラメータ調整と適応深度検証",
        "",
        "## 1. 実験目的",
        "",
        (
            f"D{dictionary_size}で固定設定と適応深度を比較した。"
            + (
                f"固定設定は`{selection_source}`から移植して再検証した。"
                if selection_source
                else "固定深度の基本設定を先に選定した。"
            )
            + "HybridAgentは実装していない。"
        ),
        "",
        "## 2. 既存実装の確認",
        "",
        "AI対AIはEdgeDictionaryとAIEdgeStateだけを使う。AlphaBetaのルートalpha共有、PVSのnull window、Beamの候補制限、共通評価関数は維持した。",
        "",
        "## 3. ベースライン",
        "",
        "- AlphaBeta D5/B8 固定",
        "- PVS D5/B8 固定",
        "- Beam D5/8-6-4-2 固定",
        f"- 1手制限 {manifest['config']['time_limit_sec']}秒",
        "",
        "## 4. 実験方法",
        "",
        f"D{dictionary_size}のseed 0・1で設定を選び、seed 2は選定後の固定局面と対局確認に用いた。固定局面で安全性を確認してから対局へ進めた。",
        "",
        "## 5. 固定局面の作成方法",
        "",
        f"実対局ログから{len(positions)}局面を抽出した。序盤・中盤・終盤、合法辺数最大・最小、候補評価差最小、枝刈り回数最大、記録時間最大を候補にし、同一turnは重複除去した。",
        "",
        "## 6. パラメータ探索範囲",
        "",
        (
            "移植元で選定済みのAlphaBeta、PVS、BeamNegamax各1設定を固定深度で再検証した。"
            if selection_source
            else "AlphaBeta/PVSはdepth 5・6・7とbranch 8・12・16、Beamは指定4幅とdepth 5・6・7を候補にした。"
        ),
        "",
        "## 7. 設定の除外基準",
        "",
        "深度6のtimeout率20%以下、p95が制限の90%以下、平均ルート完了率50%以上の場合だけ対応する深度7を実行した。",
        f"除外された深度7設定は{len(exclusions)}件だった。",
        "",
        "## 8. 固定深度の結果",
        "",
        "| agent | config | mean s | p95 s | timeout | nodes | root complete | AB move agreement |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in fixed_summary:
        lines.append(
            f"| {row['agent']} | {row['config_id']} | {row['mean_time_sec']:.4f} | "
            f"{row['p95_time_sec']:.4f} | {row['timeout_rate']:.1%} | "
            f"{row['mean_nodes']:.1f} | {row['mean_root_completion_rate']:.1%} | "
            f"{row.get('alpha_beta_move_agreement_rate', 0.0):.1%} |"
        )
    lines.extend(["", "## 9. AlphaBetaの結果", ""])
    lines.append(f"選択設定: `{selected['alpha_beta']['config_id']}`")
    lines.extend(["", "## 10. PVSの結果", ""])
    lines.append(f"選択設定: `{selected['pvs']['config_id']}`")
    lines.extend(["", "## 11. Beamの結果", ""])
    lines.append(
        f"選択設定: `{selected['beam_negamax']['config_id']}`。幅配列を超えるplyでは最後の幅を繰り返す。"
    )
    lines.extend(["", "## 12. 適応深度の有無の比較", ""])
    for row in adaptive_summary:
        lines.append(
            f"- {row['agent']} {row['profile']}: mean={row['mean_time_sec']:.4f}s, "
            f"p95={row['p95_time_sec']:.4f}s, timeout={row['timeout_rate']:.1%}, "
            f"effective depth={row['mean_effective_depth']:.2f}"
        )
    lines.extend(["", "## 13. 適応深度閾値の比較", ""])
    for agent, row in selected_adaptive.items():
        lines.append(f"- {agent}: `{row['profile']}`を適応候補として選択")
    lines.extend(["", "## 14. 対局実験結果", ""])
    lines.append(f"対局数: {len(matches)}")
    for row in match_summary["overall"]:
        lines.append(
            f"- {row['target']}: {row['wins']}/{row['games']}勝 "
            f"({row['win_rate']:.1%}), 平均{row['mean_time_sec']:.4f}秒"
        )
    lines.extend(["", "## 15. 先手・後手別分析", ""])
    for row in match_summary["by_seat"]:
        lines.append(f"- {row['seat']} {row['target']}: {row['win_rate']:.1%}")
    lines.extend(["", "## 16. 辞書seed別分析", ""])
    for row in match_summary["by_seed"]:
        lines.append(f"- seed {row['seed']} {row['target']}: {row['win_rate']:.1%}")
    lines.extend(
        [
            "",
            "## 17. 処理時間の内訳",
            "",
            "合法手生成、候補評価、候補ソート、ルート順序付け、再帰内順序付け、葉評価、再帰その他、その他をログへ保存した。candidate evaluationとsortの合計はordering timeの内訳である。",
            "",
            "## 18. 深度変更が選択手へ与えた影響",
            "",
            "適応ログには各手のeffective depth、変更前後、変更理由、回復連続回数、残存語数、合法辺数を保存した。詳細は`adaptive/runs.csv`を参照。",
            *diagnostic_lines,
            "",
            "## 19. AlphaBetaより他手法が速くならない理由",
            "",
            "PVSはnull-windowのノード削減が再探索と候補順序評価のコストで相殺される局面がある。Beamは枝刈りを使わず、残した候補を均等に読むため、幅を絞ってもAlphaBetaより多くのノードを読む場合がある。局面別散布図を併記した。",
            "",
            "## 20. 各手法の強みと弱み",
            "",
            "- AlphaBeta: ルートalpha共有と良い候補順序で安定。",
            "- PVS: 順序が当たれば少ノードだが再探索コストがある。",
            "- Beam: 計算量を幅で制御できるが参照手を落とす近似誤差がある。",
            "",
            "## 21. 採用すべき最終設定",
            "",
        ]
    )
    for agent in SEARCH_AGENTS:
        lines.append(
            f"- {agent}: 固定 `{selected[agent]['config_id']}`、"
            f"適応候補 `{selected_adaptive[agent]['profile']}`"
        )
    lines.extend(["", "## 22. 採用しなかった設定と理由", ""])
    for row in exclusions:
        lines.append(f"- {row['config_id']}: {row['reason']}")
    lines.extend(
        [
            "",
            "## 23. HybridAgentへ利用できそうな知見",
            "",
            "合法辺数、残存語数、固定深度の実測時間、AlphaBeta参照手のBeam順位は、将来の方式切替や深度選択に使える。今回は切替ロジックを実装していない。",
            "",
            "## 24. 今後の改善案",
            "",
            "前手時間だけでなく現在局面の合法辺数と残存語数を使う深度予測、候補順序改善、置換表を個別に検証する。",
            "",
            "## 25. 反復深化を導入する価値の評価",
            "",
            "現在方式は単一深度を途中まで読むため、timeout時に完了済み浅い探索結果を保証しない。反復深化は安全な完成手を保持し、次反復の手順序にも利用できるため価値が高い。ただし今回の範囲外である。",
            "",
            "## 26. 再現手順",
            "",
            "```bash",
            ".venv/bin/python src/run_search_parameter_tuning.py --full",
            "```",
            "",
            f"- commit: `{manifest['commit_id']}`",
            f"- source fingerprint: `{manifest['source_fingerprint']}`",
            f"- plots: {len(plots)}",
            "",
            "## 制限と簡略化",
            "",
            "AlphaBetaは参照手であり真の最善手ではない。Beam内部の各plyで参照主変化を追跡せず、ルート保持率を測った。固定局面は実ログ依存で、すべての局面型を完全には網羅しない。",
        ]
    )
    report = output / "final_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument(
        "--stage",
        choices=("all", "positions", "fixed", "adaptive", "matches", "analysis"),
        default="all",
    )
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--reference-log", type=Path, default=DEFAULT_REFERENCE_LOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--resume-run",
        type=Path,
        help="Resume an existing run directory after a compatible bug fix",
    )
    reuse_group = parser.add_mutually_exclusive_group()
    reuse_group.add_argument(
        "--reuse-fixed-from",
        type=Path,
        help="Reuse compatible fixed-depth and validation results from an older run",
    )
    reuse_group.add_argument(
        "--selection-from",
        type=Path,
        help="Import selected fixed settings, then revalidate them on this dictionary",
    )
    parser.add_argument("--dictionary-size", type=int, default=5000)
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument("--positions-per-seed", type=int, default=8)
    parser.add_argument("--max-moves", type=int, default=3000)
    parser.add_argument("--max-match-time-sec", type=float, default=600.0)
    parser.add_argument(
        "--match-plan",
        choices=("pilot", "full"),
        default="full",
        help="pilot runs fixed-vs-adaptive and adaptive-agent round robins only",
    )
    parser.add_argument(
        "--match-seeds",
        nargs="+",
        type=int,
        help="Dictionary seeds to execute in this invocation",
    )
    parser.add_argument(
        "--match-limit",
        type=int,
        help="Maximum number of new matches to execute in this invocation",
    )
    args = parser.parse_args(argv)
    if (
        args.dictionary_size <= 0
        or args.time_limit_sec <= 0
        or args.positions_per_seed <= 0
        or args.max_moves <= 0
        or args.max_match_time_sec <= 0
        or (args.match_limit is not None and args.match_limit <= 0)
        or (
            args.match_seeds is not None
            and any(seed < 0 for seed in args.match_seeds)
        )
    ):
        parser.error("dictionary size, time limits, moves, and position count must be positive")
    return args


def main() -> None:
    args = parse_args()
    paths = runtime_paths(args.runtime_dir, args.dictionary_size)
    quick = bool(args.quick)
    config = {
        "format_version": FORMAT_VERSION,
        "mode": "quick" if quick else "full",
        "dictionary_size": args.dictionary_size,
        "time_limit_sec": 0.15 if quick else args.time_limit_sec,
        "max_moves": args.max_moves,
        "max_match_time_sec": args.max_match_time_sec,
        "positions_per_seed": min(3, args.positions_per_seed) if quick else args.positions_per_seed,
        "runtime_paths": [str(path.resolve()) for path in paths],
        "reference_log": str(args.reference_log.resolve()),
        "fixed_configs": fixed_configs(),
        "adaptive_profiles": ADAPTIVE_PROFILES,
        "reused_fixed_run": (
            str(args.reuse_fixed_from.resolve())
            if args.reuse_fixed_from is not None
            else None
        ),
        "selection_source_run": (
            str(args.selection_from.resolve())
            if args.selection_from is not None
            else None
        ),
        "depth7_gate": {
            "timeout_rate_max": 0.2,
            "p95_time_ratio_max": 0.9,
            "root_completion_rate_min": 0.5,
        },
    }
    commit = git_commit()
    fingerprint = source_fingerprint()
    run_hash = stable_hash(
        {"config": config, "commit_id": commit, "source_fingerprint": fingerprint}
    )[:12]
    output = (
        args.resume_run.resolve()
        if args.resume_run is not None
        else args.output_root / run_hash
    )
    output.mkdir(parents=True, exist_ok=True)
    lock_handle = (output / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(
            f"the same experiment is already running: {output}"
        ) from exc
    manifest_path = output / "manifest.json"
    if args.resume_run is not None:
        if not manifest_path.is_file():
            raise FileNotFoundError(f"resume manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stable_hash(manifest.get("config")) != stable_hash(config):
            raise ValueError("resume run configuration does not match current CLI settings")
        fingerprints = list(manifest.get("source_fingerprint_history", []))
        original_fingerprint = manifest.get("source_fingerprint")
        if original_fingerprint and original_fingerprint not in fingerprints:
            fingerprints.append(original_fingerprint)
        if fingerprint not in fingerprints:
            fingerprints.append(fingerprint)
        manifest.update(
            {
                "last_resumed_at": datetime.now(timezone.utc).isoformat(),
                "latest_source_fingerprint": fingerprint,
                "source_fingerprint_history": fingerprints,
                "resume_note": (
                    "Existing compatible checkpoints were retained and the "
                    "latest source fingerprint was recorded."
                ),
            }
        )
    else:
        manifest = {
            "format_version": FORMAT_VERSION,
            "run_hash": run_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "commit_id": commit,
            "source_fingerprint": fingerprint,
            "python_version": sys.version,
            "platform": platform.platform(),
            "config": config,
        }
    write_json(manifest_path, manifest)
    positions_path = output / "fixed_positions.json"
    if positions_path.is_file():
        positions = json.loads(positions_path.read_text(encoding="utf-8"))
    elif args.reuse_fixed_from is not None:
        source_positions = args.reuse_fixed_from.resolve() / "fixed_positions.json"
        if not source_positions.is_file():
            raise FileNotFoundError(
                f"fixed-stage source positions not found: {source_positions}"
            )
        positions = json.loads(source_positions.read_text(encoding="utf-8"))
        write_json(positions_path, positions)
    else:
        positions = collect_positions(
            paths,
            args.reference_log,
            int(config["positions_per_seed"]),
        )
        write_json(positions_path, positions)
    if args.stage == "positions":
        print(output)
        return
    if args.selection_from is not None:
        selected = load_selection_source(args.selection_from, output)
        fixed_rows, fixed_summary = run_selected_fixed_benchmark(
            positions,
            selected,
            output,
            float(config["time_limit_sec"]),
        )
        exclusions: list[dict[str, Any]] = []
        run_validation(
            positions, selected, output, float(config["time_limit_sec"])
        )
    elif args.reuse_fixed_from is not None:
        fixed_rows, fixed_summary, exclusions, selected = reuse_fixed_stage(
            args.reuse_fixed_from,
            output,
            config,
        )
    else:
        fixed_rows, fixed_summary, exclusions = run_fixed_benchmark(
            positions, output, float(config["time_limit_sec"])
        )
        selected = select_fixed_settings(
            fixed_summary, float(config["time_limit_sec"])
        )
        write_json(output / "fixed_depth/selected.json", selected)
        run_validation(
            positions, selected, output, float(config["time_limit_sec"])
        )
    if args.stage == "fixed":
        print(output)
        return
    adaptive_rows, adaptive_summary = run_adaptive_benchmark(
        positions,
        selected,
        fixed_rows,
        output,
        float(config["time_limit_sec"]),
    )
    adaptive_diagnostics = analyze_adaptive_behavior(
        adaptive_rows, fixed_rows, selected, output
    )
    selected_adaptive = select_adaptive_profiles(selected, adaptive_summary)
    write_json(output / "adaptive/selected.json", selected_adaptive)
    if args.stage == "adaptive":
        print(output)
        return
    requested_match_seeds = (
        set(args.match_seeds)
        if args.match_seeds is not None
        else set(range(len(paths)))
    )
    invalid_match_seeds = sorted(
        seed
        for seed in requested_match_seeds
        if seed >= len(paths)
    )
    if invalid_match_seeds:
        raise ValueError(
            "match seeds do not have runtime files: "
            + ", ".join(map(str, invalid_match_seeds))
        )
    append_jsonl(
        output / "matches/execution_requests.jsonl",
        {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "match_plan": args.match_plan,
            "match_seeds": sorted(requested_match_seeds),
            "match_limit": args.match_limit,
        },
    )
    matches = run_matches(
        paths,
        selected,
        selected_adaptive,
        output,
        float(config["time_limit_sec"]),
        int(config["max_moves"]),
        float(config["max_match_time_sec"]),
        quick=quick,
        match_plan=args.match_plan,
        match_seeds=requested_match_seeds,
        match_limit=args.match_limit,
    )
    if args.stage == "matches":
        print(output)
        return
    match_summary = summarize_matches(matches)
    for name, rows in match_summary.items():
        write_csv(output / f"analysis/{name}.csv", rows)
        write_json(output / f"analysis/{name}.json", rows)
    plots = generate_plots(
        output,
        int(config["dictionary_size"]),
        fixed_rows,
        fixed_summary,
        adaptive_rows,
        adaptive_summary,
        match_summary,
    )
    report = generate_report(
        output,
        manifest,
        positions,
        fixed_summary,
        exclusions,
        selected,
        adaptive_summary,
        adaptive_diagnostics,
        selected_adaptive,
        matches,
        match_summary,
        plots,
    )
    write_json(
        output / "completion.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "fixed_position_count": len(positions),
            "fixed_run_count": len(fixed_rows),
            "adaptive_run_count": len(adaptive_rows),
            "match_count": len(matches),
            "plot_count": len(plots),
            "report": str(report),
        },
    )
    print(output)


if __name__ == "__main__":
    main()
