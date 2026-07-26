"""Compare unrestricted AlphaBeta with top-k selective AlphaBeta."""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agents import AlphaBetaAgent, FullAlphaBetaAgent
from match import simulate_runtime_match
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
from runtime_dictionary import RuntimeDictionary
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/full_alpha_beta_comparison"
FORMAT_VERSION = "full_alpha_beta_comparison_v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--positions",
        type=Path,
        required=True,
        help="fixed_positions.json created by run_search_parameter_tuning.py",
    )
    parser.add_argument(
        "--stage",
        choices=("benchmark", "matches", "all"),
        default="benchmark",
    )
    parser.add_argument("--depths", nargs="+", type=int, default=[3, 4, 5])
    parser.add_argument("--branch-limits", nargs="+", type=int, default=[8, 12, 16])
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--resume-run", type=Path)
    parser.add_argument("--match-depth", type=int, default=4)
    parser.add_argument("--match-branch-limit", type=int, default=8)
    parser.add_argument("--match-seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--match-limit", type=int)
    parser.add_argument("--max-moves", type=int, default=3000)
    parser.add_argument("--max-match-time-sec", type=float, default=600.0)
    args = parser.parse_args(argv)
    if (
        not args.depths
        or any(depth <= 0 for depth in args.depths)
        or not args.branch_limits
        or any(limit <= 0 for limit in args.branch_limits)
        or args.time_limit_sec <= 0
        or args.match_depth <= 0
        or args.match_branch_limit <= 0
        or any(seed < 0 for seed in args.match_seeds)
        or (args.match_limit is not None and args.match_limit <= 0)
        or args.max_moves <= 0
        or args.max_match_time_sec <= 0
    ):
        parser.error("depths, limits, seeds, move counts, and time limits must be valid")
    return args


def build_configs(
    depths: Iterable[int],
    branch_limits: Iterable[int],
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for depth in sorted(set(depths)):
        configs.append(
            {
                "config_id": f"full_alpha_beta_d{depth}",
                "agent": "full_alpha_beta",
                "depth": depth,
                "branch_limit": None,
            }
        )
        configs.extend(
            {
                "config_id": f"selective_alpha_beta_d{depth}_b{limit}",
                "agent": "selective_alpha_beta",
                "depth": depth,
                "branch_limit": limit,
            }
            for limit in sorted(set(branch_limits))
        )
    return configs


def build_comparison_agent(
    config: dict[str, Any],
    time_limit_sec: float,
):
    common = {
        "time_limit_sec": time_limit_sec,
        "depth": int(config["depth"]),
        "adaptive_depth": False,
    }
    if config["agent"] == "full_alpha_beta":
        return FullAlphaBetaAgent(**common)
    return AlphaBetaAgent(
        **common,
        branch_limit=int(config["branch_limit"]),
    )


def load_positions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"positions file not found: {path}")
    positions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(positions, list) or not positions:
        raise ValueError("positions file must contain a non-empty JSON array")
    required = {
        "position_id",
        "runtime",
        "seed",
        "split",
        "turn",
        "edge_history",
        "remaining_word_count",
        "legal_edge_count",
        "risk_level",
        "category",
    }
    seen: set[str] = set()
    for position in positions:
        missing = sorted(required - set(position))
        if missing:
            raise ValueError(
                f"position is missing fields {missing}: {position.get('position_id', '?')}"
            )
        position_id = str(position["position_id"])
        if position_id in seen:
            raise ValueError(f"duplicate position_id: {position_id}")
        seen.add(position_id)
        if not Path(position["runtime"]).is_file():
            raise FileNotFoundError(
                f"position runtime not found: {position['runtime']}"
            )
    return sorted(
        positions,
        key=lambda row: (int(row["seed"]), int(row["turn"]), str(row["position_id"])),
    )


