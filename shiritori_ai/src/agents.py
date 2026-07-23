"""Approximate shiritori AIs for word-compatible and edge-native play."""

from __future__ import annotations

import heapq
import math
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence, TypeVar

from game import WordGraph
from search_common import (
    DEFAULT_EVALUATION_CONFIG,
    LOSS_SCORE,
    WIN_SCORE,
    AdaptiveDepthMixin,
    CandidateEvaluation,
    EvaluationConfig,
    GameState,
    SearchStats,
    SearchTimeout,
    check_deadline,
    edge_candidate_analysis,
    evaluate_edge_candidate,
    evaluate_ordering_score,
    evaluate_edge_position as _evaluate_edge_position,
    evaluate_word_candidate,
    evaluate_word_position,
    legal_moves_for_state,
    loss_score,
    state_after_safe_move,
)

if TYPE_CHECKING:
    from runtime_state import AIEdgeState


DEFAULT_TIME_LIMIT_SEC = 2.0
DEFAULT_BEAM_WIDTHS = (12, 8, 4, 2)
T = TypeVar("T")


@dataclass(frozen=True)
class MoveDecision:
    word_id: int | None
    elapsed_time_sec: float
    timed_out: bool
    score: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeMoveDecision:
    start_id: int | None
    end_id: int | None
    elapsed_time_sec: float
    timed_out: bool
    score: float
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    name = "base"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ) -> None:
        self.time_limit_sec = time_limit_sec
        self.rng = random.Random(random_seed)
        self.evaluation_config = evaluation_config

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        raise NotImplementedError

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        raise NotImplementedError

    def legal_moves(self, graph: WordGraph, state: GameState) -> list[int]:
        return legal_moves_for_state(graph, state)

    def fallback_move(self, graph: WordGraph, state: GameState) -> int | None:
        moves = self.legal_moves(graph, state)
        return _safe_word_fallback(graph, moves)

    def _deadline(self) -> float:
        return time.perf_counter() + self.time_limit_sec


def edge_is_terminal(state: AIEdgeState, end_id: int) -> bool:
    return state.edge_dictionary.char_to_id.get("ん") == end_id


