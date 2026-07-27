"""Create final slide figures from existing experiment artifacts only."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from analyze_presentation_experiments import (
    AGENT_COLORS,
    AGENT_LABELS,
    fixed_comparison_summary,
    summarize_matches,
    wilson_interval,
)
from run_graph_control_comparison import read_jsonl
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESENTATION_ROOT = PROJECT_ROOT / "results/presentation_experiments"
BEAM_FOLLOWUP = (
    PROJECT_ROOT
    / "results/beam_hybrid_followup/D10000/c86fc7661da6"
)
SAME_DEPTH_RUNS = (
    PROJECT_ROOT
    / "results/hybrid_agent_comparison/benchmark/821264dd868d/runs.jsonl"
)
BOARD_ADAPTIVE_ROOT = (
    PROJECT_ROOT / "results/minimal_adaptive_hybrid/D10000"
)
BANNED_PRESENTATION_TERMS = (
    "未使用seed",
    "調整seed",
    "最終評価",
    "未知の辞書",
)


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"required input not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_presentation_run(root: Path = PRESENTATION_ROOT) -> Path:
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir()
        and (path / "manifest.json").is_file()
        and (path / "final4/raw_matches.jsonl").is_file()
        and (path / "initial6/raw_matches.jsonl").is_file()
        and (path / "fixed_comparison/raw_runs.jsonl").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"no completed presentation run found under {root}"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def canonical_settings(
    presentation_manifest: dict[str, Any],
    followup_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    presentation = presentation_manifest["config"]
    followup = followup_manifest["config"]
    presentation_beam = presentation["settings"]["beam_alpha_beta"]
    presentation_selective = presentation["settings"][
        "selective_alpha_beta"
    ]
    followup_beam = followup["variants"][
        "beam_alpha_beta_deep_wide"
    ]
    followup_selective = followup["alpha_beta"]
    followup_adaptive = followup["adaptive_profile"]
    presentation_signature = {
        "dictionary_size": int(presentation["dictionary_size"]),
        "time_limit_sec": float(presentation["time_limit_sec"]),
        "max_moves": int(presentation["max_moves"]),
        "beam_initial_depth": int(presentation_beam["initial_depth"]),
        "beam_max_depth": int(presentation_beam["max_depth"]),
        "beam_widths": list(presentation_beam["beam_widths"]),
        "selective_initial_depth": int(
            presentation_selective["initial_depth"]
        ),
        "selective_max_depth": int(
            presentation_selective["max_depth"]
        ),
        "selective_branch_limit": int(
            presentation_selective["branch_limit"]
        ),
        "target_time_ratio": float(
            presentation_selective["target_time_sec"]
        )
        / float(presentation["time_limit_sec"]),
        "depth_decrease_ratio": float(
            presentation_selective["depth_decrease_ratio"]
        ),
        "depth_recovery_ratio": float(
            presentation_selective["depth_recovery_ratio"]
        ),
        "depth_recovery_turns": int(
            presentation_selective["depth_recovery_turns"]
        ),
        "adaptive_depth": bool(
            presentation_selective["adaptive_depth"]
            and presentation_beam["adaptive_depth"]
        ),
    }
    followup_signature = {
        "dictionary_size": int(followup["dictionary_size"]),
        "time_limit_sec": float(followup["time_limit_sec"]),
        "max_moves": int(followup["max_moves"]),
        "beam_initial_depth": int(followup_beam["initial_depth"]),
        "beam_max_depth": int(followup_beam["max_depth"]),
        "beam_widths": list(followup_beam["beam_widths"]),
        "selective_initial_depth": int(
            followup_selective["initial_depth"]
        ),
        "selective_max_depth": int(followup_selective["max_depth"]),
        "selective_branch_limit": int(
            followup_selective["branch_limit"]
        ),
        "target_time_ratio": float(
            followup_adaptive["target_time_ratio"]
        ),
        "depth_decrease_ratio": float(
            followup_adaptive["depth_decrease_ratio"]
        ),
        "depth_recovery_ratio": float(
            followup_adaptive["depth_recovery_ratio"]
        ),
        "depth_recovery_turns": int(
            followup_adaptive["depth_recovery_turns"]
        ),
        "adaptive_depth": True,
    }
    return presentation_signature, followup_signature


def _winner_for(row: dict[str, Any], side: str) -> bool:
    return row["winner"] == side


def _presentation_direct_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if {row["first_target"], row["second_target"]}
        == {"beam_alpha_beta", "selective_alpha_beta"}
    ]


def _followup_direct_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("hybrid_config_id")
        == "beam_alpha_beta_deep_wide"
        and {
            row.get("first_config_id"),
            row.get("second_config_id"),
        }
        == {
            "beam_alpha_beta_deep_wide",
            "alpha_beta_reference",
        }
    ]


def direct_result(
    presentation_rows: list[dict[str, Any]],
    followup_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    current = _presentation_direct_rows(presentation_rows)
    earlier = _followup_direct_rows(followup_rows)
    canonical: list[dict[str, Any]] = []
    for source, rows in (
        ("presentation_round_robin", current),
        ("beam_followup", earlier),
    ):
        for row in rows:
            if source == "presentation_round_robin":
                first = str(row["first_target"])
                second = str(row["second_target"])
            else:
                first = (
                    "beam_alpha_beta"
                    if row["first_config_id"]
                    == "beam_alpha_beta_deep_wide"
                    else "selective_alpha_beta"
                )
                second = (
                    "beam_alpha_beta"
                    if row["second_config_id"]
                    == "beam_alpha_beta_deep_wide"
                    else "selective_alpha_beta"
                )
            canonical.append(
                {
                    "source": source,
                    "source_match_id": str(row["match_id"]),
                    "combined_match_id": f"{source}:{row['match_id']}",
                    "first": first,
                    "second": second,
                    "winner": str(row["winner"]),
                    "dictionary_seed": int(row["dictionary_seed"]),
                }
            )
    ids = [row["combined_match_id"] for row in canonical]
    beam_wins = sum(
        (row["winner"] == "first" and row["first"] == "beam_alpha_beta")
        or (
            row["winner"] == "second"
            and row["second"] == "beam_alpha_beta"
        )
        for row in canonical
    )
    selective_wins = sum(
        (
            row["winner"] == "first"
            and row["first"] == "selective_alpha_beta"
        )
        or (
            row["winner"] == "second"
            and row["second"] == "selective_alpha_beta"
        )
        for row in canonical
    )
    draws = sum(row["winner"] == "draw" for row in canonical)
    beam_first = sum(
        row["first"] == "beam_alpha_beta" for row in canonical
    )
    selective_first = sum(
        row["first"] == "selective_alpha_beta" for row in canonical
    )
    games = len(canonical)
    beam_interval = wilson_interval(beam_wins, games)
    selective_interval = wilson_interval(selective_wins, games)
    return {
        "games": games,
        "beam_alpha_beta_wins": beam_wins,
        "selective_alpha_beta_wins": selective_wins,
        "draws": draws,
        "beam_alpha_beta_win_rate": beam_wins / games if games else 0.0,
        "selective_alpha_beta_win_rate": (
            selective_wins / games if games else 0.0
        ),
        "beam_alpha_beta_wilson_low": beam_interval[0],
        "beam_alpha_beta_wilson_high": beam_interval[1],
        "selective_alpha_beta_wilson_low": selective_interval[0],
        "selective_alpha_beta_wilson_high": selective_interval[1],
        "beam_alpha_beta_first_count": beam_first,
        "selective_alpha_beta_first_count": selective_first,
        "duplicate_match_id_count": len(ids) - len(set(ids)),
        "source_counts": {
            "presentation_round_robin": len(current),
            "beam_followup": len(earlier),
        },
        "rows": canonical,
    }


def recorded_direct_conditions_match(
    presentation_rows: list[dict[str, Any]],
    followup_rows: list[dict[str, Any]],
) -> bool:
    selected = (
        _presentation_direct_rows(presentation_rows)
        + _followup_direct_rows(followup_rows)
    )
    if len(selected) != 40:
        return False
    for row in selected:
        if (
            int(row["dict_size"]) != 10000
            or int(row["max_moves"]) != 1000
            or not math.isclose(
                float(row["max_match_time_sec"]), 300.0
            )
        ):
            return False
        for turn in row["history"]:
            extra = turn.get("decision_extra", {})
            if turn["agent"] == "beam_alpha_beta":
                if (
                    int(extra.get("initial_depth", -1)) != 8
                    or int(extra.get("max_depth", -1)) != 9
                    or list(extra.get("beam_widths", []))
                    != [12, 8, 4, 2]
                    or extra.get("adaptive_depth") is not True
                    or not math.isclose(
                        float(extra.get("target_time_sec", -1.0)), 0.6
                    )
                ):
                    return False
            elif turn["agent"] == "alpha_beta":
                if (
                    int(extra.get("initial_depth", -1)) != 5
                    or int(extra.get("max_depth", -1)) != 7
                    or int(extra.get("branch_limit", -1)) != 8
                    or extra.get("adaptive_depth") is not True
                    or not math.isclose(
                        float(extra.get("target_time_sec", -1.0)), 0.6
                    )
                ):
                    return False
            else:
                return False
    return True


def same_depth_effect(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = {
        agent: [row for row in rows if row["agent"] == agent]
        for agent in ("beam_negamax", "beam_alpha_beta")
    }
    if any(len(values) != 14 for values in selected.values()):
        raise ValueError("same-depth comparison must have 14 rows per agent")
    beam_time = statistics.fmean(
        float(row["elapsed_time_sec"])
        for row in selected["beam_negamax"]
    )
    hybrid_time = statistics.fmean(
        float(row["elapsed_time_sec"])
        for row in selected["beam_alpha_beta"]
    )
    beam_nodes = statistics.fmean(
        int(row["nodes_searched"]) for row in selected["beam_negamax"]
    )
    hybrid_nodes = statistics.fmean(
        int(row["nodes_searched"])
        for row in selected["beam_alpha_beta"]
    )
    return {
        "depth": 5,
        "position_count": 14,
        "beam_mean_time_sec": beam_time,
        "beam_alpha_beta_mean_time_sec": hybrid_time,
        "time_reduction_rate": 1.0 - hybrid_time / beam_time,
        "beam_mean_nodes": beam_nodes,
        "beam_alpha_beta_mean_nodes": hybrid_nodes,
        "node_reduction_rate": 1.0 - hybrid_nodes / beam_nodes,
    }


def appendix_parameter_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    labels = {
        "beam_alpha_beta_baseline": "baseline",
        "beam_alpha_beta_deep": "deep",
        "beam_alpha_beta_wide": "wide",
        "beam_alpha_beta_deep_wide": "deep_wide",
    }
    result = []
    for config_id, label in labels.items():
        values = [
            row
            for row in rows
            if row.get("hybrid_config_id") == config_id
        ]
        wins = 0
        for row in values:
            side = (
                "first"
                if row["first_config_id"] == config_id
                else "second"
            )
            wins += _winner_for(row, side)
        result.append(
            {
                "config_id": config_id,
                "label": label,
                "games": len(values),
                "wins": wins,
                "losses": len(values) - wins,
                "win_rate": wins / len(values) if values else 0.0,
            }
        )
    return result


def board_adaptive_summary(
    rows: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile_labels = {
        "fixed_beam_alpha_beta": "固定型\nBeam AlphaBeta",
        "gap_conservative": "Gap\nConservative",
        "gap_responsive": "Gap\nResponsive",
        "proof_strict": "Proof\nStrict",
        "proof_moderate": "Proof\nModerate",
    }
    profile_order = tuple(profile_labels)
    position_by_id = {
        str(position["position_id"]): position for position in positions
    }
    if len(position_by_id) != len(positions):
        raise AssertionError("duplicate saved position_id")

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["profile"]), str(row["position_id"]))
        if key in by_key:
            raise AssertionError(f"duplicate benchmark row: {key}")
        by_key[key] = row

    position_ids = set(position_by_id)
    required_profiles = ("reference", *profile_order)
    profile_position_ids = {
        profile: {
            position_id
            for row_profile, position_id in by_key
            if row_profile == profile
        }
        for profile in required_profiles
    }
    same_positions = all(
        profile_position_ids[profile] == position_ids
        for profile in required_profiles
    )
    if not same_positions:
        raise AssertionError(
            "board-adaptive profiles do not cover the same saved positions"
        )

    reference_edges = {
        position_id: row["selected_edge"]
        for (profile, position_id), row in by_key.items()
        if profile == "reference"
        and not bool(row["timed_out"])
        and int(row["completed_root_moves"])
        == int(row["selected_root_candidate_count"])
        and row["selected_edge"] is not None
    }
    if not reference_edges:
        raise AssertionError("no stable reference positions")

    result: list[dict[str, Any]] = []
    for profile in profile_order:
        profile_rows = [
            by_key[(profile, position_id)]
            for position_id in sorted(position_ids)
        ]
        comparable = [
            row
            for row in profile_rows
            if str(row["position_id"]) in reference_edges
            and row["selected_edge"] is not None
        ]
        matches = sum(
            row["selected_edge"]
            == reference_edges[str(row["position_id"])]
            for row in comparable
        )
        denominator = len(comparable)
        interval = wilson_interval(matches, denominator)
        result.append(
            {
                "profile": profile,
                "label": profile_labels[profile],
                "position_count": len(profile_rows),
                "reference_denominator": denominator,
                "reference_match_count": matches,
                "reference_match_rate": (
                    matches / denominator if denominator else 0.0
                ),
                "wilson_low": interval[0],
                "wilson_high": interval[1],
                "mean_effective_depth": statistics.fmean(
                    float(row["effective_depth"]) for row in profile_rows
                ),
                "timeout_count": sum(
                    bool(row["timed_out"]) for row in profile_rows
                ),
            }
        )

    seed_counts: dict[str, int] = {}
    runtime_conditions_match = True
    for position in positions:
        seed = int(position["seed"])
        seed_counts[str(seed)] = seed_counts.get(str(seed), 0) + 1
        runtime_name = Path(str(position["runtime"])).name
        runtime_conditions_match &= (
            runtime_name == f"D10000_L2-12_seed{seed}.runtime.json"
        )
    denominators = {
        int(row["reference_denominator"]) for row in result
    }
    validation = {
        "dictionary_size": 10000,
        "saved_position_count": len(positions),
        "stable_reference_position_count": len(reference_edges),
        "dictionary_seeds": sorted(
            int(seed) for seed in seed_counts
        ),
        "seed_position_counts": seed_counts,
        "seat_condition": "固定局面比較のため先後なし",
        "same_position_ids_for_all_profiles": same_positions,
        "same_reference_denominator": len(denominators) == 1,
        "runtime_dictionary_conditions_match": runtime_conditions_match,
        "candidate_depths": sorted(
            {
                int(by_key[(profile, position_id)]["effective_depth"])
                for profile in profile_order
                for position_id in position_ids
            }
        ),
        "reference_depths": sorted(
            {
                int(by_key[("reference", position_id)]["effective_depth"])
                for position_id in position_ids
            }
        ),
        "profiles_kept_separate": list(profile_order),
    }
    if not all(
        (
            validation["saved_position_count"] == 50,
            validation["stable_reference_position_count"] == 49,
            validation["same_position_ids_for_all_profiles"],
            validation["same_reference_denominator"],
            validation["runtime_dictionary_conditions_match"],
            validation["candidate_depths"] == [8],
            validation["reference_depths"] == [10],
        )
    ):
        raise AssertionError(
            "board-adaptive input validation failed:\n"
            + json.dumps(validation, ensure_ascii=False, indent=2)
        )
    return result, validation


def board_adaptive_match_summary(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile_labels = {
        "fixed_beam_alpha_beta": "固定型\nBeam AlphaBeta",
        "gap_conservative": "Gap\nConservative",
        "gap_responsive": "Gap\nResponsive",
        "proof_strict": "Proof\nStrict",
        "proof_moderate": "Proof\nModerate",
    }
    profile_order = tuple(profile_labels)
    match_ids = [str(row["match_id"]) for row in rows]
    if len(match_ids) != len(set(match_ids)):
        raise AssertionError("duplicate board-adaptive match_id")
    observed_agents = {
        str(row[side])
        for row in rows
        for side in ("first_agent", "second_agent")
    }
    if observed_agents != set(profile_order):
        raise AssertionError(
            f"unexpected board-adaptive agents: {sorted(observed_agents)}"
        )

    condition_signatures = {
        (
            int(row["dictionary_size"]),
            float(row["decision_time_sec"]),
            int(row["max_moves"]),
            float(row["max_match_time_sec"]),
            int(row["candidate_depth"]),
            int(row["candidate_max_depth"]),
            tuple(int(value) for value in row["beam_widths"]),
            bool(row["adaptive_depth"]),
        )
        for row in rows
    }
    expected_signature = (
        10000,
        0.3,
        1000,
        90.0,
        8,
        9,
        (12, 8, 4, 2),
        True,
    )
    if condition_signatures != {expected_signature}:
        raise AssertionError(
            f"mixed board-adaptive conditions: {condition_signatures}"
        )

    pair_counts: dict[str, int] = {}
    for row in rows:
        pair = "|".join(
            sorted(
                (str(row["first_agent"]), str(row["second_agent"]))
            )
        )
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    expected_pair_count = math.comb(len(profile_order), 2)
    if (
        len(pair_counts) != expected_pair_count
        or set(pair_counts.values()) != {10}
    ):
        raise AssertionError(
            f"incomplete board-adaptive pairings: {pair_counts}"
        )

    result: list[dict[str, Any]] = []
    for profile in profile_order:
        selected = [
            row
            for row in rows
            if profile
            in {str(row["first_agent"]), str(row["second_agent"])}
        ]
        wins = sum(
            (
                row["winner"] == "first"
                and row["first_agent"] == profile
            )
            or (
                row["winner"] == "second"
                and row["second_agent"] == profile
            )
            for row in selected
        )
        draws = sum(row["winner"] == "draw" for row in selected)
        losses = len(selected) - wins - draws
        first_games = sum(
            row["first_agent"] == profile for row in selected
        )
        second_games = sum(
            row["second_agent"] == profile for row in selected
        )
        rate = wins / len(selected) if selected else 0.0
        interval = wilson_interval(wins, len(selected))
        result.append(
            {
                "profile": profile,
                "label": profile_labels[profile],
                "games": len(selected),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": rate,
                "wilson_low": interval[0],
                "wilson_high": interval[1],
                "first_games": first_games,
                "second_games": second_games,
            }
        )

    vs_fixed: dict[str, dict[str, int | float]] = {}
    for profile in profile_order[1:]:
        selected = [
            row
            for row in rows
            if {
                str(row["first_agent"]),
                str(row["second_agent"]),
            }
            == {"fixed_beam_alpha_beta", profile}
        ]
        wins = sum(
            (
                row["winner"] == "first"
                and row["first_agent"] == profile
            )
            or (
                row["winner"] == "second"
                and row["second_agent"] == profile
            )
            for row in selected
        )
        vs_fixed[profile] = {
            "games": len(selected),
            "wins": wins,
            "losses": len(selected) - wins,
            "win_rate": wins / len(selected) if selected else 0.0,
        }

    validation = {
        "match_count": len(rows),
        "unique_match_count": len(set(match_ids)),
        "dictionary_size": expected_signature[0],
        "decision_time_sec": expected_signature[1],
        "max_moves": expected_signature[2],
        "max_match_time_sec": expected_signature[3],
        "initial_depth": expected_signature[4],
        "max_depth": expected_signature[5],
        "beam_widths": list(expected_signature[6]),
        "adaptive_depth": expected_signature[7],
        "dictionary_seeds": sorted(
            {int(row["dictionary_seed"]) for row in rows}
        ),
        "pair_counts": pair_counts,
        "all_profiles_have_40_games": all(
            row["games"] == 40 for row in result
        ),
        "all_profiles_have_balanced_seats": all(
            row["first_games"] == row["second_games"] == 20
            for row in result
        ),
        "draw_count": sum(row["winner"] == "draw" for row in rows),
        "match_timeout_count": sum(
            row["loss_reason"] == "match_timeout" for row in rows
        ),
        "invalid_move_count": sum(
            int(row["invalid_move_count"]) for row in rows
        ),
        "profiles_kept_separate": list(profile_order),
        "vs_fixed": vs_fixed,
    }
    if not all(
        (
            validation["match_count"] == 100,
            validation["unique_match_count"] == 100,
            validation["dictionary_seeds"] == [0, 1, 2, 3, 4],
            validation["all_profiles_have_40_games"],
            validation["all_profiles_have_balanced_seats"],
            validation["draw_count"] == 0,
            validation["match_timeout_count"] == 0,
            validation["invalid_move_count"] == 0,
        )
    ):
        raise AssertionError(
            "board-adaptive match validation failed:\n"
            + json.dumps(validation, ensure_ascii=False, indent=2)
        )
    return result, validation


def end_char_usage_summary(
    rows: list[dict[str, Any]],
    *,
    top_n: int = 12,
) -> dict[str, Any]:
    agents = (
        "alpha_beta",
        "pvs",
        "beam_alpha_beta",
        "beam_pvs",
    )
    counts: dict[str, dict[str, int]] = {
        agent: {} for agent in agents
    }
    overall: dict[str, int] = {}
    for match in rows:
        history = match.get("history")
        if not isinstance(history, list):
            raise AssertionError(
                f"history is missing: {match.get('match_id')}"
            )
        for turn in history:
            agent = str(turn["agent"])
            end_char = str(turn["end_char"])
            if agent not in counts:
                raise AssertionError(f"unexpected history agent: {agent}")
            if not end_char:
                raise AssertionError("empty end_char in match history")
            counts[agent][end_char] = (
                counts[agent].get(end_char, 0) + 1
            )
            overall[end_char] = overall.get(end_char, 0) + 1

    total_moves = sum(overall.values())
    overall_rows = [
        {
            "rank": rank,
            "end_char": end_char,
            "move_count": count,
            "move_rate": count / total_moves if total_moves else 0.0,
        }
        for rank, (end_char, count) in enumerate(
            sorted(
                overall.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            start=1,
        )
    ]
    agent_rows: list[dict[str, Any]] = []
    agent_totals: dict[str, int] = {}
    for agent in agents:
        agent_total = sum(counts[agent].values())
        agent_totals[agent] = agent_total
        for rank, (end_char, count) in enumerate(
            sorted(
                counts[agent].items(),
                key=lambda item: (-item[1], item[0]),
            ),
            start=1,
        ):
            agent_rows.append(
                {
                    "agent": agent,
                    "label": AGENT_LABELS[agent],
                    "rank": rank,
                    "end_char": end_char,
                    "move_count": count,
                    "move_rate": (
                        count / agent_total if agent_total else 0.0
                    ),
                    "total_moves": agent_total,
                }
            )
    return {
        "match_count": len(rows),
        "total_moves": total_moves,
        "top_n": top_n,
        "top_end_chars": overall_rows[:top_n],
        "overall": overall_rows,
        "by_agent": agent_rows,
        "agent_totals": agent_totals,
        "ends_with_n_count": overall.get("ん", 0),
        "ends_with_n_rate": (
            overall.get("ん", 0) / total_moves if total_moves else 0.0
        ),
    }


def configure_matplotlib():
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
            "font.size": 14,
            "axes.titlesize": 20,
            "axes.labelsize": 15,
            "xtick.labelsize": 13,
            "ytick.labelsize": 13,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )
    return plt


def style_axis(ax, *, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color="#d9d9d9", linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)


def save_figure(plt, fig, path: Path) -> None:
    fig.savefig(path, dpi=220, facecolor="white")
    plt.close(fig)


def format_percent_axis(axis) -> None:
    axis.set_major_formatter(lambda value, _position: f"{value:.0%}")


def plot_horizontal_win_rates(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    positions = list(range(len(rows)))
    rates = [float(row["win_rate"]) for row in rows]
    errors = [
        [
            rate - float(row["wilson_low"])
            for rate, row in zip(rates, rows)
        ],
        [
            float(row["wilson_high"]) - rate
            for rate, row in zip(rates, rows)
        ],
    ]
    bars = ax.barh(
        positions,
        rates,
        color=[AGENT_COLORS[row["agent"]] for row in rows],
        xerr=errors,
        capsize=5,
        height=0.68,
    )
    ax.set_yticks(positions, [row["label"] for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.0)
    format_percent_axis(ax.xaxis)
    ax.set_xlabel("勝率")
    ax.set_title("基本6手法の総当たり勝率")
    style_axis(ax, grid_axis="x")
    for bar, row in zip(bars, rows):
        rate = float(row["win_rate"])
        x = max(0.015, rate - 0.015)
        ax.text(
            x,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1%}  n={row['games']}",
            ha="right" if rate >= 0.14 else "left",
            va="center",
            color="white" if rate >= 0.14 else "black",
            fontweight="bold",
            fontsize=13,
        )
    save_figure(plt, fig, path)


def plot_selective_effect(
    plt,
    row: dict[str, Any],
    path: Path,
) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(12.8, 7.2), constrained_layout=True
    )
    fig.suptitle("候補制限による探索量と選択手の変化", fontsize=20)
    labels = ["Full\nAlphaBeta", "Selective\nAlphaBeta"]
    colors = [
        AGENT_COLORS["full_alpha_beta"],
        AGENT_COLORS["selective_alpha_beta"],
    ]
    time_values = [
        float(row["full_mean_time_sec"]),
        float(row["selective_mean_time_sec"]),
    ]
    time_bars = axes[0].bar(labels, time_values, color=colors, width=0.62)
    axes[0].set_title("平均思考時間")
    axes[0].set_ylabel("秒")
    style_axis(axes[0])
    for bar, value in zip(time_bars, time_values):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.3f}秒",
            ha="center",
            va="bottom",
            fontsize=12,
        )
    axes[0].text(
        0.5,
        0.92,
        f"約{time_values[0] / time_values[1]:.1f}倍",
        transform=axes[0].transAxes,
        ha="center",
        bbox={"boxstyle": "round", "facecolor": "white"},
    )

    node_values = [
        float(row["full_mean_nodes"]),
        float(row["selective_mean_nodes"]),
    ]
    node_bars = axes[1].bar(labels, node_values, color=colors, width=0.62)
    axes[1].set_title("平均探索ノード数")
    axes[1].set_ylabel("ノード")
    style_axis(axes[1])
    for bar, value in zip(node_bars, node_values):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=12,
        )
    axes[1].text(
        0.5,
        0.92,
        f"{1.0 - node_values[1] / node_values[0]:.1%}削減",
        transform=axes[1].transAxes,
        ha="center",
        bbox={"boxstyle": "round", "facecolor": "white"},
    )

    agreement = float(row["move_agreement_rate"])
    agreement_bar = axes[2].bar(
        ["選択手一致率"],
        [agreement],
        color=AGENT_COLORS["selective_alpha_beta"],
        width=0.55,
    )
    axes[2].set_title("選択手の一致")
    axes[2].set_ylim(0.0, 1.0)
    format_percent_axis(axes[2].yaxis)
    style_axis(axes[2])
    axes[2].text(
        agreement_bar[0].get_x() + agreement_bar[0].get_width() / 2,
        agreement,
        f"{agreement:.1%}",
        ha="center",
        va="bottom",
        fontsize=13,
    )
    axes[2].text(
        0.5,
        0.08,
        f"比較可能 {row['comparable_count']}/"
        f"{row['position_count']}局面\n"
        f"Full未完了 {row['position_count'] - row['full_complete_count']}局面\n"
        f"評価値一致率 {row['score_agreement_rate']:.1%}",
        transform=axes[2].transAxes,
        ha="center",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
        fontsize=11,
    )
    save_figure(plt, fig, path)


def plot_beam_pruning(
    plt,
    data: dict[str, Any],
    path: Path,
) -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(12.8, 7.2), constrained_layout=True
    )
    fig.suptitle(
        "Beam探索へのAlphaBeta枝刈りの導入\n"
        f"同一深度{data['depth']}・固定{data['position_count']}局面",
        fontsize=18,
    )
    labels = ["Beam", "Beam\nAlphaBeta"]
    colors = [
        AGENT_COLORS["beam_negamax"],
        AGENT_COLORS["beam_alpha_beta"],
    ]
    panels = [
        (
            axes[0],
            [
                data["beam_mean_time_sec"],
                data["beam_alpha_beta_mean_time_sec"],
            ],
            "平均思考時間",
            "秒",
            data["time_reduction_rate"],
            lambda value: f"{value:.4f}秒",
        ),
        (
            axes[1],
            [data["beam_mean_nodes"], data["beam_alpha_beta_mean_nodes"]],
            "平均探索ノード数",
            "ノード",
            data["node_reduction_rate"],
            lambda value: f"{value:,.0f}",
        ),
    ]
    for ax, values, title, ylabel, reduction, formatter in panels:
        bars = ax.bar(labels, values, color=colors, width=0.6)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        style_axis(ax)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                formatter(value),
                ha="center",
                va="bottom",
                fontsize=13,
            )
        ax.text(
            0.5,
            0.92,
            f"{reduction:.1%}削減",
            transform=ax.transAxes,
            ha="center",
            bbox={"boxstyle": "round", "facecolor": "white"},
        )
    save_figure(plt, fig, path)


def plot_four_agents(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    labels = [row["label"] for row in rows]
    values = [float(row["win_rate"]) for row in rows]
    errors = [
        [
            value - float(row["wilson_low"])
            for value, row in zip(values, rows)
        ],
        [
            float(row["wilson_high"]) - value
            for value, row in zip(values, rows)
        ],
    ]
    bars = ax.bar(
        labels,
        values,
        color=[AGENT_COLORS[row["agent"]] for row in rows],
        yerr=errors,
        capsize=5,
        width=0.68,
    )
    ax.set_ylim(0.0, 1.0)
    format_percent_axis(ax.yaxis)
    ax.set_ylabel("勝率")
    ax.set_title("主要4手法の総当たり勝率")
    style_axis(ax)
    for bar, row in zip(bars, rows):
        value = float(row["win_rate"])
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=13,
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.025,
            f"{row['wins']}勝{row['losses']}敗\nn={row['games']}",
            ha="center",
            va="bottom",
            color="white",
            fontsize=11,
            fontweight="bold",
        )
    save_figure(plt, fig, path)


def plot_direct(
    plt,
    data: dict[str, Any],
    path: Path,
) -> None:
    agents = ["beam_alpha_beta", "selective_alpha_beta"]
    wins = [
        int(data["beam_alpha_beta_wins"]),
        int(data["selective_alpha_beta_wins"]),
    ]
    values = [
        float(data["beam_alpha_beta_win_rate"]),
        float(data["selective_alpha_beta_win_rate"]),
    ]
    lows = [
        float(data["beam_alpha_beta_wilson_low"]),
        float(data["selective_alpha_beta_wilson_low"]),
    ]
    highs = [
        float(data["beam_alpha_beta_wilson_high"]),
        float(data["selective_alpha_beta_wilson_high"]),
    ]
    errors = [
        [value - low for value, low in zip(values, lows)],
        [high - value for value, high in zip(values, highs)],
    ]
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    bars = ax.bar(
        [AGENT_LABELS[agent] for agent in agents],
        values,
        color=[AGENT_COLORS[agent] for agent in agents],
        yerr=errors,
        capsize=6,
        width=0.58,
    )
    ax.axhline(0.5, color="#333333", linestyle="--", linewidth=1.5)
    ax.set_ylim(0.0, 1.0)
    format_percent_axis(ax.yaxis)
    ax.set_ylabel("勝率")
    ax.set_title("Beam AlphaBetaとSelective AlphaBetaの直接対戦")
    style_axis(ax)
    for bar, value, win in zip(bars, values, wins):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=14,
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.035,
            f"{win}勝{data['games'] - win}敗",
            ha="center",
            color="white",
            fontweight="bold",
        )
    ax.text(
        0.5,
        0.94,
        f"同一設定による全{data['games']}局、先後入替",
        transform=ax.transAxes,
        ha="center",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
    )
    save_figure(plt, fig, path)


def plot_depth_strength(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    offsets = {
        "selective_alpha_beta": (8, 10),
        "pvs": (8, -24),
        "beam_alpha_beta": (8, -24),
        "beam_pvs": (8, 10),
    }
    for row in rows:
        agent = str(row["agent"])
        depth = float(row["mean_effective_depth"])
        rate = float(row["win_rate"])
        ax.scatter(
            [depth],
            [rate],
            s=180,
            color=AGENT_COLORS[agent],
            edgecolor="white",
            linewidth=1.2,
            zorder=3,
        )
        ax.annotate(
            f"{row['label']}\n深度{depth:.2f}・{rate:.1%}",
            (depth, rate),
            xytext=offsets[agent],
            textcoords="offset points",
            fontsize=12,
        )
    ax.set_xlim(5.7, 9.4)
    ax.set_ylim(0.0, 1.0)
    format_percent_axis(ax.yaxis)
    ax.set_xlabel("平均実効深度")
    ax.set_ylabel("総当たり勝率")
    ax.set_title("平均実効深度と総当たり勝率")
    style_axis(ax, grid_axis="both")
    save_figure(plt, fig, path)


def plot_appendix_parameters(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    values = [float(row["win_rate"]) for row in rows]
    bars = ax.bar(
        [row["label"] for row in rows],
        values,
        color=AGENT_COLORS["beam_alpha_beta"],
        width=0.65,
    )
    ax.axhline(0.5, color="#333333", linestyle="--", linewidth=1.5)
    ax.set_ylim(0.0, 1.0)
    format_percent_axis(ax.yaxis)
    ax.set_ylabel("対Selective AlphaBeta勝率")
    ax.set_title("Beam AlphaBetaの深度と幅の比較")
    style_axis(ax)
    for bar, row in zip(bars, rows):
        value = float(row["win_rate"])
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=13,
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.03,
            f"{row['wins']}勝{row['losses']}敗\nn={row['games']}",
            ha="center",
            color="white" if value >= 0.15 else "black",
            fontweight="bold",
        )
    save_figure(plt, fig, path)


def plot_board_adaptive_comparison(
    plt,
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), constrained_layout=True)
    values = [float(row["win_rate"]) for row in rows]
    errors = [
        [
            value - float(row["wilson_low"])
            for value, row in zip(values, rows)
        ],
        [
            float(row["wilson_high"]) - value
            for value, row in zip(values, rows)
        ],
    ]
    colors = [
        AGENT_COLORS["beam_alpha_beta"],
        "#d98880",
        "#e6b0aa",
        "#a93226",
        "#cd6155",
    ]
    bars = ax.bar(
        [row["label"] for row in rows],
        values,
        color=colors,
        yerr=errors,
        capsize=5,
        width=0.66,
        edgecolor=["#222222", "none", "none", "none", "none"],
        linewidth=[2.0, 0.0, 0.0, 0.0, 0.0],
        hatch=["//", "", "", "", ""],
    )
    ax.set_ylim(0.0, 1.0)
    format_percent_axis(ax.yaxis)
    ax.set_ylabel("総当たり勝率")
    ax.set_title("盤面適応型と固定型の勝率比較")
    style_axis(ax)
    for index, (bar, row) in enumerate(zip(bars, rows)):
        value = float(row["win_rate"])
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=13,
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.025,
            f"{row['wins']}勝{row['losses']}敗"
            f"\nn={row['games']}"
            + ("\n基準" if index == 0 else ""),
            ha="center",
            va="bottom",
            color="white" if value >= 0.2 else "black",
            fontsize=11,
            fontweight="bold",
        )
    ax.text(
        0.985,
        0.95,
        "固定型を明確に上回る\n盤面適応型は確認できなかった\n"
        "（95%区間は重なる）",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=12,
        bbox={
            "boxstyle": "round",
            "facecolor": "white",
            "edgecolor": "#666666",
            "alpha": 0.95,
        },
    )
    ax.text(
        0.015,
        0.95,
        "D10000・100局総当たり\n各設定40局・先後20局ずつ",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        bbox={
            "boxstyle": "round",
            "facecolor": "white",
            "edgecolor": "#aaaaaa",
            "alpha": 0.95,
        },
    )
    save_figure(plt, fig, path)


def plot_end_char_usage(
    plt,
    data: dict[str, Any],
    path: Path,
) -> None:
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(12.8, 7.2),
        constrained_layout=True,
        gridspec_kw={"width_ratios": [0.9, 1.45]},
    )
    fig.suptitle(
        "主要4手法の終端文字使用傾向\n"
        f"D10000・{data['match_count']}局・"
        f"{data['total_moves']:,}手／「ん」終端 "
        f"{data['ends_with_n_count']}回"
        f"（{data['ends_with_n_rate']:.1%}）",
        fontsize=18,
    )
    top_rows = data["top_end_chars"]
    chars = [str(row["end_char"]) for row in top_rows]

    counts = [int(row["move_count"]) for row in top_rows]
    positions = list(range(len(chars)))
    bars = axes[0].barh(
        positions,
        counts,
        color=AGENT_COLORS["beam_alpha_beta"],
        height=0.68,
    )
    axes[0].set_yticks(positions, chars)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("使用回数")
    axes[0].set_title("全手法合計")
    style_axis(axes[0], grid_axis="x")
    for bar, row in zip(bars, top_rows):
        axes[0].text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {row['move_count']:,}回"
            f"（{row['move_rate']:.1%}）",
            ha="left",
            va="center",
            fontsize=10,
        )
    axes[0].set_xlim(0, max(counts) * 1.28)

    agent_order = (
        "alpha_beta",
        "pvs",
        "beam_alpha_beta",
        "beam_pvs",
    )
    lookup = {
        (str(row["agent"]), str(row["end_char"])): float(
            row["move_rate"]
        )
        for row in data["by_agent"]
    }
    matrix = [
        [lookup.get((agent, end_char), 0.0) for end_char in chars]
        for agent in agent_order
    ]
    image = axes[1].imshow(
        matrix,
        cmap="Reds",
        aspect="auto",
        vmin=0.0,
        vmax=max(max(row) for row in matrix),
    )
    axes[1].set_xticks(range(len(chars)), chars)
    axes[1].set_yticks(
        range(len(agent_order)),
        [AGENT_LABELS[agent] for agent in agent_order],
    )
    axes[1].set_xlabel("終端文字")
    axes[1].set_title("手法別の使用率")
    max_rate = max(max(row) for row in matrix)
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            axes[1].text(
                x,
                y,
                f"{value:.1%}",
                ha="center",
                va="center",
                fontsize=9,
                color="white" if value >= max_rate * 0.55 else "black",
            )
    colorbar = fig.colorbar(image, ax=axes[1], fraction=0.035, pad=0.02)
    format_percent_axis(colorbar.ax.yaxis)
    colorbar.set_label("各手法内の使用率", fontsize=11)
    axes[1].tick_params(axis="both", length=0)
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)
    save_figure(plt, fig, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def figure_data_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in data["initial_agents"]:
        rows.append(
            {
                "figure": "01_initial_agents_win_rate",
                "series": item["agent"],
                "metric": "win_rate",
                "value": item["win_rate"],
                "games": item["games"],
                "wins": item["wins"],
                "losses": item["losses"],
                "wilson_low": item["wilson_low"],
                "wilson_high": item["wilson_high"],
            }
        )
    selective = data["selective_effect"]
    for series, prefix in (
        ("full_alpha_beta", "full"),
        ("selective_alpha_beta", "selective"),
    ):
        rows.extend(
            [
                {
                    "figure": "02_selective_alpha_beta_effect",
                    "series": series,
                    "metric": "mean_time_sec",
                    "value": selective[f"{prefix}_mean_time_sec"],
                    "positions": selective["position_count"],
                },
                {
                    "figure": "02_selective_alpha_beta_effect",
                    "series": series,
                    "metric": "mean_nodes",
                    "value": selective[f"{prefix}_mean_nodes"],
                    "positions": selective["position_count"],
                },
            ]
        )
    rows.append(
        {
            "figure": "02_selective_alpha_beta_effect",
            "series": "comparison",
            "metric": "move_agreement_rate",
            "value": selective["move_agreement_rate"],
            "positions": selective["comparable_count"],
        }
    )
    beam_effect = data["beam_pruning_effect"]
    for series, prefix in (
        ("beam_negamax", "beam"),
        ("beam_alpha_beta", "beam_alpha_beta"),
    ):
        for metric in ("mean_time_sec", "mean_nodes"):
            rows.append(
                {
                    "figure": "03_beam_pruning_effect",
                    "series": series,
                    "metric": metric,
                    "value": beam_effect[f"{prefix}_{metric}"],
                    "positions": beam_effect["position_count"],
                }
            )
    for item in data["four_agents"]:
        rows.append(
            {
                "figure": "04_four_agents_round_robin",
                "series": item["agent"],
                "metric": "win_rate",
                "value": item["win_rate"],
                "games": item["games"],
                "wins": item["wins"],
                "losses": item["losses"],
                "wilson_low": item["wilson_low"],
                "wilson_high": item["wilson_high"],
            }
        )
        rows.append(
            {
                "figure": "06_search_depth_and_strength",
                "series": item["agent"],
                "metric": "mean_effective_depth",
                "value": item["mean_effective_depth"],
                "games": item["games"],
            }
        )
    direct = data["direct_comparison"]
    for series, prefix in (
        ("beam_alpha_beta", "beam_alpha_beta"),
        ("selective_alpha_beta", "selective_alpha_beta"),
    ):
        rows.append(
            {
                "figure": "05_beam_alpha_beta_direct",
                "series": series,
                "metric": "win_rate",
                "value": direct[f"{prefix}_win_rate"],
                "games": direct["games"],
                "wins": direct[f"{prefix}_wins"],
                "losses": direct["games"] - direct[f"{prefix}_wins"],
                "wilson_low": direct[f"{prefix}_wilson_low"],
                "wilson_high": direct[f"{prefix}_wilson_high"],
            }
        )
    for item in data["appendix_beam_parameters"]:
        rows.append(
            {
                "figure": "appendix_beam_parameters",
                "series": item["label"],
                "metric": "win_rate",
                "value": item["win_rate"],
                "games": item["games"],
                "wins": item["wins"],
                "losses": item["losses"],
            }
        )
    for item in data["board_adaptive_comparison"]:
        rows.append(
            {
                "figure": "07_board_adaptive_comparison",
                "series": item["profile"],
                "metric": "win_rate",
                "value": item["win_rate"],
                "games": item["games"],
                "wins": item["wins"],
                "losses": item["losses"],
                "wilson_low": item["wilson_low"],
                "wilson_high": item["wilson_high"],
            }
        )
    return rows


def end_char_csv_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "scope": "overall",
            "agent": "",
            "label": "全手法",
            "rank": row["rank"],
            "end_char": row["end_char"],
            "move_count": row["move_count"],
            "move_rate": row["move_rate"],
            "total_moves": data["total_moves"],
        }
        for row in data["overall"]
    ]
    rows.extend(
        {
            "scope": "agent",
            "agent": row["agent"],
            "label": row["label"],
            "rank": row["rank"],
            "end_char": row["end_char"],
            "move_count": row["move_count"],
            "move_rate": row["move_rate"],
            "total_moves": row["total_moves"],
        }
        for row in data["by_agent"]
    )
    return rows


def verify_images(paths: list[Path]) -> dict[str, Any]:
    details = []
    for path in paths:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
        ratio = width / height
        details.append(
            {
                "file": path.name,
                "width": width,
                "height": height,
                "aspect_ratio": ratio,
                "valid_16_9": abs(ratio - 16 / 9) < 0.01,
                "minimum_slide_resolution": (
                    width >= 2500 and height >= 1400
                ),
            }
        )
    return {
        "image_count": len(details),
        "all_openable": len(details) == len(paths),
        "all_16_9": all(item["valid_16_9"] for item in details),
        "all_high_resolution": all(
            item["minimum_slide_resolution"] for item in details
        ),
        "details": details,
    }


def write_report(
    path: Path,
    data: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    initial = data["initial_agents"]
    selective = data["selective_effect"]
    beam_effect = data["beam_pruning_effect"]
    four = data["four_agents"]
    direct = data["direct_comparison"]
    appendix = data["appendix_beam_parameters"]
    board = data["board_adaptive_comparison"]
    board_validation = validation["board_adaptive"]
    proof_moderate = next(
        row for row in board if row["profile"] == "proof_moderate"
    )
    end_chars = data["end_char_usage"]
    agent_top_end_chars = [
        row for row in end_chars["by_agent"] if row["rank"] == 1
    ]
    lines = [
        "# 発表用グラフ再集計レポート",
        "",
        "既存のJSONL、JSON、CSV、manifestだけから再集計した。"
        "対局や探索の再実行は行っていない。",
        "",
        "## 01 基本6手法の総当たり勝率",
        "",
        "- raw: `initial6/raw_matches.jsonl`",
        "- 抽出条件: D10000、1手1秒、6手法全組合せ・先後入替",
        f"- 使用対局数: {validation['initial_match_count']}局",
        "- 再計算値: "
        + "、".join(
            f"{row['label']} {row['win_rate']:.1%}"
            for row in initial
        ),
        "- 変更点: 縦棒から発展順の横棒へ変更し、Wilson区間を併記。",
        "- 発表用一文: 単純手法から先読み探索へ進むにつれ、"
        "同じ1秒制限下で高い勝率が得られた。",
        "- 断定できないこと: 各手法の深度や候補上限が異なるため、"
        "探索原理だけの因果効果ではない。",
        "",
        "## 02 候補制限による探索量と選択手の変化",
        "",
        "- raw: `fixed_comparison/raw_runs.jsonl`",
        "- 抽出条件: 深度5、Fullと候補上限12、固定50局面",
        f"- 比較可能局面: {selective['comparable_count']}/"
        f"{selective['position_count']}",
        f"- 平均時間: Full {selective['full_mean_time_sec']:.3f}秒、"
        f"Selective {selective['selective_mean_time_sec']:.3f}秒",
        f"- 平均ノード: Full {selective['full_mean_nodes']:.0f}、"
        f"Selective {selective['selective_mean_nodes']:.0f}",
        f"- 選択手一致率: {selective['move_agreement_rate']:.1%}",
        f"- 評価値一致率: {selective['score_agreement_rate']:.1%}",
        "- 変更点: 時間・ノード・手一致を一枚の3パネルへ統合。",
        "- 発表用一文: 候補制限は手の一致を概ね保ちながら、"
        "探索量を大幅に削減した。",
        "- 断定できないこと: Fullが完了しなかった10局面の手の"
        "正しさは比較していない。",
        "",
        "## 03 Beam探索へのAlphaBeta枝刈りの導入",
        "",
        "- raw: `results/hybrid_agent_comparison/benchmark/"
        "821264dd868d/runs.jsonl`",
        "- 抽出条件: 同一深度5、同一14固定局面、幅8/6/4/2",
        f"- 使用局面数: {beam_effect['position_count']}局面",
        f"- 平均時間: Beam {beam_effect['beam_mean_time_sec']:.4f}秒、"
        f"Beam AlphaBeta "
        f"{beam_effect['beam_alpha_beta_mean_time_sec']:.4f}秒"
        f"（{beam_effect['time_reduction_rate']:.1%}削減）",
        f"- 平均ノード: Beam {beam_effect['beam_mean_nodes']:.0f}、"
        f"Beam AlphaBeta "
        f"{beam_effect['beam_alpha_beta_mean_nodes']:.0f}"
        f"（{beam_effect['node_reduction_rate']:.1%}削減）",
        "- 変更点: 時間とノードを一枚の2パネルへ統合。",
        "- 発表用一文: AlphaBeta枝刈りを加えることで、"
        "同一深度のBeam探索量を約7割削減した。",
        "- 断定できないこと: この図は探索量比較であり、"
        "勝率向上を直接示さない。",
        "",
        "## 04 主要4手法の総当たり勝率",
        "",
        "- raw: `final4/raw_matches.jsonl`",
        "- 抽出条件: D10000、1手1秒、4手法全組合せ・先後入替",
        f"- 使用対局数: {validation['four_agent_match_count']}局",
        "- 再計算値: "
        + "、".join(
            f"{row['label']} {row['win_rate']:.1%}"
            for row in four
        ),
        "- 変更点: 共通条件120局だけを使用し、直接対戦の追加20局を"
        "加えていない。",
        "- 発表用一文: 主要4手法の総当たりでは、"
        "Beam AlphaBetaの明確な優位性は確認できなかった。",
        "- 断定できないこと: 4方式間の勝率差はWilson区間が重なり、"
        "統計的有意差を示すものではない。",
        "",
        "## 05 Beam AlphaBetaとSelective AlphaBetaの直接対戦",
        "",
        "- raw: `beam_hybrid_followup/.../raw_matches.jsonl` と"
        " `final4/raw_matches.jsonl`",
        "- 抽出条件: 両手法の深度・幅・候補上限・適応設定・1秒制限が"
        "一致する直接対戦のみ",
        f"- 使用対局数: {direct['games']}局",
        f"- Beam AlphaBeta: {direct['beam_alpha_beta_wins']}勝"
        f"{direct['selective_alpha_beta_wins']}敗、"
        f"{direct['beam_alpha_beta_win_rate']:.1%}",
        f"- Selective AlphaBeta: {direct['selective_alpha_beta_wins']}勝"
        f"{direct['beam_alpha_beta_wins']}敗、"
        f"{direct['selective_alpha_beta_win_rate']:.1%}",
        f"- 変更点: 20局ずつを別表示せず、同一設定の全"
        f"{direct['games']}局へ統合。",
        "- 発表用一文: Beam AlphaBetaはSelective AlphaBetaとの"
        f"全{direct['games']}局で{direct['beam_alpha_beta_wins']}勝"
        f"{direct['selective_alpha_beta_wins']}敗だった。",
        f"- 断定できないこと: この{direct['games']}局には設定選定に"
        "利用した対局を含むため、データ分離を前提とする評価ではない。",
        "",
        "## 06 平均実効深度と総当たり勝率",
        "",
        "- raw: `final4/raw_matches.jsonl`",
        "- 抽出条件: 主要4手法の共通条件120局",
        f"- 使用対局数: {validation['four_agent_match_count']}局",
        "- 再計算値: "
        + "、".join(
            f"{row['label']} 深度{row['mean_effective_depth']:.2f}・"
            f"勝率{row['win_rate']:.1%}"
            for row in four
        ),
        "- 変更点: 時間と深度の棒図から、深度と勝率の散布図へ変更。",
        "- 発表用一文: Beam系は深く探索できたが、"
        "探索深度だけでは勝率は決まらなかった。",
        "- 断定できないこと: 4点のみのため相関や回帰関係は"
        "評価していない。",
        "",
        "## 補足 Beam AlphaBetaの深度と幅の比較",
        "",
        "- raw: `results/beam_hybrid_followup/D10000/c86fc7661da6/"
        "raw_matches.jsonl`",
        "- 抽出条件: 各設定をSelective AlphaBetaと20局、"
        "設定間の合算なし",
        "- 再計算値: "
        + "、".join(
            f"{row['label']} {row['wins']}勝{row['losses']}敗・"
            f"{row['win_rate']:.1%}（n={row['games']}）"
            for row in appendix
        ),
        "- 変更点: 各設定を分離したまま一枚へまとめ、勝敗数と"
        "対局数を併記。",
        "- 発表用一文: 深度とルート付近の幅を同時に増やした設定が、"
        "この比較では最も高い勝率だった。",
        "- 断定できないこと: 設定候補を選んだ対局なので、"
        "方式全体の一般的優位性ではない。",
        "",
        "## 07 盤面適応型と固定型の勝率比較",
        "",
        "- raw: `results/minimal_adaptive_hybrid/D10000/"
        "round_robin_matches.jsonl`",
        "- 抽出条件: D10000、5設定の総当たり100局、1手0.3秒、"
        "適応深度8→9、Beam幅12/8/4/2",
        f"- 辞書seed: {board_validation['dictionary_seeds']}、"
        "各seedで全組合せを先後入替",
        "- 先後条件: 各設定40局、先手20局・後手20局",
        "- 再計算値: "
        + "、".join(
            f"{row['profile']} {row['wins']}勝{row['losses']}敗・"
            f"{row['win_rate']:.1%}（n={row['games']}）"
            for row in board
        ),
        "- Proof系の扱い: proof_strictとproof_moderateは閾値と"
        "完全解析上限が異なるため統合せず、別の棒として表示。",
        "- 固定型との直接対戦: "
        + "、".join(
            f"{profile} {row['wins']}勝{row['losses']}敗"
            for profile, row in board_validation["vs_fixed"].items()
        ),
        "- 変更点: 固定型を基準色・斜線・枠線で強調し、"
        "盤面適応型4設定を同系色で比較。",
        "- 発表用一文: 固定型を明確に上回る盤面適応型は"
        "確認できなかった。",
        f"- 断定できないこと: Proof Moderateは総当たり"
        f"{proof_moderate['win_rate']:.1%}だが、"
        "各方式40局でWilson区間が重なるため、統計的な優位性や"
        "一般的な強さは断定できない。",
        "",
        "## 08 主要4手法の終端文字使用傾向",
        "",
        "- raw: `final4/raw_matches.jsonl` の各手`end_char`",
        f"- 抽出条件: D10000、主要4手法の共通条件"
        f"{end_chars['match_count']}局、全履歴",
        f"- 使用手数: {end_chars['total_moves']:,}手",
        "- 全体上位: "
        + "、".join(
            f"{row['end_char']} {row['move_count']:,}回"
            f"（{row['move_rate']:.1%}）"
            for row in end_chars["top_end_chars"][:5]
        ),
        "- 手法別最多: "
        + "、".join(
            f"{row['label']}「{row['end_char']}」"
            f"{row['move_count']:,}回（{row['move_rate']:.1%}）"
            for row in agent_top_end_chars
        ),
        f"- 「ん」終端: {end_chars['ends_with_n_count']}回"
        f"（{end_chars['ends_with_n_rate']:.1%}）",
        "- 変更点: 全体の使用回数と、手数差を補正した手法別使用率を"
        "一枚へ統合。",
        "- 発表用一文: 全手法で「る」が最も多い一方、"
        "使用率には手法ごとの差が見られた。",
        "- 断定できないこと: 出現頻度だけでは、その終端文字を"
        "選ぶことが勝敗に有利だったとは断定できない。",
        "",
        "## 発表全体の結論",
        "",
        "候補制限と枝刈りによって探索量を削減し、より深い探索が"
        "可能になった。Beam AlphaBetaはSelective AlphaBetaとの"
        f"全{direct['games']}局で{direct['beam_alpha_beta_wins']}勝"
        f"{direct['selective_alpha_beta_wins']}敗だったが、"
        "主要4手法の総当たりでは明確な"
        "優位性は確認できなかった。このことから、探索の深さだけで"
        "なく、Beamに残す候補の選び方も重要だと考えられる。",
        "",
        "## 自動検査",
        "",
        "```json",
        json.dumps(validation, ensure_ascii=False, indent=2),
        "```",
    ]
    text = "\n".join(lines) + "\n"
    for term in BANNED_PRESENTATION_TERMS:
        if term in text:
            raise AssertionError(f"banned presentation term found: {term}")
    path.write_text(text, encoding="utf-8")


def validate(
    presentation_rows: list[dict[str, Any]],
    initial_rows: list[dict[str, Any]],
    fixed_rows: list[dict[str, Any]],
    direct: dict[str, Any],
    presentation_signature: dict[str, Any],
    followup_signature: dict[str, Any],
    recorded_conditions_match: bool,
) -> dict[str, Any]:
    four_ids = [str(row["match_id"]) for row in presentation_rows]
    initial_ids = [str(row["match_id"]) for row in initial_rows]
    fixed_positions = {
        str(row["position_id"]) for row in fixed_rows
    }
    fixed_summary, representative_depth = fixed_comparison_summary(
        fixed_rows
    )
    representative = next(
        row for row in fixed_summary if row["depth"] == representative_depth
    )
    settings_match = presentation_signature == followup_signature
    validation = {
        "direct_match_count": direct["games"],
        "direct_beam_alpha_beta_wins": direct[
            "beam_alpha_beta_wins"
        ],
        "direct_selective_alpha_beta_wins": direct[
            "selective_alpha_beta_wins"
        ],
        "direct_draw_count": direct["draws"],
        "direct_duplicate_match_id_count": direct[
            "duplicate_match_id_count"
        ],
        "direct_beam_first_count": direct[
            "beam_alpha_beta_first_count"
        ],
        "direct_selective_first_count": direct[
            "selective_alpha_beta_first_count"
        ],
        "direct_settings_match": settings_match,
        "recorded_evaluation_and_game_settings_match": (
            recorded_conditions_match
        ),
        "four_agent_match_count": len(presentation_rows),
        "four_agent_unique_match_count": len(set(four_ids)),
        "initial_match_count": len(initial_rows),
        "initial_unique_match_count": len(set(initial_ids)),
        "fixed_position_count": len(fixed_positions),
        "fixed_comparable_position_count": representative[
            "comparable_count"
        ],
        "representative_depth": representative_depth,
    }
    required = {
        "direct_match_count": 40,
        "direct_beam_alpha_beta_wins": 23,
        "direct_selective_alpha_beta_wins": 17,
        "direct_draw_count": 0,
        "direct_duplicate_match_id_count": 0,
        "direct_beam_first_count": 20,
        "direct_selective_first_count": 20,
        "direct_settings_match": True,
        "recorded_evaluation_and_game_settings_match": True,
        "four_agent_match_count": 120,
        "four_agent_unique_match_count": 120,
        "initial_match_count": 90,
        "initial_unique_match_count": 90,
        "fixed_position_count": 50,
        "fixed_comparable_position_count": 40,
        "representative_depth": 5,
    }
    validation["required_values"] = required
    validation["all_data_checks_passed"] = all(
        validation[key] == expected for key, expected in required.items()
    )
    if not validation["all_data_checks_passed"]:
        raise AssertionError(
            "final figure data validation failed:\n"
            + json.dumps(validation, ensure_ascii=False, indent=2)
        )
    return validation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="presentation experiment run; latest complete run by default",
    )
    parser.add_argument(
        "--beam-followup",
        type=Path,
        default=BEAM_FOLLOWUP,
    )
    parser.add_argument(
        "--same-depth-runs",
        type=Path,
        default=SAME_DEPTH_RUNS,
    )
    parser.add_argument(
        "--board-adaptive-root",
        type=Path,
        default=BOARD_ADAPTIVE_ROOT,
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    presentation = (
        args.input.resolve()
        if args.input is not None
        else latest_presentation_run()
    )
    followup = args.beam_followup.resolve()
    board_adaptive_root = args.board_adaptive_root.resolve()
    output = presentation / "analysis/final_figures"
    output.mkdir(parents=True, exist_ok=True)

    presentation_manifest = load_json(presentation / "manifest.json")
    followup_manifest = load_json(followup / "manifest.json")
    final_rows = read_jsonl(presentation / "final4/raw_matches.jsonl")
    initial_rows = read_jsonl(presentation / "initial6/raw_matches.jsonl")
    fixed_rows = read_jsonl(
        presentation / "fixed_comparison/raw_runs.jsonl"
    )
    followup_rows = read_jsonl(followup / "raw_matches.jsonl")
    same_depth_rows = read_jsonl(args.same_depth_runs.resolve())
    board_adaptive_rows = read_jsonl(
        board_adaptive_root / "round_robin_matches.jsonl"
    )

    initial_agents = summarize_matches(
        initial_rows,
        (
            "random",
            "monte_carlo",
            "greedy",
            "minimax",
            "full_alpha_beta",
            "selective_alpha_beta",
        ),
    )
    four_agents = summarize_matches(
        final_rows,
        (
            "selective_alpha_beta",
            "pvs",
            "beam_alpha_beta",
            "beam_pvs",
        ),
    )
    fixed_summary, representative_depth = fixed_comparison_summary(
        fixed_rows
    )
    selective_effect = next(
        row for row in fixed_summary if row["depth"] == representative_depth
    )
    beam_effect = same_depth_effect(same_depth_rows)
    direct = direct_result(final_rows, followup_rows)
    appendix = appendix_parameter_rows(followup_rows)
    board_adaptive, board_adaptive_validation = (
        board_adaptive_match_summary(
            board_adaptive_rows,
        )
    )
    end_char_usage = end_char_usage_summary(final_rows)
    presentation_signature, followup_signature = canonical_settings(
        presentation_manifest, followup_manifest
    )
    recorded_conditions_match = recorded_direct_conditions_match(
        final_rows,
        followup_rows,
    )
    validation = validate(
        final_rows,
        initial_rows,
        fixed_rows,
        direct,
        presentation_signature,
        followup_signature,
        recorded_conditions_match,
    )
    validation["board_adaptive"] = board_adaptive_validation
    validation["end_char_usage"] = {
        "match_count": end_char_usage["match_count"],
        "total_moves": end_char_usage["total_moves"],
        "agent_totals": end_char_usage["agent_totals"],
        "agent_total_matches_overall": (
            sum(end_char_usage["agent_totals"].values())
            == end_char_usage["total_moves"]
        ),
        "top_end_char": end_char_usage["top_end_chars"][0][
            "end_char"
        ],
        "all_history_turns_have_end_char": True,
    }
    data = {
        "format_version": "final_presentation_figures_v1",
        "presentation_run": str(presentation),
        "sources": {
            "four_agent_raw": str(
                presentation / "final4/raw_matches.jsonl"
            ),
            "initial_six_raw": str(
                presentation / "initial6/raw_matches.jsonl"
            ),
            "fixed_comparison_raw": str(
                presentation / "fixed_comparison/raw_runs.jsonl"
            ),
            "beam_followup_raw": str(followup / "raw_matches.jsonl"),
            "same_depth_raw": str(args.same_depth_runs.resolve()),
            "board_adaptive_raw": str(
                board_adaptive_root / "round_robin_matches.jsonl"
            ),
        },
        "settings_validation": {
            "presentation_signature": presentation_signature,
            "followup_signature": followup_signature,
        },
        "initial_agents": initial_agents,
        "selective_effect": selective_effect,
        "beam_pruning_effect": beam_effect,
        "four_agents": four_agents,
        "direct_comparison": {
            key: value for key, value in direct.items() if key != "rows"
        },
        "appendix_beam_parameters": appendix,
        "board_adaptive_comparison": board_adaptive,
        "end_char_usage": end_char_usage,
        "validation": validation,
    }

    plt = configure_matplotlib()
    paths = [
        output / "01_initial_agents_win_rate.png",
        output / "02_selective_alpha_beta_effect.png",
        output / "03_beam_pruning_effect.png",
        output / "04_four_agents_round_robin.png",
        output / "05_beam_alpha_beta_direct.png",
        output / "06_search_depth_and_strength.png",
        output / "07_board_adaptive_comparison.png",
        output / "08_end_char_usage.png",
        output / "appendix_beam_parameters.png",
    ]
    plot_horizontal_win_rates(plt, initial_agents, paths[0])
    plot_selective_effect(plt, selective_effect, paths[1])
    plot_beam_pruning(plt, beam_effect, paths[2])
    plot_four_agents(plt, four_agents, paths[3])
    plot_direct(plt, direct, paths[4])
    plot_depth_strength(plt, four_agents, paths[5])
    plot_board_adaptive_comparison(plt, board_adaptive, paths[6])
    plot_end_char_usage(plt, end_char_usage, paths[7])
    plot_appendix_parameters(plt, appendix, paths[8])

    validation["images"] = verify_images(paths)
    if not all(
        (
            validation["images"]["all_openable"],
            validation["images"]["all_16_9"],
            validation["images"]["all_high_resolution"],
        )
    ):
        raise AssertionError("image verification failed")
    data["validation"] = validation
    json_text = (
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    for term in BANNED_PRESENTATION_TERMS:
        if term in json_text:
            raise AssertionError(f"banned presentation term found: {term}")
    (output / "figure_data.json").write_text(
        json_text, encoding="utf-8"
    )
    write_csv(output / "figure_data.csv", figure_data_rows(data))
    write_csv(
        output / "end_char_usage.csv",
        end_char_csv_rows(end_char_usage),
    )
    (output / "end_char_usage.json").write_text(
        json.dumps(
            end_char_usage,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(output / "figure_report.md", data, validation)
    print(output)


if __name__ == "__main__":
    main()
