"""Detailed, read-mostly analysis of existing deterministic shiritori agents."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from agents import AlphaBetaAgent, BeamNegamaxAgent, _edge_sort_key
from match import simulate_runtime_match
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState
from search_common import (
    edge_candidate_analysis,
    evaluate_edge_candidate,
    evaluate_ordering_score,
)
from visualize import ensure_matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPROVEMENT_ROOT = PROJECT_ROOT / "results/existing_agent_improvement"
ANALYSIS_ROOT = PROJECT_ROOT / "results/existing_agent_analysis"
MAJOR_AGENTS = ("alpha_beta", "pvs", "beam_negamax")
RISK_NAMES = ("normal", "caution", "danger", "near_death")


def percentile(values: Iterable[float], rate: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(len(ordered) * rate) - 1)]


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
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_risk(value: str) -> str:
    return "near_death" if value == "critical" else value


def winner_agent(row: dict[str, Any]) -> str:
    winner = str(row["winner"])
    return str(row[f"{winner}_agent"]) if winner in {"first", "second"} else "draw"


def match_id(row: dict[str, Any]) -> str:
    return (
        f"D{int(row['dict_size'])}_seed{int(row['seed'])}_"
        f"{row['first_agent']}_vs_{row['second_agent']}"
    )


def validate_final_matches(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "runtime",
        "dict_size",
        "seed",
        "first_agent",
        "second_agent",
        "winner",
        "turn_count",
        "loss_reason",
    }
    missing = [
        {"index": index, "fields": sorted(required - set(row))}
        for index, row in enumerate(rows)
        if required - set(row)
    ]
    keys = [
        (row.get("runtime"), row.get("first_agent"), row.get("second_agent"))
        for row in rows
    ]
    duplicates = [list(key) for key, count in Counter(keys).items() if count > 1]
    deterministic_repetitions = [
        list(key)
        for key, count in Counter(
            (
                row.get("dict_size"),
                row.get("seed"),
                row.get("first_agent"),
                row.get("second_agent"),
            )
            for row in rows
        ).items()
        if count > 1
    ]
    return {
        "match_count": len(rows),
        "unique_match_count": len(set(keys)),
        "missing_required_fields": missing,
        "duplicate_keys": duplicates,
        "deterministic_repetitions": deterministic_repetitions,
        "valid": not missing and not duplicates and not deterministic_repetitions,
        "available_final_fields": sorted({field for row in rows for field in row}),
        "unavailable_without_trace_rerun": [
            "per-turn nodes and evaluation fields for the final 108 matches",
            "per-turn candidate ordering and alternative candidate scores",
            "counterfactual continuations",
        ],
    }


def _appearance_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    appearances: list[dict[str, Any]] = []
    for row in matches:
        won = winner_agent(row)
        for side in ("first", "second"):
            agent = str(row[f"{side}_agent"])
            appearances.append(
                {
                    **row,
                    "agent": agent,
                    "opponent": str(
                        row["second_agent"] if side == "first" else row["first_agent"]
                    ),
                    "seat": side,
                    "won": won == agent,
                    "draw": won == "draw",
                    "avg_time_sec": float(row.get(f"{side}_avg_time_sec", 0.0)),
                    "timeout_count": int(row.get(f"{side}_timeout_count", 0)),
                }
            )
    return appearances


def aggregate_matchups(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    appearances = _appearance_rows(matches)
    direct = [
        row
        for row in appearances
        if row["agent"] in MAJOR_AGENTS and row["opponent"] in MAJOR_AGENTS
    ]

    def summarize(
        rows: list[dict[str, Any]], group_fields: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[tuple(row[field] for field in group_fields)].append(row)
        output = []
        for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
            turns = [int(row["turn_count"]) for row in values]
            wins = sum(bool(row["won"]) for row in values)
            draws = sum(bool(row["draw"]) for row in values)
            result = dict(zip(group_fields, key))
            result.update(
                {
                    "games": len(values),
                    "wins": wins,
                    "losses": len(values) - wins - draws,
                    "draws": draws,
                    "win_rate": wins / len(values),
                    "first_games": sum(row["seat"] == "first" for row in values),
                    "first_win_rate": (
                        statistics.fmean(
                            row["won"] for row in values if row["seat"] == "first"
                        )
                        if any(row["seat"] == "first" for row in values)
                        else 0.0
                    ),
                    "second_games": sum(row["seat"] == "second" for row in values),
                    "second_win_rate": (
                        statistics.fmean(
                            row["won"] for row in values if row["seat"] == "second"
                        )
                        if any(row["seat"] == "second" for row in values)
                        else 0.0
                    ),
                    "mean_turns": statistics.fmean(turns),
                    "median_turns": statistics.median(turns),
                    "p95_turns": percentile(turns, 0.95),
                    "min_turns": min(turns),
                    "max_turns": max(turns),
                    "mean_time_sec": statistics.fmean(
                        float(row["avg_time_sec"]) for row in values
                    ),
                }
            )
            output.append(result)
        return output

    overall = summarize(appearances, ("agent",))
    direct_rows = summarize(direct, ("agent", "opponent"))
    by_size = summarize(appearances, ("dict_size", "agent"))
    by_seed = summarize(appearances, ("dict_size", "seed", "agent"))
    by_seat = summarize(appearances, ("agent", "seat"))

    first_player: list[dict[str, Any]] = []
    for fields in ((), ("dict_size",), ("dict_size", "seed"), ("first_agent", "second_agent")):
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in matches:
            grouped[tuple(row[field] for field in fields)].append(row)
        for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
            first_player.append(
                {
                    **dict(zip(fields, key)),
                    "group": ",".join(fields) or "all",
                    "matches": len(values),
                    "first_wins": sum(row["winner"] == "first" for row in values),
                    "second_wins": sum(row["winner"] == "second" for row in values),
                    "draws": sum(row["winner"] == "draw" for row in values),
                    "first_win_rate": statistics.fmean(
                        row["winner"] == "first" for row in values
                    ),
                    "mean_turns": statistics.fmean(
                        int(row["turn_count"]) for row in values
                    ),
                    "median_turns": statistics.median(
                        int(row["turn_count"]) for row in values
                    ),
                    "max_turns": max(int(row["turn_count"]) for row in values),
                }
            )

    pair_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in matches:
        pair = tuple(sorted((str(row["first_agent"]), str(row["second_agent"]))))
        pair_groups[(row["runtime"], *pair)].append(row)
    paired = []
    for (_runtime, left, right), values in sorted(pair_groups.items(), key=str):
        if len(values) != 2:
            continue
        counts = Counter(winner_agent(row) for row in values)
        paired.append(
            {
                "dict_size": values[0]["dict_size"],
                "seed": values[0]["seed"],
                "left_agent": left,
                "right_agent": right,
                "left_result": (
                    "two_wins"
                    if counts[left] == 2
                    else "split"
                    if counts[left] == counts[right] == 1
                    else "two_losses"
                ),
                "left_wins": counts[left],
                "right_wins": counts[right],
            }
        )
    return {
        "overall": overall,
        "direct": direct_rows,
        "by_size": by_size,
        "by_seed": by_seed,
        "by_seat": by_seat,
        "first_player": first_player,
        "paired_seats": paired,
    }


def aggregate_length(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    appearances = _appearance_rows(matches)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in appearances:
        grouped[(row["agent"], "all")].append(row)
        grouped[(row["agent"], "win" if row["won"] else "loss")].append(row)
    output = []
    for (agent, outcome), rows in sorted(grouped.items()):
        turns = [int(row["turn_count"]) for row in rows]
        output.append(
            {
                "agent": agent,
                "outcome": outcome,
                "games": len(rows),
                "mean_turns": statistics.fmean(turns),
                "median_turns": statistics.median(turns),
                "p95_turns": percentile(turns, 0.95),
                "min_turns": min(turns),
                "max_turns": max(turns),
                "at_least_100_rate": statistics.fmean(value >= 100 for value in turns),
                "at_least_200_rate": statistics.fmean(value >= 200 for value in turns),
                "at_least_300_rate": statistics.fmean(value >= 300 for value in turns),
            }
        )
    return output


def _agent_for_name(name: str, selected: dict[str, dict[str, Any]], limit: float):
    from run_existing_agent_improvement import build_final_agent

    return build_final_agent(name, selected.get(name, {}), limit)


def run_trace_experiment(
    final_matches: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    output_path: Path,
    *,
    quick: bool,
) -> list[dict[str, Any]]:
    existing = read_jsonl(output_path) if output_path.is_file() else []
    completed = {row["match_id"] for row in existing}
    candidates = final_matches
    if quick:
        direct = [
            row
            for row in candidates
            if row["first_agent"] in MAJOR_AGENTS
            and row["second_agent"] in MAJOR_AGENTS
        ]
        candidates = direct[:6]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for expected in candidates:
        identifier = match_id(expected)
        if identifier in completed:
            continue
        runtime = RuntimeDictionary.load(Path(expected["runtime"]))
        result = simulate_runtime_match(
            runtime,
            _agent_for_name(expected["first_agent"], selected, 1.0),
            _agent_for_name(expected["second_agent"], selected, 1.0),
            max_moves=1000,
            max_match_time_sec=300.0,
            match_id=identifier,
        )
        actual = result.to_csv_row()
        trace = {
            "match_id": identifier,
            "runtime": expected["runtime"],
            "dict_size": expected["dict_size"],
            "seed": expected["seed"],
            "first_agent": expected["first_agent"],
            "second_agent": expected["second_agent"],
            "winner": result.winner,
            "winner_agent": (
                result.first_agent
                if result.winner == "first"
                else result.second_agent
                if result.winner == "second"
                else "draw"
            ),
            "turn_count": result.turn_count,
            "loss_reason": result.loss_reason,
            "matches_baseline_winner": result.winner == expected["winner"],
            "matches_baseline_turn_count": result.turn_count == expected["turn_count"],
            "history": result.history,
            "timing": {
                key: actual[key]
                for key in actual
                if "time" in key or "timeout" in key
            },
        }
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")
        existing.append(trace)
        completed.add(identifier)
    return existing


def flatten_turns(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trace in traces:
        for turn in trace["history"]:
            rows.append(
                {
                    "match_id": trace["match_id"],
                    "dict_size": trace["dict_size"],
                    "seed": trace["seed"],
                    "first_agent": trace["first_agent"],
                    "second_agent": trace["second_agent"],
                    "winner_agent": trace["winner_agent"],
                    "turn_count": trace["turn_count"],
                    "agent_won": turn["agent"] == trace["winner_agent"],
                    "phase": (
                        "early"
                        if turn["turn"] <= trace["turn_count"] / 3
                        else "middle"
                        if turn["turn"] <= 2 * trace["turn_count"] / 3
                        else "late"
                    ),
                    "candidate_bucket": (
                        "1-8"
                        if _numeric(turn, "root_candidate_count") <= 8
                        else "9-16"
                        if _numeric(turn, "root_candidate_count") <= 16
                        else "17-32"
                        if _numeric(turn, "root_candidate_count") <= 32
                        else "33+"
                    ),
                    **{
                        **turn,
                        "risk_level": normalize_risk(str(turn["risk_level"])),
                    },
                }
            )
    return rows


def _numeric(row: dict[str, Any], field: str) -> float:
    value = row.get(field, 0)
    return float(value) if value not in ("", None) else 0.0


def aggregate_turn_metrics(turns: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    fields = (
        "elapsed_time_sec",
        "nodes_searched",
        "leaf_evaluations",
        "ordering_evaluations",
        "completed_root_moves",
        "cutoff_count",
        "root_candidate_count",
        "opponent_legal_word_count",
        "opponent_safe_word_count",
        "opponent_active_edge_type_count",
        "opponent_safe_edge_type_count",
        "opponent_destination_count",
        "opponent_safe_destination_count",
        "own_safe_word_count",
        "own_safe_edge_type_count",
        "own_safe_destination_count",
        "attack_score",
        "survival_score",
        "survival_weight",
        "total_score",
    )

    def summarize(group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in turns:
            grouped[tuple(row[field] for field in group_fields)].append(row)
        output = []
        for key, rows in sorted(grouped.items(), key=lambda item: str(item[0])):
            result = {**dict(zip(group_fields, key)), "turns": len(rows)}
            for field in fields:
                values = [_numeric(row, field) for row in rows]
                result[f"mean_{field}"] = statistics.fmean(values)
                if field in {"elapsed_time_sec", "nodes_searched"}:
                    result[f"median_{field}"] = statistics.median(values)
                    result[f"p95_{field}"] = percentile(values, 0.95)
                    result[f"max_{field}"] = max(values)
            nodes = sum(_numeric(row, "nodes_searched") for row in rows)
            result["time_per_node_sec"] = (
                sum(_numeric(row, "elapsed_time_sec") for row in rows) / nodes
                if nodes
                else 0.0
            )
            result["timeout_rate"] = statistics.fmean(
                bool(row.get("timed_out")) for row in rows
            )
            result["win_rate_from_position"] = statistics.fmean(
                bool(row["agent_won"]) for row in rows
            )
            output.append(result)
        return output

    pvs_turns = [row for row in turns if row["agent"] == "pvs"]
    pvs_research = [
        {
            "match_id": row["match_id"],
            "turn": row["turn"],
            "risk_level": row["risk_level"],
            "root_candidate_count": row["root_candidate_count"],
            "nodes_searched": row["nodes_searched"],
            "elapsed_time_sec": row["elapsed_time_sec"],
            "null_window_searches": row["null_window_searches"],
            "research_count": row["research_count"],
            "research_rate": row["research_rate"],
            "had_research": _numeric(row, "research_count") > 0,
        }
        for row in pvs_turns
    ]
    return {
        "by_agent": summarize(("agent",)),
        "by_agent_risk": summarize(("agent", "risk_level")),
        "by_agent_depth": summarize(("agent", "effective_depth")),
        "by_agent_size": summarize(("agent", "dict_size")),
        "by_agent_phase": summarize(("agent", "phase")),
        "by_agent_candidate_count": summarize(("agent", "candidate_bucket")),
        "pvs_research": pvs_research,
    }


def fixed_search_efficiency(improvement_root: Path) -> dict[str, Any]:
    payload = json.loads(
        (improvement_root / "equal_depth/fixed/benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    runs = payload["runs"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[(str(row["agent"]), normalize_risk(str(row["risk_level"])))].append(row)
    rows = []
    for (agent, risk), values in sorted(grouped.items()):
        elapsed = [_numeric(row, "elapsed_time_sec") for row in values]
        nodes = [_numeric(row, "nodes_searched") for row in values]
        rows.append(
            {
                "agent": agent,
                "risk_level": risk,
                "runs": len(values),
                "mean_time_sec": statistics.fmean(elapsed),
                "median_time_sec": statistics.median(elapsed),
                "p95_time_sec": percentile(elapsed, 0.95),
                "max_time_sec": max(elapsed),
                "mean_nodes": statistics.fmean(nodes),
                "median_nodes": statistics.median(nodes),
                "p95_nodes": percentile(nodes, 0.95),
                "time_per_node_sec": sum(elapsed) / sum(nodes) if sum(nodes) else 0.0,
                "mean_leaf_evaluations": statistics.fmean(
                    _numeric(row, "leaf_evaluations") for row in values
                ),
                "mean_ordering_evaluations": statistics.fmean(
                    _numeric(row, "ordering_evaluations") for row in values
                ),
                "mean_completed_root_moves": statistics.fmean(
                    _numeric(row, "completed_root_moves") for row in values
                ),
                "mean_cutoff_count": statistics.fmean(
                    _numeric(row, "cutoff_count") for row in values
                ),
                "mean_effective_depth": statistics.fmean(
                    _numeric(row, "effective_depth") for row in values
                ),
                "timeout_rate": statistics.fmean(
                    bool(row["timed_out"]) for row in values
                ),
                "mean_research_rate": statistics.fmean(
                    _numeric(row, "research_rate") for row in values
                ),
            }
        )
    indexed = {
        (row["position_id"], row["repetition"], row["agent"]): row for row in runs
    }
    pairs = [
        (row, indexed[(row["position_id"], row["repetition"], "pvs")])
        for row in runs
        if row["agent"] == "alpha_beta"
    ]
    agreement_rows = []
    for risk in RISK_NAMES:
        position_ids = {
            row["position_id"]
            for row in runs
            if normalize_risk(str(row["risk_level"])) == risk
        }
        for left_name, right_name in (
            ("alpha_beta", "pvs"),
            ("alpha_beta", "beam_negamax"),
            ("pvs", "beam_negamax"),
        ):
            risk_pairs = [
                (
                    indexed[(position_id, repetition, left_name)],
                    indexed[(position_id, repetition, right_name)],
                )
                for position_id in position_ids
                for repetition in range(5)
                if (position_id, repetition, left_name) in indexed
                and (position_id, repetition, right_name) in indexed
            ]
            if risk_pairs:
                agreement_rows.append(
                    {
                        "risk_level": risk,
                        "left_agent": left_name,
                        "right_agent": right_name,
                        "pairs": len(risk_pairs),
                        "move_agreement_rate": statistics.fmean(
                            left["selected_edge"] == right["selected_edge"]
                            for left, right in risk_pairs
                        ),
                    }
                )
    return {
        "rows": rows,
        "risk_agreements": agreement_rows,
        "alpha_beta_pvs_pairs": len(pairs),
        "move_agreement_rate": statistics.fmean(
            left["selected_edge"] == right["selected_edge"] for left, right in pairs
        ),
        "score_agreement_rate": statistics.fmean(
            math.isclose(
                float(left["score"]), float(right["score"]), abs_tol=1e-9, rel_tol=0
            )
            for left, right in pairs
        ),
    }


def clone_state(state: AIEdgeState) -> AIEdgeState:
    return AIEdgeState(
        edge_dictionary=state.edge_dictionary,
        required_char_id=state.required_char_id,
        edge_counts=list(state.edge_counts),
        active_end_masks=list(state.active_end_masks),
    )


def restore_turn_state(trace: dict[str, Any], turn_number: int) -> tuple[RuntimeDictionary, AIEdgeState]:
    runtime = RuntimeDictionary.load(Path(trace["runtime"]))
    state = AIEdgeState.initial(runtime)
    for turn in trace["history"][: turn_number - 1]:
        state.apply_edge(int(turn["start_id"]), int(turn["end_id"]))
    state.assert_aggregates_consistent()
    return runtime, state


def analyze_beam_reference(
    traces: list[dict[str, Any]],
    output_path: Path,
    *,
    quick: bool,
) -> list[dict[str, Any]]:
    existing = read_jsonl(output_path) if output_path.is_file() else []
    completed = {(row["match_id"], int(row["turn"])) for row in existing}
    candidates = [
        (trace, turn)
        for trace in traces
        if {trace["first_agent"], trace["second_agent"]}.issubset(set(MAJOR_AGENTS))
        for turn in trace["history"]
        if turn["agent"] == "beam_negamax"
    ]
    if quick:
        candidates = candidates[:12]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for trace, turn in candidates:
        key = (trace["match_id"], int(turn["turn"]))
        if key in completed:
            continue
        runtime, state = restore_turn_state(trace, int(turn["turn"]))
        reference = AlphaBetaAgent(
            time_limit_sec=1.0,
            depth=5,
            branch_limit=16,
            adaptive_depth=False,
        ).choose_edge(clone_state(state))
        evaluations = {
            edge: evaluate_ordering_score(clone_state(state), *edge)
            for edge in state.available_edges()
        }
        ordered = sorted(
            evaluations,
            key=lambda edge: _edge_sort_key(edge, evaluations[edge], False),
        )
        reference_edge = (int(reference.start_id), int(reference.end_id))
        actual_edge = (int(turn["start_id"]), int(turn["end_id"]))
        rank = ordered.index(reference_edge) + 1
        widened_edge: tuple[int | None, int | None] = (None, None)
        if rank > 8:
            widened = BeamNegamaxAgent(
                time_limit_sec=1.0,
                depth=5,
                beam_widths=(16, 10, 6, 3),
                adaptive_depth=False,
            ).choose_edge(clone_state(state))
            widened_edge = (widened.start_id, widened.end_id)
        row = {
            "match_id": trace["match_id"],
            "dict_size": trace["dict_size"],
            "seed": trace["seed"],
            "turn": turn["turn"],
            "phase": (
                "early"
                if turn["turn"] <= trace["turn_count"] / 3
                else "middle"
                if turn["turn"] <= 2 * trace["turn_count"] / 3
                else "late"
            ),
            "required_char": turn["required_start_char"],
            "risk_level": normalize_risk(str(turn["risk_level"])),
            "candidate_count": len(ordered),
            "reference_start_id": reference.start_id,
            "reference_end_id": reference.end_id,
            "reference_edge": f"{runtime.id_to_char[reference.start_id]}→{runtime.id_to_char[reference.end_id]}",
            "reference_rank": rank,
            "reference_ordering_score": evaluations[reference_edge].total_score,
            "reference_search_score": reference.score,
            "beam_start_id": actual_edge[0],
            "beam_end_id": actual_edge[1],
            "beam_edge": f"{turn['start_char']}→{turn['end_char']}",
            "beam_ordering_score": evaluations[actual_edge].total_score,
            "beam_search_score": turn["score"],
            "same_edge": actual_edge == reference_edge,
            "match_winner": trace["winner_agent"],
            "beam_won": trace["winner_agent"] == "beam_negamax",
            "widened_edge": (
                ""
                if widened_edge[0] is None
                else f"{runtime.id_to_char[widened_edge[0]]}→{runtime.id_to_char[widened_edge[1]]}"
            ),
            "widened_selects_reference": widened_edge == reference_edge,
            **{
                f"top_{width}": rank <= width
                for width in (2, 4, 6, 8, 12, 16)
            },
        }
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        existing.append(row)
        completed.add(key)
    return existing


def aggregate_beam(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    group_specs = [
        ("all", lambda row: "all"),
        ("risk", lambda row: row["risk_level"]),
        ("size", lambda row: f"D{row['dict_size']}"),
        ("phase", lambda row: row["phase"]),
        (
            "candidate_count",
            lambda row: (
                "1-8"
                if row["candidate_count"] <= 8
                else "9-16"
                if row["candidate_count"] <= 16
                else "17+"
            ),
        ),
    ]
    for group_type, key_func in group_specs:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(key_func(row))].append(row)
        for group, values in sorted(grouped.items()):
            output.append(
                {
                    "group_type": group_type,
                    "group": group,
                    "positions": len(values),
                    "same_edge_rate": statistics.fmean(
                        bool(row["same_edge"]) for row in values
                    ),
                    **{
                        f"top_{width}_reference_retention_rate": statistics.fmean(
                            bool(row[f"top_{width}"]) for row in values
                        )
                        for width in (2, 4, 6, 8, 12, 16)
                    },
                    "beam_win_rate": statistics.fmean(
                        bool(row["beam_won"]) for row in values
                    ),
                }
            )
    return output


def compare_beam_reference_candidates(
    traces: list[dict[str, Any]],
    beam_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare actual Beam and reference edges on exactly the same states."""

    trace_by_id = {trace["match_id"]: trace for trace in traces}
    output = []
    for row in beam_rows:
        trace = trace_by_id[row["match_id"]]
        _runtime, state = restore_turn_state(trace, int(row["turn"]))
        reference = (
            int(row["reference_start_id"]),
            int(row["reference_end_id"]),
        )
        beam = (int(row["beam_start_id"]), int(row["beam_end_id"]))
        reference_metrics = edge_candidate_analysis(state, *reference)
        beam_metrics = edge_candidate_analysis(state, *beam)
        state.assert_aggregates_consistent()
        output.append(
            {
                "match_id": row["match_id"],
                "turn": row["turn"],
                "risk_level": row["risk_level"],
                "beam_won": row["beam_won"],
                "same_edge": row["same_edge"],
                "reference_rank": row["reference_rank"],
                **{
                    f"reference_{key}": value
                    for key, value in reference_metrics.items()
                },
                **{f"beam_{key}": value for key, value in beam_metrics.items()},
            }
        )
    return output