def weighted_edge_choice(
    state: AIEdgeState,
    edges: list[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int]:
    weights = [
        state.edge_counts[state.edge_dictionary.edge_index(start_id, end_id)]
        for start_id, end_id in edges
    ]
    return rng.choices(edges, weights=weights, k=1)[0]


def greedy_move_score(graph: WordGraph, state: GameState, word_id: int) -> float:
    return evaluate_word_candidate(
        graph,
        state,
        word_id,
        config=DEFAULT_EVALUATION_CONFIG,
    ).total_score


def edge_greedy_score(state: AIEdgeState, start_id: int, end_id: int) -> float:
    return evaluate_edge_candidate(
        state,
        start_id,
        end_id,
        config=DEFAULT_EVALUATION_CONFIG,
    ).total_score


def evaluate_position(
    graph: WordGraph,
    state: GameState,
    deadline: float | None = None,
) -> float:
    return evaluate_word_position(graph, state, deadline)


def evaluate_edge_position(
    state: AIEdgeState,
    deadline: float | None = None,
) -> float:
    return _evaluate_edge_position(state, deadline)


def _word_sort_key(
    graph: WordGraph,
    word_id: int,
    evaluation: CandidateEvaluation,
    aggressive: bool,
) -> tuple[object, ...]:
    if aggressive:
        return (
            not evaluation.immediate_win,
            -evaluation.attack_score,
            -evaluation.total_score,
            graph.words[word_id],
        )
    return (
        not evaluation.immediate_win,
        -evaluation.total_score,
        -evaluation.attack_score,
        graph.words[word_id],
    )


def _edge_sort_key(
    edge: tuple[int, int],
    evaluation: CandidateEvaluation,
    aggressive: bool,
) -> tuple[object, ...]:
    if aggressive:
        return (
            not evaluation.immediate_win,
            -evaluation.attack_score,
            -evaluation.total_score,
            edge[0],
            edge[1],
        )
    return (
        not evaluation.immediate_win,
        -evaluation.total_score,
        -evaluation.attack_score,
        edge[0],
        edge[1],
    )


def _score_word_candidates(
    graph: WordGraph,
    state: GameState,
    moves: Sequence[int],
    deadline: float | None,
    config: EvaluationConfig,
    allow_partial: bool,
    aggressive: bool = False,
) -> tuple[list[int], dict[int, CandidateEvaluation], bool]:
    evaluations: dict[int, CandidateEvaluation] = {}
    timed_out = False
    for word_id in moves:
        try:
            check_deadline(deadline)
            evaluations[word_id] = evaluate_word_candidate(
                graph, state, word_id, deadline, config
            )
        except SearchTimeout:
            if not allow_partial:
                raise
            timed_out = True
            break
    ordered = sorted(
        evaluations,
        key=lambda word_id: _word_sort_key(
            graph, word_id, evaluations[word_id], aggressive
        ),
    )
    return ordered, evaluations, timed_out


def _score_edge_candidates(
    state: AIEdgeState,
    edges: Sequence[tuple[int, int]],
    deadline: float | None,
    config: EvaluationConfig,
    allow_partial: bool,
    aggressive: bool = False,
    stats: SearchStats | None = None,
    candidate_limit: int | None = None,
) -> tuple[
    list[tuple[int, int]],
    dict[tuple[int, int], CandidateEvaluation],
    bool,
]:
    evaluations: dict[tuple[int, int], CandidateEvaluation] = {}
    timed_out = False
    for edge in edges:
        try:
            check_deadline(deadline)
            evaluations[edge] = evaluate_ordering_score(
                state, edge[0], edge[1], deadline, config
            )
            if stats is not None:
                stats.ordering_evaluations += 1
        except SearchTimeout:
            if not allow_partial:
                raise
            timed_out = True
            break
    sort_key = lambda edge: _edge_sort_key(  # noqa: E731
        edge, evaluations[edge], aggressive
    )
    if candidate_limit is not None and len(evaluations) > candidate_limit:
        ordered = heapq.nsmallest(candidate_limit, evaluations, key=sort_key)
    else:
        ordered = sorted(evaluations, key=sort_key)
    return ordered, evaluations, timed_out


def greedy_ordered_moves(
    graph: WordGraph,
    state: GameState,
    moves: list[int],
) -> list[int]:
    return _score_word_candidates(
        graph,
        state,
        moves,
        None,
        DEFAULT_EVALUATION_CONFIG,
        allow_partial=False,
    )[0]


def greedy_ordered_moves_until_deadline(
    graph: WordGraph,
    state: GameState,
    moves: list[int],
    deadline: float,
    limit: int | None = None,
) -> tuple[list[int], bool]:
    ordered, _evaluations, timed_out = _score_word_candidates(
        graph,
        state,
        moves,
        deadline,
        DEFAULT_EVALUATION_CONFIG,
        allow_partial=True,
    )
    return (ordered if limit is None else ordered[:limit]), timed_out


def greedy_ordered_edges_until_deadline(
    state: AIEdgeState,
    edges: list[tuple[int, int]],
    deadline: float,
    limit: int | None = None,
) -> tuple[list[tuple[int, int]], bool]:
    ordered, _evaluations, timed_out = _score_edge_candidates(
        state,
        edges,
        deadline,
        DEFAULT_EVALUATION_CONFIG,
        allow_partial=True,
    )
    return (ordered if limit is None else ordered[:limit]), timed_out


def _safe_word_fallback(graph: WordGraph, moves: Sequence[int]) -> int | None:
    if not moves:
        return None
    safe = [word_id for word_id in moves if graph.end_chars[word_id] != "ん"]
    return min(safe or list(moves), key=lambda word_id: graph.words[word_id])


def _safe_edge_fallback(
    state: AIEdgeState,
    edges: Sequence[tuple[int, int]],
) -> tuple[int, int] | None:
    if not edges:
        return None
    safe = [edge for edge in edges if not edge_is_terminal(state, edge[1])]
    return min(safe or list(edges))


class RandomAgent(BaseAgent):
    name = "random"

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)
        safe = [word_id for word_id in moves if graph.end_chars[word_id] != "ん"]
        word_id = self.rng.choice(safe or moves)
        return MoveDecision(word_id, time.perf_counter() - started, False, 0.0)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        edges = state.available_edges()
        if not edges:
            return EdgeMoveDecision(None, None, time.perf_counter() - started, False, LOSS_SCORE)
        safe = [edge for edge in edges if not edge_is_terminal(state, edge[1])]
        edge = weighted_edge_choice(state, safe or edges, self.rng)
        return EdgeMoveDecision(
            edge[0], edge[1], time.perf_counter() - started, False, 0.0,
            {"move_unit": "edge_type"},
        )


class GreedyAgent(BaseAgent):
    name = "greedy"

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)
        ordered, evaluations, timed_out = _score_word_candidates(
            graph, state, moves, deadline, self.evaluation_config, allow_partial=True
        )
        word_id = ordered[0] if ordered else _safe_word_fallback(graph, moves)
        assert word_id is not None
        score = evaluations[word_id].total_score if word_id in evaluations else (
            LOSS_SCORE if graph.end_chars[word_id] == "ん" else -math.inf
        )
        final_timed_out = timed_out or time.perf_counter() >= deadline
        return MoveDecision(
            word_id, time.perf_counter() - started, final_timed_out, score,
            {"evaluated_moves": len(evaluations)},
        )

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        edges = state.available_edges()
        if not edges:
            return EdgeMoveDecision(None, None, time.perf_counter() - started, False, LOSS_SCORE)
        ordered, evaluations, timed_out = _score_edge_candidates(
            state, edges, deadline, self.evaluation_config, allow_partial=True
        )
        edge = ordered[0] if ordered else _safe_edge_fallback(state, edges)
        assert edge is not None
        score = evaluations[edge].total_score if edge in evaluations else (
            LOSS_SCORE if edge_is_terminal(state, edge[1]) else -math.inf
        )
        final_timed_out = timed_out or time.perf_counter() >= deadline
        return EdgeMoveDecision(
            edge[0], edge[1], time.perf_counter() - started, final_timed_out, score,
            {"evaluated_moves": len(evaluations), "move_unit": "edge_type"},
        )