def run_benchmark(
    positions: list[dict[str, Any]],
    configs: list[dict[str, Any]],
    output: Path,
    time_limit_sec: float,
) -> list[dict[str, Any]]:
    path = output / "benchmark/runs.jsonl"
    rows = read_jsonl(path)
    completed = {(row["config_id"], row["position_id"]) for row in rows}
    expected = len(configs) * len(positions)
    done = len(completed)
    for config in configs:
        for position in positions:
            key = (config["config_id"], position["position_id"])
            if key in completed:
                continue
            _runtime, state = restore_position(position)
            decision = build_comparison_agent(config, time_limit_sec).choose_edge(state)
            state.assert_aggregates_consistent()
            row = decision_row(
                config,
                position,
                decision,
                profile_name="fixed",
            )
            append_jsonl(path, row)
            rows.append(row)
            completed.add(key)
            done += 1
            print(
                f"[benchmark {done}/{expected}] {config['config_id']} "
                f"{position['position_id']}: {decision.elapsed_time_sec:.4f}s"
                + (" timeout" if decision.timed_out else "")
            )
    rows.sort(key=lambda row: (row["config_id"], row["position_id"]))
    write_csv(output / "benchmark/runs.csv", rows)
    summaries = summarize_runs(rows)
    write_json(output / "benchmark/summary.json", summaries)
    write_csv(output / "benchmark/summary.csv", summaries)
    return rows


def comparison_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    full = {
        (int(row["depth"]), str(row["position_id"])): row
        for row in rows
        if row["agent"] == "full_alpha_beta"
    }
    comparisons: list[dict[str, Any]] = []
    for row in rows:
        if row["agent"] != "selective_alpha_beta":
            continue
        reference = full[(int(row["depth"]), str(row["position_id"]))]
        full_complete = (
            not bool(reference["timed_out"])
            and int(reference["completed_root_moves"])
            == int(reference["selected_root_candidate_count"])
        )
        selective_complete = (
            not bool(row["timed_out"])
            and int(row["completed_root_moves"])
            == int(row["selected_root_candidate_count"])
        )
        comparable = full_complete and selective_complete
        full_time = float(reference["elapsed_time_sec"])
        selective_time = float(row["elapsed_time_sec"])
        full_nodes = int(reference["nodes_searched"])
        selective_nodes = int(row["nodes_searched"])
        comparisons.append(
            {
                "position_id": row["position_id"],
                "seed": row["seed"],
                "split": row["split"],
                "category": row["category"],
                "turn": row["turn"],
                "depth": row["depth"],
                "branch_limit": row["branch_limit"],
                "full_config_id": reference["config_id"],
                "selective_config_id": row["config_id"],
                "full_complete": full_complete,
                "selective_complete": selective_complete,
                "comparable": comparable,
                "full_selected_edge": reference["selected_edge"],
                "selective_selected_edge": row["selected_edge"],
                "move_agreement": (
                    reference["selected_edge"] == row["selected_edge"]
                    if comparable
                    else ""
                ),
                "score_agreement": (
                    math.isclose(
                        float(reference["score"]),
                        float(row["score"]),
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )
                    if comparable
                    else ""
                ),
                "full_score": reference["score"],
                "selective_score": row["score"],
                "full_time_sec": full_time,
                "selective_time_sec": selective_time,
                "selective_speedup": (
                    full_time / selective_time if selective_time > 0 else math.inf
                ),
                "full_nodes": full_nodes,
                "selective_nodes": selective_nodes,
                "selective_node_ratio": (
                    selective_nodes / full_nodes if full_nodes > 0 else 0.0
                ),
                "full_root_candidates": reference["root_candidate_count"],
                "selective_root_candidates": row["selected_root_candidate_count"],
                "full_root_completion_rate": reference["root_completion_rate"],
                "selective_root_completion_rate": row["root_completion_rate"],
                "full_timed_out": reference["timed_out"],
                "selective_timed_out": row["timed_out"],
            }
        )
    return sorted(
        comparisons,
        key=lambda row: (
            int(row["depth"]),
            int(row["branch_limit"]),
            str(row["position_id"]),
        ),
    )


