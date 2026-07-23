"""Benchmark one edge-native search decision on fixed RuntimeDictionaries."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AggressivePVSAgent,
    AlphaBetaAgent,
    BeamNegamaxAgent,
)
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


AGENT_NAMES = ("alpha_beta", "beam_negamax", "aggressive_pvs")


def build_agent(name: str, time_limit_sec: float):
    if name == "alpha_beta":
        return AlphaBetaAgent(
            time_limit_sec=time_limit_sec,
            depth=3,
            branch_limit=12,
            adaptive_depth=False,
        )
    if name == "beam_negamax":
        return BeamNegamaxAgent(
            time_limit_sec=time_limit_sec,
            depth=4,
            beam_widths=(12, 8, 4, 2),
            adaptive_depth=False,
        )
    if name == "aggressive_pvs":
        return AggressivePVSAgent(
            time_limit_sec=time_limit_sec,
            depth=3,
            branch_limit=12,
            adaptive_depth=False,
        )
    raise ValueError(f"unknown agent: {name}")


def runtime_seed(runtime_path: Path) -> int:
    metadata_path = runtime_path.with_name(
        runtime_path.name.removesuffix(".runtime.json") + ".metadata.json"
    )
    if not metadata_path.is_file():
        return 0
    return int(json.loads(metadata_path.read_text(encoding="utf-8")).get("seed", 0))


def run_benchmark(
    runtime_paths: list[Path],
    agent_names: list[str],
    time_limit_sec: float,
    repetitions: int,
) -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for runtime_path in runtime_paths:
        runtime = RuntimeDictionary.load(runtime_path)
        seed = runtime_seed(runtime_path)
        for agent_name in agent_names:
            for repetition in range(repetitions):
                agent = build_agent(agent_name, time_limit_sec)
                decision = agent.choose_edge(AIEdgeState.initial(runtime))
                extra = decision.extra
                nodes = int(extra.get("nodes_searched", 0))
                elapsed = float(decision.elapsed_time_sec)
                runs.append(
                    {
                        "runtime": str(runtime_path),
                        "dictionary_size": runtime.word_count,
                        "seed": seed,
                        "agent": agent_name,
                        "repetition": repetition,
                        "elapsed_time_sec": elapsed,
                        "timed_out": decision.timed_out,
                        "nodes_searched": nodes,
                        "time_per_node_sec": elapsed / nodes if nodes else None,
                        "ordering_time_sec": extra.get("ordering_time_sec", 0.0),
                        "evaluation_time_sec": extra.get("evaluation_time_sec", 0.0),
                        "search_time_sec": extra.get("search_time_sec", 0.0),
                        "total_search_time_sec": extra.get(
                            "total_search_time_sec", elapsed
                        ),
                        "leaf_evaluations": extra.get("leaf_evaluations", 0),
                        "ordering_evaluations": extra.get("ordering_evaluations", 0),
                        "full_survival_evaluations": extra.get(
                            "full_survival_evaluations", 0
                        ),
                        "simple_survival_evaluations": extra.get(
                            "simple_survival_evaluations", 0
                        ),
                        "completed_root_moves": extra.get("completed_root_moves", 0),
                        "effective_depth": extra.get("effective_depth"),
                        "null_window_searches": extra.get(
                            "null_window_searches", 0
                        ),
                        "research_count": extra.get("research_count", 0),
                        "research_rate": extra.get("research_rate", 0.0),
                    }
                )

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in runs:
        grouped[str(row["agent"])].append(row)
    summaries: list[dict[str, object]] = []
    for agent_name in agent_names:
        rows = grouped[agent_name]
        total_nodes = sum(int(row["nodes_searched"]) for row in rows)
        total_elapsed = sum(float(row["elapsed_time_sec"]) for row in rows)
        null_searches = sum(int(row["null_window_searches"]) for row in rows)
        researches = sum(int(row["research_count"]) for row in rows)
        summaries.append(
            {
                "agent": agent_name,
                "run_count": len(rows),
                "average_elapsed_time_sec": statistics.fmean(
                    float(row["elapsed_time_sec"]) for row in rows
                ),
                "timeout_rate": statistics.fmean(
                    bool(row["timed_out"]) for row in rows
                ),
                "average_nodes_searched": statistics.fmean(
                    int(row["nodes_searched"]) for row in rows
                ),
                "time_per_node_sec": (
                    total_elapsed / total_nodes if total_nodes else None
                ),
                "average_ordering_time_sec": statistics.fmean(
                    float(row["ordering_time_sec"]) for row in rows
                ),
                "average_evaluation_time_sec": statistics.fmean(
                    float(row["evaluation_time_sec"]) for row in rows
                ),
                "average_full_survival_evaluations": statistics.fmean(
                    int(row["full_survival_evaluations"]) for row in rows
                ),
                "average_completed_root_moves": statistics.fmean(
                    int(row["completed_root_moves"]) for row in rows
                ),
                "average_effective_depth": statistics.fmean(
                    int(row["effective_depth"]) for row in rows
                ),
                "research_rate": researches / null_searches if null_searches else 0.0,
            }
        )
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "time_limit_sec": time_limit_sec,
        "repetitions": repetitions,
        "agents": agent_names,
        "runtimes": [str(path) for path in runtime_paths],
        "runs": runs,
        "summary": summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--agents",
        nargs="+",
        choices=AGENT_NAMES,
        default=list(AGENT_NAMES),
    )
    parser.add_argument("--time-limit-sec", type=float, default=0.3)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.time_limit_sec <= 0:
        parser.error("--time-limit-sec must be positive")
    if args.repetitions <= 0:
        parser.error("--repetitions must be positive")
    return args


def main() -> None:
    args = parse_args()
    result = run_benchmark(
        args.runtime,
        args.agents,
        args.time_limit_sec,
        args.repetitions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