class SearchAgentBase(BaseAgent, AdaptiveDepthMixin):
    def __init__(
        self,
        time_limit_sec: float,
        random_seed: int,
        depth: int,
        branch_limit: int | None,
        adaptive_depth: bool,
        min_depth: int,
        depth_recovery_turns: int,
        evaluation_config: EvaluationConfig,
    ) -> None:
        super().__init__(time_limit_sec, random_seed, evaluation_config)
        self.branch_limit = branch_limit
        self._configure_adaptive_depth(
            depth, adaptive_depth, min_depth, depth_recovery_turns
        )

    @property
    def aggressive_ordering(self) -> bool:
        return False

    def _search_extra(
        self,
        stats: SearchStats,
        effective_depth: int,
        **extra: object,
    ) -> dict[str, Any]:
        return {
            "evaluated_moves": stats.completed_root_moves,
            "depth": self.depth,
            "effective_depth": effective_depth,
            "next_depth": self.current_depth,
            "adaptive_depth": self.adaptive_depth,
            "branch_limit": self.branch_limit,
            "pruned_count": stats.pruned_move_count,
            **stats.as_extra(),
            **extra,
        }

    def _ordered_words(
        self,
        graph: WordGraph,
        state: GameState,
        moves: Sequence[int],
        deadline: float,
        allow_partial: bool,
    ) -> tuple[list[int], dict[int, CandidateEvaluation], bool]:
        ordered, evaluations, timed_out = _score_word_candidates(
            graph,
            state,
            moves,
            deadline,
            self.evaluation_config,
            allow_partial,
            self.aggressive_ordering,
        )
        if self.branch_limit is not None:
            ordered = ordered[: self.branch_limit]
        return ordered, evaluations, timed_out

    def _ordered_edges(
        self,
        state: AIEdgeState,
        edges: Sequence[tuple[int, int]],
        deadline: float,
        allow_partial: bool,
        stats: SearchStats,
        ply: int,
    ) -> tuple[
        list[tuple[int, int]],
        dict[tuple[int, int], CandidateEvaluation],
        bool,
    ]:
        ordering_started = time.perf_counter()
        try:
            ordered, evaluations, timed_out = _score_edge_candidates(
                state,
                edges,
                deadline,
                self.evaluation_config,
                allow_partial,
                self.aggressive_ordering,
                stats,
                self._edge_ordering_limit(ply),
            )
        finally:
            stats.ordering_time_sec += time.perf_counter() - ordering_started
        self._record_edge_ordering_limit(len(edges), len(ordered), ply, stats)
        return ordered, evaluations, timed_out

    def _edge_ordering_limit(self, ply: int) -> int | None:
        return self.branch_limit

    def _record_edge_ordering_limit(
        self,
        candidate_count: int,
        selected_count: int,
        ply: int,
        stats: SearchStats,
    ) -> None:
        if self.branch_limit is not None:
            stats.pruned_move_count += max(0, candidate_count - selected_count)

    def _select_root_candidates(
        self,
        candidates: list[T],
        stats: SearchStats,
    ) -> list[T]:
        return candidates