def summarize_comparisons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (int(row["depth"]), int(row["branch_limit"])),
            [],
        ).append(row)
    summaries: list[dict[str, Any]] = []
    for (depth, branch_limit), values in sorted(groups.items()):
        comparable = [row for row in values if bool(row["comparable"])]
        summaries.append(
            {
                "depth": depth,
                "branch_limit": branch_limit,
                "position_count": len(values),
                "full_complete_count": sum(
                    bool(row["full_complete"]) for row in values
                ),
                "full_complete_rate": statistics.fmean(
                    bool(row["full_complete"]) for row in values
                ),
                "selective_complete_count": sum(
                    bool(row["selective_complete"]) for row in values
                ),
                "selective_complete_rate": statistics.fmean(
                    bool(row["selective_complete"]) for row in values
                ),
                "comparable_count": len(comparable),
                "move_agreement_rate": (
                    statistics.fmean(bool(row["move_agreement"]) for row in comparable)
                    if comparable
                    else 0.0
                ),
                "score_agreement_rate": (
                    statistics.fmean(bool(row["score_agreement"]) for row in comparable)
                    if comparable
                    else 0.0
                ),
                "full_mean_time_sec": statistics.fmean(
                    float(row["full_time_sec"]) for row in values
                ),
                "selective_mean_time_sec": statistics.fmean(
                    float(row["selective_time_sec"]) for row in values
                ),
                "mean_selective_speedup": statistics.fmean(
                    float(row["selective_speedup"]) for row in values
                ),
                "full_mean_nodes": statistics.fmean(
                    int(row["full_nodes"]) for row in values
                ),
                "selective_mean_nodes": statistics.fmean(
                    int(row["selective_nodes"]) for row in values
                ),
                "mean_selective_node_ratio": statistics.fmean(
                    float(row["selective_node_ratio"]) for row in values
                ),
            }
        )
    return summaries


