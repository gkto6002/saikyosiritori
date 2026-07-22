"""Create report-ready matplotlib figures from experiment CSV files."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path


PREFERRED_AGENT_ORDER = ["random", "greedy", "minimax", "monte_carlo", "alpha_beta"]


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    csv.field_size_limit(sys.maxsize)
    with source.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def to_float(value: str) -> float:
    if value == "":
        return 0.0
    return float(value)


def rows_with_values(rows: list[dict[str, str]], fields: list[str]) -> list[dict[str, str]]:
    return [row for row in rows if all(row.get(field, "") != "" for field in fields)]


def ordered_agent_names(names: set[str] | list[str]) -> list[str]:
    unique_names = set(names)
    preferred = [name for name in PREFERRED_AGENT_ORDER if name in unique_names]
    rest = sorted(name for name in unique_names if name not in PREFERRED_AGENT_ORDER)
    return preferred + rest


def sorted_agent_size_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    agent_order = {agent: index for index, agent in enumerate(PREFERRED_AGENT_ORDER)}
    return sorted(
        rows,
        key=lambda row: (
            agent_order.get(row["agent_name"], len(agent_order)),
            row["agent_name"],
            int(row["dict_size"]),
        ),
    )


def ensure_matplotlib():
    cache_dir = Path(".matplotlib-cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
    try:
        import matplotlib

        matplotlib.use("Agg")
        logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for report figures. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc

    from matplotlib import font_manager

    preferred_font_keywords = (
        "AppleGothic",
        "Hiragino",
        "Yu Gothic",
        "Noto Sans CJK",
        "Noto Sans JP",
        "IPAexGothic",
        "IPAGothic",
        "Apple SD Gothic",
    )
    discovered_fonts: list[str] = []
    for font_path in font_manager.findSystemFonts(fontext="ttf") + font_manager.findSystemFonts(fontext="ttc"):
        try:
            font_name = font_manager.FontProperties(fname=font_path).get_name()
        except RuntimeError:
            continue
        if any(keyword in font_name for keyword in preferred_font_keywords):
            font_manager.fontManager.addfont(font_path)
            discovered_fonts.append(font_name)

    plt.style.use("seaborn-v0_8-whitegrid")
    preferred_family_order = [
        "AppleGothic",
        "Hiragino Sans",
        "Yu Gothic",
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "IPAexGothic",
        "IPAGothic",
        "Apple SD Gothic Neo",
    ]
    unique_discovered = list(dict.fromkeys(discovered_fonts))
    ordered_discovered = [
        font_name for font_name in preferred_family_order if font_name in unique_discovered
    ] + [
        font_name for font_name in unique_discovered if font_name not in preferred_family_order
    ]
    font_families = ordered_discovered + ["DejaVu Sans"]
    plt.rcParams["font.family"] = font_families
    plt.rcParams["font.sans-serif"] = font_families
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def save_exact_line_chart(
    plt,
    rows: list[dict[str, str]],
    value_field: str,
    stdev_field: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    rows = rows_with_values(rows, [value_field, stdev_field])
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    y_values = [to_float(row[value_field]) for row in rows]
    y_errors = [to_float(row[stdev_field]) for row in rows]
    lower_errors = [min(value, error) for value, error in zip(y_values, y_errors)]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        x_values,
        y_values,
        yerr=[lower_errors, y_errors],
        marker="o",
        linewidth=2,
        capsize=4,
        color="#1f77b4",
    )
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size (D)")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_values)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_exact_win_rate(plt, rows: list[dict[str, str]], output_path: Path) -> None:
    rows = rows_with_values(rows, ["first_player_win_rate"])
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    y_values = [to_float(row["first_player_win_rate"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_values, y_values, marker="o", linewidth=2, color="#2ca02c")
    ax.set_ylim(0.0, 1.03)
    ax.set_title("First-player win rate in completed exact analyses", fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size (D)")
    ax.set_ylabel("First-player win rate")
    ax.set_xticks(x_values)
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_exact_completion_chart(plt, rows: list[dict[str, str]], output_path: Path) -> None:
    rows = rows_with_values(rows, ["seed_count", "completed_seed_count"])
    if not rows:
        return
    from matplotlib.ticker import MaxNLocator

    x_values = [int(row["dict_size"]) for row in rows]
    completed_values = [to_float(row["completed_seed_count"]) for row in rows]
    timeout_values = [
        max(0.0, to_float(row["seed_count"]) - to_float(row["completed_seed_count"]))
        for row in rows
    ]
    if len(x_values) >= 2:
        min_gap = min(right - left for left, right in zip(x_values, x_values[1:]))
        bar_width = max(4.0, min(18.0, min_gap * 0.32))
    else:
        bar_width = 18.0
    left_positions = [value - bar_width / 2 for value in x_values]
    right_positions = [value + bar_width / 2 for value in x_values]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(left_positions, completed_values, width=bar_width, color="#59a14f", label="Completed")
    ax.bar(right_positions, timeout_values, width=bar_width, color="#e15759", label="Timed out")
    ax.set_title("Exact run outcomes by dictionary size", fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size (D)")
    ax.set_ylabel("Number of runs")
    ax.set_xticks(x_values)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(True, axis="y", alpha=0.35)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_agent_bar_chart(
    plt,
    rows: list[dict[str, str]],
    value_field: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    if not rows:
        return
    rows = sorted_agent_size_rows(rows)
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    values = [to_float(row[value_field]) for row in rows]

    fig_width = max(8, len(labels) * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Agent and dictionary size")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_timeout_bar_chart(plt, rows: list[dict[str, str]], output_path: Path) -> None:
    save_timeout_bar_chart_with_title(
        plt,
        rows,
        "Timeouts per match by agent and dictionary size",
        output_path,
    )


def timeout_count_per_match(row: dict[str, str]) -> float:
    if row.get("timeout_count_per_match", "") != "":
        return to_float(row["timeout_count_per_match"])
    match_count = to_float(row.get("match_count", ""))
    if match_count <= 0.0:
        return 0.0
    return to_float(row.get("timeout_count", "")) / match_count


def save_timeout_bar_chart_with_title(
    plt,
    rows: list[dict[str, str]],
    title: str,
    output_path: Path,
) -> None:
    if not rows:
        return
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    values = [timeout_count_per_match(row) for row in rows]

    fig_width = max(8, len(labels) * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(labels, values, color="#e45756")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_ylabel("Timeouts per match")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_approx_first_player_chart(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
    title: str = "Approximate matches: first-player win rate by D",
) -> None:
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    y_values = [to_float(row["first_win_rate"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_values, y_values, marker="o", linewidth=2, color="#59a14f")
    ax.set_ylim(0.0, 1.03)
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size (D)")
    ax.set_ylabel("First-player win rate")
    ax.set_xticks(x_values)
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_top_end_chars_chart(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
    top_n_per_size: int = 8,
    title: str = "Most frequent ending characters in approximate matches",
) -> None:
    if not rows:
        return
    filtered = [row for row in rows if int(row["rank"]) <= top_n_per_size]
    rows_by_size: dict[int, list[dict[str, str]]] = {}
    for row in filtered:
        rows_by_size.setdefault(int(row["dict_size"]), []).append(row)

    sizes = sorted(rows_by_size)
    fig_height = max(4.5, len(sizes) * 2.2)
    fig, axes = plt.subplots(
        len(sizes),
        1,
        figsize=(9, fig_height),
        constrained_layout=True,
    )
    axes_list = [axes] if len(sizes) == 1 else list(axes)

    for ax, dict_size in zip(axes_list, sizes):
        size_rows = sorted(rows_by_size[dict_size], key=lambda row: int(row["rank"]), reverse=True)
        labels = [row["end_char"] for row in size_rows]
        values = [to_float(row["move_count"]) for row in size_rows]
        ax.barh(labels, values, color="#f28e2b")
        ax.set_title(f"D{dict_size}", fontsize=11, pad=6)
        ax.set_xlabel("Move count")
        ax.grid(True, axis="x", alpha=0.35)
        ax.tick_params(axis="y", labelsize=10)

        max_value = max(values) if values else 0
        for label_index, value in enumerate(values):
            ax.text(
                value + max_value * 0.015,
                label_index,
                f"{int(value)}",
                va="center",
                fontsize=8,
            )
        ax.set_xlim(0, max_value * 1.15 if max_value else 1)

    fig.suptitle(title, fontsize=14)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def match_includes_random(row: dict[str, str]) -> bool:
    return row.get("first_agent") == "random" or row.get("second_agent") == "random"


def match_is_self_match(row: dict[str, str]) -> bool:
    return row.get("first_agent") == row.get("second_agent")


def rows_without_self_matches(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if not match_is_self_match(row)]


def rows_without_random(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if not match_includes_random(row) and not match_is_self_match(row)]


def matchup_key(row: dict[str, str]) -> tuple[int, int, str, str]:
    return (
        int(row["dict_size"]),
        int(row.get("random_seed", "0") or "0"),
        row["first_agent"],
        row["second_agent"],
    )


def matchup_repetition_counts(rows: list[dict[str, str]]) -> dict[tuple[int, int, str, str], int]:
    counts: dict[tuple[int, int, str, str], int] = defaultdict(int)
    for row in rows:
        if not match_is_self_match(row):
            counts[matchup_key(row)] += 1
    return counts


def row_weight(row: dict[str, str], repetition_counts: dict[tuple[int, int, str, str], int]) -> float:
    return 1.0 / max(1, repetition_counts.get(matchup_key(row), 1))


def flow_repetition_counts(rows: list[dict[str, str]]) -> dict[tuple[int, int, str, str], int]:
    match_ids_by_key: dict[tuple[int, int, str, str], set[str]] = defaultdict(set)
    for row in rows:
        match_ids_by_key[matchup_key(row)].add(row.get("match_id", ""))
    return {key: len(match_ids) for key, match_ids in match_ids_by_key.items()}


def count_value(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.6f}"


def compact_count_label(value: str) -> str:
    number = to_float(value)
    rounded = round(number)
    if abs(number - rounded) < 1e-9:
        return str(int(rounded))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def agent_move_count(row: dict[str, str], side: str) -> int:
    total_time = to_float(row[f"{side}_total_time_sec"])
    average_time = to_float(row.get(f"{side}_avg_time_sec", ""))
    if average_time > 0.0:
        return max(0, int(round(total_time / average_time)))

    turn_count = int(row["turn_count"])
    if side == "first":
        return max(0, (turn_count + 1) // 2)
    return max(0, turn_count // 2)


def summarize_agents_from_matches(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    repetition_counts = matchup_repetition_counts(rows)
    buckets: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows_without_self_matches(rows):
        dict_size = int(row["dict_size"])
        weight = row_weight(row, repetition_counts)
        buckets[(row["first_agent"], dict_size)].append({**row, "side": "first", "weight": str(weight)})
        buckets[(row["second_agent"], dict_size)].append({**row, "side": "second", "weight": str(weight)})

    summaries: list[dict[str, str]] = []
    for (agent_name, dict_size), agent_rows in sorted(buckets.items()):
        wins = 0.0
        losses = 0.0
        draws = 0.0
        match_count = 0.0
        total_time = 0.0
        total_moves = 0.0
        max_time = 0.0
        timeouts = 0.0
        turn_count_total = 0.0
        used_count_total = 0.0

        for row in agent_rows:
            side = row["side"]
            winner = row["winner"]
            weight = to_float(row["weight"])
            match_count += weight
            if winner == "draw":
                draws += weight
            elif winner == side:
                wins += weight
            else:
                losses += weight

            turn_count = int(row["turn_count"])
            if side == "first":
                total_time += weight * to_float(row["first_total_time_sec"])
                total_moves += weight * agent_move_count(row, "first")
                max_time = max(max_time, to_float(row["first_max_time_sec"]))
                timeouts += weight * int(row["first_timeout_count"])
            else:
                total_time += weight * to_float(row["second_total_time_sec"])
                total_moves += weight * agent_move_count(row, "second")
                max_time = max(max_time, to_float(row["second_max_time_sec"]))
                timeouts += weight * int(row["second_timeout_count"])

            turn_count_total += weight * turn_count
            used_count_total += weight * int(row["used_word_count"])

        summaries.append(
            {
                "agent_name": agent_name,
                "dict_size": str(dict_size),
                "match_count": count_value(match_count),
                "win_count": count_value(wins),
                "loss_count": count_value(losses),
                "draw_count": count_value(draws),
                "win_rate": f"{wins / match_count:.6f}" if match_count else "0.000000",
                "average_turn_count": f"{turn_count_total / match_count:.6f}" if match_count else "0.000000",
                "average_used_word_count": f"{used_count_total / match_count:.6f}" if match_count else "0.000000",
                "average_time_per_move_sec": f"{total_time / total_moves:.6f}" if total_moves else "0.000000",
                "max_time_sec": f"{max_time:.6f}",
                "timeout_count": count_value(timeouts),
                "timeout_count_per_match": f"{timeouts / match_count:.6f}" if match_count else "0.000000",
            }
        )
    return summaries


def summarize_first_player_from_matches(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = rows_without_self_matches(rows)
    repetition_counts = matchup_repetition_counts(rows)
    summaries: list[dict[str, str]] = []
    for dict_size in sorted({int(row["dict_size"]) for row in rows}):
        size_rows = [row for row in rows if int(row["dict_size"]) == dict_size]
        first_wins = sum(row_weight(row, repetition_counts) for row in size_rows if row["winner"] == "first")
        second_wins = sum(row_weight(row, repetition_counts) for row in size_rows if row["winner"] == "second")
        draws = sum(row_weight(row, repetition_counts) for row in size_rows if row["winner"] == "draw")
        match_count = sum(row_weight(row, repetition_counts) for row in size_rows)
        summaries.append(
            {
                "dict_size": str(dict_size),
                "match_count": count_value(match_count),
                "first_win_count": count_value(first_wins),
                "second_win_count": count_value(second_wins),
                "draw_count": count_value(draws),
                "first_win_rate": f"{first_wins / match_count:.6f}" if match_count else "0.000000",
            }
        )
    return summaries


def summarize_top_end_chars_from_flow(
    rows: list[dict[str, str]],
    top_n: int = 20,
) -> list[dict[str, str]]:
    repetition_counts = flow_repetition_counts(rows)
    totals: dict[int, float] = defaultdict(float)
    buckets: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"move_count": 0.0, "ended_with_n_count": 0.0, "elapsed_time_sec": 0.0}
    )
    for row in rows:
        dict_size = int(row["dict_size"])
        end_char = row["end_char"]
        weight = row_weight(row, repetition_counts)
        totals[dict_size] += weight
        bucket = buckets[(dict_size, end_char)]
        bucket["move_count"] += weight
        bucket["elapsed_time_sec"] += weight * to_float(row["elapsed_time_sec"])
        if end_char == "ん":
            bucket["ended_with_n_count"] += weight

    summaries: list[dict[str, str]] = []
    for dict_size in sorted(totals):
        candidates = [
            (end_char, bucket)
            for (size, end_char), bucket in buckets.items()
            if size == dict_size
        ]
        candidates.sort(key=lambda item: (-item[1]["move_count"], item[0]))
        for rank, (end_char, bucket) in enumerate(candidates[:top_n], start=1):
            move_count = bucket["move_count"]
            summaries.append(
                {
                    "dict_size": str(dict_size),
                    "rank": str(rank),
                    "end_char": end_char,
                    "move_count": count_value(move_count),
                    "move_rate": f"{move_count / totals[dict_size]:.6f}" if totals[dict_size] else "0.000000",
                    "ended_with_n_count": count_value(bucket["ended_with_n_count"]),
                    "average_elapsed_time_sec": f"{bucket['elapsed_time_sec'] / move_count:.6f}" if move_count else "0.000000",
                }
            )
    return summaries


def build_agent_win_rate_comparison_rows(
    including_random_rows: list[dict[str, str]],
    excluding_random_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    including_by_key = {
        (row["agent_name"], int(row["dict_size"])): to_float(row["win_rate"])
        for row in including_random_rows
    }
    excluding_by_key = {
        (row["agent_name"], int(row["dict_size"])): to_float(row["win_rate"])
        for row in excluding_random_rows
    }
    rows: list[dict[str, str]] = []
    for agent_name, dict_size in sorted(excluding_by_key, key=lambda item: (item[1], item[0])):
        including_rate = including_by_key.get((agent_name, dict_size))
        excluding_rate = excluding_by_key[(agent_name, dict_size)]
        if including_rate is None:
            continue
        rows.append(
            {
                "agent_name": agent_name,
                "dict_size": str(dict_size),
                "including_random_win_rate": f"{including_rate:.6f}",
                "excluding_random_win_rate": f"{excluding_rate:.6f}",
            }
        )
    return rows


def build_first_player_win_rate_comparison_rows(
    including_random_rows: list[dict[str, str]],
    excluding_random_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    including_by_size = {
        int(row["dict_size"]): to_float(row["first_win_rate"])
        for row in including_random_rows
    }
    excluding_by_size = {
        int(row["dict_size"]): to_float(row["first_win_rate"])
        for row in excluding_random_rows
    }
    rows: list[dict[str, str]] = []
    for dict_size in sorted(excluding_by_size):
        if dict_size not in including_by_size:
            continue
        including_rate = including_by_size[dict_size]
        excluding_rate = excluding_by_size[dict_size]
        rows.append(
            {
                "dict_size": str(dict_size),
                "including_random_first_win_rate": f"{including_rate:.6f}",
                "excluding_random_first_win_rate": f"{excluding_rate:.6f}",
            }
        )
    return rows


def build_pairwise_agent_result_rows(
    rows: list[dict[str, str]],
    dict_size: int = 10000,
) -> list[dict[str, str]]:
    repetition_counts = matchup_repetition_counts(rows)
    buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"match_count": 0.0, "first_win_count": 0.0, "second_win_count": 0.0, "draw_count": 0.0}
    )

    for row in rows_without_self_matches(rows):
        if int(row["dict_size"]) != dict_size:
            continue
        first_agent = row["first_agent"]
        second_agent = row["second_agent"]
        winner = row["winner"]
        weight = row_weight(row, repetition_counts)

        bucket = buckets[(first_agent, second_agent)]
        bucket["match_count"] += weight

        if winner == "first":
            bucket["first_win_count"] += weight
        elif winner == "second":
            bucket["second_win_count"] += weight
        else:
            bucket["draw_count"] += weight

    result_rows: list[dict[str, str]] = []
    agents = ordered_agent_names({agent for pair in buckets for agent in pair})
    agent_order = {agent: index for index, agent in enumerate(agents)}
    for (first_agent, second_agent), bucket in sorted(
        buckets.items(),
        key=lambda item: (agent_order.get(item[0][0], 999), agent_order.get(item[0][1], 999)),
    ):
        match_count = bucket["match_count"]
        result_rows.append(
            {
                "dict_size": str(dict_size),
                "first_agent": first_agent,
                "second_agent": second_agent,
                "match_count": count_value(match_count),
                "first_win_count": count_value(bucket["first_win_count"]),
                "second_win_count": count_value(bucket["second_win_count"]),
                "draw_count": count_value(bucket["draw_count"]),
                "first_win_rate": f"{bucket['first_win_count'] / match_count:.6f}" if match_count else "0.000000",
            }
        )
    return result_rows


def save_pairwise_agent_result_grid(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
    dict_size: int = 10000,
) -> None:
    if not rows:
        return
    import numpy as np

    agents = ordered_agent_names(
        {row["first_agent"] for row in rows} | {row["second_agent"] for row in rows}
    )
    row_by_pair = {(row["first_agent"], row["second_agent"]): row for row in rows}
    matrix = np.full((len(agents), len(agents)), np.nan)
    for y_index, first_agent in enumerate(agents):
        for x_index, second_agent in enumerate(agents):
            if first_agent == second_agent:
                continue
            row = row_by_pair.get((first_agent, second_agent))
            if row is not None:
                matrix[y_index, x_index] = to_float(row["first_win_rate"])

    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#f1f1f1")
    fig_size = max(7, len(agents) * 1.25)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    image = ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=0.0, vmax=1.0)
    ax.set_title(f"D{dict_size} first-player win rate by matchup", fontsize=14, pad=12)
    ax.set_xlabel("Second-player agent (cell: first-player win rate; first/second/draw)")
    ax.set_ylabel("First-player agent")
    ax.set_xticks(range(len(agents)))
    ax.set_yticks(range(len(agents)))
    ax.set_xticklabels(agents, rotation=35, ha="right")
    ax.set_yticklabels(agents)

    for y_index, first_agent in enumerate(agents):
        for x_index, second_agent in enumerate(agents):
            if first_agent == second_agent:
                label = "-"
            else:
                row = row_by_pair.get((first_agent, second_agent))
                if row is None:
                    label = "n/a"
                else:
                    label = (
                        f"{to_float(row['first_win_rate']):.2f}\n"
                        f"{compact_count_label(row['first_win_count'])}/"
                        f"{compact_count_label(row['second_win_count'])}/"
                        f"{compact_count_label(row['draw_count'])}"
                    )
            value = matrix[y_index, x_index]
            text_color = "white" if not np.isnan(value) and (value < 0.25 or value > 0.75) else "#222222"
            ax.text(x_index, y_index, label, ha="center", va="center", fontsize=8, color=text_color)

    ax.grid(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label("First-player win rate")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_agent_win_rate_comparison_chart(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    if not rows:
        return
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    including_values = [to_float(row["including_random_win_rate"]) for row in rows]
    excluding_values = [to_float(row["excluding_random_win_rate"]) for row in rows]
    x_positions = list(range(len(labels)))
    bar_width = 0.42

    fig_width = max(8, len(labels) * 0.7)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(
        [position - bar_width / 2 for position in x_positions],
        including_values,
        width=bar_width,
        color="#4e79a7",
        label="Including random matchups",
    )
    ax.bar(
        [position + bar_width / 2 for position in x_positions],
        excluding_values,
        width=bar_width,
        color="#f28e2b",
        label="Excluding random matchups",
    )
    ax.set_ylim(0.0, 1.03)
    ax.set_title("Win rate including and excluding random matchups", fontsize=14, pad=12)
    ax.set_ylabel("Win rate")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_first_player_win_rate_comparison_chart(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    including_values = [to_float(row["including_random_first_win_rate"]) for row in rows]
    excluding_values = [to_float(row["excluding_random_first_win_rate"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_values, including_values, marker="o", linewidth=2, color="#4e79a7", label="Including random matchups")
    ax.plot(x_values, excluding_values, marker="o", linewidth=2, color="#f28e2b", label="Excluding random matchups")
    ax.set_ylim(0.0, 1.03)
    ax.set_title(
        "First-player win rate including and excluding random matchups",
        fontsize=14,
        pad=12,
    )
    ax.set_xlabel("Dictionary size (D)")
    ax.set_ylabel("First-player win rate")
    ax.set_xticks(x_values)
    ax.grid(True, alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_rows(path: str | Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def remove_stale_renamed_figures(fig_dir: Path) -> None:
    stale_names = [
        "approx_agent_win_rate.png",
        "approx_agent_avg_time.png",
        "approx_agent_timeout_count.png",
        "approx_first_player_win_rate_by_dict_size.png",
        "approx_agent_avg_time_with_random.png",
        "approx_agent_avg_time_without_random.png",
        "approx_agent_timeout_count_with_random.png",
        "approx_agent_timeout_count_without_random.png",
        "approx_agent_win_rate_with_random.png",
        "approx_agent_win_rate_without_random.png",
        "approx_first_player_win_rate_with_random.png",
        "approx_first_player_win_rate_without_random.png",
        "approx_first_player_win_rate_by_dict_size_with_random.png",
        "approx_first_player_win_rate_by_dict_size_without_random.png",
        "approx_top_end_chars_with_random.png",
        "approx_top_end_chars_without_random.png",
        "approx_agent_win_rate_random_comparison.png",
        "approx_agent_win_rate_random_comparison.csv",
        "approx_agent_win_rate_random_delta.png",
        "approx_agent_win_rate_random_delta.csv",
        "approx_first_player_win_rate_random_comparison.png",
        "approx_first_player_win_rate_random_comparison.csv",
        "approx_first_player_win_rate_random_delta.png",
        "approx_first_player_win_rate_random_delta.csv",
    ]
    for name in stale_names:
        path = fig_dir / name
        if path.exists():
            path.unlink()


def save_random_subset_outputs(
    plt,
    including_random_agent_rows: list[dict[str, str]],
    including_random_first_player_rows: list[dict[str, str]],
    excluding_random_agent_rows: list[dict[str, str]],
    excluding_random_first_player_rows: list[dict[str, str]],
    fig_dir: Path,
) -> None:
    save_agent_bar_chart(
        plt,
        including_random_agent_rows,
        "win_rate",
        "Agent win rate",
        "Agent win rate by dictionary size, including random matchups",
        fig_dir / "approx_agent_win_rate_including_random.png",
    )
    save_agent_bar_chart(
        plt,
        excluding_random_agent_rows,
        "win_rate",
        "Agent win rate",
        "Agent win rate by dictionary size, excluding random matchups",
        fig_dir / "approx_agent_win_rate_excluding_random.png",
    )
    save_approx_first_player_chart(
        plt,
        including_random_first_player_rows,
        fig_dir / "approx_first_player_win_rate_including_random.png",
        title="First-player win rate by dictionary size, including random matchups",
    )
    save_approx_first_player_chart(
        plt,
        excluding_random_first_player_rows,
        fig_dir / "approx_first_player_win_rate_excluding_random.png",
        title="First-player win rate by dictionary size, excluding random matchups",
    )


def save_win_rate_comparison_outputs(
    plt,
    with_random_agent_rows: list[dict[str, str]],
    with_random_first_player_rows: list[dict[str, str]],
    without_random_agent_rows: list[dict[str, str]],
    without_random_first_player_rows: list[dict[str, str]],
    fig_dir: Path,
) -> None:
    agent_comparison_rows = build_agent_win_rate_comparison_rows(
        with_random_agent_rows,
        without_random_agent_rows,
    )
    first_player_comparison_rows = build_first_player_win_rate_comparison_rows(
        with_random_first_player_rows,
        without_random_first_player_rows,
    )

    save_agent_win_rate_comparison_chart(
        plt,
        agent_comparison_rows,
        fig_dir / "approx_agent_win_rate_random_comparison.png",
    )
    save_first_player_win_rate_comparison_chart(
        plt,
        first_player_comparison_rows,
        fig_dir / "approx_first_player_win_rate_random_comparison.png",
    )
    write_rows(
        fig_dir / "approx_agent_win_rate_random_comparison.csv",
        [
            "agent_name",
            "dict_size",
            "including_random_win_rate",
            "excluding_random_win_rate",
        ],
        agent_comparison_rows,
    )
    write_rows(
        fig_dir / "approx_first_player_win_rate_random_comparison.csv",
        [
            "dict_size",
            "including_random_first_win_rate",
            "excluding_random_first_win_rate",
        ],
        first_player_comparison_rows,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact-dir", default="results/exact")
    parser.add_argument("--approx-dir", default="results/approx")
    parser.add_argument("--fig-dir", default="results/figures")
    parser.add_argument("--pairwise-dict-size", type=int, default=10000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plt = ensure_matplotlib()
    fig_dir = Path(args.fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_renamed_figures(fig_dir)

    exact_summary = read_csv_rows(Path(args.exact_dir) / "exact_summary_by_size.csv")
    save_exact_line_chart(
        plt,
        exact_summary,
        "searched_state_count_mean",
        "searched_state_count_stdev",
        "Mean searched states per completed seed",
        "Exact search cost by dictionary size",
        fig_dir / "exact_search_states_by_dict_size.png",
    )
    save_exact_line_chart(
        plt,
        exact_summary,
        "elapsed_time_sec_mean",
        "elapsed_time_sec_stdev",
        "Mean elapsed time per completed seed (sec)",
        "Exact analysis time by dictionary size",
        fig_dir / "exact_time_by_dict_size.png",
    )
    save_exact_line_chart(
        plt,
        exact_summary,
        "winning_first_move_count_mean",
        "winning_first_move_count_stdev",
        "Mean count of winning opening moves",
        "Winning opening move count by dictionary size",
        fig_dir / "exact_winning_first_moves_by_dict_size.png",
    )
    save_exact_win_rate(
        plt,
        exact_summary,
        fig_dir / "exact_first_player_win_rate_by_dict_size.png",
    )
    save_exact_completion_chart(
        plt,
        exact_summary,
        fig_dir / "exact_completion_by_dict_size.png",
    )

    match_rows = read_csv_rows(Path(args.approx_dir) / "matches.csv")
    agent_summary = (
        summarize_agents_from_matches(match_rows)
        if match_rows
        else read_csv_rows(Path(args.approx_dir) / "agent_summary.csv")
    )

    save_agent_bar_chart(
        plt,
        agent_summary,
        "average_time_per_move_sec",
        "Seconds per move",
        "Average thinking time per move by agent and dictionary size",
        fig_dir / "approx_agent_avg_time_per_move.png",
    )
    save_timeout_bar_chart(
        plt,
        agent_summary,
        fig_dir / "approx_agent_timeouts_per_match.png",
    )
    first_player_rows = (
        summarize_first_player_from_matches(match_rows)
        if match_rows
        else read_csv_rows(Path(args.approx_dir) / "first_player_by_size.csv")
    )
    top_end_char_rows = read_csv_rows(Path(args.approx_dir) / "top_end_chars.csv")
    save_top_end_chars_chart(
        plt,
        top_end_char_rows,
        fig_dir / "approx_top_end_chars.png",
        title="Most frequent ending characters in approximate matches",
    )

    if match_rows:
        no_random_match_rows = rows_without_random(match_rows)
        no_random_agent_summary = summarize_agents_from_matches(no_random_match_rows)
        no_random_first_player_rows = summarize_first_player_from_matches(no_random_match_rows)
        save_random_subset_outputs(
            plt,
            agent_summary,
            first_player_rows,
            no_random_agent_summary,
            no_random_first_player_rows,
            fig_dir,
        )
        pairwise_rows = build_pairwise_agent_result_rows(match_rows, dict_size=args.pairwise_dict_size)
        save_pairwise_agent_result_grid(
            plt,
            pairwise_rows,
            fig_dir / f"approx_d{args.pairwise_dict_size}_pairwise_agent_results.png",
            dict_size=args.pairwise_dict_size,
        )
        write_rows(
            fig_dir / f"approx_d{args.pairwise_dict_size}_pairwise_agent_results.csv",
            [
                "dict_size",
                "first_agent",
                "second_agent",
                "match_count",
                "first_win_count",
                "second_win_count",
                "draw_count",
                "first_win_rate",
            ],
            pairwise_rows,
        )
    else:
        save_agent_bar_chart(
            plt,
            agent_summary,
            "win_rate",
            "Agent win rate",
            "Agent win rate by dictionary size",
            fig_dir / "approx_agent_win_rate_including_random.png",
        )
        save_approx_first_player_chart(
            plt,
            first_player_rows,
            fig_dir / "approx_first_player_win_rate_including_random.png",
            title="First-player win rate by dictionary size",
        )

    print(f"figures written to {fig_dir}")


if __name__ == "__main__":
    main()
