"""Aggregate and plot the existing-agent improvement experiment."""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from visualize import ensure_matplotlib


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
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


def _winner_agent(row: dict[str, Any]) -> str:
    return str(row[f"{row['winner']}_agent"])


def _agent_rows(
    matches: list[dict[str, Any]],
    *,
    group_field: str | None = None,
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, str], list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for row in matches:
        group_value = row[group_field] if group_field else "all"
        groups[(group_value, str(row["first_agent"]))].append((row, "first"))
        groups[(group_value, str(row["second_agent"]))].append((row, "second"))
    output: list[dict[str, Any]] = []
    for (group_value, agent), appearances in sorted(groups.items()):
        wins = sum(_winner_agent(row) == agent for row, _side in appearances)
        first = [(row, side) for row, side in appearances if side == "first"]
        second = [(row, side) for row, side in appearances if side == "second"]
        times = [
            float(row[f"{side}_avg_time_sec"]) for row, side in appearances
        ]
        result = {
            "agent": agent,
            "games": len(appearances),
            "wins": wins,
            "losses": len(appearances) - wins,
            "win_rate": wins / len(appearances),
            "first_games": len(first),
            "first_wins": sum(_winner_agent(row) == agent for row, _side in first),
            "second_games": len(second),
            "second_wins": sum(_winner_agent(row) == agent for row, _side in second),
            "mean_time_sec": statistics.fmean(times),
            "internal_timeout_count": sum(
                int(row[f"{side}_timeout_count"]) for row, side in appearances
            ),
        }
        result["first_win_rate"] = (
            result["first_wins"] / result["first_games"] if first else 0.0
        )
        result["second_win_rate"] = (
            result["second_wins"] / result["second_games"] if second else 0.0
        )
        if group_field:
            result = {group_field: group_value, **result}
        output.append(result)
    return output


def _seed_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in matches:
        grouped[int(row["seed"])].append(row)
    return [
        {
            "seed": seed,
            "matches": len(rows),
            "mean_turn_count": statistics.fmean(int(row["turn_count"]) for row in rows),
            "first_player_win_rate": statistics.fmean(
                row["winner"] == "first" for row in rows
            ),
            "internal_timeout_count": sum(
                int(row["first_timeout_count"]) + int(row["second_timeout_count"])
                for row in rows
            ),
        }
        for seed, rows in sorted(grouped.items())
    ]


def _pairwise_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matches:
        grouped[(str(row["first_agent"]), str(row["second_agent"]))].append(row)
    return [
        {
            "first_agent": first,
            "second_agent": second,
            "matches": len(rows),
            "first_wins": sum(row["winner"] == "first" for row in rows),
            "second_wins": sum(row["winner"] == "second" for row in rows),
            "first_win_rate": statistics.fmean(
                row["winner"] == "first" for row in rows
            ),
            "mean_turn_count": statistics.fmean(
                int(row["turn_count"]) for row in rows
            ),
        }
        for (first, second), rows in sorted(grouped.items())
    ]