def runtime_by_seed(positions: list[dict[str, Any]]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for position in positions:
        seed = int(position["seed"])
        runtime = Path(position["runtime"])
        previous = result.get(seed)
        if previous is not None and previous.resolve() != runtime.resolve():
            raise ValueError(f"seed {seed} refers to multiple runtimes")
        result[seed] = runtime
    return result


def run_matches(
    positions: list[dict[str, Any]],
    output: Path,
    *,
    depth: int,
    branch_limit: int,
    seeds: set[int],
    match_limit: int | None,
    time_limit_sec: float,
    max_moves: int,
    max_match_time_sec: float,
) -> list[dict[str, Any]]:
    runtimes = runtime_by_seed(positions)
    missing = sorted(seeds - set(runtimes))
    if missing:
        raise ValueError("match seeds missing from positions: " + ", ".join(map(str, missing)))
    jobs: list[tuple[int, str, str]] = []
    for seed in sorted(seeds):
        jobs.extend(
            (
                (seed, "full_alpha_beta", "selective_alpha_beta"),
                (seed, "selective_alpha_beta", "full_alpha_beta"),
            )
        )
    path = output / "matches/results.jsonl"
    rows = read_jsonl(path)
    completed = {str(row["match_id"]) for row in rows}
    new_count = 0
    for seed, first_target, second_target in jobs:
        match_id = (
            f"seed{seed}_d{depth}_b{branch_limit}_"
            f"{first_target}_vs_{second_target}"
        )
        if match_id in completed:
            continue
        if match_limit is not None and new_count >= match_limit:
            break
        runtime_path = runtimes[seed]
        runtime = RuntimeDictionary.load(runtime_path)

        def agent(target: str):
            if target == "full_alpha_beta":
                return FullAlphaBetaAgent(
                    time_limit_sec=time_limit_sec,
                    depth=depth,
                    adaptive_depth=False,
                )
            return AlphaBetaAgent(
                time_limit_sec=time_limit_sec,
                depth=depth,
                branch_limit=branch_limit,
                adaptive_depth=False,
            )

        result = simulate_runtime_match(
            runtime,
            agent(first_target),
            agent(second_target),
            max_moves=min(max_moves, runtime.word_count),
            max_match_time_sec=max_match_time_sec,
            match_id=match_id,
        )
        row = {
            **asdict(result),
            "match_id": match_id,
            "seed": seed,
            "runtime": str(runtime_path.resolve()),
            "depth": depth,
            "branch_limit": branch_limit,
            "first_target": first_target,
            "second_target": second_target,
        }
        append_jsonl(path, row)
        rows.append(row)
        completed.add(match_id)
        new_count += 1
        print(
            f"[match {len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns"
        )
    rows.sort(key=lambda row: str(row["match_id"]))
    write_csv(
        output / "matches/results.csv",
        [{key: value for key, value in row.items() if key != "history"} for row in rows],
    )
    return rows


def summarize_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = ("full_alpha_beta", "selective_alpha_beta")
    summaries: list[dict[str, Any]] = []
    for target in targets:
        games = 0
        wins = 0
        losses = 0
        draws = 0
        decision_times: list[float] = []
        timeouts = 0
        for row in rows:
            if row["first_target"] == target:
                seat = "first"
                decision_times.append(float(row["first_avg_time_sec"]))
                timeouts += int(row["first_timeout_count"])
            elif row["second_target"] == target:
                seat = "second"
                decision_times.append(float(row["second_avg_time_sec"]))
                timeouts += int(row["second_timeout_count"])
            else:
                continue
            games += 1
            if row["winner"] == seat:
                wins += 1
            elif row["winner"] == "draw":
                draws += 1
            else:
                losses += 1
        summaries.append(
            {
                "target": target,
                "games": games,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": wins / games if games else 0.0,
                "mean_decision_time_sec": (
                    statistics.fmean(decision_times) if decision_times else 0.0
                ),
                "timeout_count": timeouts,
            }
        )
    return summaries


def add_value_labels(ax, values: list[float], *, percent: bool = False) -> None:
    for index, value in enumerate(values):
        label = f"{value:.1%}" if percent else f"{value:.3f}"
        ax.text(index, value, label, ha="center", va="bottom", fontsize=8)


def generate_plots(
    output: Path,
    benchmark_summary: list[dict[str, Any]],
    comparison_summary: list[dict[str, Any]],
    match_summary: list[dict[str, Any]],
) -> list[str]:
    plt = ensure_matplotlib()
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def bar(
        filename: str,
        labels: list[str],
        values: list[float],
        ylabel: str,
        *,
        percent: bool = False,
    ) -> None:
        fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.85), 5))
        ax.bar(range(len(labels)), values)
        ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        add_value_labels(ax, values, percent=percent)
        fig.tight_layout()
        path = plot_dir / f"{filename}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    labels = [str(row["config_id"]) for row in benchmark_summary]
    bar(
        "mean_decision_time",
        labels,
        [float(row["mean_time_sec"]) for row in benchmark_summary],
        "Mean seconds",
    )
    bar(
        "mean_nodes",
        labels,
        [float(row["mean_nodes"]) for row in benchmark_summary],
        "Mean searched nodes",
    )
    comparison_labels = [
        f"D{row['depth']} B{row['branch_limit']}" for row in comparison_summary
    ]
    bar(
        "full_completion_rate",
        comparison_labels,
        [float(row["full_complete_rate"]) for row in comparison_summary],
        "Full AlphaBeta completion rate",
        percent=True,
    )
    bar(
        "move_agreement_rate",
        comparison_labels,
        [float(row["move_agreement_rate"]) for row in comparison_summary],
        "Move agreement on completed pairs",
        percent=True,
    )
    if match_summary and any(int(row["games"]) for row in match_summary):
        bar(
            "match_win_rate",
            [str(row["target"]) for row in match_summary],
            [float(row["win_rate"]) for row in match_summary],
            "Win rate",
            percent=True,
        )
    return created


