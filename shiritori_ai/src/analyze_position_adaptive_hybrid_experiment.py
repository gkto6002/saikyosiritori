"""Analyze tuning, final-match, and fixed-position adaptive-hybrid results."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from adaptive_hybrid import AdaptiveHybridConfig
from run_graph_control_comparison import read_jsonl, write_csv
from run_position_adaptive_hybrid_experiment import NEW_AGENTS, PROFILES
from visualize import ensure_matplotlib


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return statistics.fmean(materialized) if materialized else 0.0


def _number(value: object) -> float:
    return 0.0 if value in (None, "") else float(value)


def _wilson(wins: int, games: int) -> tuple[float, float]:
    if games == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    p = wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    radius = (
        z
        * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games))
        / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def _two_sided_binomial_p(left_wins: int, right_wins: int) -> float:
    decisive = left_wins + right_wins
    if decisive == 0:
        return 1.0
    tail = min(left_wins, right_wins)
    probability = sum(
        math.comb(decisive, k) for k in range(tail + 1)
    ) / (2**decisive)
    return min(1.0, 2 * probability)


def _agent_turns(
    match: dict[str, Any], agent: str
) -> list[dict[str, Any]]:
    sides = []
    if match.get("first_agent") == agent:
        sides.append("first")
    if match.get("second_agent") == agent:
        sides.append("second")
    return [
        turn
        for turn in match.get("history", [])
        if turn.get("player") in sides
    ]


def summarize_agent(
    matches: list[dict[str, Any]], agent: str
) -> dict[str, Any]:
    relevant = [
        row
        for row in matches
        if agent in (row.get("first_agent"), row.get("second_agent"))
    ]
    wins = losses = draws = first_games = first_wins = second_games = second_wins = 0
    turns: list[dict[str, Any]] = []
    for match in relevant:
        side = "first" if match["first_agent"] == agent else "second"
        winner = match.get("winner")
        wins += int(winner == side)
        draws += int(winner == "draw")
        losses += int(winner not in {side, "draw"})
        first_games += int(side == "first")
        first_wins += int(side == "first" and winner == "first")
        second_games += int(side == "second")
        second_wins += int(side == "second" and winner == "second")
        turns.extend(_agent_turns(match, agent))
    low, high = _wilson(wins, len(relevant))
    mode_counts: Counter[str] = Counter()
    width_counts: Counter[str] = Counter()
    for turn in turns:
        turn_mode_counts = turn.get("mode_counts") or {}
        if turn_mode_counts:
            for key, value in turn_mode_counts.items():
                mode_counts[str(key)] += int(value)
        elif turn.get("search_mode"):
            mode_counts[str(turn["search_mode"])] += 1
        for key, value in (
            turn.get("dynamic_beam_width_counts") or {}
        ).items():
            width_counts[str(key)] += int(value)
    return {
        "agent": agent,
        "games": len(relevant),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": wins / len(relevant) if relevant else 0.0,
        "win_rate_ci95_low": low,
        "win_rate_ci95_high": high,
        "first_win_rate": first_wins / first_games if first_games else 0.0,
        "second_win_rate": second_wins / second_games if second_games else 0.0,
        "decision_count": len(turns),
        "mean_decision_time_sec": _mean(
            _number(turn.get("elapsed_time_sec")) for turn in turns
        ),
        "max_decision_time_sec": max(
            (_number(turn.get("elapsed_time_sec")) for turn in turns),
            default=0.0,
        ),
        "timeout_count": sum(bool(turn.get("timed_out")) for turn in turns),
        "mean_nodes": _mean(
            _number(turn.get("nodes_searched")) for turn in turns
        ),
        "mean_effective_depth": _mean(
            _number(turn.get("effective_depth"))
            for turn in turns
            if turn.get("effective_depth") not in (None, "")
        ),
        "depth_change_count": sum(
            bool(turn.get("depth_changed")) for turn in turns
        ),
        "mode_switch_count": sum(
            int(_number(turn.get("mode_switch_count"))) for turn in turns
        ),
        "fallback_count": sum(
            int(_number(turn.get("fallback_count"))) for turn in turns
        ),
        "exact_attempt_count": sum(
            int(_number(turn.get("exact_attempt_count"))) for turn in turns
        ),
        "exact_success_count": sum(
            int(_number(turn.get("exact_success_count"))) for turn in turns
        ),
        "exact_timeout_count": sum(
            int(_number(turn.get("exact_timeout_count"))) for turn in turns
        ),
        "exact_limit_count": sum(
            int(_number(turn.get("exact_limit_count"))) for turn in turns
        ),
        "null_window_search_count": sum(
            int(_number(turn.get("null_window_search_count"))) for turn in turns
        ),
        "research_count": sum(
            int(_number(turn.get("research_count"))) for turn in turns
        ),
        "beam_pruned_move_count": sum(
            int(_number(turn.get("beam_pruned_move_count"))) for turn in turns
        ),
        "mode_counts": dict(sorted(mode_counts.items())),
        "dynamic_beam_width_counts": dict(sorted(width_counts.items())),
    }


def adaptive_detail_rows(
    matches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    mode_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    widths: Counter[tuple[str, str]] = Counter()
    exact_rows: list[dict[str, Any]] = []
    for match in matches:
        for turn in match.get("history", []):
            agent = str(turn.get("agent", ""))
            mode = str(turn.get("search_mode") or "unreported")
            mode_groups[(agent, mode)].append(turn)
            for key, value in (
                turn.get("dynamic_beam_width_counts") or {}
            ).items():
                widths[(agent, str(key))] += int(value)
            if _number(turn.get("exact_attempt_count")):
                scale = turn.get("position_scale") or {}
                exact_rows.append(
                    {
                        "match_id": match.get("match_id", ""),
                        "turn": turn.get("turn", ""),
                        "agent": agent,
                        "result": turn.get("exact_result", ""),
                        "success": int(
                            _number(turn.get("exact_success_count"))
                        ),
                        "timeout": int(
                            _number(turn.get("exact_timeout_count"))
                        ),
                        "limit_exceeded": int(
                            _number(turn.get("exact_limit_count"))
                        ),
                        "states": int(
                            _number(turn.get("exact_state_count"))
                        ),
                        "reachable_words": scale.get(
                            "reachable_word_count", ""
                        ),
                        "reachable_edge_types": scale.get(
                            "reachable_edge_types", ""
                        ),
                        "reachable_vertices": scale.get(
                            "reachable_vertices", ""
                        ),
                        "estimated_states": scale.get(
                            "estimated_state_count", ""
                        ),
                    }
                )
    mode_rows = []
    for (agent, mode), turns in sorted(mode_groups.items()):
        scales = [turn.get("position_scale") or {} for turn in turns]
        null_searches = sum(
            _number(turn.get("null_window_search_count")) for turn in turns
        )
        researches = sum(
            _number(turn.get("research_count")) for turn in turns
        )
        mode_rows.append(
            {
                "agent": agent,
                "search_mode": mode,
                "decision_count": len(turns),
                "mean_legal_edge_types": _mean(
                    _number(scale.get("legal_edge_types")) for scale in scales
                ),
                "mean_legal_word_count": _mean(
                    _number(scale.get("legal_word_count")) for scale in scales
                ),
                "mean_safe_word_count": _mean(
                    _number(scale.get("safe_word_count")) for scale in scales
                ),
                "mean_reachable_word_count": _mean(
                    _number(scale.get("reachable_word_count"))
                    for scale in scales
                ),
                "mean_decision_time_sec": _mean(
                    _number(turn.get("elapsed_time_sec")) for turn in turns
                ),
                "mean_nodes": _mean(
                    _number(turn.get("nodes_searched")) for turn in turns
                ),
                "research_rate": researches / null_searches
                if null_searches
                else 0.0,
            }
        )
    width_rows = [
        {"agent": agent, "ply_and_width": key, "use_count": count}
        for (agent, key), count in sorted(widths.items())
    ]
    return mode_rows, width_rows, exact_rows


def direct_results(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        left, right = sorted(
            (str(match["first_agent"]), str(match["second_agent"]))
        )
        groups[(left, right)].append(match)
    rows = []
    for (left, right), values in sorted(groups.items()):
        left_wins = sum(
            (row["winner"] == "first" and row["first_agent"] == left)
            or (row["winner"] == "second" and row["second_agent"] == left)
            for row in values
        )
        right_wins = sum(
            (row["winner"] == "first" and row["first_agent"] == right)
            or (row["winner"] == "second" and row["second_agent"] == right)
            for row in values
        )
        decisive = left_wins + right_wins
        low, high = _wilson(left_wins, decisive)
        rows.append(
            {
                "left_agent": left,
                "right_agent": right,
                "games": len(values),
                "left_wins": left_wins,
                "right_wins": right_wins,
                "draws": len(values) - decisive,
                "left_decisive_win_rate": (
                    left_wins / decisive if decisive else 0.0
                ),
                "ci95_low": low,
                "ci95_high": high,
                "two_sided_binomial_p": _two_sided_binomial_p(
                    left_wins, right_wins
                ),
            }
        )
    return rows


def anchor_results(
    matches: list[dict[str, Any]],
    anchor: str = "beam_alpha_beta",
) -> list[dict[str, Any]]:
    opponents = sorted(
        {
            str(row["first_agent"])
            if row["second_agent"] == anchor
            else str(row["second_agent"])
            for row in matches
            if anchor in (row["first_agent"], row["second_agent"])
            and row["first_agent"] != row["second_agent"]
        }
    )
    output = []
    for opponent in opponents:
        values = [
            row
            for row in matches
            if {row["first_agent"], row["second_agent"]}
            == {anchor, opponent}
        ]
        wins = sum(
            (row["winner"] == "first" and row["first_agent"] == opponent)
            or (row["winner"] == "second" and row["second_agent"] == opponent)
            for row in values
        )
        anchor_wins = sum(
            (row["winner"] == "first" and row["first_agent"] == anchor)
            or (row["winner"] == "second" and row["second_agent"] == anchor)
            for row in values
        )
        decisive = wins + anchor_wins
        low, high = _wilson(wins, decisive)
        output.append(
            {
                "agent": opponent,
                "reference_agent": anchor,
                "games": len(values),
                "wins": wins,
                "reference_wins": anchor_wins,
                "draws": len(values) - decisive,
                "decisive_win_rate": wins / decisive if decisive else 0.0,
                "ci95_low": low,
                "ci95_high": high,
                "two_sided_binomial_p": _two_sided_binomial_p(
                    wins, anchor_wins
                ),
            }
        )
    return output


def tuning_summary(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for profile in PROFILES:
        profile_matches = [
            row for row in matches if row.get("profile_name") == profile
        ]
        agent_rows = [
            summarize_agent(profile_matches, agent) for agent in NEW_AGENTS
        ]
        total_games = sum(int(row["games"]) for row in agent_rows)
        total_wins = sum(int(row["wins"]) for row in agent_rows)
        decisions = sum(int(row["decision_count"]) for row in agent_rows)
        rows.append(
            {
                "profile": profile,
                "new_agent_games": total_games,
                "new_agent_wins": total_wins,
                "new_agent_win_rate": total_wins / total_games
                if total_games
                else 0.0,
                "mean_decision_time_sec": (
                    sum(
                        float(row["mean_decision_time_sec"])
                        * int(row["decision_count"])
                        for row in agent_rows
                    )
                    / decisions
                    if decisions
                    else 0.0
                ),
                "timeout_count": sum(
                    int(row["timeout_count"]) for row in agent_rows
                ),
                "fallback_count": sum(
                    int(row["fallback_count"]) for row in agent_rows
                ),
            }
        )
    return rows


def tuning_agent_summary(
    matches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    agent_rows: list[dict[str, Any]] = []
    matchup_rows: list[dict[str, Any]] = []
    for profile in PROFILES:
        profile_matches = [
            row for row in matches if row.get("profile_name") == profile
        ]
        for agent in NEW_AGENTS:
            summary = summarize_agent(profile_matches, agent)
            agent_rows.append(
                {
                    "profile": profile,
                    **{
                        key: value
                        for key, value in summary.items()
                        if key
                        not in {
                            "mode_counts",
                            "dynamic_beam_width_counts",
                        }
                    },
                }
            )
        for row in anchor_results(profile_matches):
            matchup_rows.append({"profile": profile, **row})
    return agent_rows, matchup_rows


def select_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if int(row["new_agent_games"]) > 0]
    if not complete:
        raise ValueError("no completed tuning matches")
    winner = min(
        complete,
        key=lambda row: (
            -float(row["new_agent_win_rate"]),
            int(row["timeout_count"]),
            float(row["mean_decision_time_sec"]),
            str(row["profile"]),
        ),
    )
    name = str(winner["profile"])
    return {
        "selected_profile": name,
        "selection_rule": (
            "max aggregate win rate vs beam_alpha_beta, then fewer "
            "timeouts, then lower mean decision time"
        ),
        "selection_metrics": winner,
        "config": asdict(PROFILES[name]),
    }


def fixed_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["agent"])].append(row)
    return [
        {
            "agent": agent,
            "positions": len(values),
            "legal_decision_rate": _mean(
                float(
                    row.get("start_id") is not None
                    and row.get("end_id") is not None
                )
                for row in values
            ),
            "mean_elapsed_time_sec": _mean(
                _number(row.get("elapsed_time_sec")) for row in values
            ),
            "mean_nodes": _mean(
                _number(row.get("nodes_searched")) for row in values
            ),
            "mean_effective_depth": _mean(
                _number(row.get("effective_depth")) for row in values
            ),
        }
        for agent, values in sorted(grouped.items())
    ]


def fixed_agreement(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = {
        str(row["position_id"]): (
            row.get("start_id"),
            row.get("end_id"),
        )
        for row in rows
        if row.get("agent") == "beam_alpha_beta"
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("agent") != "beam_alpha_beta":
            grouped[str(row["agent"])].append(row)
    output = []
    for agent, values in sorted(grouped.items()):
        paired = [
            row for row in values if str(row["position_id"]) in baseline
        ]
        same = sum(
            (row.get("start_id"), row.get("end_id"))
            == baseline[str(row["position_id"])]
            for row in paired
        )
        output.append(
            {
                "agent": agent,
                "reference_agent": "beam_alpha_beta",
                "paired_positions": len(paired),
                "same_move_count": same,
                "same_move_rate": same / len(paired) if paired else 0.0,
            }
        )
    return output


def _annotated_bar(
    path: Path,
    labels: list[str],
    values: list[float],
    title: str,
    ylabel: str,
    *,
    percent: bool = False,
) -> None:
    if not labels:
        return
    plt = ensure_matplotlib()
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.2), 5.5))
    bars = ax.bar(labels, values, color="#377eb8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=35)
    if percent:
        ax.set_ylim(0, max(1.0, max(values) * 1.15))
    for bar, value in zip(bars, values):
        label = f"{value * 100:.1f}%" if percent else f"{value:.3f}"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            label,
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_report(
    output: Path,
    stage: str,
    agents: list[dict[str, Any]],
    direct: list[dict[str, Any]],
) -> None:
    lines = [
        "# Position-adaptive hybrid analysis",
        "",
        f"- stage: `{stage}`",
        f"- completed matches/decisions were read from the parent run directory",
        "",
        "## Agent summary",
        "",
        "| agent | games | wins | win rate | mean time (s) | mean depth | exact success |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in agents:
        lines.append(
            f"| {row['agent']} | {row.get('games', 0)} | "
            f"{row.get('wins', 0)} | {float(row.get('win_rate', 0)):.3f} | "
            f"{float(row.get('mean_decision_time_sec', 0)):.4f} | "
            f"{float(row.get('mean_effective_depth', 0)):.2f} | "
            f"{row.get('exact_success_count', 0)} |"
        )
    if direct:
        lines.extend(
            [
                "",
                "## Direct matchups",
                "",
                "| left | right | W-L-D | left decisive rate | exact binomial p |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for row in direct:
            lines.append(
                f"| {row['left_agent']} | {row['right_agent']} | "
                f"{row['left_wins']}-{row['right_wins']}-{row['draws']} | "
                f"{float(row['left_decisive_win_rate']):.3f} | "
                f"{float(row['two_sided_binomial_p']):.4f} |"
            )
    lines.extend(
        [
            "",
            "Wilson 95% intervals and exact two-sided binomial p-values are "
            "descriptive; tuning and final seeds are separated to reduce "
            "selection bias.",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(run_dir: Path, output: Path | None = None) -> Path:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage = str(manifest["config"]["stage"])
    destination = (output or run_dir / "analysis").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if stage == "fixed":
        rows = read_jsonl(run_dir / "fixed_runs.jsonl")
        summary = fixed_summary(rows)
        agreement = fixed_agreement(rows)
        write_csv(destination / "fixed_summary.csv", summary)
        write_csv(destination / "fixed_move_agreement.csv", agreement)
        (destination / "fixed_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        _annotated_bar(
            destination / "fixed_mean_time.png",
            [str(row["agent"]) for row in summary],
            [float(row["mean_elapsed_time_sec"]) for row in summary],
            "Fixed-position mean decision time",
            "seconds",
        )
        return destination

    matches = read_jsonl(run_dir / "raw_matches.jsonl")
    if not matches:
        raise ValueError("no match results found")
    names = sorted(
        {
            str(row[field])
            for row in matches
            for field in ("first_agent", "second_agent")
        }
    )
    agent_rows = [summarize_agent(matches, name) for name in names]
    direct = direct_results(matches)
    anchor = anchor_results(matches)
    mode_rows, width_rows, exact_rows = adaptive_detail_rows(matches)
    write_csv(
        destination / "agent_summary.csv",
        [
            {
                key: value
                for key, value in row.items()
                if key not in {"mode_counts", "dynamic_beam_width_counts"}
            }
            for row in agent_rows
        ],
    )
    write_csv(destination / "direct_matchups.csv", direct)
    write_csv(destination / "vs_beam_alpha_beta.csv", anchor)
    write_csv(destination / "mode_usage.csv", mode_rows)
    write_csv(destination / "dynamic_beam_width_usage.csv", width_rows)
    write_csv(destination / "exact_attempts.csv", exact_rows)
    (destination / "agent_summary.json").write_text(
        json.dumps(agent_rows, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if stage == "tune":
        tune = tuning_summary(matches)
        tune_agents, tune_matchups = tuning_agent_summary(matches)
        write_csv(destination / "tuning_summary.csv", tune)
        write_csv(destination / "tuning_agent_summary.csv", tune_agents)
        write_csv(destination / "tuning_matchups.csv", tune_matchups)
        completion_path = run_dir / "completion.json"
        completion = (
            json.loads(completion_path.read_text(encoding="utf-8"))
            if completion_path.is_file()
            else {"complete": True}
        )
        if completion.get("complete"):
            selected = select_profile(tune)
            (destination / "selected_profile.json").write_text(
                json.dumps(
                    selected, ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            (destination / "selection_pending.json").write_text(
                json.dumps(
                    {
                        "reason": "tuning_run_incomplete",
                        "completed_match_count": completion.get(
                            "completed_match_count", 0
                        ),
                        "expected_match_count": completion.get(
                            "expected_match_count", 0
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    _annotated_bar(
        destination / "win_rate.png",
        [str(row["agent"]) for row in agent_rows],
        [float(row["win_rate"]) for row in agent_rows],
        "Win rate",
        "win rate",
        percent=True,
    )
    _annotated_bar(
        destination / "vs_beam_alpha_beta_win_rate.png",
        [str(row["agent"]) for row in anchor],
        [float(row["decisive_win_rate"]) for row in anchor],
        "Direct win rate vs BeamAlphaBeta",
        "decisive win rate",
        percent=True,
    )
    _annotated_bar(
        destination / "mean_decision_time.png",
        [str(row["agent"]) for row in agent_rows],
        [float(row["mean_decision_time_sec"]) for row in agent_rows],
        "Mean decision time",
        "seconds",
    )
    exact_agents = [
        row for row in agent_rows if int(row["exact_attempt_count"]) > 0
    ]
    _annotated_bar(
        destination / "exact_success_rate.png",
        [str(row["agent"]) for row in exact_agents],
        [
            int(row["exact_success_count"]) / int(row["exact_attempt_count"])
            for row in exact_agents
        ],
        "Exact-search completion rate",
        "completion rate",
        percent=True,
    )
    _write_report(destination, stage, agent_rows, direct)
    return destination


def main() -> None:
    args = parse_args()
    try:
        print(analyze(args.input, args.output))
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
