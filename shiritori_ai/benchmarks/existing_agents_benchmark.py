"""Fixed-position benchmark utilities for the existing edge search agents."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import AlphaBetaAgent, BeamNegamaxAgent, PVSAgent  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402
from search_common import edge_position_metrics, risk_level_for_metrics  # noqa: E402


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip()


def percentile(values: list[float], rate: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * rate) - 1)]


def load_reference_histories(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def collect_fixed_positions(
    runtime_paths: list[Path],
    reference_match_log: Path,
) -> list[dict[str, Any]]:
    """Take repeatable phase/risk snapshots from completed reference matches."""

    reference_rows = load_reference_histories(reference_match_log)
    positions: list[dict[str, Any]] = []
    for runtime_path in runtime_paths:
        runtime = RuntimeDictionary.load(runtime_path)
        metadata_path = runtime_path.with_name(
            runtime_path.name.removesuffix(".runtime.json") + ".metadata.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        seed = int(metadata["seed"])
        reference = next(
            row for row in reference_rows if f"_seed{seed}_" in str(row["match_id"])
        )
        history = reference["history"]
        state = AIEdgeState.initial(runtime)
        risks: list[str] = []
        for row in history:
            risks.append(risk_level_for_metrics(edge_position_metrics(state)).value)
            state.apply_edge(int(row["start_id"]), int(row["end_id"]))

        first_risk = {
            risk: risks.index(risk)
            for risk in ("caution", "danger", "critical")
            if risk in risks
        }
        requested = {
            "early": 0,
            "middle": len(history) // 2,
            "late": max(0, len(history) - 10),
            **first_risk,
        }
        for phase, turn in requested.items():
            prefix = [
                [int(row["start_id"]), int(row["end_id"])]
                for row in history[:turn]
            ]
            positions.append(
                {
                    "position_id": f"seed{seed}_{phase}_t{turn}",
                    "runtime": str(runtime_path),
                    "seed": seed,
                    "phase": phase,
                    "turn": turn,
                    "risk_level": risks[turn],
                    "edge_history": prefix,
                }
            )
    return positions


def restore_position(position: dict[str, Any]) -> tuple[RuntimeDictionary, AIEdgeState]:
    runtime = RuntimeDictionary.load(position["runtime"])
    state = AIEdgeState.initial(runtime)
    for start_id, end_id in position["edge_history"]:
        state.apply_edge(int(start_id), int(end_id))
    state.assert_aggregates_consistent()
    return runtime, state


def build_profile_agent(
    agent_name: str,
    profile: str,
    time_limit_sec: float,
):
    if profile == "equal_depth":
        depth = 4
        if agent_name == "alpha_beta":
            return AlphaBetaAgent(
                time_limit_sec=time_limit_sec,
                depth=depth,
                branch_limit=12,
                adaptive_depth=False,
            )
        if agent_name == "beam_negamax":
            return BeamNegamaxAgent(
                time_limit_sec=time_limit_sec,
                depth=depth,
                beam_widths=(12, 8, 4, 2),
                adaptive_depth=False,
            )
        return PVSAgent(
            time_limit_sec=time_limit_sec,
            depth=depth,
            branch_limit=12,
            adaptive_depth=False,
        )
    if agent_name == "alpha_beta":
        return AlphaBetaAgent(
            time_limit_sec=time_limit_sec,
            depth=3,
            branch_limit=12,
            adaptive_depth=False,
        )
    if agent_name == "beam_negamax":
        return BeamNegamaxAgent(
            time_limit_sec=time_limit_sec,
            depth=4,
            beam_widths=(12, 8, 4, 2),
            adaptive_depth=False,
        )
    return PVSAgent(
        time_limit_sec=time_limit_sec,
        depth=3,
        branch_limit=12,
        adaptive_depth=False,
    )


def benchmark_positions(
    positions: list[dict[str, Any]],
    output_dir: Path,
    profile: str,
    repetitions: int,
    time_limit_sec: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for position in positions:
        runtime, template = restore_position(position)
        for agent_name in ("alpha_beta", "beam_negamax", "pvs"):
            for repetition in range(repetitions):
                state = AIEdgeState(
                    edge_dictionary=template.edge_dictionary,
                    required_char_id=template.required_char_id,
                    edge_counts=list(template.edge_counts),
                    active_end_masks=list(template.active_end_masks),
                )
                agent = build_profile_agent(agent_name, profile, time_limit_sec)
                decision = agent.choose_edge(state)
                extra = decision.extra
                start_char = (
                    runtime.id_to_char[decision.start_id]
                    if decision.start_id is not None
                    else ""
                )
                end_char = (
                    runtime.id_to_char[decision.end_id]
                    if decision.end_id is not None
                    else ""
                )
                nodes = int(extra.get("nodes_searched", 0))
                elapsed = float(decision.elapsed_time_sec)
                runs.append(
                    {
                        "position_id": position["position_id"],
                        "seed": position["seed"],
                        "phase": position["phase"],
                        "risk_level": position["risk_level"],
                        "turn": position["turn"],
                        "agent": agent_name,
                        "repetition": repetition,
                        "start_id": decision.start_id,
                        "end_id": decision.end_id,
                        "selected_edge": f"{start_char}→{end_char}",
                        "score": decision.score,
                        "elapsed_time_sec": elapsed,
                        "timed_out": decision.timed_out,
                        "nodes_searched": nodes,
                        "time_per_node_sec": elapsed / nodes if nodes else None,
                        "leaf_evaluations": extra.get("leaf_evaluations", 0),
                        "ordering_evaluations": extra.get("ordering_evaluations", 0),
                        "completed_root_moves": extra.get("completed_root_moves", 0),
                        "cutoff_count": extra.get("cutoff_count", 0),
                        "pruned_move_count": extra.get("pruned_move_count", 0),
                        "beam_pruned_move_count": extra.get(
                            "beam_pruned_move_count", 0
                        ),
                        "null_window_searches": extra.get(
                            "null_window_searches", 0
                        ),
                        "research_count": extra.get("research_count", 0),
                        "research_rate": extra.get("research_rate", 0.0),
                        "effective_depth": extra.get("effective_depth"),
                    }
                )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[(row["position_id"], row["agent"])].append(row)
    summaries: list[dict[str, Any]] = []
    for (position_id, agent_name), rows in sorted(grouped.items()):
        elapsed = [float(row["elapsed_time_sec"]) for row in rows]
        choices = defaultdict(int)
        for row in rows:
            choices[str(row["selected_edge"])] += 1
        summaries.append(
            {
                "position_id": position_id,
                "seed": rows[0]["seed"],
                "phase": rows[0]["phase"],
                "risk_level": rows[0]["risk_level"],
                "agent": agent_name,
                "runs": len(rows),
                "selected_edge": max(choices, key=choices.get),
                "stable_choice": len(choices) == 1,
                "mean_time_sec": statistics.fmean(elapsed),
                "median_time_sec": statistics.median(elapsed),
                "p95_time_sec": percentile(elapsed, 0.95),
                "timeout_rate": statistics.fmean(
                    bool(row["timed_out"]) for row in rows
                ),
                "mean_nodes": statistics.fmean(
                    int(row["nodes_searched"]) for row in rows
                ),
                "mean_completed_root_moves": statistics.fmean(
                    int(row["completed_root_moves"]) for row in rows
                ),
                "mean_cutoff_count": statistics.fmean(
                    int(row["cutoff_count"]) for row in rows
                ),
                "mean_research_rate": statistics.fmean(
                    float(row["research_rate"]) for row in rows
                ),
            }
        )

    config = {
        "commit_id": git_commit(),
        "profile": profile,
        "repetitions": repetitions,
        "time_limit_sec": time_limit_sec,
        "position_count": len(positions),
    }
    config["config_hash"] = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    payload = {"config": config, "positions": positions, "runs": runs, "summary": summaries}
    (output_dir / "benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "benchmark_runs.csv", runs)
    write_csv(output_dir / "benchmark_summary.csv", summaries)
    return payload


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for fieldname in row:
            if fieldname not in seen:
                seen.add(fieldname)
                fieldnames.append(fieldname)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", nargs="+", required=True, type=Path)
    parser.add_argument("--reference-match-log", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--profile", choices=("current", "equal_depth"), default="current")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    positions = collect_fixed_positions(args.runtime, args.reference_match_log)
    result = benchmark_positions(
        positions,
        args.output_dir,
        args.profile,
        args.repetitions,
        args.time_limit_sec,
    )
    print(
        f"positions={len(result['positions'])} runs={len(result['runs'])} "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
