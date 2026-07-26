"""Analyze AlphaBeta matches against Beam hybrid parameter variants."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from run_beam_hybrid_followup import ALPHA_CONFIG_ID
from run_graph_control_comparison import read_jsonl, write_csv
from visualize import ensure_matplotlib


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _turns(
    match: dict[str, Any],
    seat: str,
) -> list[dict[str, Any]]:
    return [
        turn
        for turn in match.get("history", [])
        if turn.get("player") == seat
    ]


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def summarize_variants(
    matches: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        grouped[str(match["hybrid_config_id"])].append(match)
    rows: list[dict[str, Any]] = []
    for config_id in specs:
        values = grouped.get(config_id, [])
        hybrid_times: list[float] = []
        hybrid_nodes: list[float] = []
        hybrid_depths: list[float] = []
        alpha_times: list[float] = []
        alpha_nodes: list[float] = []
        alpha_depths: list[float] = []
        hybrid_timeouts = 0
        alpha_timeouts = 0
        hybrid_depth_changes = 0
        alpha_depth_changes = 0
        hybrid_researches = 0.0
        hybrid_null_searches = 0.0
        hybrid_wins = 0
        alpha_wins = 0
        draws = 0
        hybrid_first_games = 0
        hybrid_first_wins = 0
        hybrid_second_games = 0
        hybrid_second_wins = 0
        for match in values:
            if match["first_config_id"] == config_id:
                hybrid_seat, alpha_seat = "first", "second"
                hybrid_first_games += 1
            else:
                hybrid_seat, alpha_seat = "second", "first"
                hybrid_second_games += 1
            winner = str(match["winner"])
            if winner == hybrid_seat:
                hybrid_wins += 1
                if hybrid_seat == "first":
                    hybrid_first_wins += 1
                else:
                    hybrid_second_wins += 1
            elif winner == alpha_seat:
                alpha_wins += 1
            else:
                draws += 1
            for turn in _turns(match, hybrid_seat):
                hybrid_times.append(float(turn.get("elapsed_time_sec", 0.0)))
                hybrid_nodes.append(float(turn.get("nodes_searched", 0.0)))
                if turn.get("effective_depth") not in ("", None):
                    hybrid_depths.append(float(turn["effective_depth"]))
                hybrid_timeouts += int(bool(turn.get("timed_out")))
                hybrid_depth_changes += int(bool(turn.get("depth_changed")))
                hybrid_researches += float(turn.get("research_count", 0.0))
                hybrid_null_searches += float(
                    turn.get("null_window_search_count", 0.0)
                )
            for turn in _turns(match, alpha_seat):
                alpha_times.append(float(turn.get("elapsed_time_sec", 0.0)))
                alpha_nodes.append(float(turn.get("nodes_searched", 0.0)))
                if turn.get("effective_depth") not in ("", None):
                    alpha_depths.append(float(turn["effective_depth"]))
                alpha_timeouts += int(bool(turn.get("timed_out")))
                alpha_depth_changes += int(bool(turn.get("depth_changed")))
        games = len(values)
        spec = specs[config_id]
        rows.append(
            {
                "config_id": config_id,
                "agent": spec["agent"],
                "initial_depth": spec["initial_depth"],
                "max_depth": spec["max_depth"],
                "beam_widths": "-".join(map(str, spec["beam_widths"])),
                "games": games,
                "hybrid_wins": hybrid_wins,
                "alpha_beta_wins": alpha_wins,
                "draws": draws,
                "hybrid_win_rate": hybrid_wins / games if games else 0.0,
                "hybrid_first_win_rate": (
                    hybrid_first_wins / hybrid_first_games
                    if hybrid_first_games
                    else 0.0
                ),
                "hybrid_second_win_rate": (
                    hybrid_second_wins / hybrid_second_games
                    if hybrid_second_games
                    else 0.0
                ),
                "hybrid_decision_count": len(hybrid_times),
                "hybrid_mean_time_sec": _mean(hybrid_times),
                "hybrid_max_time_sec": max(hybrid_times) if hybrid_times else 0.0,
                "hybrid_mean_nodes": _mean(hybrid_nodes),
                "hybrid_mean_effective_depth": _mean(hybrid_depths),
                "hybrid_timeout_count": hybrid_timeouts,
                "hybrid_timeout_rate": (
                    hybrid_timeouts / len(hybrid_times)
                    if hybrid_times
                    else 0.0
                ),
                "hybrid_depth_change_count": hybrid_depth_changes,
                "hybrid_research_rate": (
                    hybrid_researches / hybrid_null_searches
                    if hybrid_null_searches
                    else 0.0
                ),
                "alpha_beta_decision_count": len(alpha_times),
                "alpha_beta_mean_time_sec": _mean(alpha_times),
                "alpha_beta_mean_nodes": _mean(alpha_nodes),
                "alpha_beta_mean_effective_depth": _mean(alpha_depths),
                "alpha_beta_timeout_count": alpha_timeouts,
                "alpha_beta_timeout_rate": (
                    alpha_timeouts / len(alpha_times)
                    if alpha_times
                    else 0.0
                ),
                "alpha_beta_depth_change_count": alpha_depth_changes,
            }
        )
    return rows


def summarize_by_seed(
    matches: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        grouped[
            (int(match["dictionary_seed"]), str(match["hybrid_config_id"]))
        ].append(match)
    rows: list[dict[str, Any]] = []
    for (seed, config_id), values in sorted(grouped.items()):
        wins = 0
        losses = 0
        draws = 0
        for match in values:
            hybrid_seat = (
                "first"
                if match["first_config_id"] == config_id
                else "second"
            )
            winner = str(match["winner"])
            if winner == hybrid_seat:
                wins += 1
            elif winner == "draw":
                draws += 1
            else:
                losses += 1
        rows.append(
            {
                "dictionary_seed": seed,
                "config_id": config_id,
                "agent": specs[config_id]["agent"],
                "games": len(values),
                "hybrid_wins": wins,
                "alpha_beta_wins": losses,
                "draws": draws,
                "hybrid_win_rate": wins / len(values),
            }
        )
    return rows


def generate_plots(
    output: Path,
    summary: list[dict[str, Any]],
    seed_summary: list[dict[str, Any]],
) -> list[str]:
    plt = ensure_matplotlib()
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    labels = [str(row["config_id"]) for row in summary]
    created: list[str] = []

    def bar(
        name: str,
        values: list[float],
        ylabel: str,
        *,
        percent: bool = False,
        reference: float | None = None,
    ) -> None:
        fig, ax = plt.subplots(figsize=(max(11, len(labels) * 1.35), 6))
        ax.bar(range(len(labels)), values)
        ax.set_xticks(range(len(labels)), labels, rotation=32, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        if reference is not None:
            ax.axhline(reference, color="black", linestyle="--", linewidth=1)
        for index, value in enumerate(values):
            text = f"{value:.1%}" if percent else f"{value:.3f}"
            ax.text(index, value, text, ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        path = plot_dir / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    bar(
        "hybrid_win_rate_vs_alpha_beta",
        [float(row["hybrid_win_rate"]) for row in summary],
        "Hybrid win rate vs AlphaBeta",
        percent=True,
        reference=0.5,
    )
    bar(
        "hybrid_mean_decision_time",
        [float(row["hybrid_mean_time_sec"]) for row in summary],
        "Hybrid mean seconds",
    )
    bar(
        "hybrid_mean_effective_depth",
        [float(row["hybrid_mean_effective_depth"]) for row in summary],
        "Hybrid mean effective depth",
    )
    bar(
        "hybrid_timeout_rate",
        [float(row["hybrid_timeout_rate"]) for row in summary],
        "Hybrid timeout rate",
        percent=True,
    )
    bar(
        "hybrid_mean_nodes",
        [float(row["hybrid_mean_nodes"]) for row in summary],
        "Hybrid nodes per decision",
    )

    seeds = sorted({int(row["dictionary_seed"]) for row in seed_summary})
    seed_values = {
        (int(row["dictionary_seed"]), str(row["config_id"])): float(
            row["hybrid_win_rate"]
        )
        for row in seed_summary
    }
    fig, axes = plt.subplots(
        len(labels),
        1,
        figsize=(12, max(6, len(labels) * 2.6)),
        sharex=True,
    )
    if len(labels) == 1:
        axes = [axes]
    for axis, config_id in zip(axes, labels):
        values = [seed_values.get((seed, config_id), 0.0) for seed in seeds]
        bars = axis.bar(range(len(seeds)), values)
        axis.set_title(config_id)
        axis.set_ylabel("Win rate")
        axis.set_ylim(0.0, 1.12)
        axis.grid(axis="y", alpha=0.25)
        for item, value in zip(bars, values):
            axis.text(
                item.get_x() + item.get_width() / 2,
                value,
                f"{value:.0%}",
                ha="center",
                va="bottom",
                fontsize=7,
            )
    axes[-1].set_xticks(range(len(seeds)), [str(seed) for seed in seeds])
    axes[-1].set_xlabel("Dictionary seed")
    fig.tight_layout()
    path = plot_dir / "hybrid_win_rate_by_dictionary_seed.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))
    return created


def write_report(
    output: Path,
    manifest: dict[str, Any],
    summary: list[dict[str, Any]],
    plots: list[str],
) -> Path:
    config = manifest["config"]
    lines = [
        "# Beamハイブリッド深度・幅追試",
        "",
        "AlphaBetaの採用済み適応設定を基準に、BeamAlphaBetaとBeamPVSの"
        "現行、深度増加、幅増加、深度+幅増加を先後入替で比較した。",
        "",
        f"- 辞書サイズ: D{config['dictionary_size']}",
        f"- 辞書seed: {config['dictionary_seeds']}",
        f"- 1手制限: {config['time_limit_sec']}秒",
        f"- AlphaBeta: 初期深度{config['alpha_beta']['initial_depth']}、"
        f"最大深度{config['alpha_beta']['max_depth']}、"
        f"branch {config['alpha_beta']['branch_limit']}",
        "",
        "## 設定と対局結果",
        "",
        "| config | depth | max | widths | W-L-D | win | first | second | sec | nodes | effective depth | timeout | research |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['config_id']} | {row['initial_depth']} | "
            f"{row['max_depth']} | {row['beam_widths']} | "
            f"{row['hybrid_wins']}-{row['alpha_beta_wins']}-{row['draws']} | "
            f"{row['hybrid_win_rate']:.1%} | "
            f"{row['hybrid_first_win_rate']:.1%} | "
            f"{row['hybrid_second_win_rate']:.1%} | "
            f"{row['hybrid_mean_time_sec']:.4f} | "
            f"{row['hybrid_mean_nodes']:.1f} | "
            f"{row['hybrid_mean_effective_depth']:.2f} | "
            f"{row['hybrid_timeout_rate']:.1%} | "
            f"{row['hybrid_research_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "勝率50%を超えた設定だけが、この実験内でAlphaBetaへ勝ち越した設定である。",
            "差が小さい場合は辞書seed別結果と速度・タイムアウトも合わせて判断する。",
            "",
            "## 図",
            "",
        ]
    )
    lines.extend(f"- `{path}`" for path in plots)
    report = output / "beam_hybrid_followup_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    matches = read_jsonl(args.input / "raw_matches.jsonl")
    if not matches:
        raise FileNotFoundError(f"no raw matches: {args.input}")
    manifest = json.loads(
        (args.input / "manifest.json").read_text(encoding="utf-8")
    )
    specs = manifest["config"]["variants"]
    output = (args.output or args.input / "analysis").resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = summarize_variants(matches, specs)
    seed_summary = summarize_by_seed(matches, specs)
    (output / "variant_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "seed_summary.json").write_text(
        json.dumps(seed_summary, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    write_csv(output / "variant_summary.csv", summary)
    write_csv(output / "seed_summary.csv", seed_summary)
    plots = generate_plots(output, summary, seed_summary)
    report = write_report(output, manifest, summary, plots)
    print(report)


if __name__ == "__main__":
    main()