class MinimaxAgent(SearchAgentBase):
    name = "minimax"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        depth: int = 3,
        branch_limit: int | None = 12,
        adaptive_depth: bool = True,
        min_depth: int = 1,
        depth_recovery_turns: int = 5,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ) -> None:
        super().__init__(
            time_limit_sec,
            random_seed,
            depth,
            branch_limit,
            adaptive_depth,
            min_depth,
            depth_recovery_turns,
            evaluation_config,
        )

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        effective_depth = self._effective_depth()
        stats = SearchStats()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)
        ordered, pre_scores, ordering_timed_out = self._ordered_words(
            graph, state, moves, deadline, allow_partial=True
        )
        ordered = self._select_root_candidates(ordered, stats)
        if not ordered:
            fallback = _safe_word_fallback(graph, moves)
            assert fallback is not None
            self._record_depth_result(True)
            return MoveDecision(
                fallback,
                time.perf_counter() - started,
                True,
                LOSS_SCORE if graph.end_chars[fallback] == "ん" else -math.inf,
                self._search_extra(
                    stats, effective_depth, timed_out=True, score_complete=False
                ),
            )

        best_move = ordered[0]
        best_score = pre_scores[best_move].total_score
        timed_out = ordering_timed_out
        for word_id in ordered:
            try:
                score = self._score_move(
                    graph, state, word_id, effective_depth, deadline, stats
                )
            except SearchTimeout:
                timed_out = True
                break
            stats.completed_root_moves += 1
            if score > best_score or stats.completed_root_moves == 1:
                best_score = score
                best_move = word_id
        final_timed_out = timed_out or time.perf_counter() >= deadline
        self._record_depth_result(final_timed_out)
        return MoveDecision(
            best_move,
            time.perf_counter() - started,
            final_timed_out,
            best_score,
            self._search_extra(stats, effective_depth, timed_out=final_timed_out),
        )

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        effective_depth = self._effective_depth()
        stats = SearchStats()
        edges = state.available_edges()
        if not edges:
            return EdgeMoveDecision(None, None, time.perf_counter() - started, False, LOSS_SCORE)
        ordered, pre_scores, ordering_timed_out = self._ordered_edges(
            state, edges, deadline, allow_partial=True, stats=stats, ply=0
        )
        ordered = self._select_root_candidates(ordered, stats)
        if not ordered:
            fallback = _safe_edge_fallback(state, edges)
            assert fallback is not None
            analysis = edge_candidate_analysis(
                state, fallback[0], fallback[1], self.evaluation_config
            )
            elapsed = time.perf_counter() - started
            stats.total_search_time_sec = elapsed
            elapsed_ratio = elapsed / self.time_limit_sec if self.time_limit_sec > 0 else math.inf
            self._record_depth_result(True, elapsed_ratio)
            return EdgeMoveDecision(
                fallback[0],
                fallback[1],
                elapsed,
                True,
                LOSS_SCORE if edge_is_terminal(state, fallback[1]) else -math.inf,
                self._search_extra(
                    stats,
                    effective_depth,
                    timed_out=True,
                    move_unit="edge_type",
                    score_complete=False,
                    elapsed_ratio=elapsed_ratio,
                    root_candidate_count=len(edges),
                    searched_root_candidate_count=0,
                    **analysis,
                ),
            )

        best_edge = ordered[0]
        best_score = pre_scores[best_edge].total_score
        timed_out = ordering_timed_out
        search_started = time.perf_counter()
        try:
            for edge in ordered:
                try:
                    score = self._score_edge(
                        state, edge[0], edge[1], effective_depth, deadline, stats
                    )
                except SearchTimeout:
                    timed_out = True
                    break
                stats.completed_root_moves += 1
                if score > best_score or stats.completed_root_moves == 1:
                    best_score = score
                    best_edge = edge
        finally:
            stats.search_time_sec += time.perf_counter() - search_started
        final_timed_out = timed_out or time.perf_counter() >= deadline
        analysis = edge_candidate_analysis(
            state, best_edge[0], best_edge[1], self.evaluation_config
        )
        elapsed = time.perf_counter() - started
        stats.total_search_time_sec = elapsed
        elapsed_ratio = elapsed / self.time_limit_sec if self.time_limit_sec > 0 else math.inf
        self._record_depth_result(final_timed_out, elapsed_ratio)
        return EdgeMoveDecision(
            best_edge[0],
            best_edge[1],
            elapsed,
            final_timed_out,
            best_score,
            self._search_extra(
                stats,
                effective_depth,
                timed_out=final_timed_out,
                move_unit="edge_type",
                elapsed_ratio=elapsed_ratio,
                root_candidate_count=len(edges),
                searched_root_candidate_count=stats.completed_root_moves,
                **analysis,
            ),
        )

    def _score_move(
        self,
        graph: WordGraph,
        state: GameState,
        word_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        next_state = state_after_safe_move(graph, state, word_id)
        if next_state is None:
            return loss_score(0)
        return -self._negamax(graph, next_state, depth - 1, 1, deadline, stats)

    def _negamax(
        self,
        graph: WordGraph,
        state: GameState,
        depth: int,
        ply: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        moves = self.legal_moves(graph, state)
        if not moves:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            return evaluate_word_position(
                graph, state, deadline, self.evaluation_config, ply=ply
            )
        ordered, _scores, _timed_out = self._ordered_words(
            graph, state, moves, deadline, allow_partial=False
        )
        best = LOSS_SCORE
        for word_id in ordered:
            check_deadline(deadline)
            next_state = state_after_safe_move(graph, state, word_id)
            score = (
                loss_score(ply)
                if next_state is None
                else -self._negamax(
                    graph, next_state, depth - 1, ply + 1, deadline, stats
                )
            )
            best = max(best, score)
        return best

    def _score_edge(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        if edge_is_terminal(state, end_id):
            return loss_score(0)
        state.apply_edge(start_id, end_id)
        try:
            return -self._edge_negamax(state, depth - 1, 1, deadline, stats)
        finally:
            state.undo_edge()

    def _edge_negamax(
        self,
        state: AIEdgeState,
        depth: int,
        ply: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        edges = state.available_edges()
        if not edges:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            evaluation_started = time.perf_counter()
            try:
                return _evaluate_edge_position(
                    state, deadline, self.evaluation_config, ply=ply, stats=stats
                )
            finally:
                stats.evaluation_time_sec += time.perf_counter() - evaluation_started
        ordered, _scores, _timed_out = self._ordered_edges(
            state, edges, deadline, allow_partial=False, stats=stats, ply=ply
        )
        best = LOSS_SCORE
        for start_id, end_id in ordered:
            check_deadline(deadline)
            if edge_is_terminal(state, end_id):
                score = loss_score(ply)
            else:
                state.apply_edge(start_id, end_id)
                try:
                    score = -self._edge_negamax(
                        state, depth - 1, ply + 1, deadline, stats
                    )
                finally:
                    state.undo_edge()
            best = max(best, score)
        return best


class AlphaBetaAgent(MinimaxAgent):
    name = "alpha_beta"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        depth: int = 3,
        branch_limit: int | None = 12,
        adaptive_depth: bool = True,
        min_depth: int = 1,
        depth_recovery_turns: int = 5,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
        share_root_alpha: bool = True,
    ) -> None:
        self.share_root_alpha = share_root_alpha
        super().__init__(
            time_limit_sec,
            random_seed,
            depth,
            branch_limit,
            adaptive_depth,
            min_depth,
            depth_recovery_turns,
            evaluation_config,
        )

    def _score_move(
        self,
        graph: WordGraph,
        state: GameState,
        word_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        next_state = state_after_safe_move(graph, state, word_id)
        if next_state is None:
            return loss_score(0)
        root_alpha = getattr(stats, "_root_alpha", LOSS_SCORE)
        alpha = root_alpha if self.share_root_alpha else LOSS_SCORE
        score = -self._negamax_alpha_beta(
            graph,
            next_state,
            depth - 1,
            1,
            -WIN_SCORE,
            -alpha,
            deadline,
            stats,
        )
        if self.share_root_alpha and score > root_alpha:
            setattr(stats, "_root_alpha", score)
            stats.root_alpha_updates += 1
        return score

    def _negamax_alpha_beta(
        self,
        graph: WordGraph,
        state: GameState,
        depth: int,
        ply: int,
        alpha: float,
        beta: float,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        moves = self.legal_moves(graph, state)
        if not moves:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            return evaluate_word_position(
                graph, state, deadline, self.evaluation_config, ply=ply
            )
        ordered, _scores, _timed_out = self._ordered_words(
            graph, state, moves, deadline, allow_partial=False
        )
        best = LOSS_SCORE
        for index, word_id in enumerate(ordered):
            check_deadline(deadline)
            next_state = state_after_safe_move(graph, state, word_id)
            score = (
                loss_score(ply)
                if next_state is None
                else -self._negamax_alpha_beta(
                    graph,
                    next_state,
                    depth - 1,
                    ply + 1,
                    -beta,
                    -alpha,
                    deadline,
                    stats,
                )
            )
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.cutoff_count += 1
                stats.pruned_move_count += len(ordered) - index - 1
                break
        return best

    def _score_edge(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        if edge_is_terminal(state, end_id):
            return loss_score(0)
        root_alpha = getattr(stats, "_root_alpha", LOSS_SCORE)
        alpha = root_alpha if self.share_root_alpha else LOSS_SCORE
        state.apply_edge(start_id, end_id)
        try:
            score = -self._edge_negamax_alpha_beta(
                state,
                depth - 1,
                1,
                -WIN_SCORE,
                -alpha,
                deadline,
                stats,
            )
        finally:
            state.undo_edge()
        if self.share_root_alpha and score > root_alpha:
            setattr(stats, "_root_alpha", score)
            stats.root_alpha_updates += 1
        return score

    def _edge_negamax_alpha_beta(
        self,
        state: AIEdgeState,
        depth: int,
        ply: int,
        alpha: float,
        beta: float,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        edges = state.available_edges()
        if not edges:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            evaluation_started = time.perf_counter()
            try:
                return _evaluate_edge_position(
                    state, deadline, self.evaluation_config, ply=ply, stats=stats
                )
            finally:
                stats.evaluation_time_sec += time.perf_counter() - evaluation_started
        ordered, _scores, _timed_out = self._ordered_edges(
            state, edges, deadline, allow_partial=False, stats=stats, ply=ply
        )
        best = LOSS_SCORE
        for index, (start_id, end_id) in enumerate(ordered):
            check_deadline(deadline)
            if edge_is_terminal(state, end_id):
                score = loss_score(ply)
            else:
                state.apply_edge(start_id, end_id)
                try:
                    score = -self._edge_negamax_alpha_beta(
                        state,
                        depth - 1,
                        ply + 1,
                        -beta,
                        -alpha,
                        deadline,
                        stats,
                    )
                finally:
                    state.undo_edge()
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.cutoff_count += 1
                stats.pruned_move_count += len(ordered) - index - 1
                break
        return best


class BeamNegamaxAgent(MinimaxAgent):
    name = "beam_negamax"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        depth: int = 4,
        beam_widths: Sequence[int] = DEFAULT_BEAM_WIDTHS,
        adaptive_depth: bool = True,
        min_depth: int = 1,
        depth_recovery_turns: int = 5,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ) -> None:
        if not beam_widths or any(width <= 0 for width in beam_widths):
            raise ValueError("beam_widths must contain positive integers")
        self.beam_widths = tuple(int(width) for width in beam_widths)
        super().__init__(
            time_limit_sec,
            random_seed,
            depth,
            branch_limit=None,
            adaptive_depth=adaptive_depth,
            min_depth=min_depth,
            depth_recovery_turns=depth_recovery_turns,
            evaluation_config=evaluation_config,
        )

    def _beam_width(self, ply: int) -> int:
        return self.beam_widths[min(ply, len(self.beam_widths) - 1)]

    def _edge_ordering_limit(self, ply: int) -> int | None:
        return self._beam_width(ply)

    def _record_edge_ordering_limit(
        self,
        candidate_count: int,
        selected_count: int,
        ply: int,
        stats: SearchStats,
    ) -> None:
        width = self._beam_width(ply)
        stats.beam_widths_used[ply] = width
        stats.beam_pruned_move_count += max(0, candidate_count - selected_count)

    def _select_root_candidates(
        self,
        candidates: list[T],
        stats: SearchStats,
    ) -> list[T]:
        width = self._beam_width(0)
        stats.beam_widths_used[0] = width
        stats.beam_pruned_move_count += max(0, len(candidates) - width)
        return candidates[:width]

    def _limit_beam(self, candidates: list[T], ply: int, stats: SearchStats) -> list[T]:
        width = self._beam_width(ply)
        stats.beam_widths_used[ply] = width
        stats.beam_pruned_move_count += max(0, len(candidates) - width)
        return candidates[:width]

    def _negamax(
        self,
        graph: WordGraph,
        state: GameState,
        depth: int,
        ply: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        moves = self.legal_moves(graph, state)
        if not moves:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            return evaluate_word_position(
                graph, state, deadline, self.evaluation_config, ply=ply
            )
        ordered, _scores, _ = self._ordered_words(
            graph, state, moves, deadline, allow_partial=False
        )
        ordered = self._limit_beam(ordered, ply, stats)
        best = LOSS_SCORE
        for word_id in ordered:
            next_state = state_after_safe_move(graph, state, word_id)
            score = loss_score(ply) if next_state is None else -self._negamax(
                graph, next_state, depth - 1, ply + 1, deadline, stats
            )
            best = max(best, score)
        return best

    def _edge_negamax(
        self,
        state: AIEdgeState,
        depth: int,
        ply: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        edges = state.available_edges()
        if not edges:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            evaluation_started = time.perf_counter()
            try:
                return _evaluate_edge_position(
                    state, deadline, self.evaluation_config, ply=ply, stats=stats
                )
            finally:
                stats.evaluation_time_sec += time.perf_counter() - evaluation_started
        ordered, _scores, _ = self._ordered_edges(
            state, edges, deadline, allow_partial=False, stats=stats, ply=ply
        )
        ordered = self._limit_beam(ordered, ply, stats)
        best = LOSS_SCORE
        for start_id, end_id in ordered:
            if edge_is_terminal(state, end_id):
                score = loss_score(ply)
            else:
                state.apply_edge(start_id, end_id)
                try:
                    score = -self._edge_negamax(
                        state, depth - 1, ply + 1, deadline, stats
                    )
                finally:
                    state.undo_edge()
            best = max(best, score)
        return best

    def _search_extra(
        self,
        stats: SearchStats,
        effective_depth: int,
        **extra: object,
    ) -> dict[str, Any]:
        return super()._search_extra(
            stats,
            effective_depth,
            beam_widths=list(self.beam_widths),
            **extra,
        )


class PVSAgent(AlphaBetaAgent):
    name = "pvs"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        depth: int = 3,
        branch_limit: int | None = 12,
        adaptive_depth: bool = True,
        min_depth: int = 1,
        depth_recovery_turns: int = 5,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
        null_window_epsilon: float | None = None,
    ) -> None:
        self.null_window_epsilon = null_window_epsilon
        super().__init__(
            time_limit_sec,
            random_seed,
            depth,
            branch_limit=branch_limit,
            adaptive_depth=adaptive_depth,
            min_depth=min_depth,
            depth_recovery_turns=depth_recovery_turns,
            evaluation_config=evaluation_config,
        )

    @property
    def aggressive_ordering(self) -> bool:
        return False

    def _null_window_upper(self, alpha: float) -> float:
        if self.null_window_epsilon is not None:
            return alpha + self.null_window_epsilon
        return math.nextafter(alpha, math.inf)

    def _score_move(
        self,
        graph: WordGraph,
        state: GameState,
        word_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        next_state = state_after_safe_move(graph, state, word_id)
        if next_state is None:
            return loss_score(0)
        if stats.completed_root_moves == 0:
            score = -self._pvs_word(
                graph, next_state, depth - 1, 1, -WIN_SCORE, WIN_SCORE, deadline, stats
            )
            setattr(stats, "_root_alpha", score)
            return score
        alpha = getattr(stats, "_root_alpha", LOSS_SCORE)
        upper = self._null_window_upper(alpha)
        stats.null_window_search_count += 1
        score = -self._pvs_word(
            graph, next_state, depth - 1, 1, -upper, -alpha, deadline, stats
        )
        if alpha < score < WIN_SCORE:
            stats.research_count += 1
            score = -self._pvs_word(
                graph, next_state, depth - 1, 1, -WIN_SCORE, -alpha, deadline, stats
            )
        setattr(stats, "_root_alpha", max(alpha, score))
        return score

    def _score_edge(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        if edge_is_terminal(state, end_id):
            return loss_score(0)
        state.apply_edge(start_id, end_id)
        try:
            if stats.completed_root_moves == 0:
                score = -self._pvs_edge(
                    state, depth - 1, 1, -WIN_SCORE, WIN_SCORE, deadline, stats
                )
                setattr(stats, "_root_alpha", score)
                return score
            alpha = getattr(stats, "_root_alpha", LOSS_SCORE)
            upper = self._null_window_upper(alpha)
            stats.null_window_search_count += 1
            score = -self._pvs_edge(
                state, depth - 1, 1, -upper, -alpha, deadline, stats
            )
            if alpha < score < WIN_SCORE:
                stats.research_count += 1
                score = -self._pvs_edge(
                    state, depth - 1, 1, -WIN_SCORE, -alpha, deadline, stats
                )
            setattr(stats, "_root_alpha", max(alpha, score))
            return score
        finally:
            state.undo_edge()

    def _pvs_word(
        self,
        graph: WordGraph,
        state: GameState,
        depth: int,
        ply: int,
        alpha: float,
        beta: float,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        moves = self.legal_moves(graph, state)
        if not moves:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            return evaluate_word_position(
                graph, state, deadline, self.evaluation_config, ply=ply
            )
        ordered, _scores, _ = self._ordered_words(
            graph, state, moves, deadline, allow_partial=False
        )
        best = LOSS_SCORE
        for index, word_id in enumerate(ordered):
            next_state = state_after_safe_move(graph, state, word_id)
            if next_state is None:
                score = loss_score(ply)
            elif index == 0:
                score = -self._pvs_word(
                    graph, next_state, depth - 1, ply + 1, -beta, -alpha, deadline, stats
                )
            else:
                upper = self._null_window_upper(alpha)
                stats.null_window_search_count += 1
                score = -self._pvs_word(
                    graph, next_state, depth - 1, ply + 1, -upper, -alpha, deadline, stats
                )
                if alpha < score < beta:
                    stats.research_count += 1
                    score = -self._pvs_word(
                        graph, next_state, depth - 1, ply + 1, -beta, -alpha, deadline, stats
                    )
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.cutoff_count += 1
                stats.pruned_move_count += len(ordered) - index - 1
                break
        return best

    def _pvs_edge(
        self,
        state: AIEdgeState,
        depth: int,
        ply: int,
        alpha: float,
        beta: float,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        stats.nodes_searched += 1
        edges = state.available_edges()
        if not edges:
            return loss_score(ply)
        if depth <= 0:
            stats.leaf_evaluations += 1
            evaluation_started = time.perf_counter()
            try:
                return _evaluate_edge_position(
                    state, deadline, self.evaluation_config, ply=ply, stats=stats
                )
            finally:
                stats.evaluation_time_sec += time.perf_counter() - evaluation_started
        ordered, _scores, _ = self._ordered_edges(
            state, edges, deadline, allow_partial=False, stats=stats, ply=ply
        )
        best = LOSS_SCORE
        for index, (start_id, end_id) in enumerate(ordered):
            if edge_is_terminal(state, end_id):
                score = loss_score(ply)
            else:
                state.apply_edge(start_id, end_id)
                try:
                    if index == 0:
                        score = -self._pvs_edge(
                            state, depth - 1, ply + 1, -beta, -alpha, deadline, stats
                        )
                    else:
                        upper = self._null_window_upper(alpha)
                        stats.null_window_search_count += 1
                        score = -self._pvs_edge(
                            state, depth - 1, ply + 1, -upper, -alpha, deadline, stats
                        )
                        if alpha < score < beta:
                            stats.research_count += 1
                            score = -self._pvs_edge(
                                state, depth - 1, ply + 1, -beta, -alpha, deadline, stats
                            )
                finally:
                    state.undo_edge()
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.cutoff_count += 1
                stats.pruned_move_count += len(ordered) - index - 1
                break
        return best


class AggressivePVSAgent(PVSAgent):
    """Backward-compatible CLI/class alias for the now-fair PVS implementation."""

    name = "aggressive_pvs"


class MonteCarloAgent(BaseAgent):
    name = "monte_carlo"

    def __init__(
        self,
        time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
        random_seed: int = 0,
        candidate_limit: int = 20,
        playouts_per_move: int = 10,
        max_playout_moves: int = 200,
        evaluation_config: EvaluationConfig = DEFAULT_EVALUATION_CONFIG,
    ) -> None:
        super().__init__(time_limit_sec, random_seed, evaluation_config)
        self.candidate_limit = candidate_limit
        self.playouts_per_move = playouts_per_move
        self.max_playout_moves = max_playout_moves

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)
        candidates, pre_scores, timed_out = _score_word_candidates(
            graph, state, moves, deadline, self.evaluation_config, allow_partial=True
        )
        candidates = candidates[: self.candidate_limit]
        if not candidates:
            fallback = _safe_word_fallback(graph, moves)
            assert fallback is not None
            return MoveDecision(
                fallback, time.perf_counter() - started, True, -math.inf,
                self._monte_extra([], 0),
            )
        wins = [0.0] * len(candidates)
        counts = [0] * len(candidates)
        for _round in range(self.playouts_per_move):
            for index, word_id in enumerate(candidates):
                try:
                    check_deadline(deadline)
                    result = self._playout_after_move(graph, state, word_id, deadline)
                except SearchTimeout:
                    timed_out = True
                    break
                wins[index] += result
                counts[index] += 1
            if timed_out:
                break
        scored_indices = [index for index, count in enumerate(counts) if count]
        if scored_indices:
            best_index = max(
                scored_indices,
                key=lambda index: (wins[index] / counts[index], -index),
            )
            score = wins[best_index] / counts[best_index]
        else:
            best_index = 0
            score = pre_scores[candidates[0]].total_score
        final_timed_out = timed_out or time.perf_counter() >= deadline
        return MoveDecision(
            candidates[best_index],
            time.perf_counter() - started,
            final_timed_out,
            score,
            self._monte_extra(counts, sum(counts)),
        )

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        edges = state.available_edges()
        if not edges:
            return EdgeMoveDecision(None, None, time.perf_counter() - started, False, LOSS_SCORE)
        candidates, pre_scores, timed_out = _score_edge_candidates(
            state, edges, deadline, self.evaluation_config, allow_partial=True
        )
        candidates = candidates[: self.candidate_limit]
        if not candidates:
            fallback = _safe_edge_fallback(state, edges)
            assert fallback is not None
            return EdgeMoveDecision(
                fallback[0], fallback[1], time.perf_counter() - started, True, -math.inf,
                {**self._monte_extra([], 0), "move_unit": "edge_type"},
            )
        wins = [0.0] * len(candidates)
        counts = [0] * len(candidates)
        for _round in range(self.playouts_per_move):
            for index, edge in enumerate(candidates):
                try:
                    check_deadline(deadline)
                    result = self._edge_playout_after_move(
                        state, edge[0], edge[1], deadline
                    )
                except SearchTimeout:
                    timed_out = True
                    break
                wins[index] += result
                counts[index] += 1
            if timed_out:
                break
        scored_indices = [index for index, count in enumerate(counts) if count]
        if scored_indices:
            best_index = max(
                scored_indices,
                key=lambda index: (wins[index] / counts[index], -index),
            )
            score = wins[best_index] / counts[best_index]
        else:
            best_index = 0
            score = pre_scores[candidates[0]].total_score
        edge = candidates[best_index]
        final_timed_out = timed_out or time.perf_counter() >= deadline
        return EdgeMoveDecision(
            edge[0], edge[1], time.perf_counter() - started, final_timed_out, score,
            {**self._monte_extra(counts, sum(counts)), "move_unit": "edge_type"},
        )

    def _monte_extra(self, counts: list[int], total: int) -> dict[str, object]:
        return {
            "candidate_limit": self.candidate_limit,
            "playouts_per_move": self.playouts_per_move,
            "evaluated_playouts": total,
            "playout_counts": counts,
            "max_playout_moves": self.max_playout_moves,
            "max_playout_policy": "mobility_tiebreak",
            "playout_schedule": "round_robin",
        }

    def _playout_after_move(
        self,
        graph: WordGraph,
        state: GameState,
        word_id: int,
        deadline: float,
    ) -> float:
        if graph.end_chars[word_id] == "ん":
            return 0.0
        used = set(state.used_ids)
        used.add(word_id)
        current_char = graph.end_chars[word_id]
        player_to_move = 1
        for _turn in range(self.max_playout_moves):
            check_deadline(deadline)
            moves = graph.available_word_ids_set(current_char, used)
            if not moves:
                return 1.0 if player_to_move == 1 else 0.0
            safe = [candidate for candidate in moves if graph.end_chars[candidate] != "ん"]
            move = self.rng.choice(safe or moves)
            used.add(move)
            if graph.end_chars[move] == "ん":
                return 1.0 if player_to_move == 1 else 0.0
            current_char = graph.end_chars[move]
            player_to_move = 1 - player_to_move
        score = evaluate_word_position(
            graph, GameState(current_char, frozenset(used)), deadline, self.evaluation_config
        )
        side_rate = 0.5 + max(-0.4, min(0.4, score / 200.0))
        return 1.0 - side_rate if player_to_move == 1 else side_rate

    def _edge_playout_after_move(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        deadline: float,
    ) -> float:
        if edge_is_terminal(state, end_id):
            return 0.0
        initial_history_length = len(state.edge_history)
        state.apply_edge(start_id, end_id)
        player_to_move = 1
        try:
            for _turn in range(self.max_playout_moves):
                check_deadline(deadline)
                edges = state.available_edges()
                if not edges:
                    return 1.0 if player_to_move == 1 else 0.0
                safe = [edge for edge in edges if not edge_is_terminal(state, edge[1])]
                edge = weighted_edge_choice(state, safe or edges, self.rng)
                state.apply_edge(*edge)
                if edge_is_terminal(state, edge[1]):
                    return 1.0 if player_to_move == 1 else 0.0
                player_to_move = 1 - player_to_move
            score = _evaluate_edge_position(state, deadline, self.evaluation_config)
            side_rate = 0.5 + max(-0.4, min(0.4, score / 200.0))
            return 1.0 - side_rate if player_to_move == 1 else side_rate
        finally:
            while len(state.edge_history) > initial_history_length:
                state.undo_edge()


def build_agent(
    agent_name: str,
    time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
    random_seed: int = 0,
    minimax_depth: int = 3,
    alpha_beta_depth: int = 3,
    branch_limit: int | None = 12,
    monte_carlo_candidates: int = 20,
    monte_carlo_playouts: int = 10,
    monte_carlo_max_moves: int = 200,
    beam_negamax_depth: int = 4,
    beam_widths: Sequence[int] = DEFAULT_BEAM_WIDTHS,
    aggressive_pvs_depth: int = 3,
    adaptive_depth: bool = True,
    min_depth: int = 1,
    depth_recovery_turns: int = 5,
) -> BaseAgent:
    common = {"time_limit_sec": time_limit_sec, "random_seed": random_seed}
    search_common = {
        **common,
        "adaptive_depth": adaptive_depth,
        "min_depth": min_depth,
        "depth_recovery_turns": depth_recovery_turns,
    }
    if agent_name == "random":
        return RandomAgent(**common)
    if agent_name == "greedy":
        return GreedyAgent(**common)
    if agent_name == "minimax":
        return MinimaxAgent(
            **search_common, depth=minimax_depth, branch_limit=branch_limit
        )
    if agent_name == "alpha_beta":
        return AlphaBetaAgent(
            **search_common, depth=alpha_beta_depth, branch_limit=branch_limit
        )
    if agent_name == "beam_negamax":
        return BeamNegamaxAgent(
            **search_common, depth=beam_negamax_depth, beam_widths=beam_widths
        )
    if agent_name in {"pvs", "aggressive_pvs"}:
        agent_class = PVSAgent if agent_name == "pvs" else AggressivePVSAgent
        return agent_class(
            **search_common,
            depth=aggressive_pvs_depth,
            branch_limit=branch_limit,
        )
    if agent_name == "monte_carlo":
        return MonteCarloAgent(
            **common,
            candidate_limit=monte_carlo_candidates,
            playouts_per_move=monte_carlo_playouts,
            max_playout_moves=monte_carlo_max_moves,
        )
    raise ValueError(f"unknown agent: {agent_name}")
