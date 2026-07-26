"""Match simulation for approximate AI and human-vs-AI modes."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from agents import BaseAgent, EdgeMoveDecision, GameState
from game import WordGraph
from runtime_dictionary import EdgeDictionary, RuntimeDictionary
from runtime_state import AIEdgeState


@dataclass
class PlayerTiming:
    total_time_sec: float = 0.0
    max_time_sec: float = 0.0
    move_count: int = 0
    timeout_count: int = 0

    @property
    def average_time_sec(self) -> float:
        if self.move_count == 0:
            return 0.0
        return self.total_time_sec / self.move_count

    def add(self, elapsed_time_sec: float, timed_out: bool) -> None:
        self.total_time_sec += elapsed_time_sec
        self.max_time_sec = max(self.max_time_sec, elapsed_time_sec)
        self.move_count += 1
        if timed_out:
            self.timeout_count += 1


@dataclass
class MatchResult:
    dict_size: int
    first_agent: str
    second_agent: str
    winner: str
    turn_count: int
    used_word_count: int
    loss_reason: str
    first_total_time_sec: float
    second_total_time_sec: float
    first_avg_time_sec: float
    second_avg_time_sec: float
    first_max_time_sec: float
    second_max_time_sec: float
    first_timeout_count: int
    second_timeout_count: int
    max_moves: int
    max_match_time_sec: float
    match_elapsed_time_sec: float
    history: list[dict[str, object]] = field(default_factory=list)

    def to_csv_row(self) -> dict[str, object]:
        row = asdict(self)
        row["history"] = json.dumps(self.history, ensure_ascii=False)
        return row


def simulate_match(
    graph: WordGraph,
    first_agent: BaseAgent,
    second_agent: BaseAgent,
    max_moves: int,
    max_match_time_sec: float,
    match_id: str = "",
) -> MatchResult:
    agents = [first_agent, second_agent]
    timings = [PlayerTiming(), PlayerTiming()]
    used_ids: set[int] = set()
    current_char: str | None = None
    previous_word: str | None = None
    history: list[dict[str, object]] = []
    started = time.perf_counter()
    winner = "draw"
    loss_reason = "max_moves_reached"

    for turn_index in range(max_moves):
        elapsed_match = time.perf_counter() - started
        if elapsed_match >= max_match_time_sec:
            winner = "draw"
            loss_reason = "match_timeout"
            break

        player_index = turn_index % 2
        agent = agents[player_index]
        legal_moves = (
            [word_id for word_id in range(len(graph.words)) if word_id not in used_ids]
            if current_char is None
            else graph.available_word_ids_set(current_char, used_ids)
        )
        if not legal_moves:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "no_legal_move"
            break

        state = GameState(current_char=current_char, used_ids=frozenset(used_ids))
        decision = agent.choose_move(graph, state)
        timings[player_index].add(decision.elapsed_time_sec, decision.timed_out)

        if decision.word_id is None or decision.word_id not in legal_moves:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "invalid_ai_move"
            break

        word_id = decision.word_id
        word = graph.words[word_id]
        required_start_char = current_char if current_char is not None else "ANY"
        used_ids.add(word_id)
        history.append(
            {
                "match_id": match_id,
                "turn": turn_index + 1,
                "player": "first" if player_index == 0 else "second",
                "agent": agent.name,
                "required_start_char": required_start_char,
                "previous_word": previous_word or "",
                "word_id": word_id,
                "word": word,
                "start_char": graph.start_chars[word_id],
                "end_char": graph.end_chars[word_id],
                "next_required_start_char": "" if graph.end_chars[word_id] == "ん" else graph.end_chars[word_id],
                "elapsed_time_sec": round(decision.elapsed_time_sec, 6),
                "timed_out": decision.timed_out,
                "score": decision.score,
                "effective_depth": decision.extra.get("effective_depth", ""),
                "next_depth": decision.extra.get("next_depth", ""),
                "adaptive_depth": decision.extra.get("adaptive_depth", ""),
                "depth_before": decision.extra.get("depth_before", ""),
                "depth_after": decision.extra.get("depth_after", ""),
                "depth_change": decision.extra.get("depth_change", ""),
                "depth_changed": decision.extra.get("depth_changed", ""),
                "depth_change_reason": decision.extra.get("depth_change_reason", ""),
                "depth_recovery_streak": decision.extra.get("recovery_streak", ""),
                "initial_depth": decision.extra.get("initial_depth", ""),
                "max_depth": decision.extra.get("max_depth", ""),
                "min_depth": decision.extra.get("min_depth", ""),
                "target_time_sec": decision.extra.get("target_time_sec", ""),
                "elapsed_ratio": decision.extra.get("elapsed_ratio", ""),
                "target_elapsed_ratio": decision.extra.get("target_elapsed_ratio", ""),
                "pruned_count": decision.extra.get(
                    "pruned_move_count", decision.extra.get("pruned_count", "")
                ),
                "nodes_searched": decision.extra.get("nodes_searched", ""),
                "leaf_evaluations": decision.extra.get("leaf_evaluations", ""),
                "ordering_evaluations": decision.extra.get("ordering_evaluations", ""),
                "full_survival_evaluations": decision.extra.get("full_survival_evaluations", ""),
                "simple_survival_evaluations": decision.extra.get("simple_survival_evaluations", ""),
                "completed_root_moves": decision.extra.get("completed_root_moves", ""),
                "ordering_time_sec": decision.extra.get("ordering_time_sec", ""),
                "legal_move_generation_time_sec": decision.extra.get("legal_move_generation_time_sec", ""),
                "candidate_evaluation_time_sec": decision.extra.get("candidate_evaluation_time_sec", ""),
                "candidate_sort_time_sec": decision.extra.get("candidate_sort_time_sec", ""),
                "evaluation_time_sec": decision.extra.get("evaluation_time_sec", ""),
                "search_time_sec": decision.extra.get("search_time_sec", ""),
                "total_search_time_sec": decision.extra.get("total_search_time_sec", ""),
                "elapsed_ratio": decision.extra.get("elapsed_ratio", ""),
                "risk_level": decision.extra.get("risk_level", ""),
                "attack_score": decision.extra.get("attack_score", ""),
                "survival_score": decision.extra.get("survival_score", ""),
                "survival_weight": decision.extra.get("survival_weight", ""),
                "total_score": decision.extra.get("total_score", ""),
                "opponent_legal_word_count": decision.extra.get("opponent_legal_word_count", ""),
                "opponent_safe_word_count": decision.extra.get("opponent_safe_word_count", ""),
                "opponent_active_edge_type_count": decision.extra.get("opponent_active_edge_type_count", ""),
                "opponent_safe_edge_type_count": decision.extra.get("opponent_safe_edge_type_count", ""),
                "opponent_destination_count": decision.extra.get("opponent_destination_count", ""),
                "opponent_safe_destination_count": decision.extra.get("opponent_safe_destination_count", ""),
                "own_safe_word_count": decision.extra.get("own_safe_word_count", ""),
                "own_safe_edge_type_count": decision.extra.get("own_safe_edge_type_count", ""),
                "own_safe_destination_count": decision.extra.get("own_safe_destination_count", ""),
                "root_candidate_count": decision.extra.get("root_candidate_count", ""),
                "selected_root_candidate_count": decision.extra.get("selected_root_candidate_count", ""),
                "searched_root_candidate_count": decision.extra.get("searched_root_candidate_count", ""),
                "cutoff_count": decision.extra.get("cutoff_count", ""),
                "pruned_move_count": decision.extra.get("pruned_move_count", ""),
                "beam_pruned_move_count": decision.extra.get("beam_pruned_move_count", ""),
                "null_window_search_count": decision.extra.get("null_window_search_count", ""),
                "null_window_searches": decision.extra.get("null_window_searches", ""),
                "research_count": decision.extra.get("research_count", ""),
                "research_rate": decision.extra.get("research_rate", ""),
                "search_mode": decision.extra.get("search_mode", ""),
                "mode_history": decision.extra.get("mode_history", ""),
                "switch_reason": decision.extra.get("switch_reason", ""),
                "mode_counts": decision.extra.get("mode_counts", ""),
                "mode_switch_count": decision.extra.get("mode_switch_count", ""),
                "beam_widths_used": decision.extra.get("beam_widths_used", ""),
                "dynamic_beam_width_counts": decision.extra.get(
                    "dynamic_beam_width_counts", ""
                ),
                "dynamic_beam_config": decision.extra.get(
                    "dynamic_beam_config", ""
                ),
                "beam_candidate_counts_by_ply": decision.extra.get("beam_candidate_counts_by_ply", ""),
                "beam_selected_counts_by_ply": decision.extra.get("beam_selected_counts_by_ply", ""),
                "beam_ordering_calls_by_ply": decision.extra.get("beam_ordering_calls_by_ply", ""),
                "beam_max_selected_by_ply": decision.extra.get("beam_max_selected_by_ply", ""),
                "graph_ordering_evaluations": decision.extra.get("graph_ordering_evaluations", ""),
                "graph_ordering_calls": decision.extra.get("graph_ordering_calls", ""),
                "graph_ordering_changed_first_count": decision.extra.get("graph_ordering_changed_first_count", ""),
                "graph_ordering_time_sec": decision.extra.get("graph_ordering_time_sec", ""),
                "graph_root_baseline_first": decision.extra.get("graph_root_baseline_first", ""),
                "graph_root_ordered_first": decision.extra.get("graph_root_ordered_first", ""),
                "completed_iterative_depth": decision.extra.get(
                    "completed_iterative_depth", ""
                ),
                "predicted_next_depth_time_sec": decision.extra.get(
                    "predicted_next_depth_time_sec", ""
                ),
                "position_scale": decision.extra.get("position_scale", ""),
                "exact_gate": decision.extra.get("exact_gate", ""),
                "exact_attempt_count": decision.extra.get(
                    "exact_attempt_count", ""
                ),
                "exact_success_count": decision.extra.get(
                    "exact_success_count", ""
                ),
                "exact_timeout_count": decision.extra.get(
                    "exact_timeout_count", ""
                ),
                "exact_limit_count": decision.extra.get(
                    "exact_limit_count", ""
                ),
                "exact_state_count": decision.extra.get(
                    "exact_state_count", ""
                ),
                "exact_result": decision.extra.get("exact_result", ""),
                "exact_time_budget_sec": decision.extra.get(
                    "exact_time_budget_sec", ""
                ),
                "fallback_count": decision.extra.get("fallback_count", ""),
                "evaluated_moves": decision.extra.get("evaluated_moves", ""),
                "decision_extra": decision.extra,
            }
        )

        if graph.end_chars[word_id] == "ん":
            winner = "second" if player_index == 0 else "first"
            loss_reason = "ended_with_n"
            break

        previous_word = word
        current_char = graph.end_chars[word_id]
    else:
        winner = "draw"
        loss_reason = "max_moves_reached"

    match_elapsed = time.perf_counter() - started
    return MatchResult(
        dict_size=len(graph.words),
        first_agent=first_agent.name,
        second_agent=second_agent.name,
        winner=winner,
        turn_count=len(history),
        used_word_count=len(used_ids),
        loss_reason=loss_reason,
        first_total_time_sec=timings[0].total_time_sec,
        second_total_time_sec=timings[1].total_time_sec,
        first_avg_time_sec=timings[0].average_time_sec,
        second_avg_time_sec=timings[1].average_time_sec,
        first_max_time_sec=timings[0].max_time_sec,
        second_max_time_sec=timings[1].max_time_sec,
        first_timeout_count=timings[0].timeout_count,
        second_timeout_count=timings[1].timeout_count,
        max_moves=max_moves,
        max_match_time_sec=max_match_time_sec,
        match_elapsed_time_sec=match_elapsed,
        history=history,
    )


def simulate_runtime_match(
    runtime: RuntimeDictionary | EdgeDictionary,
    first_agent: BaseAgent,
    second_agent: BaseAgent,
    max_moves: int,
    max_match_time_sec: float,
    match_id: str = "",
    turn_observer: Callable[
        [int, int, BaseAgent, EdgeMoveDecision, AIEdgeState], None
    ] | None = None,
) -> MatchResult:
    """Run an AI-vs-AI match using only character IDs and edge multiplicities."""

    edge_dictionary = (
        runtime.to_edge_dictionary()
        if isinstance(runtime, RuntimeDictionary)
        else runtime
    )
    agents = [first_agent, second_agent]
    timings = [PlayerTiming(), PlayerTiming()]
    state = AIEdgeState.initial(edge_dictionary)
    history: list[dict[str, object]] = []
    started = time.perf_counter()
    winner = "draw"
    loss_reason = "max_moves_reached"

    for turn_index in range(max_moves):
        if time.perf_counter() - started >= max_match_time_sec:
            loss_reason = "match_timeout"
            break
        player_index = turn_index % 2
        if state.legal_word_count() == 0:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "no_legal_move"
            break

        agent = agents[player_index]
        decision = agent.choose_edge(state)
        timings[player_index].add(decision.elapsed_time_sec, decision.timed_out)
        if decision.start_id is None or decision.end_id is None:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "invalid_ai_move"
            break
        start_id = decision.start_id
        end_id = decision.end_id
        if state.required_char_id is not None and start_id != state.required_char_id:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "invalid_ai_move"
            break
        edge_index = state.edge_dictionary.edge_index(start_id, end_id)
        edge_count_before = state.edge_counts[edge_index]
        if edge_count_before <= 0:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "invalid_ai_move"
            break
        if turn_observer is not None:
            turn_observer(turn_index, player_index, agent, decision, state)
        required_start = (
            "ANY"
            if state.required_char_id is None
            else edge_dictionary.id_to_char[state.required_char_id]
        )
        state.apply_edge(start_id, end_id)
        history.append(
            {
                "match_id": match_id,
                "turn": turn_index + 1,
                "player": "first" if player_index == 0 else "second",
                "agent": agent.name,
                "required_start_char": required_start,
                "edge_index": edge_index,
                "start_id": start_id,
                "end_id": end_id,
                "start_char": edge_dictionary.id_to_char[start_id],
                "end_char": edge_dictionary.id_to_char[end_id],
                "next_required_start_char": (
                    ""
                    if edge_dictionary.id_to_char[end_id] == "ん"
                    else edge_dictionary.id_to_char[end_id]
                ),
                "edge_count_before": edge_count_before,
                "edge_count_after": edge_count_before - 1,
                "elapsed_time_sec": round(decision.elapsed_time_sec, 6),
                "timed_out": decision.timed_out,
                "score": decision.score,
                "effective_depth": decision.extra.get("effective_depth", ""),
                "next_depth": decision.extra.get("next_depth", ""),
                "adaptive_depth": decision.extra.get("adaptive_depth", ""),
                "depth_before": decision.extra.get("depth_before", ""),
                "depth_after": decision.extra.get("depth_after", ""),
                "depth_change": decision.extra.get("depth_change", ""),
                "depth_changed": decision.extra.get("depth_changed", ""),
                "depth_change_reason": decision.extra.get("depth_change_reason", ""),
                "depth_recovery_streak": decision.extra.get("recovery_streak", ""),
                "initial_depth": decision.extra.get("initial_depth", ""),
                "max_depth": decision.extra.get("max_depth", ""),
                "min_depth": decision.extra.get("min_depth", ""),
                "target_time_sec": decision.extra.get("target_time_sec", ""),
                "elapsed_ratio": decision.extra.get("elapsed_ratio", ""),
                "target_elapsed_ratio": decision.extra.get("target_elapsed_ratio", ""),
                "pruned_count": decision.extra.get(
                    "pruned_move_count", decision.extra.get("pruned_count", "")
                ),
                "nodes_searched": decision.extra.get("nodes_searched", ""),
                "leaf_evaluations": decision.extra.get("leaf_evaluations", ""),
                "ordering_evaluations": decision.extra.get("ordering_evaluations", ""),
                "full_survival_evaluations": decision.extra.get("full_survival_evaluations", ""),
                "simple_survival_evaluations": decision.extra.get("simple_survival_evaluations", ""),
                "completed_root_moves": decision.extra.get("completed_root_moves", ""),
                "ordering_time_sec": decision.extra.get("ordering_time_sec", ""),
                "legal_move_generation_time_sec": decision.extra.get("legal_move_generation_time_sec", ""),
                "candidate_evaluation_time_sec": decision.extra.get("candidate_evaluation_time_sec", ""),
                "candidate_sort_time_sec": decision.extra.get("candidate_sort_time_sec", ""),
                "evaluation_time_sec": decision.extra.get("evaluation_time_sec", ""),
                "search_time_sec": decision.extra.get("search_time_sec", ""),
                "total_search_time_sec": decision.extra.get("total_search_time_sec", ""),
                "elapsed_ratio": decision.extra.get("elapsed_ratio", ""),
                "risk_level": decision.extra.get("risk_level", ""),
                "attack_score": decision.extra.get("attack_score", ""),
                "survival_score": decision.extra.get("survival_score", ""),
                "survival_weight": decision.extra.get("survival_weight", ""),
                "total_score": decision.extra.get("total_score", ""),
                "opponent_legal_word_count": decision.extra.get("opponent_legal_word_count", ""),
                "opponent_safe_word_count": decision.extra.get("opponent_safe_word_count", ""),
                "opponent_active_edge_type_count": decision.extra.get("opponent_active_edge_type_count", ""),
                "opponent_safe_edge_type_count": decision.extra.get("opponent_safe_edge_type_count", ""),
                "opponent_destination_count": decision.extra.get("opponent_destination_count", ""),
                "opponent_safe_destination_count": decision.extra.get("opponent_safe_destination_count", ""),
                "own_safe_word_count": decision.extra.get("own_safe_word_count", ""),
                "own_safe_edge_type_count": decision.extra.get("own_safe_edge_type_count", ""),
                "own_safe_destination_count": decision.extra.get("own_safe_destination_count", ""),
                "root_candidate_count": decision.extra.get("root_candidate_count", ""),
                "selected_root_candidate_count": decision.extra.get("selected_root_candidate_count", ""),
                "searched_root_candidate_count": decision.extra.get("searched_root_candidate_count", ""),
                "cutoff_count": decision.extra.get("cutoff_count", ""),
                "pruned_move_count": decision.extra.get("pruned_move_count", ""),
                "beam_pruned_move_count": decision.extra.get("beam_pruned_move_count", ""),
                "null_window_search_count": decision.extra.get("null_window_search_count", ""),
                "null_window_searches": decision.extra.get("null_window_searches", ""),
                "research_count": decision.extra.get("research_count", ""),
                "research_rate": decision.extra.get("research_rate", ""),
                "search_mode": decision.extra.get("search_mode", ""),
                "mode_history": decision.extra.get("mode_history", ""),
                "switch_reason": decision.extra.get("switch_reason", ""),
                "mode_counts": decision.extra.get("mode_counts", ""),
                "mode_switch_count": decision.extra.get("mode_switch_count", ""),
                "beam_widths_used": decision.extra.get("beam_widths_used", ""),
                "dynamic_beam_width_counts": decision.extra.get(
                    "dynamic_beam_width_counts", ""
                ),
                "dynamic_beam_config": decision.extra.get(
                    "dynamic_beam_config", ""
                ),
                "beam_candidate_counts_by_ply": decision.extra.get("beam_candidate_counts_by_ply", ""),
                "beam_selected_counts_by_ply": decision.extra.get("beam_selected_counts_by_ply", ""),
                "beam_ordering_calls_by_ply": decision.extra.get("beam_ordering_calls_by_ply", ""),
                "beam_max_selected_by_ply": decision.extra.get("beam_max_selected_by_ply", ""),
                "graph_ordering_evaluations": decision.extra.get("graph_ordering_evaluations", ""),
                "graph_ordering_calls": decision.extra.get("graph_ordering_calls", ""),
                "graph_ordering_changed_first_count": decision.extra.get("graph_ordering_changed_first_count", ""),
                "graph_ordering_time_sec": decision.extra.get("graph_ordering_time_sec", ""),
                "graph_root_baseline_first": decision.extra.get("graph_root_baseline_first", ""),
                "graph_root_ordered_first": decision.extra.get("graph_root_ordered_first", ""),
                "completed_iterative_depth": decision.extra.get(
                    "completed_iterative_depth", ""
                ),
                "predicted_next_depth_time_sec": decision.extra.get(
                    "predicted_next_depth_time_sec", ""
                ),
                "position_scale": decision.extra.get("position_scale", ""),
                "exact_gate": decision.extra.get("exact_gate", ""),
                "exact_attempt_count": decision.extra.get(
                    "exact_attempt_count", ""
                ),
                "exact_success_count": decision.extra.get(
                    "exact_success_count", ""
                ),
                "exact_timeout_count": decision.extra.get(
                    "exact_timeout_count", ""
                ),
                "exact_limit_count": decision.extra.get(
                    "exact_limit_count", ""
                ),
                "exact_state_count": decision.extra.get(
                    "exact_state_count", ""
                ),
                "exact_result": decision.extra.get("exact_result", ""),
                "exact_time_budget_sec": decision.extra.get(
                    "exact_time_budget_sec", ""
                ),
                "fallback_count": decision.extra.get("fallback_count", ""),
                "evaluated_moves": decision.extra.get("evaluated_moves", ""),
                "decision_extra": decision.extra,
            }
        )
        if edge_dictionary.id_to_char[end_id] == "ん":
            winner = "second" if player_index == 0 else "first"
            loss_reason = "ended_with_n"
            break
    else:
        winner = "draw"

    match_elapsed = time.perf_counter() - started
    return MatchResult(
        dict_size=edge_dictionary.edge_instance_count,
        first_agent=first_agent.name,
        second_agent=second_agent.name,
        winner=winner,
        turn_count=len(history),
        used_word_count=len(state.edge_history),
        loss_reason=loss_reason,
        first_total_time_sec=timings[0].total_time_sec,
        second_total_time_sec=timings[1].total_time_sec,
        first_avg_time_sec=timings[0].average_time_sec,
        second_avg_time_sec=timings[1].average_time_sec,
        first_max_time_sec=timings[0].max_time_sec,
        second_max_time_sec=timings[1].max_time_sec,
        first_timeout_count=timings[0].timeout_count,
        second_timeout_count=timings[1].timeout_count,
        max_moves=max_moves,
        max_match_time_sec=max_match_time_sec,
        match_elapsed_time_sec=match_elapsed,
        history=history,
    )


def append_jsonl(rows: list[dict[str, object]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as jsonl_file:
        for row in rows:
            jsonl_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
