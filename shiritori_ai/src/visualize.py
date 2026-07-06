"""Create report-ready matplotlib figures from experiment CSV files."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path


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
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    y_values = [to_float(row[value_field]) for row in rows]
    y_errors = [to_float(row[stdev_field]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        x_values,
        y_values,
        yerr=y_errors,
        marker="o",
        linewidth=2,
        capsize=4,
        color="#1f77b4",
    )
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size D")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_values)
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_exact_win_rate(plt, rows: list[dict[str, str]], output_path: Path) -> None:
    if not rows:
        return
    x_values = [int(row["dict_size"]) for row in rows]
    y_values = [to_float(row["first_player_win_rate"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_values, y_values, marker="o", linewidth=2, color="#2ca02c")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title("First-player win rate by dictionary size", fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size D")
    ax.set_ylabel("First-player win rate")
    ax.set_xticks(x_values)
    ax.grid(True, alpha=0.35)
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
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    values = [to_float(row[value_field]) for row in rows]

    fig_width = max(8, len(labels) * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_timeout_bar_chart(plt, rows: list[dict[str, str]], output_path: Path) -> None:
    save_timeout_bar_chart_with_title(
        plt,
        rows,
        "Timeout count by approximate AI",
        output_path,
    )


def save_timeout_bar_chart_with_title(
    plt,
    rows: list[dict[str, str]],
    title: str,
    output_path: Path,
) -> None:
    if not rows:
        return
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    values = [to_float(row["timeout_count"]) for row in rows]

    fig_width = max(8, len(labels) * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(labels, values, color="#e45756")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_ylabel("Timeout count")
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
    ax.set_ylim(-0.03, 1.03)
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel("Dictionary size D")
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


def summarize_agents_from_matches(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buckets: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows_without_self_matches(rows):
        dict_size = int(row["dict_size"])
        buckets[(row["first_agent"], dict_size)].append({**row, "side": "first"})
        buckets[(row["second_agent"], dict_size)].append({**row, "side": "second"})

    summaries: list[dict[str, str]] = []
    for (agent_name, dict_size), agent_rows in sorted(buckets.items()):
        wins = 0
        losses = 0
        draws = 0
        total_time = 0.0
        total_moves = 0
        max_time = 0.0
        timeouts = 0
        turn_counts: list[int] = []
        used_counts: list[int] = []

        for row in agent_rows:
            side = row["side"]
            winner = row["winner"]
            if winner == "draw":
                draws += 1
            elif winner == side:
                wins += 1
            else:
                losses += 1

            turn_count = int(row["turn_count"])
            if side == "first":
                total_time += to_float(row["first_total_time_sec"])
                total_moves += max(0, (turn_count + 1) // 2)
                max_time = max(max_time, to_float(row["first_max_time_sec"]))
                timeouts += int(row["first_timeout_count"])
            else:
                total_time += to_float(row["second_total_time_sec"])
                total_moves += turn_count // 2
                max_time = max(max_time, to_float(row["second_max_time_sec"]))
                timeouts += int(row["second_timeout_count"])

            turn_counts.append(turn_count)
            used_counts.append(int(row["used_word_count"]))

        match_count = len(agent_rows)
        summaries.append(
            {
                "agent_name": agent_name,
                "dict_size": str(dict_size),
                "match_count": str(match_count),
                "win_count": str(wins),
                "loss_count": str(losses),
                "draw_count": str(draws),
                "win_rate": f"{wins / match_count:.6f}" if match_count else "0.000000",
                "average_turn_count": f"{statistics.mean(turn_counts):.6f}" if turn_counts else "0.000000",
                "average_used_word_count": f"{statistics.mean(used_counts):.6f}" if used_counts else "0.000000",
                "average_time_per_move_sec": f"{total_time / total_moves:.6f}" if total_moves else "0.000000",
                "max_time_sec": f"{max_time:.6f}",
                "timeout_count": str(timeouts),
            }
        )
    return summaries


def summarize_first_player_from_matches(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = rows_without_self_matches(rows)
    summaries: list[dict[str, str]] = []
    for dict_size in sorted({int(row["dict_size"]) for row in rows}):
        size_rows = [row for row in rows if int(row["dict_size"]) == dict_size]
        first_wins = sum(1 for row in size_rows if row["winner"] == "first")
        second_wins = sum(1 for row in size_rows if row["winner"] == "second")
        draws = sum(1 for row in size_rows if row["winner"] == "draw")
        match_count = len(size_rows)
        summaries.append(
            {
                "dict_size": str(dict_size),
                "match_count": str(match_count),
                "first_win_count": str(first_wins),
                "second_win_count": str(second_wins),
                "draw_count": str(draws),
                "first_win_rate": f"{first_wins / match_count:.6f}" if match_count else "0.000000",
            }
        )
    return summaries


def summarize_top_end_chars_from_flow(
    rows: list[dict[str, str]],
    top_n: int = 20,
) -> list[dict[str, str]]:
    totals: dict[int, int] = defaultdict(int)
    buckets: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"move_count": 0.0, "ended_with_n_count": 0.0, "elapsed_time_sec": 0.0}
    )
    for row in rows:
        dict_size = int(row["dict_size"])
        end_char = row["end_char"]
        totals[dict_size] += 1
        bucket = buckets[(dict_size, end_char)]
        bucket["move_count"] += 1
        bucket["elapsed_time_sec"] += to_float(row["elapsed_time_sec"])
        if end_char == "ん":
            bucket["ended_with_n_count"] += 1

    summaries: list[dict[str, str]] = []
    for dict_size in sorted(totals):
        candidates = [
            (end_char, bucket)
            for (size, end_char), bucket in buckets.items()
            if size == dict_size
        ]
        candidates.sort(key=lambda item: (-item[1]["move_count"], item[0]))
        for rank, (end_char, bucket) in enumerate(candidates[:top_n], start=1):
            move_count = int(bucket["move_count"])
            summaries.append(
                {
                    "dict_size": str(dict_size),
                    "rank": str(rank),
                    "end_char": end_char,
                    "move_count": str(move_count),
                    "move_rate": f"{move_count / totals[dict_size]:.6f}" if totals[dict_size] else "0.000000",
                    "ended_with_n_count": str(int(bucket["ended_with_n_count"])),
                    "average_elapsed_time_sec": f"{bucket['elapsed_time_sec'] / move_count:.6f}" if move_count else "0.000000",
                }
            )
    return summaries


def build_agent_win_rate_comparison_rows(
    with_random_rows: list[dict[str, str]],
    without_random_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    with_by_key = {
        (row["agent_name"], int(row["dict_size"])): to_float(row["win_rate"])
        for row in with_random_rows
    }
    without_by_key = {
        (row["agent_name"], int(row["dict_size"])): to_float(row["win_rate"])
        for row in without_random_rows
    }
    rows: list[dict[str, str]] = []
    for agent_name, dict_size in sorted(without_by_key, key=lambda item: (item[1], item[0])):
        with_rate = with_by_key.get((agent_name, dict_size))
        without_rate = without_by_key[(agent_name, dict_size)]
        if with_rate is None:
            continue
        rows.append(
            {
                "agent_name": agent_name,
                "dict_size": str(dict_size),
                "with_random_win_rate": f"{with_rate:.6f}",
                "without_random_win_rate": f"{without_rate:.6f}",
            }
        )
    return rows


def build_first_player_win_rate_comparison_rows(
    with_random_rows: list[dict[str, str]],
    without_random_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    with_by_size = {
        int(row["dict_size"]): to_float(row["first_win_rate"])
        for row in with_random_rows
    }
    without_by_size = {
        int(row["dict_size"]): to_float(row["first_win_rate"])
        for row in without_random_rows
    }
    rows: list[dict[str, str]] = []
    for dict_size in sorted(without_by_size):
        if dict_size not in with_by_size:
            continue
        with_rate = with_by_size[dict_size]
        without_rate = without_by_size[dict_size]
        rows.append(
            {
                "dict_size": str(dict_size),
                "with_random_first_win_rate": f"{with_rate:.6f}",
                "without_random_first_win_rate": f"{without_rate:.6f}",
            }
        )
    return rows


def save_agent_win_rate_comparison_chart(
    plt,
    rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    if not rows:
        return
    labels = [f"{row['agent_name']}\nD{row['dict_size']}" for row in rows]
    with_values = [to_float(row["with_random_win_rate"]) for row in rows]
    without_values = [to_float(row["without_random_win_rate"]) for row in rows]
    x_positions = list(range(len(labels)))
    bar_width = 0.42

    fig_width = max(8, len(labels) * 0.7)
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    ax.bar(
        [position - bar_width / 2 for position in x_positions],
        with_values,
        width=bar_width,
        color="#4e79a7",
        label="With random matches",
    )
    ax.bar(
        [position + bar_width / 2 for position in x_positions],
        without_values,
        width=bar_width,
        color="#f28e2b",
        label="Without random matches",
    )
    ax.set_ylim(-0.03, 1.03)
    ax.set_title("Win rate with and without random matches", fontsize=14, pad=12)
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
    with_values = [to_float(row["with_random_first_win_rate"]) for row in rows]
    without_values = [to_float(row["without_random_first_win_rate"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_values, with_values, marker="o", linewidth=2, color="#4e79a7", label="With random matches")
    ax.plot(x_values, without_values, marker="o", linewidth=2, color="#f28e2b", label="Without random matches")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title(
        "First-player win rate with and without random matches",
        fontsize=14,
        pad=12,
    )
    ax.set_xlabel("Dictionary size D")
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


def remove_stale_random_comparison_figures(fig_dir: Path) -> None:
    stale_names = [
        "approx_agent_avg_time_with_random.png",
        "approx_agent_avg_time_without_random.png",
        "approx_agent_timeout_count_with_random.png",
        "approx_agent_timeout_count_without_random.png",
        "approx_agent_win_rate_with_random.png",
        "approx_agent_win_rate_without_random.png",
        "approx_first_player_win_rate_by_dict_size_with_random.png",
        "approx_first_player_win_rate_by_dict_size_without_random.png",
        "approx_top_end_chars_with_random.png",
        "approx_top_end_chars_without_random.png",
        "approx_agent_win_rate_random_delta.png",
        "approx_agent_win_rate_random_delta.csv",
        "approx_first_player_win_rate_random_delta.png",
        "approx_first_player_win_rate_random_delta.csv",
    ]
    for name in stale_names:
        path = fig_dir / name
        if path.exists():
            path.unlink()


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
            "with_random_win_rate",
            "without_random_win_rate",
        ],
        agent_comparison_rows,
    )
    write_rows(
        fig_dir / "approx_first_player_win_rate_random_comparison.csv",
        [
            "dict_size",
            "with_random_first_win_rate",
            "without_random_first_win_rate",
        ],
        first_player_comparison_rows,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact-dir", default="results/exact")
    parser.add_argument("--approx-dir", default="results/approx")
    parser.add_argument("--fig-dir", default="results/figures")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plt = ensure_matplotlib()
    fig_dir = Path(args.fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    exact_summary = read_csv_rows(Path(args.exact_dir) / "exact_summary_by_size.csv")
    save_exact_line_chart(
        plt,
        exact_summary,
        "searched_state_count_mean",
        "searched_state_count_stdev",
        "Searched state count",
        "Exact analysis: searched states by dictionary size",
        fig_dir / "exact_search_states_by_dict_size.png",
    )
    save_exact_line_chart(
        plt,
        exact_summary,
        "elapsed_time_sec_mean",
        "elapsed_time_sec_stdev",
        "Elapsed time (sec)",
        "Exact analysis: elapsed time by dictionary size",
        fig_dir / "exact_time_by_dict_size.png",
    )
    save_exact_line_chart(
        plt,
        exact_summary,
        "winning_first_move_count_mean",
        "winning_first_move_count_stdev",
        "Winning first move count",
        "Exact analysis: winning first moves by dictionary size",
        fig_dir / "exact_winning_first_moves_by_dict_size.png",
    )
    save_exact_win_rate(
        plt,
        exact_summary,
        fig_dir / "exact_first_player_win_rate_by_dict_size.png",
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
        "win_rate",
        "Win rate",
        "Approximate AI win rate",
        fig_dir / "approx_agent_win_rate.png",
    )
    save_agent_bar_chart(
        plt,
        agent_summary,
        "average_time_per_move_sec",
        "Average time per move (sec)",
        "Approximate AI thinking time",
        fig_dir / "approx_agent_avg_time.png",
    )
    save_timeout_bar_chart(
        plt,
        agent_summary,
        fig_dir / "approx_agent_timeout_count.png",
    )
    first_player_rows = (
        summarize_first_player_from_matches(match_rows)
        if match_rows
        else read_csv_rows(Path(args.approx_dir) / "first_player_by_size.csv")
    )
    save_approx_first_player_chart(
        plt,
        first_player_rows,
        fig_dir / "approx_first_player_win_rate_by_dict_size.png",
    )
    top_end_char_rows = read_csv_rows(Path(args.approx_dir) / "top_end_chars.csv")
    save_top_end_chars_chart(
        plt,
        top_end_char_rows,
        fig_dir / "approx_top_end_chars.png",
    )

    if match_rows:
        remove_stale_random_comparison_figures(fig_dir)
        no_random_match_rows = rows_without_random(match_rows)
        no_random_agent_summary = summarize_agents_from_matches(no_random_match_rows)
        no_random_first_player_rows = summarize_first_player_from_matches(no_random_match_rows)
        save_win_rate_comparison_outputs(
            plt,
            agent_summary,
            first_player_rows,
            no_random_agent_summary,
            no_random_first_player_rows,
            fig_dir,
        )

    print(f"figures written to {fig_dir}")


if __name__ == "__main__":
    main()
