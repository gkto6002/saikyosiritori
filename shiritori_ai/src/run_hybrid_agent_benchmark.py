"""Benchmark three hybrid search agents on saved D10000 positions."""

from __future__ import annotations

import argparse
import fcntl
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import (
    AlphaBetaAgent,
    BeamAlphaBetaAgent,
    BeamNegamaxAgent,
    BeamPVSAgent,
    GraphControlAgent,
    GraphPVSAgent,
    PVSAgent,
)
from run_full_alpha_beta_comparison import load_positions
from run_search_parameter_tuning import (
    append_jsonl,
    decision_row,
    git_commit,
    read_jsonl,
    restore_position,
    source_fingerprint,
    stable_hash,
    summarize_runs,
    write_csv,
    write_json,
)
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/hybrid_agent_comparison/benchmark"
FORMAT_VERSION = "hybrid_agent_benchmark_v1"
DEFAULT_AGENTS = (
    "alpha_beta",
    "pvs",
    "beam_negamax",
    "graph_control",
    "graph_pvs",
    "beam_alpha_beta",
    "beam_pvs",
)


def parse_beam_widths(value: str) -> tuple[int, ...]:
    try:
        widths = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("beam widths must be integers") from exc
    if not widths or any(width <= 0 for width in widths):
        raise argparse.ArgumentTypeError("beam widths must be positive")
    return widths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--branch-limit", type=int, default=8)
    parser.add_argument(
        "--beam-widths",
        type=parse_beam_widths,
        default=(8, 6, 4, 2),
    )
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument(
        "--agents",
        nargs="+",
        choices=DEFAULT_AGENTS,
        default=list(DEFAULT_AGENTS),
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--resume-run", type=Path)
    args = parser.parse_args(argv)
    if args.depth <= 0 or args.branch_limit <= 0 or args.time_limit_sec <= 0:
        parser.error("depth, branch limit, and time limit must be positive")
    return args


def build_configs(
    agents: list[str],
    depth: int,
    branch_limit: int,
    beam_widths: tuple[int, ...],
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    beam_label = "-".join(map(str, beam_widths))
    for agent in agents:
        config: dict[str, Any] = {
            "config_id": agent,
            "agent": agent,
            "depth": 1 if agent == "graph_control" else depth,
            "branch_limit": (
                branch_limit
                if agent in {"alpha_beta", "pvs", "graph_pvs"}
                else None
            ),
        }
        if agent in {"beam_negamax", "beam_alpha_beta", "beam_pvs"}:
            config["config_id"] = f"{agent}_w{beam_label}"
            config["beam_widths"] = beam_widths
        configs.append(config)
    return configs


def build_benchmark_agent(
    config: dict[str, Any],
    time_limit_sec: float,
):
    agent = str(config["agent"])
    common = {
        "time_limit_sec": time_limit_sec,
        "random_seed": 0,
    }
    search = {
        **common,
        "depth": int(config["depth"]),
        "adaptive_depth": False,
    }
    if agent == "graph_control":
        return GraphControlAgent(**common)
    if agent == "alpha_beta":
        return AlphaBetaAgent(
            **search,
            branch_limit=int(config["branch_limit"]),
        )
    if agent == "pvs":
        return PVSAgent(
            **search,
            branch_limit=int(config["branch_limit"]),
        )
    if agent == "beam_negamax":
        return BeamNegamaxAgent(
            **search,
            beam_widths=config["beam_widths"],
        )
    if agent == "graph_pvs":
        return GraphPVSAgent(
            **search,
            branch_limit=int(config["branch_limit"]),
        )
    if agent == "beam_alpha_beta":
        return BeamAlphaBetaAgent(
            **search,
            beam_widths=config["beam_widths"],
        )
    if agent == "beam_pvs":
        return BeamPVSAgent(
            **search,
            beam_widths=config["beam_widths"],
        )
    raise ValueError(f"unknown benchmark agent: {agent}")


def run_benchmark(
    positions: list[dict[str, Any]],
    configs: list[dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> list[dict[str, Any]]:
    path = output / "runs.jsonl"
    rows = read_jsonl(path)
    completed = {(row["config_id"], row["position_id"]) for row in rows}
    expected = len(configs) * len(positions)
    for config in configs:
        for position in positions:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_benchmark_agent(config, time_limit_sec).choose_edge(state)
            state.assert_aggregates_consistent()
            row = decision_row(config, position, decision, profile_name="fixed")
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
            print(
                f"[{len(completed)}/{expected}] {config['config_id']} "
                f"{position['position_id']}: {decision.elapsed_time_sec:.4f}s"
                + (" timeout" if decision.timed_out else ""),
                flush=True,
            )
    rows.sort(key=lambda row: (str(row["config_id"]), str(row["position_id"])))
    write_csv(output / "runs.csv", rows)
    return rows


def extended_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = summarize_runs(rows)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["config_id"]), []).append(row)
    for summary in summaries:
        values = groups[str(summary["config_id"])]
        null_searches = sum(int(row["null_window_searches"]) for row in values)
        researches = sum(int(row["research_count"]) for row in values)
        graph_calls = sum(int(row["graph_ordering_calls"]) for row in values)
        graph_changes = sum(
            int(row["graph_ordering_changed_first_count"]) for row in values
        )
        summary.update(
            {
                "mean_cutoff_count": statistics.fmean(
                    int(row["cutoff_count"]) for row in values
                ),
                "mean_pruned_move_count": statistics.fmean(
                    int(row["pruned_move_count"]) for row in values
                ),
                "mean_beam_pruned_move_count": statistics.fmean(
                    int(row["beam_pruned_move_count"]) for row in values
                ),
                "null_window_search_count": null_searches,
                "research_count": researches,
                "overall_research_rate": (
                    researches / null_searches if null_searches else 0.0
                ),
                "mean_graph_ordering_time_sec": statistics.fmean(
                    float(row["graph_ordering_time_sec"]) for row in values
                ),
                "graph_ordering_calls": graph_calls,
                "graph_ordering_changed_first_count": graph_changes,
                "graph_ordering_changed_first_rate": (
                    graph_changes / graph_calls if graph_calls else 0.0
                ),
            }
        )
    return summaries


def generate_plots(output: Path, rows: list[dict[str, Any]]) -> list[str]:
    plt = ensure_matplotlib()
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    labels = [str(row["agent"]) for row in rows]

    def bar(
        name: str,
        values: list[float],
        ylabel: str,
        *,
        percent: bool = False,
    ) -> None:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        ax.bar(range(len(labels)), values)
        ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        for index, value in enumerate(values):
            text = f"{value:.1%}" if percent else f"{value:.3f}"
            ax.text(index, value, text, ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        path = plot_dir / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    bar("mean_decision_time", [float(row["mean_time_sec"]) for row in rows], "Seconds")
    bar("mean_nodes", [float(row["mean_nodes"]) for row in rows], "Nodes")
    bar("timeout_rate", [float(row["timeout_rate"]) for row in rows], "Timeout rate", percent=True)
    bar(
        "root_completion_rate",
        [float(row["mean_root_completion_rate"]) for row in rows],
        "Root completion rate",
        percent=True,
    )
    return created


def write_report(
    output: Path,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    plots: list[str],
) -> Path:
    lines = [
        "# D10000 ハイブリッド探索・固定局面比較",
        "",
        "同一の保存局面、固定深度、同一時間制限で既存手法と3ハイブリッドを比較した。",
        "",
        f"- 深度: {config['depth']}",
        f"- AlphaBeta/PVS候補上限: {config['branch_limit']}",
        f"- Beam幅: {config['beam_widths']}",
        f"- 1手制限: {config['time_limit_sec']}秒",
        "",
        "| agent | mean sec | p95 sec | timeout | nodes | root complete | cutoff | beam pruned | research | graph order sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['agent']} | {row['mean_time_sec']:.4f} | "
            f"{row['p95_time_sec']:.4f} | {row['timeout_rate']:.1%} | "
            f"{row['mean_nodes']:.1f} | {row['mean_root_completion_rate']:.1%} | "
            f"{row['mean_cutoff_count']:.1f} | "
            f"{row['mean_beam_pruned_move_count']:.1f} | "
            f"{row['overall_research_rate']:.1%} | "
            f"{row['mean_graph_ordering_time_sec']:.4f} |"
        )
    lines.extend(["", "## 図", ""])
    lines.extend(f"- `{path}`" for path in plots)
    report = output / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    positions_path = args.positions.resolve()
    positions = load_positions(positions_path)
    config = {
        "format_version": FORMAT_VERSION,
        "positions": str(positions_path),
        "positions_hash": stable_hash(
            json.loads(positions_path.read_text(encoding="utf-8"))
        ),
        "agents": list(args.agents),
        "depth": args.depth,
        "branch_limit": args.branch_limit,
        "beam_widths": list(args.beam_widths),
        "time_limit_sec": args.time_limit_sec,
    }
    fingerprint = source_fingerprint()
    run_hash = stable_hash(
        {
            "config": config,
            "commit_id": git_commit(),
            "source_fingerprint": fingerprint,
        }
    )[:12]
    output = (
        args.resume_run.resolve()
        if args.resume_run
        else args.output_root.resolve() / run_hash
    )
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"benchmark is already running: {output}") from exc
    manifest_path = output / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stable_hash(manifest["config"]) != stable_hash(config):
            raise ValueError("resume configuration does not match")
    else:
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "commit_id": git_commit(),
            "source_fingerprint": fingerprint,
            "config": config,
        }
    write_json(manifest_path, manifest)
    configs = build_configs(
        list(args.agents),
        args.depth,
        args.branch_limit,
        args.beam_widths,
    )
    runs = run_benchmark(positions, configs, output, args.time_limit_sec)
    summaries = extended_summaries(runs)
    write_json(output / "summary.json", summaries)
    write_csv(output / "summary.csv", summaries)
    plots = generate_plots(output, summaries)
    report = write_report(output, config, summaries, plots)
    write_json(
        output / "completion.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "run_count": len(runs),
            "plot_count": len(plots),
            "report": str(report),
        },
    )
    print(output)


if __name__ == "__main__":
    main()
