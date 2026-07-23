"""Shared evaluation, timeout, statistics, and depth control for search agents."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from game import WordGraph

if TYPE_CHECKING:
    from runtime_state import AIEdgeState


LOSS_SCORE = -1_000_000.0
WIN_SCORE = 1_000_000.0


class SearchTimeout(RuntimeError):
    """Raised when a search deadline is reached."""


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.perf_counter() >= deadline:
        raise SearchTimeout


def win_score(ply: int) -> float:
    return WIN_SCORE - float(ply)


def loss_score(ply: int) -> float:
    return LOSS_SCORE + float(ply)


@dataclass(frozen=True)
class GameState:
    current_char: str | None
    used_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class EvaluationConfig:
    attack_legal_word_weight: float = 12.0
    attack_safe_word_weight: float = 8.0
    attack_safe_edge_type_weight: float = 6.0
    attack_safe_end_type_weight: float = 4.0
    attack_danger_word_weight: float = 2.5
    survival_safe_word_weight: float = 4.0
    survival_safe_edge_type_weight: float = 8.0
    survival_safe_end_type_weight: float = 6.0
    survival_average_weight: float = 0.15
    normal_survival_weight: float = 0.15
    caution_survival_weight: float = 0.35
    danger_survival_weight: float = 0.8
    critical_survival_weight: float = 1.5
    caution_safe_words: int = 10
    caution_safe_edge_types: int = 3
    danger_safe_words: int = 5
    danger_safe_edge_types: int = 2
    critical_safe_words: int = 2
    critical_safe_edge_types: int = 1


DEFAULT_EVALUATION_CONFIG = EvaluationConfig()


@dataclass(frozen=True)
class PositionMetrics:
    legal_word_count: int
    safe_word_count: int
    danger_word_count: int
    safe_edge_type_count: int
    safe_end_type_count: int


@dataclass(frozen=True)
class CandidateEvaluation:
    total_score: float
    attack_score: float
    survival_score: float
    survival_weight: float
    immediate_win: bool
    immediate_loss: bool


@dataclass
class SearchStats:
    nodes_searched: int = 0
    leaf_evaluations: int = 0
    completed_root_moves: int = 0
    cutoff_count: int = 0
    pruned_move_count: int = 0
    beam_pruned_move_count: int = 0
    null_window_search_count: int = 0
    research_count: int = 0
    beam_widths_used: dict[int, int] = field(default_factory=dict)

    def as_extra(self) -> dict[str, object]:
        return {
            "nodes_searched": self.nodes_searched,
            "leaf_evaluations": self.leaf_evaluations,
            "completed_root_moves": self.completed_root_moves,
            "cutoff_count": self.cutoff_count,
            "pruned_move_count": self.pruned_move_count,
            "beam_pruned_move_count": self.beam_pruned_move_count,
            "null_window_search_count": self.null_window_search_count,
            "research_count": self.research_count,
            "beam_widths_used": dict(sorted(self.beam_widths_used.items())),
        }


class AdaptiveDepthMixin:
    """Shared one-search-per-turn adaptive depth controller."""

    depth: int
    current_depth: int
    adaptive_depth: bool
    min_depth: int
    depth_recovery_turns: int
    _non_timeout_streak: int

    def _configure_adaptive_depth(
        self,
        depth: int,
        adaptive_depth: bool,
        min_depth: int,
        depth_recovery_turns: int,
    ) -> None:
        self.depth = max(1, depth)
        self.current_depth = self.depth
        self.adaptive_depth = adaptive_depth
        self.min_depth = min(self.depth, max(1, min_depth))
        self.depth_recovery_turns = max(1, depth_recovery_turns)
        self._non_timeout_streak = 0

    def _effective_depth(self) -> int:
        return self.current_depth if self.adaptive_depth else self.depth

    def _record_depth_result(self, timed_out: bool) -> None:
        if not self.adaptive_depth:
            return
        if timed_out:
            self.current_depth = max(self.min_depth, self.current_depth - 1)
            self._non_timeout_streak = 0
            return
        if self.current_depth >= self.depth:
            self._non_timeout_streak = 0
            return
        self._non_timeout_streak += 1
        if self._non_timeout_streak >= self.depth_recovery_turns:
            self.current_depth = min(self.depth, self.current_depth + 1)
            self._non_timeout_streak = 0


def legal_moves_for_state(graph: WordGraph, state: GameState) -> list[int]:
    if state.current_char is None:
        return [
            word_id
            for word_id in range(len(graph.words))
            if word_id not in state.used_ids
        ]
    return graph.available_word_ids_set(state.current_char, set(state.used_ids))


def state_after_safe_move(
    graph: WordGraph,
    state: GameState,
    word_id: int,
) -> GameState | None:
    end_char = graph.end_chars[word_id]
    if end_char == "ん":
        return None
    return GameState(end_char, state.used_ids | frozenset({word_id}))


def word_position_metrics(
    graph: WordGraph,
    state: GameState,
    deadline: float | None = None,
) -> PositionMetrics:
    moves = legal_moves_for_state(graph, state)
    safe_moves: list[int] = []
    safe_edges: set[tuple[str, str]] = set()
    for word_id in moves:
        check_deadline(deadline)
        if graph.end_chars[word_id] == "ん":
            continue
        safe_moves.append(word_id)
        safe_edges.add((graph.start_chars[word_id], graph.end_chars[word_id]))
    return PositionMetrics(
        legal_word_count=len(moves),
        safe_word_count=len(safe_moves),
        danger_word_count=len(moves) - len(safe_moves),
        safe_edge_type_count=len(safe_edges),
        safe_end_type_count=len({end_char for _start_char, end_char in safe_edges}),
    )


def edge_position_metrics(
    state: AIEdgeState,
    deadline: float | None = None,
) -> PositionMetrics:
    safe_words = 0
    danger_words = 0
    safe_edges = 0
    safe_end_ids: set[int] = set()
    n_id = state.edge_dictionary.char_to_id.get("ん")
    for start_id, end_id in state.available_edges():
        check_deadline(deadline)
        multiplicity = state.edge_counts[
            state.edge_dictionary.edge_index(start_id, end_id)
        ]
        if end_id == n_id:
            danger_words += multiplicity
        else:
            safe_words += multiplicity
            safe_edges += 1
            safe_end_ids.add(end_id)
    return PositionMetrics(
        legal_word_count=safe_words + danger_words,
        safe_word_count=safe_words,
        danger_word_count=danger_words,
        safe_edge_type_count=safe_edges,
        safe_end_type_count=len(safe_end_ids),
    )


def survival_weight_for_metrics(
    metrics: PositionMetrics,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
) -> float:
    if (
        metrics.safe_word_count <= config.critical_safe_words
        or metrics.safe_edge_type_count <= config.critical_safe_edge_types
        or metrics.safe_end_type_count <= 1
    ):
        return config.critical_survival_weight
    if (
        metrics.safe_word_count <= config.danger_safe_words
        or metrics.safe_edge_type_count <= config.danger_safe_edge_types
    ):
        return config.danger_survival_weight
    if (
        metrics.safe_word_count <= config.caution_safe_words
        or metrics.safe_edge_type_count <= config.caution_safe_edge_types
    ):
        return config.caution_survival_weight
    return config.normal_survival_weight


def attack_score_from_metrics(
    opponent: PositionMetrics,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
) -> float:
    return (
        -config.attack_legal_word_weight * opponent.legal_word_count
        -config.attack_safe_word_weight * opponent.safe_word_count
        -config.attack_safe_edge_type_weight * opponent.safe_edge_type_count
        -config.attack_safe_end_type_weight * opponent.safe_end_type_count
        +config.attack_danger_word_weight * opponent.danger_word_count
    )


def _survival_value(
    metrics: PositionMetrics,
    config: EvaluationConfig,
) -> float:
    return (
        config.survival_safe_word_weight * metrics.safe_word_count
        +config.survival_safe_edge_type_weight * metrics.safe_edge_type_count
        +config.survival_safe_end_type_weight * metrics.safe_end_type_count
    )


def _combine_survival_samples(
    samples: Iterable[tuple[float, int]],
    config: EvaluationConfig,
) -> float:
    values = list(samples)
    if not values:
        return 0.0
    worst = min(value for value, _weight in values)
    total_weight = sum(weight for _value, weight in values)
    average = sum(value * weight for value, weight in values) / total_weight
    return worst + config.survival_average_weight * average


def evaluate_word_candidate(
    graph: WordGraph,
    state: GameState,
    word_id: int,
    deadline: float | None = None,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
) -> CandidateEvaluation:
    check_deadline(deadline)
    if graph.end_chars[word_id] == "ん":
        return CandidateEvaluation(LOSS_SCORE, LOSS_SCORE, 0.0, 0.0, False, True)

    own_metrics = word_position_metrics(graph, state, deadline)
    next_state = state_after_safe_move(graph, state, word_id)
    assert next_state is not None
    opponent_metrics = word_position_metrics(graph, next_state, deadline)
    if opponent_metrics.legal_word_count == 0 or opponent_metrics.safe_word_count == 0:
        return CandidateEvaluation(WIN_SCORE, WIN_SCORE, 0.0, 0.0, True, False)

    attack_score = attack_score_from_metrics(opponent_metrics, config)
    opponent_moves = legal_moves_for_state(graph, next_state)
    grouped: dict[tuple[str, str], list[int]] = {}
    for reply_id in opponent_moves:
        check_deadline(deadline)
        if graph.end_chars[reply_id] == "ん":
            continue
        key = (graph.start_chars[reply_id], graph.end_chars[reply_id])
        grouped.setdefault(key, []).append(reply_id)

    samples: list[tuple[float, int]] = []
    for reply_ids in grouped.values():
        check_deadline(deadline)
        reply_state = state_after_safe_move(graph, next_state, reply_ids[0])
        assert reply_state is not None
        samples.append(
            (
                _survival_value(
                    word_position_metrics(graph, reply_state, deadline),
                    config,
                ),
                len(reply_ids),
            )
        )

    survival_score = _combine_survival_samples(samples, config)
    survival_weight = survival_weight_for_metrics(own_metrics, config)
    return CandidateEvaluation(
        attack_score + survival_weight * survival_score,
        attack_score,
        survival_score,
        survival_weight,
        False,
        False,
    )


def evaluate_edge_candidate(
    state: AIEdgeState,
    start_id: int,
    end_id: int,
    deadline: float | None = None,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
) -> CandidateEvaluation:
    check_deadline(deadline)
    if state.edge_dictionary.char_to_id.get("ん") == end_id:
        return CandidateEvaluation(LOSS_SCORE, LOSS_SCORE, 0.0, 0.0, False, True)

    own_metrics = edge_position_metrics(state, deadline)
    state.apply_edge(start_id, end_id)
    try:
        opponent_metrics = edge_position_metrics(state, deadline)
        if opponent_metrics.legal_word_count == 0 or opponent_metrics.safe_word_count == 0:
            return CandidateEvaluation(WIN_SCORE, WIN_SCORE, 0.0, 0.0, True, False)

        attack_score = attack_score_from_metrics(opponent_metrics, config)
        samples: list[tuple[float, int]] = []
        for reply_start, reply_end in state.available_edges():
            check_deadline(deadline)
            if state.edge_dictionary.char_to_id.get("ん") == reply_end:
                continue
            edge_index = state.edge_dictionary.edge_index(reply_start, reply_end)
            multiplicity = state.edge_counts[edge_index]
            state.apply_edge(reply_start, reply_end)
            try:
                samples.append(
                    (
                        _survival_value(edge_position_metrics(state, deadline), config),
                        multiplicity,
                    )
                )
            finally:
                state.undo_edge()

        survival_score = _combine_survival_samples(samples, config)
        survival_weight = survival_weight_for_metrics(own_metrics, config)
        return CandidateEvaluation(
            attack_score + survival_weight * survival_score,
            attack_score,
            survival_score,
            survival_weight,
            False,
            False,
        )
    finally:
        state.undo_edge()


def evaluate_word_position(
    graph: WordGraph,
    state: GameState,
    deadline: float | None = None,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ply: int = 0,
) -> float:
    moves = legal_moves_for_state(graph, state)
    if not moves:
        return LOSS_SCORE
    best = LOSS_SCORE
    for word_id in moves:
        check_deadline(deadline)
        evaluation = evaluate_word_candidate(
            graph, state, word_id, deadline, config
        )
        if evaluation.immediate_win:
            score = win_score(ply + 1)
        elif evaluation.immediate_loss:
            score = loss_score(ply)
        else:
            score = evaluation.total_score
        best = max(best, score)
    return best


def evaluate_edge_position(
    state: AIEdgeState,
    deadline: float | None = None,
    config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ply: int = 0,
) -> float:
    edges = state.available_edges()
    if not edges:
        return LOSS_SCORE
    best = LOSS_SCORE
    for start_id, end_id in edges:
        check_deadline(deadline)
        evaluation = evaluate_edge_candidate(
            state,
            start_id,
            end_id,
            deadline,
            config,
        )
        if evaluation.immediate_win:
            score = win_score(ply + 1)
        elif evaluation.immediate_loss:
            score = loss_score(ply)
        else:
            score = evaluation.total_score
        best = max(best, score)
    return best
