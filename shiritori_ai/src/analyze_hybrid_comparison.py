"""Analyze D10000 hybrid-agent matches and fixed-position benchmarks."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from run_graph_control_comparison import read_jsonl, write_csv
from visualize import ensure_matplotlib


AGENT_ORDER = (
    "alpha_beta",
    "pvs",
    "beam_negamax",
    "graph_control",
    "graph_pvs",
    "beam_alpha_beta",
    "beam_pvs",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _number(turn: dict[str, Any], field: str) -> float:
    value = turn.get(field, 0)
    return 0.0 if value in ("", None) else float(value)


def aggregate_agents(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    present_agents = {
        str(match[field])
        for match in matches
        for field in ("first_agent", "second_agent")
    }
    ordered_agents = [
        agent for agent in AGENT_ORDER if agent in present_agents
    ] + sorted(present_agents - set(AGENT_ORDER))
    records: dict[str, dict[str, Any]] = {}
    for agent in ordered_agents:
        records[agent] = {
            "agent": agent,
            "games": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "first_games": 0,
            "first_wins": 0,
            "second_games": 0,
            "second_wins": 0,
            "turn_counts": [],
            "times": [],
            "nodes": [],
            "depths": [],
            "timeout_count": 0,
            "depth_change_count": 0,
            "cutoff_count": 0.0,
            "beam_pruned_move_count": 0.0,
            "null_window_search_count": 0.0,
            "research_count": 0.0,
            "graph_ordering_calls": 0.0,
            "graph_ordering_changed_first_count": 0.0,
            "graph_ordering_time_sec": 0.0,
        }
    for match in matches:
        for seat, agent in (
            ("first", str(match["first_agent"])),
            ("second", str(match["second_agent"])),
        ):
            if agent not in records:
                continue
            record = records[agent]
            record["games"] += 1
            record[f"{seat}_games"] += 1
            winner = str(match["winner"])
            if winner == seat:
                record["wins"] += 1
                record[f"{seat}_wins"] += 1
            elif winner == "draw":
                record["draws"] += 1
            else:
                record["losses"] += 1
            record["turn_counts"].append(int(match["turn_count"]))
            turns = [
                turn
                for turn in match.get("history", [])
                if turn.get("player") == seat
            ]
            for turn in turns:
                record["times"].append(_number(turn, "elapsed_time_sec"))
                record["nodes"].append(_number(turn, "nodes_searched"))
                if turn.get("effective_depth") not in ("", None):
                    record["depths"].append(_number(turn, "effective_depth"))
                record["timeout_count"] += int(bool(turn.get("timed_out")))
                record["depth_change_count"] += int(
                    bool(turn.get("depth_changed"))
                )
                for field in (
                    "cutoff_count",
                    "beam_pruned_move_count",
                    "null_window_search_count",
                    "research_count",
                    "graph_ordering_calls",
                    "graph_ordering_changed_first_count",
                    "graph_ordering_time_sec",
                ):
                    record[field] += _number(turn, field)
    result: list[dict[str, Any]] = []
    for agent in ordered_agents:
        record = records[agent]
        games = int(record["games"])
        null_searches = float(record["null_window_search_count"])
        graph_calls = float(record["graph_ordering_calls"])
        times = record["times"]
        nodes = record["nodes"]
        depths = record["depths"]
        result.append(
            {
                "agent": agent,
                "games": games,
                "wins": record["wins"],
                "losses": record["losses"],
                "draws": record["draws"],
                "win_rate": record["wins"] / games if games else 0.0,
                "first_win_rate": (
                    record["first_wins"] / record["first_games"]
                    if record["first_games"]
                    else 0.0
                ),
                "second_win_rate": (
                    record["second_wins"] / record["second_games"]
                    if record["second_games"]
                    else 0.0
                ),
                "mean_match_turns": statistics.fmean(record["turn_counts"])
                if record["turn_counts"]
                else 0.0,
                "decision_count": len(times),
                "mean_decision_time_sec": statistics.fmean(times)
                if times
                else 0.0,
                "max_decision_time_sec": max(times) if times else 0.0,
                "timeout_count": record["timeout_count"],
                "mean_nodes_per_decision": statistics.fmean(nodes)
                if nodes
                else 0.0,
                "mean_effective_depth": statistics.fmean(depths)
                if depths
                else 0.0,
                "depth_change_count": record["depth_change_count"],
                "cutoff_count": record["cutoff_count"],
                "beam_pruned_move_count": record["beam_pruned_move_count"],
                "research_count": record["research_count"],
                "null_window_search_count": null_searches,
                "research_rate": (
                    record["research_count"] / null_searches
                    if null_searches
                    else 0.0
                ),
                "graph_ordering_calls": graph_calls,
                "graph_ordering_changed_first_count": record[
                    "graph_ordering_changed_first_count"
                ],
                "graph_ordering_changed_first_rate": (
                    record["graph_ordering_changed_first_count"] / graph_calls
                    if graph_calls
                    else 0.0
                ),
                "graph_ordering_time_sec": record["graph_ordering_time_sec"],
            }
        )
    return result


def direct_results(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        first = str(match["first_agent"])
        second = str(match["second_agent"])
        if first not in AGENT_ORDER or second not in AGENT_ORDER:
            continue
        left, right = sorted(
            (first, second),
            key=lambda name: AGENT_ORDER.index(name),
        )
        groups[(left, right)].append(match)
    rows: list[dict[str, Any]] = []
    for (left, right), values in sorted(
        groups.items(),
        key=lambda item: (
            AGENT_ORDER.index(item[0][0]),
            AGENT_ORDER.index(item[0][1]),
        ),
    ):
        left_wins = sum(
            (match["winner"] == "first" and match["first_agent"] == left)
            or (match["winner"] == "second" and match["second_agent"] == left)
            for match in values
        )
        right_wins = sum(
            (match["winner"] == "first" and match["first_agent"] == right)
            or (match["winner"] == "second" and match["second_agent"] == right)
            for match in values
        )
        draws = len(values) - left_wins - right_wins
        rows.append(
            {
                "left_agent": left,
                "right_agent": right,
                "games": len(values),
                "left_wins": left_wins,
                "right_wins": right_wins,
                "draws": draws,
                "left_win_rate": left_wins / len(values),
                "right_win_rate": right_wins / len(values),
            }
        )
    return rows


def aggregate_by_seed(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[tuple[int, str], dict[str, int | str]] = {}
    for match in matches:
        seed = int(match["dictionary_seed"])
        for seat, agent in (
            ("first", str(match["first_agent"])),
            ("second", str(match["second_agent"])),
        ):
            key = (seed, agent)
            record = records.setdefault(
                key,
                {
                    "dictionary_seed": seed,
                    "agent": agent,
                    "games": 0,
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                },
            )
            record["games"] = int(record["games"]) + 1
            winner = str(match["winner"])
            if winner == seat:
                record["wins"] = int(record["wins"]) + 1
            elif winner == "draw":
                record["draws"] = int(record["draws"]) + 1
            else:
                record["losses"] = int(record["losses"]) + 1
    order = {agent: index for index, agent in enumerate(AGENT_ORDER)}
    rows: list[dict[str, Any]] = []
    for (_seed, _agent), record in sorted(
        records.items(),
        key=lambda item: (
            item[0][0],
            order.get(item[0][1], len(order)),
            item[0][1],
        ),
    ):
        games = int(record["games"])
        rows.append(
            {
                **record,
                "win_rate": int(record["wins"]) / games if games else 0.0,
            }
        )
    return rows


def generate_plots(output: Path, agents: list[dict[str, Any]]) -> list[str]:
    plt = ensure_matplotlib()
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    labels = [str(row["agent"]) for row in agents]
    created: list[str] = []

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
            label = f"{value:.1%}" if percent else f"{value:.3f}"
            ax.text(index, value, label, ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        path = plot_dir / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    bar("win_rate", [float(row["win_rate"]) for row in agents], "Win rate", percent=True)
    bar("first_win_rate", [float(row["first_win_rate"]) for row in agents], "First-seat win rate", percent=True)
    bar("second_win_rate", [float(row["second_win_rate"]) for row in agents], "Second-seat win rate", percent=True)
    bar("mean_decision_time", [float(row["mean_decision_time_sec"]) for row in agents], "Seconds")
    bar("mean_nodes", [float(row["mean_nodes_per_decision"]) for row in agents], "Nodes per decision")
    bar("mean_match_turns", [float(row["mean_match_turns"]) for row in agents], "Turns")
    return created


def generate_seed_plot(
    output: Path,
    seed_rows: list[dict[str, Any]],
) -> str:
    plt = ensure_matplotlib()
    plot_dir = output / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    agents = list(
        dict.fromkeys(str(row["agent"]) for row in seed_rows)
    )
    seeds = sorted({int(row["dictionary_seed"]) for row in seed_rows})
    values = {
        (int(row["dictionary_seed"]), str(row["agent"])): float(row["win_rate"])
        for row in seed_rows
    }
    fig, axes = plt.subplots(
        len(agents),
        1,
        figsize=(12, max(4.0, 2.8 * len(agents))),
        sharex=True,
    )
    if len(agents) == 1:
        axes = [axes]
    for axis, agent in zip(axes, agents):
        rates = [values.get((seed, agent), 0.0) for seed in seeds]
        bars = axis.bar(range(len(seeds)), rates)
        axis.set_title(agent)
        axis.set_ylabel("Win rate")
        axis.set_ylim(0.0, 1.12)
        axis.grid(axis="y", alpha=0.25)
        for bar, rate in zip(bars, rates):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                rate,
                f"{rate:.1%}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    axes[-1].set_xticks(range(len(seeds)), [str(seed) for seed in seeds])
    axes[-1].set_xlabel("Dictionary seed")
    fig.tight_layout()
    path = plot_dir / "win_rate_by_dictionary_seed.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def _percentage_change(value: float, baseline: float) -> float:
    return (value / baseline - 1.0) if baseline else 0.0


def write_report(
    output: Path,
    agents: list[dict[str, Any]],
    direct: list[dict[str, Any]],
    benchmark: list[dict[str, Any]],
    plots: list[str],
    dictionary_seed_count: int,
    seed_rows: list[dict[str, Any]],
) -> Path:
    agent_index = {row["agent"]: row for row in agents}
    benchmark_index = {row["agent"]: row for row in benchmark}
    lines = [
        "# D10000 ハイブリッドエージェント比較",
        "",
        f"対局は{dictionary_seed_count}辞書seed、先後入替、"
        "決定的組合せ1回、1手1秒で実施した。"
        "固定局面比較は全探索手法を深度5に揃えた。",
        "",
        "## 対局集計",
        "",
        "| agent | games | W-L-D | win | first | second | mean sec | max sec | nodes | depth | timeout |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in agents:
        lines.append(
            f"| {row['agent']} | {row['games']} | "
            f"{row['wins']}-{row['losses']}-{row['draws']} | "
            f"{row['win_rate']:.1%} | {row['first_win_rate']:.1%} | "
            f"{row['second_win_rate']:.1%} | "
            f"{row['mean_decision_time_sec']:.4f} | "
            f"{row['max_decision_time_sec']:.4f} | "
            f"{row['mean_nodes_per_decision']:.1f} | "
            f"{row['mean_effective_depth']:.2f} | {row['timeout_count']} |"
        )
    lines.extend(
        [
            "",
            "## 同一深度・固定局面での効果",
            "",
        ]
    )
    comparisons = (
        ("graph_pvs", "pvs", "Graph+PVS / PVS"),
        ("beam_alpha_beta", "beam_negamax", "Beam+AlphaBeta / Beam"),
        ("beam_alpha_beta", "alpha_beta", "Beam+AlphaBeta / AlphaBeta"),
        ("beam_pvs", "beam_negamax", "Beam+PVS / Beam"),
        ("beam_pvs", "pvs", "Beam+PVS / PVS"),
    )
    for hybrid, baseline, label in comparisons:
        left = benchmark_index[hybrid]
        right = benchmark_index[baseline]
        lines.append(
            f"- {label}: 時間変化 "
            f"{_percentage_change(float(left['mean_time_sec']), float(right['mean_time_sec'])):+.1%}、"
            f"ノード変化 "
            f"{_percentage_change(float(left['mean_nodes']), float(right['mean_nodes'])):+.1%}。"
        )
    graph = benchmark_index["graph_pvs"]
    lines.append(
        f"- Graph+PVSのGraph ordering時間は平均{graph['mean_graph_ordering_time_sec']:.4f}秒、"
        f"探索ノードで先頭候補を変更した割合は{graph['graph_ordering_changed_first_rate']:.1%}。"
    )
    for name in ("pvs", "graph_pvs", "beam_pvs"):
        if name not in agent_index:
            continue
        row = agent_index[name]
        lines.append(
            f"- {name} 対局中再探索率: {row['research_rate']:.1%} "
            f"({int(row['research_count'])}/{int(row['null_window_search_count'])})。"
        )
    lines.extend(
        [
            "",
            "## 直接対戦",
            "",
            "| left | right | games | left wins | right wins | draws |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in direct:
        lines.append(
            f"| {row['left_agent']} | {row['right_agent']} | {row['games']} | "
            f"{row['left_wins']} | {row['right_wins']} | {row['draws']} |"
        )
    seed_agents = list(
        dict.fromkeys(str(row["agent"]) for row in seed_rows)
    )
    seed_values = {
        (int(row["dictionary_seed"]), str(row["agent"])): row
        for row in seed_rows
    }
    seeds = sorted({int(row["dictionary_seed"]) for row in seed_rows})
    lines.extend(
        [
            "",
            "## 辞書seed別勝率",
            "",
            "| seed | " + " | ".join(seed_agents) + " |",
            "|---:|" + "|".join("---:" for _ in seed_agents) + "|",
        ]
    )
    for seed in seeds:
        rates = [
            float(seed_values[(seed, agent)]["win_rate"])
            for agent in seed_agents
        ]
        lines.append(
            f"| {seed} | "
            + " | ".join(f"{rate:.1%}" for rate in rates)
            + " |"
        )
    lines.extend(["", "## 図", ""])
    lines.extend(f"- `{path}`" for path in plots)
    report = output / "hybrid_comparison_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    matches = read_jsonl(args.input / "raw_matches.jsonl")
    if not matches:
        raise FileNotFoundError(f"no raw matches: {args.input}")
    benchmark_path = (
        args.benchmark / "summary.json"
        if args.benchmark.is_dir()
        else args.benchmark
    )
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    output = args.output or args.input / "hybrid_analysis"
    output.mkdir(parents=True, exist_ok=True)
    agents = aggregate_agents(matches)
    direct = direct_results(matches)
    seed_rows = aggregate_by_seed(matches)
    (output / "agent_summary.json").write_text(
        json.dumps(agents, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "direct_results.json").write_text(
        json.dumps(direct, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output / "agent_summary.csv", agents)
    write_csv(output / "direct_results.csv", direct)
    (output / "seed_summary.json").write_text(
        json.dumps(seed_rows, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    write_csv(output / "seed_summary.csv", seed_rows)
    plots = generate_plots(output, agents)
    plots.append(generate_seed_plot(output, seed_rows))
    dictionary_seed_count = len(
        {int(match["dictionary_seed"]) for match in matches}
    )
    report = write_report(
        output,
        agents,
        direct,
        benchmark,
        plots,
        dictionary_seed_count,
        seed_rows,
    )
    print(report)


if __name__ == "__main__":
    main()
