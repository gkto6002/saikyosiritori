"""Aggregate, plot, and report GraphControlAgent comparison results."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from agents import AlphaBetaAgent, GreedyAgent
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_FEATURES = (
    "reachable_char_count",
    "reachable_edge_count",
    "scc_vertex_count",
    "scc_internal_edge_count",
    "scc_exit_edge_count",
)
LOCAL_FEATURES = (
    "legal_word_count",
    "safe_word_count",
    "dangerous_word_count",
    "depth2_char_count",
    "depth3_char_count",
    "low_out_degree_reach_rate",
    "dead_end_reach_rate",
    "destination_count",
    "destination_concentration",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: Iterable[float], rate: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(len(ordered) * rate) - 1)]


def wilson_interval(wins: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = wins / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def variance(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return statistics.pvariance(data) if len(data) > 1 else 0.0


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or variance(xs) == 0 or variance(ys) == 0:
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    covariance = statistics.fmean(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
    )
    return covariance / (statistics.pstdev(xs) * statistics.pstdev(ys))


def remaining_bin(rate: float) -> str:
    if rate > 0.8:
        return "80-100%"
    if rate > 0.6:
        return "60-80%"
    if rate > 0.4:
        return "40-60%"
    if rate > 0.2:
        return "20-40%"
    return "0-20%"


def appearances(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        for side in ("first", "second"):
            opponent_side = "second" if side == "first" else "first"
            won = match["winner"] == side
            draw = match["winner"] == "draw"
            turns = [
                turn
                for turn in match["history"]
                if turn["player"] == side
            ]
            times = [float(turn["elapsed_time_sec"]) for turn in turns]
            rows.append(
                {
                    "match_id": match["match_id"],
                    "dict_size": int(match["dict_size"]),
                    "dictionary_seed": int(match["dictionary_seed"]),
                    "repetition": int(match["repetition"]),
                    "agent": match[f"{side}_agent"],
                    "opponent": match[f"{opponent_side}_agent"],
                    "seat": side,
                    "won": won,
                    "draw": draw,
                    "turn_count": int(match["turn_count"]),
                    "mean_time_sec": statistics.fmean(times) if times else 0.0,
                    "median_time_sec": statistics.median(times) if times else 0.0,
                    "p95_time_sec": percentile(times, 0.95),
                    "max_time_sec": max(times, default=0.0),
                    "timeout_count": int(match[f"{side}_timeout_count"]),
                    "invalid_move_count": (
                        int(match["invalid_move_count"])
                        if not draw and not won
                        else 0
                    ),
                    "move_count": len(turns),
                    "nodes_searched": sum(
                        float(turn["nodes_searched"])
                        for turn in turns
                        if turn.get("nodes_searched") not in ("", None)
                    ),
                    "candidate_evaluations": sum(
                        float(turn["ordering_evaluations"])
                        for turn in turns
                        if turn.get("ordering_evaluations") not in ("", None)
                    ),
                }
            )
    return rows


def summarize(
    rows: list[dict[str, Any]], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        wins = sum(bool(row["won"]) for row in values)
        draws = sum(bool(row["draw"]) for row in values)
        low, high = wilson_interval(wins, len(values))
        move_count = sum(int(row["move_count"]) for row in values)
        result = dict(zip(fields, key))
        result.update(
            {
                "games": len(values),
                "wins": wins,
                "losses": len(values) - wins - draws,
                "draws": draws,
                "win_rate": wins / len(values),
                "win_rate_ci95_low": low,
                "win_rate_ci95_high": high,
                "mean_match_turns": statistics.fmean(
                    int(row["turn_count"]) for row in values
                ),
                "mean_time_sec": (
                    sum(float(row["mean_time_sec"]) * int(row["move_count"]) for row in values)
                    / move_count
                    if move_count
                    else 0.0
                ),
                "timeout_count": sum(int(row["timeout_count"]) for row in values),
                "invalid_move_count": sum(
                    int(row["invalid_move_count"]) for row in values
                ),
                "nodes_per_move": (
                    sum(float(row["nodes_searched"]) for row in values) / move_count
                    if move_count
                    else 0.0
                ),
                "candidate_evaluations_per_move": (
                    sum(float(row["candidate_evaluations"]) for row in values)
                    / move_count
                    if move_count
                    else 0.0
                ),
            }
        )
        output.append(result)
    return output


def aggregate_matches(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    app = appearances(matches)
    overall = summarize(app, ("agent",))
    non_random_app = [
        row
        for row in app
        if row["agent"] != "random" and row["opponent"] != "random"
    ]
    overall_without_random = summarize(non_random_app, ("agent",))
    by_seat = summarize(app, ("agent", "seat"))
    by_size = summarize(app, ("dict_size", "agent"))
    by_seed = summarize(app, ("dict_size", "dictionary_seed", "agent"))
    by_opponent = summarize(app, ("agent", "opponent"))

    pair_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in app:
        pair_groups[(row["agent"], row["opponent"])].append(row)
    direct = summarize(app, ("agent", "opponent"))

    timing = []
    for agent in sorted({row["agent"] for row in app}):
        agent_rows = [row for row in app if row["agent"] == agent]
        turn_times = [
            float(turn["elapsed_time_sec"])
            for match in matches
            for turn in match["history"]
            if turn["agent"] == agent
        ]
        timing.append(
            {
                "agent": agent,
                "move_count": len(turn_times),
                "mean_time_sec": statistics.fmean(turn_times) if turn_times else 0.0,
                "median_time_sec": statistics.median(turn_times) if turn_times else 0.0,
                "p95_time_sec": percentile(turn_times, 0.95),
                "max_time_sec": max(turn_times, default=0.0),
                "timeout_count": sum(row["timeout_count"] for row in agent_rows),
            }
        )

    length_outcome = []
    for agent in sorted({row["agent"] for row in app}):
        for outcome, predicate in (
            ("win", lambda row: row["won"]),
            ("loss", lambda row: not row["won"] and not row["draw"]),
        ):
            selected = [row for row in app if row["agent"] == agent and predicate(row)]
            length_outcome.append(
                {
                    "agent": agent,
                    "outcome": outcome,
                    "games": len(selected),
                    "mean_turns": (
                        statistics.fmean(row["turn_count"] for row in selected)
                        if selected
                        else 0.0
                    ),
                }
            )

    paired = []
    paired_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        pair = tuple(sorted((match["first_agent"], match["second_agent"])))
        key = (
            int(match["dict_size"]),
            int(match["dictionary_seed"]),
            int(match["repetition"]),
            pair[0],
            pair[1],
        )
        paired_groups[key].append(match)
    for key, values in sorted(paired_groups.items(), key=lambda item: str(item[0])):
        paired.append(
            {
                "dict_size": key[0],
                "dictionary_seed": key[1],
                "repetition": key[2],
                "agent_a": key[3],
                "agent_b": key[4],
                "seat_order_games": len(values),
                "complete_seat_pair": len(values) == 2,
                "agent_a_wins": sum(
                    (
                        row["winner"] == "first"
                        and row["first_agent"] == key[3]
                    )
                    or (
                        row["winner"] == "second"
                        and row["second_agent"] == key[3]
                    )
                    for row in values
                ),
            }
        )
    return {
        "overall": overall,
        "overall_without_random": overall_without_random,
        "by_seat": by_seat,
        "by_size": by_size,
        "by_seed": by_seed,
        "by_opponent": by_opponent,
        "direct": direct,
        "timing": timing,
        "length_outcome": length_outcome,
        "paired_conditions": paired,
        "appearances": app,
    }


def flatten_turns(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for match in matches:
        for turn in match["history"]:
            rows.append(
                {
                    "match_id": match["match_id"],
                    "dict_size": match["dict_size"],
                    "dictionary_seed": match["dictionary_seed"],
                    "winner": match["winner"],
                    **{
                        key: value
                        for key, value in turn.items()
                        if key != "decision_extra"
                    },
                }
            )
    return rows


def _candidate_feature_variances(
    detail: dict[str, Any]
) -> dict[str, float]:
    candidates = detail["candidates"]
    keys = sorted(
        {
            key
            for candidate in candidates
            for key in candidate.get("normalized", {})
        }
    )
    return {
        key: variance(candidate["normalized"][key] for candidate in candidates)
        for key in keys
    }


def analyze_graph_details(
    details: list[dict[str, Any]],
    agreements: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]] | dict[str, Any]]:
    agreement_by_key = {
        (row["match_id"], int(row["turn"])): row for row in agreements
    }
    per_turn = []
    feature_variance_rows = []
    selected_feature_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    outcome_feature_groups: dict[tuple[str, bool], list[float]] = defaultdict(list)
    correlations: dict[str, tuple[list[float], list[float]]] = {}
    contribution_counts: dict[str, int] = defaultdict(int)

    for detail in details:
        candidates = detail["candidates"]
        if not candidates:
            continue
        selected = next(candidate for candidate in candidates if candidate["selected"])
        summary = detail["summary"]
        feature_variances = _candidate_feature_variances(detail)
        global_diff = any(feature_variances.get(key, 0.0) > 1e-15 for key in GLOBAL_FEATURES)
        local_diff = any(feature_variances.get(key, 0.0) > 1e-15 for key in LOCAL_FEATURES)
        contribution = (
            "both"
            if global_diff and local_diff
            else "global_only"
            if global_diff
            else "local_only"
            if local_diff
            else "neither"
        )
        contribution_counts[contribution] += 1
        agreement = agreement_by_key.get((detail["match_id"], int(detail["turn"])), {})
        max_reachable = max(
            float(candidate["raw"]["reachable_edge_count"]) for candidate in candidates
        )
        reachable_edge_range = (
            max(float(candidate["raw"]["reachable_edge_count"]) for candidate in candidates)
            - min(float(candidate["raw"]["reachable_edge_count"]) for candidate in candidates)
        )
        row = {
            "match_id": detail["match_id"],
            "turn": detail["turn"],
            "dict_size": detail["dict_size"],
            "remaining_bin": remaining_bin(float(detail["remaining_word_rate"])),
            "remaining_word_rate": detail["remaining_word_rate"],
            "graph_control_won": detail["graph_control_won"],
            "candidate_count": len(candidates),
            "score_range": summary.get(
                "structural_score_range", summary["score_range"]
            ),
            "score_stddev": summary.get(
                "structural_score_stddev", summary["score_stddev"]
            ),
            "best_score_tie_count": summary.get(
                "structural_best_score_tie_count",
                summary["best_score_tie_count"],
            ),
            "distinct_score_count": summary.get(
                "structural_distinct_score_count",
                summary["distinct_score_count"],
            ),
            "all_candidates_tied": summary.get(
                "structural_all_candidates_tied",
                summary["all_candidates_tied"],
            ),
            "all_candidate_score_range_including_terminal": summary[
                "score_range"
            ],
            "scc_nearly_whole": (
                float(selected["normalized"]["scc_vertex_count"]) >= 0.95
            ),
            "reachable_chars_all_same": (
                feature_variances.get("reachable_char_count", 0.0) == 0
            ),
            "reachable_edges_nearly_same": (
                reachable_edge_range / max(1.0, max_reachable) <= 0.01
            ),
            "feature_contribution": contribution,
            "greedy_agreement": agreement.get("greedy_agreement"),
            "alpha_beta_agreement": agreement.get("alpha_beta_agreement"),
            "evaluation_time_sec": summary["evaluation_time_sec"],
            "scc_time_sec": summary["scc_time_sec"],
            "reachability_time_sec": summary["reachability_time_sec"],
            "local_time_sec": summary["local_time_sec"],
        }
        per_turn.append(row)

        for key, value in feature_variances.items():
            feature_variance_rows.append(
                {
                    "match_id": detail["match_id"],
                    "turn": detail["turn"],
                    "remaining_bin": row["remaining_bin"],
                    "feature": key,
                    "variance": value,
                }
            )
        for candidate in candidates:
            selected_label = "selected" if candidate["selected"] else "not_selected"
            for key, value in candidate["normalized"].items():
                selected_feature_groups[(key, selected_label)].append(float(value))
                outcome_feature_groups[(key, bool(detail["graph_control_won"]))].append(
                    float(value)
                )
                if not candidate["immediate_win"] and not candidate["immediate_loss"]:
                    xs, ys = correlations.setdefault(key, ([], []))
                    xs.append(float(value))
                    ys.append(float(candidate["score"]))

    bin_rows = []
    order = ("80-100%", "60-80%", "40-60%", "20-40%", "0-20%")
    for bin_name in order:
        values = [row for row in per_turn if row["remaining_bin"] == bin_name]
        if not values:
            continue
        greedy = [row for row in values if row["greedy_agreement"] is not None]
        alpha = [row for row in values if row["alpha_beta_agreement"] is not None]
        bin_rows.append(
            {
                "remaining_bin": bin_name,
                "turns": len(values),
                "mean_score_range": statistics.fmean(row["score_range"] for row in values),
                "mean_score_stddev": statistics.fmean(row["score_stddev"] for row in values),
                "mean_best_score_tie_count": statistics.fmean(
                    row["best_score_tie_count"] for row in values
                ),
                "mean_distinct_score_count": statistics.fmean(
                    row["distinct_score_count"] for row in values
                ),
                "all_candidates_tied_rate": statistics.fmean(
                    bool(row["all_candidates_tied"]) for row in values
                ),
                "greedy_agreement_rate": (
                    statistics.fmean(bool(row["greedy_agreement"]) for row in greedy)
                    if greedy
                    else None
                ),
                "greedy_reference_positions": len(greedy),
                "alpha_beta_agreement_rate": (
                    statistics.fmean(bool(row["alpha_beta_agreement"]) for row in alpha)
                    if alpha
                    else None
                ),
                "alpha_beta_reference_positions": len(alpha),
            }
        )

    feature_variance_summary = []
    for feature in sorted({row["feature"] for row in feature_variance_rows}):
        values = [
            row["variance"]
            for row in feature_variance_rows
            if row["feature"] == feature
        ]
        feature_variance_summary.append(
            {
                "feature": feature,
                "positions": len(values),
                "mean_candidate_variance": statistics.fmean(values),
                "median_candidate_variance": statistics.median(values),
                "nonzero_variance_rate": statistics.fmean(value > 1e-15 for value in values),
            }
        )

    selected_comparison = []
    for feature in sorted({key[0] for key in selected_feature_groups}):
        selected_values = selected_feature_groups[(feature, "selected")]
        other_values = selected_feature_groups[(feature, "not_selected")]
        selected_comparison.append(
            {
                "feature": feature,
                "selected_mean": statistics.fmean(selected_values),
                "not_selected_mean": (
                    statistics.fmean(other_values) if other_values else 0.0
                ),
                "difference": (
                    statistics.fmean(selected_values)
                    - statistics.fmean(other_values)
                    if other_values
                    else 0.0
                ),
            }
        )

    outcome_comparison = []
    for feature in sorted({key[0] for key in outcome_feature_groups}):
        wins = outcome_feature_groups[(feature, True)]
        losses = outcome_feature_groups[(feature, False)]
        outcome_comparison.append(
            {
                "feature": feature,
                "winning_turn_candidate_mean": statistics.fmean(wins) if wins else 0.0,
                "losing_turn_candidate_mean": statistics.fmean(losses) if losses else 0.0,
                "difference": (
                    statistics.fmean(wins) - statistics.fmean(losses)
                    if wins and losses
                    else 0.0
                ),
            }
        )

    correlation_rows = [
        {
            "feature": feature,
            "candidate_count": len(values[0]),
            "pearson_correlation_with_score": correlation(*values),
        }
        for feature, values in sorted(correlations.items())
    ]
    timing_rows = []
    for field in (
        "evaluation_time_sec",
        "scc_time_sec",
        "reachability_time_sec",
        "local_time_sec",
    ):
        values = [float(row[field]) for row in per_turn]
        timing_rows.append(
            {
                "component": field,
                "mean_time_sec": statistics.fmean(values) if values else 0.0,
                "median_time_sec": statistics.median(values) if values else 0.0,
                "p95_time_sec": percentile(values, 0.95),
                "total_time_sec": sum(values),
            }
        )
    total_positions = max(1, len(per_turn))
    contribution_rows = [
        {
            "contribution": name,
            "positions": contribution_counts[name],
            "rate": contribution_counts[name] / total_positions,
        }
        for name in ("global_only", "local_only", "both", "neither")
    ]
    headline = {
        "positions": len(per_turn),
        "all_candidates_tied_rate": (
            statistics.fmean(bool(row["all_candidates_tied"]) for row in per_turn)
            if per_turn
            else 0.0
        ),
        "scc_nearly_whole_rate": (
            statistics.fmean(bool(row["scc_nearly_whole"]) for row in per_turn)
            if per_turn
            else 0.0
        ),
        "reachable_chars_all_same_rate": (
            statistics.fmean(
                bool(row["reachable_chars_all_same"]) for row in per_turn
            )
            if per_turn
            else 0.0
        ),
        "reachable_edges_nearly_same_rate": (
            statistics.fmean(
                bool(row["reachable_edges_nearly_same"]) for row in per_turn
            )
            if per_turn
            else 0.0
        ),
        "greedy_agreement_rate": (
            statistics.fmean(
                bool(row["greedy_agreement"])
                for row in per_turn
                if row["greedy_agreement"] is not None
            )
            if any(row["greedy_agreement"] is not None for row in per_turn)
            else None
        ),
        "alpha_beta_agreement_rate": (
            statistics.fmean(
                bool(row["alpha_beta_agreement"])
                for row in per_turn
                if row["alpha_beta_agreement"] is not None
            )
            if any(row["alpha_beta_agreement"] is not None for row in per_turn)
            else None
        ),
    }
    return {
        "per_turn": per_turn,
        "by_remaining_bin": bin_rows,
        "feature_variance": feature_variance_summary,
        "selected_comparison": selected_comparison,
        "outcome_comparison": outcome_comparison,
        "feature_score_correlation": correlation_rows,
        "timing": timing_rows,
        "contribution": contribution_rows,
        "headline": headline,
    }


def sample_reference_positions(
    details: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    if len(details) <= limit:
        return details
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detail in details:
        grouped[remaining_bin(float(detail["remaining_word_rate"]))].append(detail)
    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, int]] = set()
    per_bin = max(1, limit // 5)
    for bin_name in ("80-100%", "60-80%", "40-60%", "20-40%", "0-20%"):
        values = grouped[bin_name]
        if len(values) <= per_bin:
            selected.extend(values)
            selected_keys.update(
                (row["match_id"], int(row["turn"])) for row in values
            )
            continue
        step = len(values) / per_bin
        chosen = [
            values[min(len(values) - 1, int(index * step))]
            for index in range(per_bin)
        ]
        selected.extend(chosen)
        selected_keys.update(
            (row["match_id"], int(row["turn"])) for row in chosen
        )
    if len(selected) < limit:
        for detail in details:
            key = (detail["match_id"], int(detail["turn"]))
            if key in selected_keys:
                continue
            selected.append(detail)
            selected_keys.add(key)
            if len(selected) >= limit:
                break
    return selected[:limit]


def calculate_reference_agreements(
    matches: list[dict[str, Any]],
    details: list[dict[str, Any]],
    output_path: Path,
    limit: int,
    time_limit_sec: float,
) -> list[dict[str, Any]]:
    existing = read_jsonl(output_path)
    completed = {(row["match_id"], int(row["turn"])) for row in existing}
    match_map = {row["match_id"]: row for row in matches}
    for detail in sample_reference_positions(details, limit):
        key = (detail["match_id"], int(detail["turn"]))
        if key in completed:
            continue
        match = match_map[detail["match_id"]]
        runtime = RuntimeDictionary.load(match["runtime"])
        state = AIEdgeState.initial(runtime)
        for turn in match["history"]:
            if int(turn["turn"]) >= int(detail["turn"]):
                break
            state.apply_edge(int(turn["start_id"]), int(turn["end_id"]))
        selected = next(
            candidate for candidate in detail["candidates"] if candidate["selected"]
        )
        graph_edge = (int(selected["start_id"]), int(selected["end_id"]))
        greedy = GreedyAgent(time_limit_sec=time_limit_sec).choose_edge(state)
        alpha = AlphaBetaAgent(
            time_limit_sec=time_limit_sec,
            depth=5,
            branch_limit=8,
            adaptive_depth=False,
        ).choose_edge(state)
        row = {
            "match_id": detail["match_id"],
            "turn": detail["turn"],
            "remaining_word_rate": detail["remaining_word_rate"],
            "remaining_bin": remaining_bin(float(detail["remaining_word_rate"])),
            "graph_start_id": graph_edge[0],
            "graph_end_id": graph_edge[1],
            "greedy_start_id": greedy.start_id,
            "greedy_end_id": greedy.end_id,
            "greedy_agreement": graph_edge == (greedy.start_id, greedy.end_id),
            "alpha_beta_start_id": alpha.start_id,
            "alpha_beta_end_id": alpha.end_id,
            "alpha_beta_agreement": graph_edge == (alpha.start_id, alpha.end_id),
            "alpha_beta_timed_out": alpha.timed_out,
            "alpha_beta_is_reference_not_ground_truth": True,
        }
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        existing.append(row)
        completed.add(key)
    return existing


def _format_plot_value(value: float, ylabel: str) -> str:
    if "rate" in ylabel.lower():
        return f"{value:.1%}"
    if float(value).is_integer() and abs(value) >= 1:
        return f"{int(value):,}"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _add_bar_value_labels(ax, ylabel: str) -> None:
    for container in ax.containers:
        values = getattr(container, "datavalues", None)
        if values is None:
            continue
        ax.bar_label(
            container,
            labels=[_format_plot_value(float(value), ylabel) for value in values],
            padding=3,
            fontsize=8,
        )
    ax.margins(y=0.12)


def _bar(plt, path: Path, labels, values, title: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=28)
    ax.grid(axis="y", alpha=0.25)
    _add_bar_value_labels(ax, ylabel)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def create_plots(
    output: Path,
    matches: list[dict[str, Any]],
    aggregates: dict[str, list[dict[str, Any]]],
    graph: dict[str, Any],
) -> list[str]:
    plt = ensure_matplotlib()
    plots = output / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def bar(name, rows, label, metric, title, ylabel):
        path = plots / f"{name}.png"
        _bar(plt, path, [row[label] for row in rows], [row[metric] for row in rows], title, ylabel)
        created.append(str(path))

    overall = aggregates["overall"]
    bar("agent_overall_win_rate", overall, "agent", "win_rate", "Overall win rate by agent", "Win rate")
    bar(
        "agent_overall_win_rate_without_random",
        aggregates["overall_without_random"],
        "agent",
        "win_rate",
        "Overall win rate by agent (matches against Random excluded)",
        "Win rate",
    )
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = range(len(overall))
    ax.bar([value - 0.2 for value in x], [row["wins"] for row in overall], 0.4, label="wins")
    ax.bar([value + 0.2 for value in x], [row["losses"] for row in overall], 0.4, label="losses")
    ax.set_xticks(list(x), [row["agent"] for row in overall], rotation=28)
    ax.set_title("Wins and losses by agent")
    _add_bar_value_labels(ax, "Games")
    ax.legend()
    fig.tight_layout()
    path = plots / "agent_wins_losses.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    seat = aggregates["by_seat"]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    labels = sorted({row["agent"] for row in seat})
    x = range(len(labels))
    first = {row["agent"]: row["win_rate"] for row in seat if row["seat"] == "first"}
    second = {row["agent"]: row["win_rate"] for row in seat if row["seat"] == "second"}
    ax.bar([value - 0.2 for value in x], [first.get(agent, 0) for agent in labels], 0.4, label="first")
    ax.bar([value + 0.2 for value in x], [second.get(agent, 0) for agent in labels], 0.4, label="second")
    ax.set_xticks(list(x), labels, rotation=28)
    ax.set_ylabel("Win rate")
    ax.set_title("First and second seat win rates")
    _add_bar_value_labels(ax, "Win rate")
    ax.legend()
    fig.tight_layout()
    path = plots / "agent_first_second_win_rate.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    for metric, name, title, ylabel in (
        ("win_rate", "win_rate_by_dictionary_size", "Win rate by dictionary size", "Win rate"),
        ("mean_match_turns", "mean_match_turns_by_dictionary_size", "Mean match length by dictionary size", "Turns"),
    ):
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for agent in sorted({row["agent"] for row in aggregates["by_size"]}):
            rows = sorted(
                (row for row in aggregates["by_size"] if row["agent"] == agent),
                key=lambda row: row["dict_size"],
            )
            ax.plot([row["dict_size"] for row in rows], [row[metric] for row in rows], marker="o", label=agent)
        ax.set_title(title)
        ax.set_xlabel("Dictionary size")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = plots / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    agents = sorted({row["agent"] for row in aggregates["direct"]})
    matrix = []
    direct_map = {(row["agent"], row["opponent"]): row["win_rate"] for row in aggregates["direct"]}
    for agent in agents:
        matrix.append([direct_map.get((agent, opponent), math.nan) for opponent in agents])
    fig, ax = plt.subplots(figsize=(9, 8))
    image = ax.imshow(matrix, vmin=0, vmax=1, cmap="RdYlBu")
    ax.set_xticks(range(len(agents)), agents, rotation=35, ha="right")
    ax.set_yticks(range(len(agents)), agents)
    ax.set_title("Pairwise win-rate heatmap")
    fig.colorbar(image, ax=ax, label="Win rate")
    fig.tight_layout()
    path = plots / "pairwise_win_rate_heatmap.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    timing = aggregates["timing"]
    bar("agent_mean_think_time", timing, "agent", "mean_time_sec", "Mean decision time by agent", "Seconds")
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = range(len(timing))
    ax.bar([value - 0.2 for value in x], [row["median_time_sec"] for row in timing], 0.4, label="median")
    ax.bar([value + 0.2 for value in x], [row["p95_time_sec"] for row in timing], 0.4, label="p95")
    ax.set_xticks(list(x), [row["agent"] for row in timing], rotation=28)
    ax.set_title("Median and p95 decision time")
    ax.set_ylabel("Seconds")
    _add_bar_value_labels(ax, "Seconds")
    ax.legend()
    fig.tight_layout()
    path = plots / "agent_median_p95_think_time.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    turn_time_groups = [
        [
            float(turn["elapsed_time_sec"])
            for match in matches
            for turn in match["history"]
            if turn["agent"] == agent
        ]
        for agent in agents
    ]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.boxplot(turn_time_groups, tick_labels=agents, showfliers=False)
    ax.tick_params(axis="x", rotation=28)
    ax.set_title("Decision-time distribution by agent")
    ax.set_ylabel("Seconds")
    fig.tight_layout()
    path = plots / "agent_think_time_boxplot.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    bar("agent_mean_match_turns", overall, "agent", "mean_match_turns", "Mean match length by agent", "Turns")
    bar("agent_timeout_count", timing, "agent", "timeout_count", "Timeout count by agent", "Timeouts")
    outcome_plot_rows = [
        {**row, "agent_outcome": f"{row['agent']} {row['outcome']}"}
        for row in aggregates["length_outcome"]
    ]
    bar(
        "win_loss_mean_match_turns",
        outcome_plot_rows,
        "agent_outcome",
        "mean_turns",
        "Mean match length for wins and losses (two bars per agent in CSV)",
        "Turns",
    )
    search_agents = {
        "alpha_beta",
        "pvs",
        "beam_negamax",
        "graph_pvs",
        "beam_alpha_beta",
        "beam_pvs",
    }
    search_timing = [row for row in timing if row["agent"] in search_agents]
    bar("search_agent_mean_time", search_timing, "agent", "mean_time_sec", "Search-agent mean decision time", "Seconds")
    search_overall = [row for row in overall if row["agent"] in search_agents]
    bar("search_agent_nodes", search_overall, "agent", "nodes_per_move", "Search nodes per move", "Nodes")

    turns = flatten_turns(matches)
    depth_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in turns:
        if row["agent"] in search_agents and row.get("effective_depth") not in ("", None):
            depth_groups[(row["agent"], str(row["effective_depth"]))].append(float(row["elapsed_time_sec"]))
    depth_rows = [
        {"agent_depth": f"{key[0]} D{key[1]}", "mean_time_sec": statistics.fmean(values)}
        for key, values in sorted(depth_groups.items())
    ]
    bar("search_agent_time_by_depth", depth_rows, "agent_depth", "mean_time_sec", "Search-agent time by effective depth", "Seconds")
    pvs_agents = {"pvs", "graph_pvs", "beam_pvs"}
    pvs_turns = [row for row in turns if row["agent"] in pvs_agents]
    pvs_rate = (
        sum(float(row["research_count"] or 0) for row in pvs_turns)
        / max(1.0, sum(float(row["null_window_searches"] or 0) for row in pvs_turns))
    )
    path = plots / "pvs_research_rate.png"
    _bar(
        plt,
        path,
        ["PVS family"],
        [pvs_rate],
        "PVS-family re-search rate",
        "Rate",
    )
    created.append(str(path))

    candidate_agents = [row for row in timing if row["agent"] in {"greedy", "graph_control"}]
    bar("candidate_evaluation_agent_time", candidate_agents, "agent", "mean_time_sec", "One-ply candidate-evaluation time", "Seconds")
    graph_size = [row for row in aggregates["by_size"] if row["agent"] == "graph_control"]
    bar("graph_control_win_rate_by_size", graph_size, "dict_size", "win_rate", "GraphControl win rate by dictionary size", "Win rate")

    bin_rows = graph["by_remaining_bin"]
    for metric, name, title, ylabel in (
        ("mean_score_range", "graph_score_range_by_remaining", "GraphControl score range by residual ratio", "Score range"),
        ("mean_score_stddev", "graph_score_stddev_by_remaining", "GraphControl score standard deviation by residual ratio", "Score standard deviation"),
        ("all_candidates_tied_rate", "graph_tie_rate_by_remaining", "All-candidate tie rate by residual ratio", "Tie rate"),
        ("mean_best_score_tie_count", "graph_best_tie_count_by_remaining", "Best-score ties by residual ratio", "Candidates"),
        ("mean_distinct_score_count", "graph_distinct_scores_by_remaining", "Distinct scores by residual ratio", "Distinct scores"),
        ("alpha_beta_agreement_rate", "graph_alpha_beta_agreement_by_remaining", "GraphControl and AlphaBeta agreement", "Agreement rate"),
        ("greedy_agreement_rate", "graph_greedy_agreement_by_remaining", "GraphControl and Greedy agreement", "Agreement rate"),
    ):
        usable = [row for row in bin_rows if row[metric] is not None]
        bar(name, usable, "remaining_bin", metric, title, ylabel)

    bar(
        "graph_feature_candidate_variance",
        graph["feature_variance"],
        "feature",
        "mean_candidate_variance",
        "Mean candidate variance of GraphControl features",
        "Variance",
    )
    comparison = graph["selected_comparison"]
    path = plots / "graph_selected_vs_nonselected_features.png"
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(comparison))
    ax.bar([value - 0.2 for value in x], [row["selected_mean"] for row in comparison], 0.4, label="selected")
    ax.bar([value + 0.2 for value in x], [row["not_selected_mean"] for row in comparison], 0.4, label="not selected")
    ax.set_xticks(list(x), [row["feature"] for row in comparison], rotation=40, ha="right")
    ax.set_title("Selected and non-selected feature means")
    _add_bar_value_labels(ax, "Feature value")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))
    bar("graph_time_breakdown", graph["timing"], "component", "total_time_sec", "GraphControl time breakdown", "Total seconds")
    bar("graph_global_local_contribution", graph["contribution"], "contribution", "rate", "Global/local feature variation contribution", "Position rate")

    beam_source = (
        PROJECT_ROOT
        / "results/existing_agent_analysis/beam_analysis/summary.csv"
    )
    path = plots / "beam_reference_retention_by_width.png"
    if beam_source.is_file():
        with beam_source.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        all_row = next(
            (
                row
                for row in rows
                if row.get("group_type") == "all" and row.get("group") == "all"
            ),
            None,
        )
        if all_row:
            widths = (2, 4, 6, 8, 12, 16)
            values = [
                float(all_row[f"top_{width}_reference_retention_rate"])
                for width in widths
            ]
            _bar(plt, path, [str(width) for width in widths], values, "Beam reference-move retention (reused compatible analysis)", "Retention rate")
        else:
            _bar(plt, path, ["unavailable"], [0], "Beam reference retention unavailable", "Rate")
    else:
        _bar(plt, path, ["unavailable"], [0], "Beam reference retention unavailable", "Rate")
    created.append(str(path))
    return created


def write_reports(
    output: Path,
    aggregates: dict[str, list[dict[str, Any]]],
    graph: dict[str, Any],
    match_count: int,
    duplicate_count: int,
    reference_count: int,
) -> None:
    graph_overall = next(
        row for row in aggregates["overall"] if row["agent"] == "graph_control"
    )
    headline = graph["headline"]
    comparison_lines = [
        "# 全エージェント比較 自動レポート",
        "",
        f"- 対局数: {match_count}",
        f"- 重複対局: {duplicate_count}",
        f"- GraphControl参照手比較局面: {reference_count}",
        "",
        "## AI別成績",
        "",
        "| AI | 勝/局 | 勝率 | 95% CI | 平均思考秒 | timeout |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    timing = {row["agent"]: row for row in aggregates["timing"]}
    for row in aggregates["overall"]:
        comparison_lines.append(
            f"| {row['agent']} | {row['wins']}/{row['games']} | "
            f"{row['win_rate']:.1%} | {row['win_rate_ci95_low']:.1%}–"
            f"{row['win_rate_ci95_high']:.1%} | "
            f"{timing[row['agent']]['mean_time_sec']:.6f} | "
            f"{row['timeout_count']} |"
        )
    comparison_lines.extend(
        [
            "",
            "AlphaBeta、PVS、Beamの設定は既存の最終比較設定を維持した。",
            "AggressivePVSはPVSの後方互換別名なので重複比較から除外した。",
            "AI対AIログの候補単位は具体語ではなく、有向辺種別と残存多重度である。",
        ]
    )
    (output / "all_agent_comparison.md").write_text(
        "\n".join(comparison_lines) + "\n", encoding="utf-8"
    )

    graph_lines = [
        "# GraphControlAgent 分析 自動レポート",
        "",
        f"- 勝率: {graph_overall['wins']}/{graph_overall['games']} "
        f"({graph_overall['win_rate']:.1%})",
        f"- 全候補同点率: {headline['all_candidates_tied_rate']:.1%}",
        f"- SCCが全体の95%以上: {headline['scc_nearly_whole_rate']:.1%}",
        f"- 到達可能文字数が全候補で同じ: "
        f"{headline['reachable_chars_all_same_rate']:.1%}",
        f"- 到達可能辺数の候補差1%以下: "
        f"{headline['reachable_edges_nearly_same_rate']:.1%}",
        f"- Greedy一致率（抽出参照局面）: {headline['greedy_agreement_rate']}",
        f"- AlphaBeta一致率（抽出参照局面、最善手の証明ではない）: "
        f"{headline['alpha_beta_agreement_rate']}",
        "",
        "大域・局所寄与は、各特徴群に候補間分散が存在したかによる診断であり、"
        "勝敗への因果効果を表すものではない。",
    ]
    (output / "graph_control_agent_analysis.md").write_text(
        "\n".join(graph_lines) + "\n", encoding="utf-8"
    )

    hybrid = [
        "# HybridAgent 次期設計案",
        "",
        "今回はHybridAgentを実装していない。GraphControlAgentを最後の独立単体AIとする。",
        "",
        "## 検討順位",
        "",
        "1. GraphControlの軽量局所特徴をAlphaBetaの候補順序付けへ限定導入する。",
        "2. danger/near-deathまたは残存率20%以下だけ葉評価の補助特徴として試す。",
        "3. SCC・全到達計算は、候補分散と時間内訳が十分有利な場合だけ採用する。",
        "",
        "独立手選択、葉評価、終盤限定、危険局面判定、未採用の判断は、"
        "本レポートの勝率・同点率・特徴分散・処理時間を用いて次段階で検証する。"
        "AlphaBeta参照手は真の最善手とは扱わない。",
    ]
    (output / "hybrid_agent_next_design.md").write_text(
        "\n".join(hybrid) + "\n", encoding="utf-8"
    )


def run(args: argparse.Namespace) -> Path:
    input_dir = args.input
    matches = read_jsonl(input_dir / "raw_matches.jsonl")
    details = read_jsonl(input_dir / "graph_control_candidate_details.jsonl")
    if not matches:
        raise ValueError(f"no raw matches: {input_dir}")
    ids = [row["match_id"] for row in matches]
    duplicate_count = len(ids) - len(set(ids))
    if duplicate_count:
        raise ValueError(f"duplicate match IDs: {duplicate_count}")

    output = input_dir / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    agreements = calculate_reference_agreements(
        matches,
        details,
        output / "graph_reference_agreements.jsonl",
        limit=args.reference_positions,
        time_limit_sec=args.reference_time_limit_sec,
    )
    aggregates = aggregate_matches(matches)
    graph = analyze_graph_details(details, agreements)
    turns = flatten_turns(matches)

    for name, rows in aggregates.items():
        write_csv(output / "csv" / f"{name}.csv", rows)
        write_json(output / "json" / f"{name}.json", rows)
    for name, value in graph.items():
        write_json(output / "json" / f"graph_{name}.json", value)
        if isinstance(value, list):
            write_csv(output / "csv" / f"graph_{name}.csv", value)
    write_csv(output / "csv/turn_metrics.csv", turns)
    write_csv(output / "csv/graph_reference_agreements.csv", agreements)
    plots = create_plots(output, matches, aggregates, graph)
    write_reports(
        output,
        aggregates,
        graph,
        len(matches),
        duplicate_count,
        len(agreements),
    )
    summary = {
        "match_count": len(matches),
        "duplicate_match_count": duplicate_count,
        "graph_detail_turn_count": len(details),
        "reference_position_count": len(agreements),
        "plot_count": len(plots),
        "plots": plots,
        "overall": aggregates["overall"],
        "graph_control": graph["headline"],
    }
    write_json(output / "summary.json", summary)
    print(output)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--reference-positions", type=int, default=500)
    parser.add_argument("--reference-time-limit-sec", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.reference_positions <= 0 or args.reference_time_limit_sec <= 0:
        parser.error("reference limits must be positive")
    return args


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