def write_report(
    output: Path,
    manifest: dict[str, Any],
    benchmark_summary: list[dict[str, Any]],
    comparison_summary: list[dict[str, Any]],
    match_summary: list[dict[str, Any]],
    plots: list[str],
) -> Path:
    lines = [
        "# Full AlphaBetaとSelective AlphaBetaの比較",
        "",
        "Full AlphaBetaは各plyの全合法辺を対象にし、Selective AlphaBetaは評価上位だけを対象にする。どちらも固定深度で、評価関数とAlphaBeta枝刈りは共通である。",
        "",
        f"- 1手制限: {manifest['config']['time_limit_sec']}秒",
        f"- 局面ファイル: `{manifest['config']['positions']}`",
        "",
        "## 固定局面ベンチマーク",
        "",
        "| config | depth | branch | mean sec | p95 sec | timeout | mean nodes | root completion |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in benchmark_summary:
        lines.append(
            f"| {row['config_id']} | {row['depth']} | "
            f"{row['branch_limit'] if row['branch_limit'] is not None else 'all'} | "
            f"{row['mean_time_sec']:.4f} | {row['p95_time_sec']:.4f} | "
            f"{row['timeout_rate']:.1%} | {row['mean_nodes']:.1f} | "
            f"{row['mean_root_completion_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Fullとの一致",
            "",
            "Fullが制限時間内にルート全候補を完了した局面だけを、手と評価値の参照比較に使用する。",
            "",
            "| depth | branch | Full完了 | 比較可能 | 手一致 | 評価一致 | Selective速度倍率 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in comparison_summary:
        lines.append(
            f"| {row['depth']} | {row['branch_limit']} | "
            f"{row['full_complete_count']}/{row['position_count']} | "
            f"{row['comparable_count']} | {row['move_agreement_rate']:.1%} | "
            f"{row['score_agreement_rate']:.1%} | "
            f"{row['mean_selective_speedup']:.2f}x |"
        )
    if match_summary and any(int(row["games"]) for row in match_summary):
        lines.extend(
            [
                "",
                "## 対局",
                "",
                "| agent | games | wins | losses | draws | win rate | mean sec | timeout |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in match_summary:
            lines.append(
                f"| {row['target']} | {row['games']} | {row['wins']} | "
                f"{row['losses']} | {row['draws']} | {row['win_rate']:.1%} | "
                f"{row['mean_decision_time_sec']:.4f} | {row['timeout_count']} |"
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
        "positions_sha256": stable_hash(
            json.loads(positions_path.read_text(encoding="utf-8"))
        ),
        "depths": sorted(set(args.depths)),
        "branch_limits": sorted(set(args.branch_limits)),
        "time_limit_sec": args.time_limit_sec,
        "match_depth": args.match_depth,
        "match_branch_limit": args.match_branch_limit,
        "max_moves": args.max_moves,
        "max_match_time_sec": args.max_match_time_sec,
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
        if args.resume_run is not None
        else args.output_root.resolve() / run_hash
    )
    output.mkdir(parents=True, exist_ok=True)
    lock_handle = (output / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"comparison is already running: {output}") from exc

    manifest_path = output / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stable_hash(manifest.get("config")) != stable_hash(config):
            raise ValueError("resume run configuration does not match current CLI settings")
        manifest["last_resumed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["latest_source_fingerprint"] = fingerprint
    else:
        manifest = {
            "format_version": FORMAT_VERSION,
            "run_hash": run_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "commit_id": git_commit(),
            "source_fingerprint": fingerprint,
            "config": config,
        }
    write_json(manifest_path, manifest)

    configs = build_configs(args.depths, args.branch_limits)
    benchmark_rows = run_benchmark(
        positions,
        configs,
        output,
        args.time_limit_sec,
    )
    benchmark_summary = summarize_runs(benchmark_rows)
    comparisons = comparison_rows(benchmark_rows)
    comparison_summary = summarize_comparisons(comparisons)
    write_csv(output / "comparison/details.csv", comparisons)
    write_json(output / "comparison/details.json", comparisons)
    write_csv(output / "comparison/summary.csv", comparison_summary)
    write_json(output / "comparison/summary.json", comparison_summary)

    match_rows: list[dict[str, Any]] = []
    if args.stage in {"matches", "all"}:
        match_rows = run_matches(
            positions,
            output,
            depth=args.match_depth,
            branch_limit=args.match_branch_limit,
            seeds=set(args.match_seeds),
            match_limit=args.match_limit,
            time_limit_sec=args.time_limit_sec,
            max_moves=args.max_moves,
            max_match_time_sec=args.max_match_time_sec,
        )
    else:
        match_rows = read_jsonl(output / "matches/results.jsonl")
    match_summary = summarize_matches(match_rows)
    write_csv(output / "matches/summary.csv", match_summary)
    write_json(output / "matches/summary.json", match_summary)
    plots = generate_plots(
        output,
        benchmark_summary,
        comparison_summary,
        match_summary,
    )
    report = write_report(
        output,
        manifest,
        benchmark_summary,
        comparison_summary,
        match_summary,
        plots,
    )
    write_json(
        output / "completion.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "stage": args.stage,
            "benchmark_run_count": len(benchmark_rows),
            "comparison_count": len(comparisons),
            "match_count": len(match_rows),
            "plot_count": len(plots),
            "report": str(report),
        },
    )
    print(output)


if __name__ == "__main__":
    main()