def _equal_depth_metrics(root: Path) -> dict[str, Any]:
    payload = json.loads(
        (root / "equal_depth/fixed/benchmark.json").read_text(encoding="utf-8")
    )
    runs = payload["runs"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[str(row["agent"])].append(row)
    agent_metrics = [
        {
            "agent": agent,
            "mean_time_sec": statistics.fmean(
                float(row["elapsed_time_sec"]) for row in rows
            ),
            "median_time_sec": statistics.median(
                float(row["elapsed_time_sec"]) for row in rows
            ),
            "p95_time_sec": _nearest_rank(
                [float(row["elapsed_time_sec"]) for row in rows], 0.95
            ),
            "mean_nodes": statistics.fmean(
                int(row["nodes_searched"]) for row in rows
            ),
            "timeout_rate": statistics.fmean(bool(row["timed_out"]) for row in rows),
            "mean_research_rate": statistics.fmean(
                float(row["research_rate"]) for row in rows
            ),
        }
        for agent, rows in sorted(grouped.items())
    ]
    indexed = {
        (row["position_id"], row["repetition"], row["agent"]): row for row in runs
    }
    pairs = [
        (row, indexed[(row["position_id"], row["repetition"], "pvs")])
        for row in runs
        if row["agent"] == "alpha_beta"
        and (row["position_id"], row["repetition"], "pvs") in indexed
        and not row["timed_out"]
        and not indexed[(row["position_id"], row["repetition"], "pvs")]["timed_out"]
    ]
    return {
        "agents": agent_metrics,
        "alpha_beta_pvs_pair_count": len(pairs),
        "alpha_beta_pvs_move_agreement_rate": (
            statistics.fmean(
                left["selected_edge"] == right["selected_edge"]
                for left, right in pairs
            )
            if pairs
            else 0.0
        ),
    }


def _nearest_rank(values: list[float], rate: float) -> float:
    ordered = sorted(values)
    index = max(0, int(-(-len(ordered) * rate // 1)) - 1)
    return ordered[index]


def _save_bar(
    plt,
    labels: list[str],
    values: list[float],
    title: str,
    ylabel: str,
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_figures(
    root: Path,
    agent_summary: list[dict[str, Any]],
    by_size: list[dict[str, Any]],
    seed_summary: list[dict[str, Any]],
    equal_depth: dict[str, Any],
) -> None:
    plt = ensure_matplotlib()
    output = root / "figures"
    output.mkdir(parents=True, exist_ok=True)
    _save_bar(
        plt,
        [row["agent"] for row in agent_summary],
        [row["win_rate"] for row in agent_summary],
        "Final match win rate by agent",
        "Win rate",
        output / "agent_win_rate.png",
    )
    _save_bar(
        plt,
        [row["agent"] for row in agent_summary],
        [row["mean_time_sec"] for row in agent_summary],
        "Mean decision time by agent",
        "Seconds",
        output / "agent_mean_time.png",
    )
    _save_bar(
        plt,
        [row["agent"] for row in equal_depth["agents"]],
        [row["mean_nodes"] for row in equal_depth["agents"]],
        "Equal-depth mean searched nodes",
        "Nodes",
        output / "agent_mean_nodes.png",
    )
    _save_bar(
        plt,
        ["AB-PVS"],
        [equal_depth["alpha_beta_pvs_move_agreement_rate"]],
        "AlphaBeta and PVS move agreement",
        "Agreement rate",
        output / "alpha_beta_pvs_agreement.png",
    )
    pvs = next(row for row in equal_depth["agents"] if row["agent"] == "pvs")
    _save_bar(
        plt,
        ["PVS"],
        [pvs["mean_research_rate"]],
        "PVS re-search rate",
        "Rate",
        output / "pvs_research_rate.png",
    )

    retention = json.loads(
        (root / "beam_retention/beam_retention.json").read_text(encoding="utf-8")
    )["retention"]
    all_row = next(row for row in retention if row["risk_level"] == "all")
    widths = [2, 4, 8, 12, 16]
    _save_bar(
        plt,
        [str(width) for width in widths],
        [all_row[f"top_{width}_retention_rate"] for width in widths],
        "Beam reference-move retention by width",
        "Retention rate",
        output / "beam_retention_by_width.png",
    )
    risk_rows = [row for row in retention if row["risk_level"] != "all"]
    fig, ax = plt.subplots(figsize=(9, 5))
    for row in risk_rows:
        ax.plot(
            widths,
            [row[f"top_{width}_retention_rate"] for width in widths],
            marker="o",
            label=row["risk_level"],
        )
    ax.set_title("Beam reference-move retention by risk")
    ax.set_xlabel("Beam width")
    ax.set_ylabel("Retention rate")
    ax.set_xticks(widths)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "beam_retention_by_risk.png", dpi=180)
    plt.close(fig)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in by_size:
        grouped[str(row["agent"])].append(row)
    fig, ax = plt.subplots(figsize=(9, 5))
    for agent, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: int(row["dict_size"]))
        ax.plot(
            [int(row["dict_size"]) for row in rows],
            [float(row["win_rate"]) for row in rows],
            marker="o",
            label=agent,
        )
    ax.set_title("Win rate by dictionary size")
    ax.set_xlabel("Dictionary size")
    ax.set_ylabel("Win rate")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "win_rate_by_dictionary_size.png", dpi=180)
    plt.close(fig)

    _save_bar(
        plt,
        [str(row["seed"]) for row in seed_summary],
        [row["mean_turn_count"] for row in seed_summary],
        "Mean match length by seed",
        "Turns",
        output / "mean_turns_by_seed.png",
    )


def generate_analysis_outputs(root: Path) -> dict[str, Any]:
    """Create deterministic CSV/JSON summaries and report figures."""

    final_matches = json.loads(
        (root / "final/final_matches.json").read_text(encoding="utf-8")
    )
    for row in final_matches:
        row.setdefault("first_agent", "")
        row.setdefault("second_agent", "")
    agent_summary = _agent_rows(final_matches)
    by_size = _agent_rows(final_matches, group_field="dict_size")
    seed_summary = _seed_rows(final_matches)
    pairwise = _pairwise_rows(final_matches)
    equal_depth = _equal_depth_metrics(root)
    output = root / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "final_agent_summary.csv", agent_summary)
    _write_csv(output / "final_agent_by_size.csv", by_size)
    _write_csv(output / "final_seed_summary.csv", seed_summary)
    _write_csv(output / "final_pairwise.csv", pairwise)
    _write_csv(output / "equal_depth_agent_summary.csv", equal_depth["agents"])
    payload = {
        "agent_summary": agent_summary,
        "agent_by_size": by_size,
        "seed_summary": seed_summary,
        "pairwise": pairwise,
        "equal_depth": equal_depth,
        "match_count": len(final_matches),
        "match_timeout_count": sum(
            row["loss_reason"] in {"match_timeout", "match_time_limit"}
            for row in final_matches
        ),
        "invalid_move_count": sum(
            row["loss_reason"] == "invalid_move" for row in final_matches
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _save_figures(root, agent_summary, by_size, seed_summary, equal_depth)
    return payload


if __name__ == "__main__":
    experiment_root = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("results/existing_agent_improvement")
    )
    result = generate_analysis_outputs(experiment_root)
    print(f"matches={result['match_count']} output={experiment_root / 'analysis'}")