def analyze_caution_survival(
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Measure whether candidate-dependent caution survival changes root ordering."""

    output = []
    for trace in traces:
        for turn in trace["history"]:
            if normalize_risk(str(turn["risk_level"])) != "caution":
                continue
            _runtime, state = restore_turn_state(trace, int(turn["turn"]))
            evaluations = {
                edge: evaluate_edge_candidate(state, *edge)
                for edge in state.available_edges()
            }
            if not evaluations:
                continue

            def attack_key(item: tuple[tuple[int, int], Any]) -> tuple[Any, ...]:
                edge, evaluation = item
                return (
                    evaluation.immediate_win,
                    not evaluation.immediate_loss,
                    evaluation.attack_score,
                    -edge[0],
                    -edge[1],
                )

            def total_key(item: tuple[tuple[int, int], Any]) -> tuple[Any, ...]:
                edge, evaluation = item
                return (
                    evaluation.immediate_win,
                    not evaluation.immediate_loss,
                    evaluation.total_score,
                    -edge[0],
                    -edge[1],
                )

            attack_best = max(evaluations.items(), key=attack_key)[0]
            total_best = max(evaluations.items(), key=total_key)[0]
            selected = (int(turn["start_id"]), int(turn["end_id"]))
            survival_values = [
                evaluation.survival_score for evaluation in evaluations.values()
            ]
            output.append(
                {
                    "match_id": trace["match_id"],
                    "turn": turn["turn"],
                    "agent": turn["agent"],
                    "candidate_count": len(evaluations),
                    "survival_min": min(survival_values),
                    "survival_max": max(survival_values),
                    "survival_varies": (
                        max(survival_values) - min(survival_values) > 1e-12
                    ),
                    "survival_changes_static_best": attack_best != total_best,
                    "selected_equals_attack_best": selected == attack_best,
                    "selected_equals_total_best": selected == total_best,
                    "agent_won": trace["winner_agent"] == turn["agent"],
                }
            )
            state.assert_aggregates_consistent()
    return output


def classify_beam_losses(
    traces: list[dict[str, Any]],
    beam_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_match: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in beam_rows:
        rows_by_match[row["match_id"]].append(row)
    output = []
    for trace in traces:
        if (
            "beam_negamax" not in {trace["first_agent"], trace["second_agent"]}
            or trace["winner_agent"] == "beam_negamax"
            or not {
                trace["first_agent"],
                trace["second_agent"],
            }.issubset(set(MAJOR_AGENTS))
        ):
            continue
        rows = sorted(rows_by_match[trace["match_id"]], key=lambda row: row["turn"])
        dropped = next((row for row in rows if row["reference_rank"] > 8), None)
        different = next((row for row in rows if not row["same_edge"]), None)
        if dropped:
            cause = "reference_excluded_by_root_width"
            evidence = dropped
        elif different:
            cause = (
                "deep_beam_or_approximation"
                if different["reference_rank"] <= 8
                else "lightweight_ordering"
            )
            evidence = different
        else:
            cause = "unavoidable_or_unknown"
            evidence = rows[-1] if rows else {}
        output.append(
            {
                "match_id": trace["match_id"],
                "dict_size": trace["dict_size"],
                "seed": trace["seed"],
                "opponent": (
                    trace["second_agent"]
                    if trace["first_agent"] == "beam_negamax"
                    else trace["first_agent"]
                ),
                "turn_count": trace["turn_count"],
                "cause": cause,
                "evidence_turn": evidence.get("turn", ""),
                "risk_level": evidence.get("risk_level", ""),
                "reference_rank": evidence.get("reference_rank", ""),
                "candidate_count": evidence.get("candidate_count", ""),
                "reference_edge": evidence.get("reference_edge", ""),
                "beam_edge": evidence.get("beam_edge", ""),
                "classification_is_hypothesis": True,
            }
        )
    return output


def continue_from_state(
    state: AIEdgeState,
    first_agent: Any,
    second_agent: Any,
    next_player_index: int,
    max_moves: int,
) -> dict[str, Any]:
    agents = [first_agent, second_agent]
    history = []
    original = (
        state.required_char_id,
        tuple(state.edge_counts),
        tuple(state.active_end_masks),
        tuple(state.edge_history),
    )
    winner = "draw"
    for offset in range(max_moves):
        player = (next_player_index + offset) % 2
        if state.legal_word_count() == 0:
            winner = "second" if player == 0 else "first"
            break
        decision = agents[player].choose_edge(state)
        if decision.start_id is None or decision.end_id is None:
            winner = "second" if player == 0 else "first"
            break
        start_id, end_id = decision.start_id, decision.end_id
        state.apply_edge(start_id, end_id)
        history.append([start_id, end_id])
        if state.edge_dictionary.id_to_char[end_id] == "ん":
            winner = "second" if player == 0 else "first"
            break
    final = {
        "winner": winner,
        "suffix_turn_count": len(history),
        "edge_history": history,
    }
    while len(state.edge_history) > len(original[3]):
        state.undo_edge()
    restored = (
        state.required_char_id,
        tuple(state.edge_counts),
        tuple(state.active_end_masks),
        tuple(state.edge_history),
    )
    if restored != original:
        raise AssertionError("counterfactual continuation did not restore state")
    return final


def run_counterfactuals(
    traces: list[dict[str, Any]],
    beam_rows: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    *,
    quick: bool,
) -> list[dict[str, Any]]:
    trace_by_id = {row["match_id"]: row for row in traces}
    missed = [
        row
        for row in beam_rows
        if row["reference_rank"] > 8 and not row["beam_won"]
    ]
    first_by_match: dict[str, dict[str, Any]] = {}
    for row in missed:
        first_by_match.setdefault(row["match_id"], row)
    candidates = list(first_by_match.values())
    if quick:
        candidates = candidates[:2]
    output = []
    for row in candidates:
        trace = trace_by_id[row["match_id"]]
        _runtime, state = restore_turn_state(trace, int(row["turn"]))
        reference_edge = (int(row["reference_start_id"]), int(row["reference_end_id"]))
        state.apply_edge(*reference_edge)
        first = _agent_for_name(trace["first_agent"], selected, 1.0)
        second = _agent_for_name(trace["second_agent"], selected, 1.0)
        alternative = continue_from_state(
            state,
            first,
            second,
            int(row["turn"]) % 2,
            max(0, 1000 - int(row["turn"])),
        )
        state.undo_edge()
        state.assert_aggregates_consistent()
        alternative_winner_agent = (
            trace["first_agent"]
            if alternative["winner"] == "first"
            else trace["second_agent"]
            if alternative["winner"] == "second"
            else "draw"
        )
        original_beam_win = trace["winner_agent"] == "beam_negamax"
        alternative_beam_win = alternative_winner_agent == "beam_negamax"
        original_remaining = int(trace["turn_count"]) - int(row["turn"])
        if alternative_beam_win and not original_beam_win:
            classification = "outcome_improved"
        elif alternative_beam_win == original_beam_win and alternative["suffix_turn_count"] > original_remaining:
            classification = "same_outcome_longer_survival"
        elif alternative_beam_win == original_beam_win:
            classification = "same_outcome"
        else:
            classification = "outcome_worsened"
        output.append(
            {
                **row,
                "original_winner_agent": trace["winner_agent"],
                "counterfactual_winner_agent": alternative_winner_agent,
                "original_match_turns": trace["turn_count"],
                "counterfactual_match_turns": int(row["turn"]) + alternative["suffix_turn_count"],
                "classification": classification,
                "counterfactual_edge_history": alternative["edge_history"],
            }
        )
    return output


def _strong_components(adjacency: list[set[int]]) -> list[list[int]]:
    index = 0
    stack: list[int] = []
    indices = [-1] * len(adjacency)
    low = [0] * len(adjacency)
    on_stack = [False] * len(adjacency)
    components: list[list[int]] = []

    def visit(vertex: int) -> None:
        nonlocal index
        indices[vertex] = low[vertex] = index
        index += 1
        stack.append(vertex)
        on_stack[vertex] = True
        for neighbor in adjacency[vertex]:
            if indices[neighbor] < 0:
                visit(neighbor)
                low[vertex] = min(low[vertex], low[neighbor])
            elif on_stack[neighbor]:
                low[vertex] = min(low[vertex], indices[neighbor])
        if low[vertex] == indices[vertex]:
            component = []
            while True:
                neighbor = stack.pop()
                on_stack[neighbor] = False
                component.append(neighbor)
                if neighbor == vertex:
                    break
            components.append(component)

    for vertex in range(len(adjacency)):
        if indices[vertex] < 0:
            visit(vertex)
    return components


def analyze_dictionaries(
    final_matches: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trace_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        trace_groups[trace["runtime"]].append(trace)
    output = []
    for runtime_path in sorted({row["runtime"] for row in final_matches}):
        runtime = RuntimeDictionary.load(Path(runtime_path))
        n_id = runtime.char_to_id.get("ん")
        counts = runtime.initial_edge_counts
        adjacency = [set() for _ in range(runtime.char_count)]
        outgoing_words = [0] * runtime.char_count
        incoming_words = [0] * runtime.char_count
        safe_words = 0
        edge_types = safe_edge_types = 0
        for start_id in range(runtime.char_count):
            for end_id in range(runtime.char_count):
                count = counts[start_id * runtime.char_count + end_id]
                if not count:
                    continue
                adjacency[start_id].add(end_id)
                outgoing_words[start_id] += count
                incoming_words[end_id] += count
                edge_types += 1
                if end_id != n_id:
                    safe_words += count
                    safe_edge_types += 1
        components = _strong_components(adjacency)
        active = [value for value in outgoing_words if value]
        total = sum(outgoing_words)
        concentration = sum((value / total) ** 2 for value in outgoing_words)
        related = trace_groups.get(runtime_path, [])
        turns = [
            turn
            for trace in related
            for turn in trace["history"]
        ]
        output.append(
            {
                "runtime": runtime_path,
                "dict_size": runtime.word_count,
                "seed": next(
                    int(row["seed"])
                    for row in final_matches
                    if row["runtime"] == runtime_path
                ),
                "total_words": runtime.word_count,
                "safe_words": safe_words,
                "edge_types": edge_types,
                "safe_edge_types": safe_edge_types,
                "start_char_count": len(active),
                "safe_start_char_count": sum(
                    any(end != n_id for end in adjacency[start])
                    for start in range(runtime.char_count)
                ),
                "start_word_hhi": concentration,
                "mean_outgoing_words_active": statistics.fmean(active),
                "max_outgoing_words": max(outgoing_words),
                "dead_end_char_count": sum(not adjacency[index] for index in range(runtime.char_count)),
                "strong_component_count": len(components),
                "largest_strong_component": max(map(len, components)),
                "cycle_char_count": sum(
                    len(component)
                    for component in components
                    if len(component) > 1
                    or component[0] in adjacency[component[0]]
                ),
                "mean_match_turns": (
                    statistics.fmean(trace["turn_count"] for trace in related)
                    if related
                    else 0.0
                ),
                "danger_turn_rate": (
                    statistics.fmean(
                        normalize_risk(str(turn["risk_level"]))
                        in {"danger", "near_death"}
                        for turn in turns
                    )
                    if turns
                    else 0.0
                ),
            }
        )
    return output


def dictionary_correlations(
    dictionaries: list[dict[str, Any]],
    beam_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    retention: dict[tuple[int, int], list[bool]] = defaultdict(list)
    for row in beam_rows:
        retention[(int(row["dict_size"]), int(row["seed"]))].append(
            bool(row["top_8"])
        )
    enriched = []
    for row in dictionaries:
        values = retention.get((int(row["dict_size"]), int(row["seed"])), [])
        enriched.append(
            {
                **row,
                "beam_top8_retention": statistics.fmean(values) if values else 0.0,
            }
        )

    def pearson(left: list[float], right: list[float]) -> float:
        if len(left) < 2:
            return 0.0
        left_mean = statistics.fmean(left)
        right_mean = statistics.fmean(right)
        numerator = sum(
            (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
        )
        denominator = math.sqrt(
            sum((x - left_mean) ** 2 for x in left)
            * sum((y - right_mean) ** 2 for y in right)
        )
        return numerator / denominator if denominator else 0.0

    features = (
        "total_words",
        "safe_words",
        "edge_types",
        "safe_edge_types",
        "start_word_hhi",
        "mean_outgoing_words_active",
        "largest_strong_component",
        "cycle_char_count",
    )
    outcomes = ("mean_match_turns", "danger_turn_rate", "beam_top8_retention")
    return [
        {
            "feature": feature,
            "outcome": outcome,
            "sample_count": len(enriched),
            "pearson_r": pearson(
                [float(row[feature]) for row in enriched],
                [float(row[outcome]) for row in enriched],
            ),
            "descriptive_only": True,
        }
        for feature in features
        for outcome in outcomes
    ]


def select_representatives(
    traces: list[dict[str, Any]],
    beam_rows: list[dict[str, Any]],
    counterfactuals: list[dict[str, Any]],
) -> dict[str, str | None]:
    def find(predicate) -> str | None:
        match = next((trace for trace in traces if predicate(trace)), None)
        return match["match_id"] if match else None

    missed_ids = {row["match_id"] for row in beam_rows if row["reference_rank"] > 8}
    changed = next(
        (
            row["match_id"]
            for row in counterfactuals
            if row["classification"] == "outcome_improved"
        ),
        None,
    )
    return {
        "alpha_beta_beats_beam": find(
            lambda trace: {trace["first_agent"], trace["second_agent"]}
            == {"alpha_beta", "beam_negamax"}
            and trace["winner_agent"] == "alpha_beta"
        ),
        "beam_beats_alpha_beta": find(
            lambda trace: {trace["first_agent"], trace["second_agent"]}
            == {"alpha_beta", "beam_negamax"}
            and trace["winner_agent"] == "beam_negamax"
        ),
        "alpha_beta_pvs_equivalent_result": find(
            lambda trace: {trace["first_agent"], trace["second_agent"]}
            == {"alpha_beta", "pvs"}
        ),
        "beam_drops_reference": next(iter(sorted(missed_ids)), None),
        "counterfactual_changes_outcome": changed,
        "wins_from_danger": find(
            lambda trace: any(
                normalize_risk(str(turn["risk_level"])) in {"danger", "near_death"}
                and turn["agent"] == trace["winner_agent"]
                for turn in trace["history"]
            )
        ),
        "longest": max(traces, key=lambda trace: trace["turn_count"])["match_id"]
        if traces
        else None,
        "shortest": min(traces, key=lambda trace: trace["turn_count"])["match_id"]
        if traces
        else None,
    }


def write_representative_markdown(
    traces: list[dict[str, Any]],
    selections: dict[str, str | None],
    output_dir: Path,
) -> None:
    by_id = {trace["match_id"]: trace for trace in traces}
    output_dir.mkdir(parents=True, exist_ok=True)
    index_lines = ["# 代表対局", ""]
    for category, identifier in selections.items():
        index_lines.append(f"- {category}: `{identifier or '該当なし'}`")
        if not identifier or identifier not in by_id:
            continue
        trace = by_id[identifier]
        lines = [
            f"# {category}: {identifier}",
            "",
            f"- D={trace['dict_size']} seed={trace['seed']}",
            f"- {trace['first_agent']} vs {trace['second_agent']}",
            f"- winner={trace['winner_agent']} turns={trace['turn_count']}",
            "",
            "## 全手順",
            "",
            "| 手 | AI | 必要文字 | 辺 | risk | 候補 | 深度 | nodes | score |",
            "|---:|---|---|---|---|---:|---:|---:|---:|",
        ]
        for turn in trace["history"]:
            lines.append(
                f"| {turn['turn']} | {turn['agent']} | {turn['required_start_char']} | "
                f"{turn['start_char']}→{turn['end_char']} | "
                f"{normalize_risk(str(turn['risk_level']))} | "
                f"{turn['root_candidate_count']} | {turn['effective_depth']} | "
                f"{turn['nodes_searched']} | {turn['score']} |"
            )
        important = sorted(
            trace["history"],
            key=lambda turn: (
                normalize_risk(str(turn["risk_level"])) == "near_death",
                _numeric(turn, "nodes_searched"),
            ),
            reverse=True,
        )[:6]
        lines.extend(["", "## 重要局面", ""])
        for turn in sorted(important, key=lambda item: item["turn"]):
            runtime, state = restore_turn_state(trace, int(turn["turn"]))
            evaluations = {
                edge: evaluate_ordering_score(state, *edge)
                for edge in state.available_edges()
            }
            ordered = sorted(
                evaluations,
                key=lambda edge: _edge_sort_key(edge, evaluations[edge], False),
            )
            selected = (int(turn["start_id"]), int(turn["end_id"]))
            selected_rank = ordered.index(selected) + 1
            top_text = ", ".join(
                f"{runtime.id_to_char[start]}→{runtime.id_to_char[end]}"
                f"({evaluations[(start, end)].total_score:.1f})"
                for start, end in ordered[:5]
            )
            lines.append(
                f"- 手{turn['turn']}、必要文字`{turn['required_start_char']}`、"
                f"{normalize_risk(str(turn['risk_level']))}、候補"
                f"{turn['root_candidate_count']}、選択`{turn['start_char']}→"
                f"{turn['end_char']}`、深度{turn['effective_depth']}、"
                f"{turn['nodes_searched']} nodes。攻撃score "
                f"{turn['attack_score']}、生存score {turn['survival_score']}。"
                f"軽量順位{selected_rank}、上位候補: {top_text}。"
            )
        (output_dir / f"{category}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    (output_dir / "index.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )


def create_plots(root: Path, payload: dict[str, Any]) -> list[str]:
    plt = ensure_matplotlib()
    output = root / "plots"
    output.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def bar(name: str, labels: list[str], values: list[float], title: str, ylabel: str) -> None:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(labels, values, color="#4c78a8")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.tick_params(axis="x", rotation=25)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        path = output / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    direct = payload["matchups"]["direct"]
    bar(
        "major_direct_win_rate",
        [f"{row['agent']}\\nvs {row['opponent']}" for row in direct],
        [row["win_rate"] for row in direct],
        "Major-agent direct matchup win rate",
        "Win rate",
    )
    seat = payload["matchups"]["overall"]
    fig, ax = plt.subplots(figsize=(9, 5))
    labels = [row["agent"] for row in seat]
    x = list(range(len(labels)))
    ax.bar([v - 0.2 for v in x], [row["first_win_rate"] for row in seat], 0.4, label="first")
    ax.bar([v + 0.2 for v in x], [row["second_win_rate"] for row in seat], 0.4, label="second")
    ax.set_xticks(x, labels, rotation=25)
    ax.set_ylabel("Win rate")
    ax.set_title("First and second seat win rates")
    ax.legend()
    fig.tight_layout()
    path = output / "agent_first_second_win_rate.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    by_size = payload["matchups"]["by_size"]
    for metric, name, title, ylabel in (
        ("win_rate", "win_rate_by_size", "Win rate by dictionary size", "Win rate"),
        ("mean_turns", "mean_turns_by_size", "Mean match length by dictionary size", "Turns"),
    ):
        fig, ax = plt.subplots(figsize=(9, 5))
        agents = sorted({row["agent"] for row in by_size})
        for agent in agents:
            rows = sorted(
                (row for row in by_size if row["agent"] == agent),
                key=lambda row: int(row["dict_size"]),
            )
            if agent == "minimax":
                rows = [row for row in rows if int(row["dict_size"]) <= 5000]
            ax.plot(
                [row["dict_size"] for row in rows],
                [row[metric] for row in rows],
                marker="o",
                label=agent,
            )
        ax.set_title(title)
        ax.set_xlabel("Dictionary size")
        ax.set_ylabel(ylabel)
        ax.legend()
        fig.tight_layout()
        path = output / f"{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        created.append(str(path))

    turns = payload["turn_metrics"]["by_agent"]
    major_turns = [row for row in turns if row["agent"] in MAJOR_AGENTS]
    bar(
        "agent_mean_think_time",
        [row["agent"] for row in major_turns],
        [row["mean_elapsed_time_sec"] for row in major_turns],
        "Mean decision time (major agents, all available dictionaries)",
        "Seconds",
    )
    bar(
        "agent_mean_nodes",
        [row["agent"] for row in major_turns],
        [row["mean_nodes_searched"] for row in major_turns],
        "Mean searched nodes (major agents, all available dictionaries)",
        "Nodes",
    )
    abpvs = [row for row in major_turns if row["agent"] in {"alpha_beta", "pvs"}]
    bar(
        "alpha_beta_pvs_time_per_node",
        [row["agent"] for row in abpvs],
        [row["time_per_node_sec"] for row in abpvs],
        "AlphaBeta and PVS time per node",
        "Seconds per node",
    )
    pvs = next(row for row in turns if row["agent"] == "pvs")
    bar(
        "pvs_research_rate",
        ["PVS"],
        [
            sum(row["research_count"] for row in payload["turn_metrics"]["pvs_research"])
            / max(
                1,
                sum(
                    row["null_window_searches"]
                    for row in payload["turn_metrics"]["pvs_research"]
                ),
            )
        ],
        "PVS re-search rate",
        "Rate",
    )
    bar(
        "alpha_beta_pvs_move_agreement",
        ["AB-PVS"],
        [payload["fixed_efficiency"]["move_agreement_rate"]],
        "AlphaBeta and PVS fixed-position move agreement",
        "Agreement rate",
    )

    beam_all = next(
        row
        for row in payload["beam_summary"]
        if row["group_type"] == "all" and row["group"] == "all"
    )
    widths = (2, 4, 6, 8, 12, 16)
    bar(
        "beam_reference_retention_by_width",
        [str(width) for width in widths],
        [beam_all[f"top_{width}_reference_retention_rate"] for width in widths],
        "Beam reference-move retention by width",
        "Retention rate",
    )
    risk_beam = [
        row for row in payload["beam_summary"] if row["group_type"] == "risk"
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for row in risk_beam:
        ax.plot(
            widths,
            [row[f"top_{width}_reference_retention_rate"] for width in widths],
            marker="o",
            label=row["group"],
        )
    ax.set_title("Beam reference-move retention by risk")
    ax.set_xlabel("Width")
    ax.set_ylabel("Retention rate")
    ax.legend()
    fig.tight_layout()
    path = output / "beam_reference_retention_by_risk.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    created.append(str(path))

    length = [
        row for row in payload["length"] if row["outcome"] in {"win", "loss"}
    ]
    bar(
        "mean_turns_by_agent_outcome",
        [f"{row['agent']}\\n{row['outcome']}" for row in length],
        [row["mean_turns"] for row in length],
        "Mean match length by agent outcome",
        "Turns",
    )
    seed_rows = [
        row
        for row in payload["matchups"]["first_player"]
        if row["group"] == "dict_size,seed" and int(row["dict_size"]) == 20000
    ]
    bar(
        "mean_turns_by_seed",
        [f"seed{row['seed']}" for row in seed_rows],
        [row["mean_turns"] for row in seed_rows],
        "D20000 mean match length by seed",
        "Turns",
    )
    risk_rows = payload["turn_metrics"]["by_agent_risk"]
    risk_counts = Counter()
    for row in risk_rows:
        risk_counts[row["risk_level"]] += row["turns"]
    total_risk = sum(risk_counts.values())
    bar(
        "risk_position_share",
        list(RISK_NAMES),
        [risk_counts[name] / total_risk for name in RISK_NAMES],
        "Risk-level position share",
        "Share",
    )
    bar(
        "opponent_safe_words_after_move",
        [row["agent"] for row in major_turns],
        [row["mean_opponent_safe_word_count"] for row in major_turns],
        "Safe words left to opponent after selected move",
        "Words",
    )
    bar(
        "own_safe_words_before_move",
        [row["agent"] for row in major_turns],
        [row["mean_own_safe_word_count"] for row in major_turns],
        "Own safe words before selected move",
        "Words",
    )
    size_seed = payload["matchups"]["by_seed"]
    d20 = [row for row in size_seed if int(row["dict_size"]) == 20000]
    bar(
        "agent_win_rate_by_seed_d20000",
        [f"{row['agent']}\\nseed{row['seed']}" for row in d20],
        [row["win_rate"] for row in d20],
        "D20000 agent win rate by seed",
        "Win rate",
    )
    return created
