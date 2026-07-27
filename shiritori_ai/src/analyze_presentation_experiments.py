"""Analyze presentation experiments and create slide-ready Japanese figures."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

from run_graph_control_comparison import (
    read_jsonl,
    source_fingerprint,
    write_csv,
)
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAME_DEPTH_SUMMARY = (
    PROJECT_ROOT
    / "results/hybrid_agent_comparison/benchmark/821264dd868d/summary.json"
)
BEAM_FOLLOWUP_SUMMARY = (
    PROJECT_ROOT
    / "results/beam_hybrid_followup/D10000/c86fc7661da6/"
    "analysis/variant_summary.json"
)
MINIMAL_HYBRID_SUMMARY = (
    PROJECT_ROOT
    / "results/minimal_adaptive_hybrid/D10000/benchmark_summary.json"
)
MINIMAL_HYBRID_PREPARE = (
    PROJECT_ROOT
    / "results/minimal_adaptive_hybrid/D10000/prepare_summary.json"
)
AGENT_LABELS = {
    "random": "Random",
    "monte_carlo": "Monte Carlo",
    "greedy": "Greedy",
    "minimax": "Minimax",
    "full_alpha_beta": "Full AlphaBeta",
    "selective_alpha_beta": "Selective AlphaBeta",
    "alpha_beta": "Selective AlphaBeta",
    "pvs": "PVS",
    "beam_negamax": "Beam",
    "beam_alpha_beta": "Beam AlphaBeta",
    "beam_pvs": "Beam PVS",
}
AGENT_COLORS = {
    "random": "#808080",
    "monte_carlo": "#8e44ad",
    "greedy": "#d4ac0d",
    "minimax": "#3498db",
    "full_alpha_beta": "#85c1e9",
    "selective_alpha_beta": "#1f4e79",
    "alpha_beta": "#1f4e79",
    "pvs": "#27ae60",
    "beam_negamax": "#b7950b",
    "beam_alpha_beta": "#c0392b",
    "beam_pvs": "#e67e22",
}


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"required analysis input not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def wilson_interval(
    wins: int, games: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    if games <= 0:
        return 0.0, 0.0
    rate = wins / games
    denominator = 1.0 + z * z / games
    center = (rate + z * z / (2.0 * games)) / denominator
    margin = (
        z
        * math.sqrt(
            rate * (1.0 - rate) / games + z * z / (4.0 * games * games)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def side_for_agent(row: dict[str, Any], agent: str) -> str | None:
    if row["first_target"] == agent:
        return "first"
    if row["second_target"] == agent:
        return "second"
    return None


def summarize_matches(
    rows: list[dict[str, Any]],
    agents: Iterable[str],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for agent in agents:
        games = wins = losses = draws = 0
        first_games = first_wins = second_games = second_wins = 0
        times: list[float] = []
        max_times: list[float] = []
        nodes = depths = 0.0
        decision_count = internal_timeouts = depth_changes = 0
        cutoffs = beam_pruned = null_windows = researches = 0.0
        for row in rows:
            side = side_for_agent(row, agent)
            if side is None:
                continue
            games += 1
            if side == "first":
                first_games += 1
            else:
                second_games += 1
            if row["winner"] == side:
                wins += 1
                if side == "first":
                    first_wins += 1
                else:
                    second_wins += 1
            elif row["winner"] == "draw":
                draws += 1
            else:
                losses += 1
            times.append(float(row[f"{side}_avg_time_sec"]))
            max_times.append(float(row[f"{side}_max_time_sec"]))
            nodes += float(row.get(f"{side}_nodes_searched", 0) or 0)
            cutoffs += float(row.get(f"{side}_cutoff_count", 0) or 0)
            beam_pruned += float(
                row.get(f"{side}_beam_pruned_move_count", 0) or 0
            )
            null_windows += float(
                row.get(f"{side}_null_window_search_count", 0) or 0
            )
            researches += float(
                row.get(f"{side}_research_count", 0) or 0
            )
            depth_changes += int(
                row.get(f"{side}_depth_change_count", 0) or 0
            )
            internal_timeouts += int(row[f"{side}_timeout_count"])
            side_turns = [
                turn
                for turn in row["history"]
                if turn["player"] == side
            ]
            decision_count += len(side_turns)
            depth_values = [
                float(turn["effective_depth"])
                for turn in side_turns
                if turn.get("effective_depth") not in ("", None)
            ]
            depths += sum(depth_values)
        low, high = wilson_interval(wins, games)
        summaries.append(
            {
                "agent": agent,
                "label": AGENT_LABELS[agent],
                "games": games,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": wins / games if games else 0.0,
                "wilson_low": low,
                "wilson_high": high,
                "first_games": first_games,
                "first_wins": first_wins,
                "first_win_rate": (
                    first_wins / first_games if first_games else 0.0
                ),
                "second_games": second_games,
                "second_wins": second_wins,
                "second_win_rate": (
                    second_wins / second_games if second_games else 0.0
                ),
                "mean_decision_time_sec": (
                    statistics.fmean(times) if times else 0.0
                ),
                "maximum_decision_time_sec": max(max_times, default=0.0),
                "nodes_searched": nodes,
                "mean_nodes_per_decision": (
                    nodes / decision_count if decision_count else 0.0
                ),
                "decision_count": decision_count,
                "mean_effective_depth": (
                    depths / decision_count if decision_count else 0.0
                ),
                "internal_timeout_count": internal_timeouts,
                "depth_change_count": depth_changes,
                "cutoff_count": cutoffs,
                "beam_pruned_move_count": beam_pruned,
                "null_window_search_count": null_windows,
                "research_count": researches,
                "research_rate": (
                    researches / null_windows if null_windows else 0.0
                ),
            }
        )
    return summaries


def pairwise_rows(
    rows: list[dict[str, Any]],
    agents: Iterable[str],
    stage: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    selected = tuple(agents)
    for agent in selected:
        for opponent in selected:
            if agent == opponent:
                continue
            games = wins = losses = draws = 0
            for row in rows:
                if {row["first_target"], row["second_target"]} != {
                    agent,
                    opponent,
                }:
                    continue
                side = side_for_agent(row, agent)
                assert side is not None
                games += 1
                if row["winner"] == side:
                    wins += 1
                elif row["winner"] == "draw":
                    draws += 1
                else:
                    losses += 1
            result.append(
                {
                    "stage": stage,
                    "agent": agent,
                    "opponent": opponent,
                    "games": games,
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "win_rate": wins / games if games else 0.0,
                }
            )
    return result


def validate_match_rows(
    rows: list[dict[str, Any]],
    expected_count: int,
    agents: Iterable[str],
    seeds: Iterable[int],
) -> dict[str, Any]:
    ids = [str(row["match_id"]) for row in rows]
    paired_missing = []
    for seed in seeds:
        for first, second in ((a, b) for a in agents for b in agents if a < b):
            forward = any(
                int(row["dictionary_seed"]) == int(seed)
                and row["first_target"] == first
                and row["second_target"] == second
                for row in rows
            )
            reverse = any(
                int(row["dictionary_seed"]) == int(seed)
                and row["first_target"] == second
                and row["second_target"] == first
                for row in rows
            )
            if not (forward and reverse):
                paired_missing.append(f"seed{seed}:{first}<->{second}")
    missing_scalar = sum(
        value is None
        for row in rows
        for key, value in row.items()
        if key != "history"
    )
    return {
        "expected_count": expected_count,
        "actual_count": len(rows),
        "unique_count": len(set(ids)),
        "duplicate_count": len(ids) - len(set(ids)),
        "invalid_move_count": sum(
            row.get("loss_reason") == "invalid_ai_move" for row in rows
        ),
        "match_timeout_count": sum(
            row.get("loss_reason") == "match_timeout" for row in rows
        ),
        "max_moves_count": sum(
            row.get("loss_reason") == "max_moves_reached" for row in rows
        ),
        "internal_timeout_count": sum(
            int(row["first_timeout_count"])
            + int(row["second_timeout_count"])
            for row in rows
        ),
        "missing_scalar_value_count": missing_scalar,
        "missing_seat_pairs": paired_missing,
        "complete": (
            len(rows) == expected_count
            and len(ids) == len(set(ids))
            and not paired_missing
        ),
    }


def fixed_comparison_summary(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    full = {
        (int(row["depth"]), str(row["position_id"])): row
        for row in rows
        if row["agent"] == "full_alpha_beta"
    }
    summaries: list[dict[str, Any]] = []
    for depth in sorted({int(row["depth"]) for row in rows}):
        selective = [
            row
            for row in rows
            if row["agent"] == "selective_alpha_beta"
            and int(row["depth"]) == depth
        ]
        values: list[dict[str, Any]] = []
        for row in selective:
            reference = full[(depth, str(row["position_id"]))]
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
            values.append(
                {
                    "full": reference,
                    "selective": row,
                    "full_complete": full_complete,
                    "selective_complete": selective_complete,
                    "comparable": comparable,
                }
            )
        comparable = [value for value in values if value["comparable"]]
        summaries.append(
            {
                "depth": depth,
                "position_count": len(values),
                "full_complete_count": sum(
                    value["full_complete"] for value in values
                ),
                "full_completion_rate": (
                    statistics.fmean(
                        value["full_complete"] for value in values
                    )
                    if values
                    else 0.0
                ),
                "selective_complete_count": sum(
                    value["selective_complete"] for value in values
                ),
                "selective_completion_rate": (
                    statistics.fmean(
                        value["selective_complete"] for value in values
                    )
                    if values
                    else 0.0
                ),
                "comparable_count": len(comparable),
                "comparable_rate": (
                    len(comparable) / len(values) if values else 0.0
                ),
                "move_agreement_rate": (
                    statistics.fmean(
                        value["full"]["selected_edge"]
                        == value["selective"]["selected_edge"]
                        for value in comparable
                    )
                    if comparable
                    else 0.0
                ),
                "score_agreement_rate": (
                    statistics.fmean(
                        math.isclose(
                            float(value["full"]["score"]),
                            float(value["selective"]["score"]),
                            abs_tol=1e-9,
                            rel_tol=0.0,
                        )
                        for value in comparable
                    )
                    if comparable
                    else 0.0
                ),
                "full_mean_time_sec": statistics.fmean(
                    float(value["full"]["elapsed_time_sec"])
                    for value in values
                ),
                "selective_mean_time_sec": statistics.fmean(
                    float(value["selective"]["elapsed_time_sec"])
                    for value in values
                ),
                "full_mean_nodes": statistics.fmean(
                    int(value["full"]["nodes_searched"])
                    for value in values
                ),
                "selective_mean_nodes": statistics.fmean(
                    int(value["selective"]["nodes_searched"])
                    for value in values
                ),
            }
        )
    eligible = [
        row for row in summaries if row["full_completion_rate"] >= 0.8
    ]
    representative = (
        max(eligible, key=lambda row: int(row["depth"]))["depth"]
        if eligible
        else max(
            summaries,
            key=lambda row: (
                float(row["full_completion_rate"]),
                -int(row["depth"]),
            ),
        )["depth"]
    )
    return summaries, int(representative)


def _configure_plotting():
    plt = ensure_matplotlib()
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Hiragino Sans",
                "Yu Gothic",
                "Noto Sans CJK JP",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "figure.figsize": (12.8, 7.2),
            "figure.dpi": 120,
            "savefig.dpi": 220,
        }
    )
    return plt


def _label_bars(
    ax,
    bars,
    values: Iterable[float],
    *,
    percent: bool = False,
    suffix: str = "",
) -> None:
    for bar, value in zip(bars, values):
        label = f"{value:.1%}" if percent else f"{value:,.2f}{suffix}"
        ax.annotate(
            label,
            (
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
            ),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
        )


def _save(plt, fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def graph_win_rate(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
    title: str,
) -> None:
    labels = [row["label"] for row in rows]
    rates = [float(row["win_rate"]) for row in rows]
    errors = [
        [
            rate - float(row["wilson_low"]) for rate, row in zip(rates, rows)
        ],
        [
            float(row["wilson_high"]) - rate for rate, row in zip(rates, rows)
        ],
    ]
    fig, ax = plt.subplots()
    bars = ax.bar(
        labels,
        rates,
        color=[AGENT_COLORS[row["agent"]] for row in rows],
        yerr=errors,
        capsize=5,
    )
    ax.set_title(title)
    ax.set_ylabel("勝率")
    ax.set_ylim(0.0, 1.0)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0%}")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=20)
    _label_bars(ax, bars, rates, percent=True)
    for bar, row in zip(bars, rows):
        short_bar = float(row["win_rate"]) <= 0.12
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.065 if short_bar else 0.025,
            f"n={row['games']}",
            ha="center",
            va="bottom",
            color="black" if short_bar else "white",
            fontsize=9,
            fontweight="bold",
        )
    _save(plt, fig, path)


def graph_two_bars(
    plt,
    path: Path,
    title: str,
    ylabel: str,
    values: list[float],
    *,
    percent: bool = False,
    annotation: str = "",
) -> None:
    agents = ["full_alpha_beta", "selective_alpha_beta"]
    labels = [AGENT_LABELS[agent] for agent in agents]
    fig, ax = plt.subplots()
    bars = ax.bar(
        labels,
        values,
        color=[AGENT_COLORS[agent] for agent in agents],
        width=0.55,
    )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if percent:
        ax.set_ylim(0.0, 1.0)
        ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0%}")
    ax.grid(axis="y", alpha=0.25)
    _label_bars(ax, bars, values, percent=percent)
    if annotation:
        ax.text(
            0.5,
            0.94,
            annotation,
            transform=ax.transAxes,
            ha="center",
            va="top",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
        )
    _save(plt, fig, path)


def generate_figures(
    output: Path,
    initial_summary: list[dict[str, Any]],
    final_summary: list[dict[str, Any]],
    pairwise: list[dict[str, Any]],
    fixed_summary: list[dict[str, Any]],
    representative_depth: int,
    same_depth: list[dict[str, Any]],
    beam_followup: list[dict[str, Any]],
) -> list[str]:
    plt = _configure_plotting()
    figures = output / "analysis/figures"
    figures.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    path = figures / "01_initial_agents_win_rate.png"
    graph_win_rate(plt, initial_summary, path, "初期6AIの総当たり勝率")
    created.append(str(path))

    representative = next(
        row for row in fixed_summary if row["depth"] == representative_depth
    )
    full_time = float(representative["full_mean_time_sec"])
    selective_time = float(representative["selective_mean_time_sec"])
    path = figures / "02_full_selective_time.png"
    graph_two_bars(
        plt,
        path,
        f"固定局面の平均思考時間（深度{representative_depth}）",
        "平均思考時間（秒）",
        [full_time, selective_time],
        annotation=(
            f"Full / Selective = "
            f"{full_time / selective_time:.2f}倍"
            if selective_time
            else ""
        ),
    )
    created.append(str(path))

    full_nodes = float(representative["full_mean_nodes"])
    selective_nodes = float(representative["selective_mean_nodes"])
    reduction = 1.0 - selective_nodes / full_nodes if full_nodes else 0.0
    path = figures / "03_full_selective_nodes.png"
    graph_two_bars(
        plt,
        path,
        f"固定局面の平均探索ノード数（深度{representative_depth}）",
        "平均探索ノード数",
        [full_nodes, selective_nodes],
        annotation=f"Selectiveの削減率 = {reduction:.1%}",
    )
    created.append(str(path))

    quality_values = [
        float(representative["move_agreement_rate"]),
        float(representative["score_agreement_rate"]),
        float(representative["full_completion_rate"]),
    ]
    fig, ax = plt.subplots()
    bars = ax.bar(
        ["選択手一致率", "評価値一致率", "Fullルート完了率"],
        quality_values,
        color=[
            AGENT_COLORS["selective_alpha_beta"],
            "#5b7fa3",
            AGENT_COLORS["full_alpha_beta"],
        ],
    )
    ax.set_title(
        f"FullとSelectiveの探索品質指標（深度{representative_depth}）"
    )
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("割合")
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0%}")
    ax.grid(axis="y", alpha=0.25)
    _label_bars(ax, bars, quality_values, percent=True)
    ax.text(
        0.5,
        0.05,
        f"比較可能局面: {representative['comparable_count']}/"
        f"{representative['position_count']}",
        transform=ax.transAxes,
        ha="center",
        bbox={"boxstyle": "round", "facecolor": "white"},
    )
    path = figures / "04_full_selective_quality.png"
    _save(plt, fig, path)
    created.append(str(path))

    depth_lookup = {row["agent"]: row for row in same_depth}
    selected_agents = ["alpha_beta", "beam_negamax", "beam_alpha_beta"]
    for filename, field, title, ylabel in (
        (
            "05_beam_pruning_time.png",
            "mean_time_sec",
            "同一深度5の平均思考時間",
            "平均思考時間（秒）",
        ),
        (
            "06_beam_pruning_nodes.png",
            "mean_nodes",
            "同一深度5の平均探索ノード数",
            "平均探索ノード数",
        ),
    ):
        values = [
            float(depth_lookup[agent][field]) for agent in selected_agents
        ]
        fig, ax = plt.subplots()
        bars = ax.bar(
            [AGENT_LABELS[agent] for agent in selected_agents],
            values,
            color=[AGENT_COLORS[agent] for agent in selected_agents],
        )
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        _label_bars(ax, bars, values)
        path = figures / filename
        _save(plt, fig, path)
        created.append(str(path))

    variants = [
        row
        for row in beam_followup
        if row["agent"] == "beam_alpha_beta"
    ]
    order = {
        "beam_alpha_beta_baseline": 0,
        "beam_alpha_beta_deep": 1,
        "beam_alpha_beta_wide": 2,
        "beam_alpha_beta_deep_wide": 3,
    }
    variants.sort(key=lambda row: order[row["config_id"]])
    variant_rates = [float(row["hybrid_win_rate"]) for row in variants]
    fig, ax = plt.subplots()
    bars = ax.bar(
        ["baseline", "deep", "wide", "deep_wide"],
        variant_rates,
        color=[AGENT_COLORS["beam_alpha_beta"]] * 4,
    )
    ax.axhline(0.5, color="black", linestyle="--", linewidth=1)
    ax.set_title("Beam AlphaBeta設定別の対AlphaBeta勝率")
    ax.set_ylabel("勝率")
    ax.set_ylim(0.0, 1.0)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0%}")
    ax.grid(axis="y", alpha=0.25)
    _label_bars(ax, bars, variant_rates, percent=True)
    path = figures / "07_beam_depth_width_win_rate.png"
    _save(plt, fig, path)
    created.append(str(path))

    path = figures / "08_unseen_seed_round_robin.png"
    graph_win_rate(
        plt,
        final_summary,
        path,
        "未使用辞書seedにおける最終4手法の総当たり勝率",
    )
    created.append(str(path))

    direct = [
        row
        for row in pairwise
        if row["stage"] == "final4"
        and row["agent"] == "beam_alpha_beta"
    ]
    opponent_order = {
        "selective_alpha_beta": 0,
        "pvs": 1,
        "beam_pvs": 2,
    }
    direct.sort(key=lambda row: opponent_order[row["opponent"]])
    rates = [float(row["win_rate"]) for row in direct]
    fig, ax = plt.subplots()
    bars = ax.bar(
        [f"vs {AGENT_LABELS[row['opponent']]}" for row in direct],
        rates,
        color=AGENT_COLORS["beam_alpha_beta"],
    )
    ax.axhline(0.5, color="black", linestyle="--", linewidth=1)
    ax.set_title("未使用辞書seedにおけるBeam AlphaBetaの直接対戦")
    ax.set_ylabel("Beam AlphaBeta勝率")
    ax.set_ylim(0.0, 1.0)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0%}")
    ax.grid(axis="y", alpha=0.25)
    _label_bars(ax, bars, rates, percent=True)
    for bar, row in zip(bars, direct):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.03,
            f"{row['wins']}勝{row['losses']}敗"
            f"{row['draws']}分 / n={row['games']}",
            ha="center",
            va="bottom",
            color="white" if row["win_rate"] > 0.15 else "black",
            fontsize=9,
        )
    path = figures / "09_unseen_seed_beam_direct.png"
    _save(plt, fig, path)
    created.append(str(path))

    labels = [row["label"] for row in final_summary]
    fig, axes = plt.subplots(2, 1, sharex=True)
    time_values = [
        float(row["mean_decision_time_sec"]) for row in final_summary
    ]
    depth_values = [
        float(row["mean_effective_depth"]) for row in final_summary
    ]
    colors = [AGENT_COLORS[row["agent"]] for row in final_summary]
    top = axes[0].bar(labels, time_values, color=colors)
    axes[0].set_ylabel("平均思考時間（秒）")
    axes[0].set_title("未使用辞書seedにおける探索効率")
    axes[0].grid(axis="y", alpha=0.25)
    _label_bars(axes[0], top, time_values)
    bottom = axes[1].bar(labels, depth_values, color=colors)
    axes[1].set_ylabel("平均実効深度")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].tick_params(axis="x", rotation=20)
    _label_bars(axes[1], bottom, depth_values)
    path = figures / "10_unseen_seed_efficiency.png"
    _save(plt, fig, path)
    created.append(str(path))
    return created


def flatten_summary_rows(
    sections: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    result = []
    for section, rows in sections.items():
        for row in rows:
            result.append({"section": section, **row})
    return result


def write_report(
    output: Path,
    manifest: dict[str, Any],
    validation: dict[str, Any],
    initial_summary: list[dict[str, Any]],
    final_summary: list[dict[str, Any]],
    pairwise: list[dict[str, Any]],
    fixed_summary: list[dict[str, Any]],
    representative_depth: int,
    same_depth: list[dict[str, Any]],
    beam_followup: list[dict[str, Any]],
    exact_summary: dict[str, Any],
    exact_prepare: dict[str, Any],
    figures: list[str],
) -> Path:
    representative = next(
        row for row in fixed_summary if row["depth"] == representative_depth
    )
    beam = next(
        row for row in final_summary if row["agent"] == "beam_alpha_beta"
    )
    direct = [
        row
        for row in pairwise
        if row["stage"] == "final4"
        and row["agent"] == "beam_alpha_beta"
    ]
    proof_rows = [
        row
        for row in exact_summary.get("metrics", [])
        if row["profile"].startswith("proof_")
    ]
    lines = [
        "# 発表用追加実験レポート",
        "",
        "## 条件とデータ分離",
        "",
        f"- Git commit: `{manifest['commit_id']}`",
        f"- source fingerprint: `{manifest['source_fingerprint']}`",
        "- 設定選定seed: 0〜9（探索的結果）",
        "- 未使用確認seed: "
        + ", ".join(map(str, manifest["config"]["confirmation_seeds"])),
        "- D10000、2〜12文字、1手1秒、直列実行",
        "- 未使用seedの結果をseed 0〜9の勝率へ合算していない。",
        "",
        "## 使用設定",
        "",
        "| 手法 | 初期深度 | 最大深度 | 候補上限 / Beam幅 | 適応深度 |",
        "|---|---:|---:|---|---|",
        "| Random | - | - | - | - |",
        "| Monte Carlo | - | - | 候補20・playout 10 | - |",
        "| Greedy | 1 | 1 | - | なし |",
        "| Minimax | 3 | 3 | 8 | なし |",
        "| Full AlphaBeta | 4 | 4 | 全候補 | なし |",
        "| Selective AlphaBeta | 5 | 7 | 8 | あり |",
        "| PVS | 5 | 7 | 8 | あり |",
        "| Beam AlphaBeta | 8 | 9 | 12, 8, 4, 2 | あり |",
        "| Beam PVS | 8 | 9 | 12, 8, 4, 2 | あり |",
        "",
        "適応深度4手法は目標0.6秒、低下閾値0.95、回復閾値0.6、"
        "回復待ち2手で統一した。",
        "",
        "## 自動検査",
        "",
        "```json",
        json.dumps(validation, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 固定局面 Full対Selective",
        "",
        f"代表深度は、Fullのルート完了率80%以上という事前規則により"
        f"深度{representative_depth}とした。選択手一致率では選定していない。",
        "",
        "| 深度 | Full完了 | 比較可能 | 手一致 | 評価一致 | Full秒 | Selective秒 | Full nodes | Selective nodes |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in fixed_summary:
        lines.append(
            f"| {row['depth']} | {row['full_completion_rate']:.1%} | "
            f"{row['comparable_count']}/{row['position_count']} | "
            f"{row['move_agreement_rate']:.1%} | "
            f"{row['score_agreement_rate']:.1%} | "
            f"{row['full_mean_time_sec']:.4f} | "
            f"{row['selective_mean_time_sec']:.4f} | "
            f"{row['full_mean_nodes']:.1f} | "
            f"{row['selective_mean_nodes']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## 未使用seedの最終4手法",
            "",
            "| 手法 | 対局 | 勝-敗-分 | 勝率 | 平均秒 | 平均深度 | 内部timeout |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in final_summary:
        lines.append(
            f"| {row['label']} | {row['games']} | "
            f"{row['wins']}-{row['losses']}-{row['draws']} | "
            f"{row['win_rate']:.1%} | "
            f"{row['mean_decision_time_sec']:.4f} | "
            f"{row['mean_effective_depth']:.2f} | "
            f"{row['internal_timeout_count']} |"
        )
    lines.extend(
        [
            "",
            f"Beam AlphaBetaの総当たり勝率は{beam['win_rate']:.1%}"
            f"（{beam['wins']}勝{beam['losses']}敗{beam['draws']}分、"
            f"n={beam['games']}）だった。",
            "",
            "### Beam AlphaBeta直接対戦",
            "",
        ]
    )
    for row in direct:
        lines.append(
            f"- vs {AGENT_LABELS[row['opponent']]}: "
            f"{row['wins']}勝{row['losses']}敗{row['draws']}分、"
            f"{row['win_rate']:.1%}（n={row['games']}）"
        )
    lines.extend(
        [
            "",
            "## 確認実験からの結論",
            "",
            "- Beam AlphaBetaは平均思考時間"
            f"{beam['mean_decision_time_sec']:.3f}秒、平均実効深度"
            f"{beam['mean_effective_depth']:.2f}で、Selective AlphaBetaより"
            "高速かつ深く探索した。",
            f"- ただし未使用seedの勝率は{beam['win_rate']:.1%}で、"
            "調整seedで観測した勝率優位は再現しなかった。",
            "- Beam AlphaBetaの直接成績はSelective AlphaBetaに7勝13敗、"
            "PVSに7勝13敗、Beam PVSに10勝10敗だった。",
            "- したがって発表では「探索効率の改善」は主張できるが、"
            "「未使用辞書でも最強」は主張できない。",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "## 初期6AI",
            "",
            "| 手法 | 対局 | 勝-敗-分 | 勝率 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in initial_summary:
        lines.append(
            f"| {row['label']} | {row['games']} | "
            f"{row['wins']}-{row['losses']}-{row['draws']} | "
            f"{row['win_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## 既存結果の再利用",
            "",
            "- 同一深度5のAlphaBeta、Beam、Beam AlphaBeta比較は"
            "`results/hybrid_agent_comparison/benchmark/821264dd868d/summary.json`"
            "から読み取った。",
            "- Beamの深度・幅追試は"
            "`results/beam_hybrid_followup/D10000/c86fc7661da6/"
            "analysis/variant_summary.json`から読み取った。",
            "- 盤面適応型の修正前180局は使用していない。",
            "",
            "## 完全解析ハイブリッドの扱い",
            "",
            f"- 完全解析正解データ作成: "
            f"{exact_prepare.get('exact_truth_count', 0)}/"
            f"{exact_prepare.get('exact_truth_attempt_count', 0)}局面完了。",
            f"- proof方式の非自明成功合計: "
            f"{sum(int(row.get('exact_nontrivial_success_count', 0)) for row in proof_rows)}。",
            f"- proof方式による選択変更合計: "
            f"{sum(int(row.get('exact_choice_change_count', 0)) for row in proof_rows)}。",
            "- 非自明局面での改善は確認されていないため、強さが向上したとは"
            "表現しない。",
            "",
            "## グラフ別の読み方",
            "",
        ]
    )
    graph_notes = [
        (
            "01",
            "初期6AI・未使用seed 3個・90局",
            "同一1秒制限下の実用設定の勝率",
            "探索原理だけの因果効果や同一深度の強さ",
            "同じ時間制限の実用設定では、探索手法ごとに成績差が見られた。",
        ),
        (
            "02",
            f"固定50局面・代表深度{representative_depth}",
            "FullとSelectiveの平均時間差",
            "タイムアウト局面を除いた純粋計算量だけの差",
            "候補制限による平均思考時間の変化を示す。",
        ),
        (
            "03",
            f"固定50局面・代表深度{representative_depth}",
            "平均探索ノード数",
            "ノード1個あたりの計算コスト",
            "Selectiveは探索対象を絞ることでノード数を削減した。",
        ),
        (
            "04",
            f"固定50局面・比較可能{representative['comparable_count']}局面",
            "完了局面上の手・評価一致",
            "未完了局面における正解率",
            "品質比較の分母を両方式が完了した局面に限定した。",
        ),
        (
            "05-06",
            "既存同一深度5・14局面",
            "BeamへのAlphaBeta導入前後の時間とノード",
            "対局勝率の改善",
            "枝刈り併用により同一深度の探索量が変化した。",
        ),
        (
            "07",
            "既存seed 0〜9・各設定20局",
            "調整段階の対AlphaBeta勝率",
            "未使用seedへの一般化",
            "深度とルート幅へ計算量を再配分した設定を比較した。",
        ),
        (
            "08-10",
            "未使用seed 10〜19・120局",
            "最終4手法の確認実験",
            "seed 0〜9と合算した母集団勝率",
            "未使用辞書seedで最終設定の再現性を確認した。",
        ),
    ]
    for identifier, source, can_say, cannot_say, slide in graph_notes:
        lines.extend(
            [
                f"### 図{identifier}",
                "",
                f"- 使用データ: {source}",
                f"- 直接言えること: {can_say}",
                f"- 言えないこと: {cannot_say}",
                f"- スライド用一文: {slide}",
                "",
            ]
        )
    lines.extend(["## 生成グラフ", ""])
    lines.extend(f"- `{Path(path).name}`" for path in figures)
    report = output / "analysis/presentation_experiment_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="generate partial summaries while experiments are incomplete",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    output = args.input.resolve()
    manifest = load_json(output / "manifest.json")
    config = manifest["config"]
    final_rows = read_jsonl(output / "final4/raw_matches.jsonl")
    initial_rows = read_jsonl(output / "initial6/raw_matches.jsonl")
    fixed_rows = read_jsonl(
        output / "fixed_comparison/raw_runs.jsonl"
    )
    validation = {
        "final4": validate_match_rows(
            final_rows,
            len(config["confirmation_seeds"])
            * len(config["final_agents"])
            * (len(config["final_agents"]) - 1),
            config["final_agents"],
            config["confirmation_seeds"],
        ),
        "initial6": validate_match_rows(
            initial_rows,
            len(config["initial_comparison_seeds"])
            * len(config["initial_agents"])
            * (len(config["initial_agents"]) - 1),
            config["initial_agents"],
            config["initial_comparison_seeds"],
        ),
        "fixed_comparison": {
            "expected_count": int(
                config["fixed_position_comparison"]["position_count"]
            )
            * 2
            * len(config["fixed_position_comparison"]["depths"]),
            "actual_count": len(fixed_rows),
            "unique_count": len(
                {
                    (row["config_id"], row["position_id"])
                    for row in fixed_rows
                }
            ),
        },
    }
    validation["fixed_comparison"]["duplicate_count"] = (
        validation["fixed_comparison"]["actual_count"]
        - validation["fixed_comparison"]["unique_count"]
    )
    validation["fixed_comparison"]["complete"] = (
        validation["fixed_comparison"]["actual_count"]
        == validation["fixed_comparison"]["expected_count"]
        and validation["fixed_comparison"]["duplicate_count"] == 0
    )
    if not args.allow_partial and not all(
        validation[stage]["complete"]
        for stage in ("final4", "initial6", "fixed_comparison")
    ):
        raise RuntimeError(
            "presentation experiments are incomplete; use --allow-partial "
            "only for diagnostic output"
        )

    final_summary = summarize_matches(
        final_rows, config["final_agents"]
    )
    initial_summary = summarize_matches(
        initial_rows, config["initial_agents"]
    )
    pairwise = pairwise_rows(
        final_rows, config["final_agents"], "final4"
    ) + pairwise_rows(initial_rows, config["initial_agents"], "initial6")
    fixed_summary, representative_depth = fixed_comparison_summary(
        fixed_rows
    )
    same_depth = load_json(SAME_DEPTH_SUMMARY)
    beam_followup = load_json(BEAM_FOLLOWUP_SUMMARY)
    exact_summary = load_json(MINIMAL_HYBRID_SUMMARY)
    exact_prepare = load_json(MINIMAL_HYBRID_PREPARE)

    analysis = output / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    summary = {
        "format_version": "presentation_analysis_v1",
        "run_hash": manifest["run_hash"],
        "analysis_source_fingerprint": source_fingerprint(),
        "validation": validation,
        "representative_depth": representative_depth,
        "initial_agents": initial_summary,
        "unseen_seed_final_agents": final_summary,
        "fixed_comparison": fixed_summary,
        "reused_same_depth_summary": same_depth,
        "reused_beam_followup_summary": beam_followup,
        "exact_hybrid_summary": exact_summary,
        "exact_hybrid_prepare": exact_prepare,
    }
    (analysis / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    write_csv(
        analysis / "summary.csv",
        flatten_summary_rows(
            {
                "initial_agents": initial_summary,
                "unseen_seed_final_agents": final_summary,
                "fixed_comparison": fixed_summary,
            }
        ),
    )
    write_csv(analysis / "pairwise.csv", pairwise)
    figures = generate_figures(
        output,
        initial_summary,
        final_summary,
        pairwise,
        fixed_summary,
        representative_depth,
        same_depth,
        beam_followup,
    )
    report = write_report(
        output,
        manifest,
        validation,
        initial_summary,
        final_summary,
        pairwise,
        fixed_summary,
        representative_depth,
        same_depth,
        beam_followup,
        exact_summary,
        exact_prepare,
        figures,
    )
    print(report)


if __name__ == "__main__":
    main()
