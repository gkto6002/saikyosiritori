"""Approximate shiritori AIs for large dictionaries."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from game import WordGraph


LOSS_SCORE = -1_000_000.0
WIN_SCORE = 1_000_000.0


@dataclass(frozen=True)
class GameState:
    current_char: str | None
    used_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class MoveDecision:
    word_id: int | None
    elapsed_time_sec: float
    timed_out: bool
    score: float
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    name = "base"

    def __init__(self, time_limit_sec: float = 0.5, random_seed: int = 0) -> None:
        self.time_limit_sec = time_limit_sec
        self.rng = random.Random(random_seed)

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        raise NotImplementedError

    def legal_moves(self, graph: WordGraph, state: GameState) -> list[int]:
        if state.current_char is None:
            return [word_id for word_id in range(len(graph.words)) if word_id not in state.used_ids]
        return graph.available_word_ids_set(state.current_char, set(state.used_ids))

    def fallback_move(self, graph: WordGraph, state: GameState) -> int | None:
        moves = self.legal_moves(graph, state)
        if not moves:
            return None
        return greedy_ordered_moves(graph, state, moves)[0]

    def _deadline(self) -> float:
        return time.perf_counter() + self.time_limit_sec


def greedy_move_score(graph: WordGraph, state: GameState, word_id: int) -> float:
    end_char = graph.end_chars[word_id]
    if end_char == "ん":
        return LOSS_SCORE

    used = set(state.used_ids)
    used.add(word_id)
    opponent_reply_count = graph.count_available_words_set(end_char, used)
    if opponent_reply_count == 0:
        return WIN_SCORE

    next_safe_count = sum(
        1
        for reply_id in graph.available_word_ids_set(end_char, used)
        if graph.end_chars[reply_id] != "ん"
    )
    return -opponent_reply_count * 10.0 + (opponent_reply_count - next_safe_count)


def greedy_ordered_moves(graph: WordGraph, state: GameState, moves: list[int]) -> list[int]:
    return sorted(
        moves,
        key=lambda word_id: (
            -greedy_move_score(graph, state, word_id),
            graph.words[word_id],
        ),
    )


def greedy_ordered_moves_until_deadline(
    graph: WordGraph,
    state: GameState,
    moves: list[int],
    deadline: float,
    limit: int | None = None,
) -> tuple[list[int], bool]:
    scored_moves: list[tuple[float, str, int]] = []
    timed_out = False
    for word_id in moves:
        if time.perf_counter() >= deadline:
            timed_out = True
            break
        scored_moves.append((greedy_move_score(graph, state, word_id), graph.words[word_id], word_id))

    scored_moves.sort(key=lambda item: (-item[0], item[1]))
    ordered = [word_id for _score, _word, word_id in scored_moves]
    if limit is not None:
        ordered = ordered[:limit]
    return ordered, timed_out or time.perf_counter() >= deadline


def evaluate_position(graph: WordGraph, state: GameState, deadline: float | None = None) -> float:
    moves = BaseAgent().legal_moves(graph, state)
    if not moves:
        return LOSS_SCORE

    best_greedy = LOSS_SCORE
    current_mobility = 0
    total_mobility = 0
    timed_out = False
    for word_id in moves:
        if deadline is not None and time.perf_counter() >= deadline:
            timed_out = True
            break
        total_mobility += 1
        if graph.end_chars[word_id] == "ん":
            continue
        current_mobility += 1
        best_greedy = max(best_greedy, greedy_move_score(graph, state, word_id))

    if current_mobility == 0:
        if timed_out and total_mobility:
            return 0.0
        return LOSS_SCORE / 2

    return best_greedy + current_mobility * 3.0 + total_mobility


class RandomAgent(BaseAgent):
    name = "random"

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)

        safe_moves = [word_id for word_id in moves if graph.end_chars[word_id] != "ん"]
        candidates = safe_moves or moves
        word_id = self.rng.choice(candidates)
        return MoveDecision(
            word_id=word_id,
            elapsed_time_sec=time.perf_counter() - started,
            timed_out=False,
            score=0.0,
        )


class GreedyAgent(BaseAgent):
    name = "greedy"

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)

        best_move = moves[0]
        best_score = -math.inf
        evaluated = 0
        timed_out = False
        for word_id in moves:
            if time.perf_counter() >= deadline:
                timed_out = True
                break
            score = greedy_move_score(graph, state, word_id)
            evaluated += 1
            if score > best_score:
                best_score = score
                best_move = word_id

        if best_score == -math.inf:
            best_score = 0.0
            safe_moves = [word_id for word_id in moves if graph.end_chars[word_id] != "ん"]
            best_move = self.rng.choice(safe_moves or moves)

        return MoveDecision(
            word_id=best_move,
            elapsed_time_sec=time.perf_counter() - started,
            timed_out=timed_out or time.perf_counter() >= deadline,
            score=best_score,
            extra={"evaluated_moves": evaluated},
        )


class MinimaxAgent(BaseAgent):
    name = "minimax"

    def __init__(
        self,
        time_limit_sec: float = 0.5,
        random_seed: int = 0,
        depth: int = 3,
        branch_limit: int = 20,
    ) -> None:
        super().__init__(time_limit_sec=time_limit_sec, random_seed=random_seed)
        self.depth = depth
        self.branch_limit = branch_limit

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)

        ordered, ordering_timed_out = greedy_ordered_moves_until_deadline(
            graph,
            state,
            moves,
            deadline,
            limit=self.branch_limit,
        )
        if not ordered:
            fallback = self.rng.choice(moves)
            return MoveDecision(
                word_id=fallback,
                elapsed_time_sec=time.perf_counter() - started,
                timed_out=True,
                score=greedy_move_score(graph, state, fallback),
                extra={"evaluated_moves": 0, "depth": self.depth, "branch_limit": self.branch_limit},
            )
        best_move = ordered[0]
        best_score = LOSS_SCORE
        evaluated = 0
        timed_out = ordering_timed_out

        for word_id in ordered:
            if time.perf_counter() >= deadline:
                timed_out = True
                break
            score = self._score_move(graph, state, word_id, self.depth, deadline)
            evaluated += 1
            if score > best_score:
                best_score = score
                best_move = word_id

        return MoveDecision(
            word_id=best_move,
            elapsed_time_sec=time.perf_counter() - started,
            timed_out=timed_out or time.perf_counter() >= deadline,
            score=best_score,
            extra={"evaluated_moves": evaluated, "depth": self.depth, "branch_limit": self.branch_limit},
        )

    def _score_move(
        self,
        graph: WordGraph,
        state: GameState,
        word_id: int,
        depth: int,
        deadline: float,
    ) -> float:
        end_char = graph.end_chars[word_id]
        if end_char == "ん":
            return LOSS_SCORE
        next_used = frozenset(set(state.used_ids) | {word_id})
        next_state = GameState(current_char=end_char, used_ids=next_used)
        return -self._negamax(graph, next_state, depth - 1, deadline)

    def _negamax(self, graph: WordGraph, state: GameState, depth: int, deadline: float) -> float:
        if time.perf_counter() >= deadline:
            return 0.0

        moves = self.legal_moves(graph, state)
        if not moves:
            return LOSS_SCORE
        if depth <= 0:
            return evaluate_position(graph, state, deadline)

        ordered, _timed_out = greedy_ordered_moves_until_deadline(
            graph,
            state,
            moves,
            deadline,
            limit=self.branch_limit,
        )
        if not ordered:
            return evaluate_position(graph, state, deadline)
        best = LOSS_SCORE
        for word_id in ordered:
            end_char = graph.end_chars[word_id]
            if end_char == "ん":
                score = LOSS_SCORE
            else:
                next_used = frozenset(set(state.used_ids) | {word_id})
                score = -self._negamax(
                    graph,
                    GameState(current_char=end_char, used_ids=next_used),
                    depth - 1,
                    deadline,
                )
            best = max(best, score)
            if best >= WIN_SCORE:
                break
        return best


class MonteCarloAgent(BaseAgent):
    name = "monte_carlo"

    def __init__(
        self,
        time_limit_sec: float = 0.5,
        random_seed: int = 0,
        candidate_limit: int = 20,
        playouts_per_move: int = 10,
        max_playout_moves: int = 200,
    ) -> None:
        super().__init__(time_limit_sec=time_limit_sec, random_seed=random_seed)
        self.candidate_limit = candidate_limit
        self.playouts_per_move = playouts_per_move
        self.max_playout_moves = max_playout_moves

    def choose_move(self, graph: WordGraph, state: GameState) -> MoveDecision:
        started = time.perf_counter()
        deadline = self._deadline()
        moves = self.legal_moves(graph, state)
        if not moves:
            return MoveDecision(None, time.perf_counter() - started, False, LOSS_SCORE)

        candidates, ordering_timed_out = greedy_ordered_moves_until_deadline(
            graph,
            state,
            moves,
            deadline,
            limit=self.candidate_limit,
        )
        if not candidates:
            fallback = self.rng.choice(moves)
            return MoveDecision(
                word_id=fallback,
                elapsed_time_sec=time.perf_counter() - started,
                timed_out=True,
                score=greedy_move_score(graph, state, fallback),
                extra={
                    "candidate_limit": self.candidate_limit,
                    "playouts_per_move": self.playouts_per_move,
                    "evaluated_playouts": 0,
                    "max_playout_moves": self.max_playout_moves,
                    "max_playout_policy": "mobility_tiebreak",
                },
            )
        best_move = candidates[0]
        best_score = -math.inf
        evaluated_playouts = 0
        timed_out = ordering_timed_out

        for word_id in candidates:
            wins = 0.0
            playouts = 0
            for _index in range(self.playouts_per_move):
                if time.perf_counter() >= deadline:
                    timed_out = True
                    break
                wins += self._playout_after_move(graph, state, word_id)
                playouts += 1
                evaluated_playouts += 1
            if playouts:
                score = wins / playouts
                if score > best_score:
                    best_score = score
                    best_move = word_id
            if timed_out:
                break

        if best_score == -math.inf:
            best_score = greedy_move_score(graph, state, best_move)

        return MoveDecision(
            word_id=best_move,
            elapsed_time_sec=time.perf_counter() - started,
            timed_out=timed_out or time.perf_counter() >= deadline,
            score=best_score,
            extra={
                "candidate_limit": self.candidate_limit,
                "playouts_per_move": self.playouts_per_move,
                "evaluated_playouts": evaluated_playouts,
                "max_playout_moves": self.max_playout_moves,
                "max_playout_policy": "mobility_tiebreak",
            },
        )

    def _playout_after_move(self, graph: WordGraph, state: GameState, word_id: int) -> float:
        if graph.end_chars[word_id] == "ん":
            return 0.0

        used = set(state.used_ids)
        used.add(word_id)
        current_char = graph.end_chars[word_id]
        player_to_move = 1

        for _turn in range(self.max_playout_moves):
            moves = graph.available_word_ids_set(current_char, used)
            if not moves:
                return 1.0 if player_to_move == 1 else 0.0

            safe_moves = [candidate for candidate in moves if graph.end_chars[candidate] != "ん"]
            candidates = safe_moves or moves
            move = self.rng.choice(candidates)
            used.add(move)
            if graph.end_chars[move] == "ん":
                return 1.0 if player_to_move == 1 else 0.0

            current_char = graph.end_chars[move]
            player_to_move = 1 - player_to_move

        # Draw-like cutoff: decide by mobility from the side to move.
        current_mobility = len(graph.available_word_ids_set(current_char, used))
        return 0.5 if current_mobility else (1.0 if player_to_move == 1 else 0.0)


def build_agent(
    agent_name: str,
    time_limit_sec: float = 0.5,
    random_seed: int = 0,
    minimax_depth: int = 3,
    branch_limit: int = 20,
    monte_carlo_candidates: int = 20,
    monte_carlo_playouts: int = 10,
    monte_carlo_max_moves: int = 200,
) -> BaseAgent:
    if agent_name == "random":
        return RandomAgent(time_limit_sec=time_limit_sec, random_seed=random_seed)
    if agent_name == "greedy":
        return GreedyAgent(time_limit_sec=time_limit_sec, random_seed=random_seed)
    if agent_name == "minimax":
        return MinimaxAgent(
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            depth=minimax_depth,
            branch_limit=branch_limit,
        )
    if agent_name == "monte_carlo":
        return MonteCarloAgent(
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            candidate_limit=monte_carlo_candidates,
            playouts_per_move=monte_carlo_playouts,
            max_playout_moves=monte_carlo_max_moves,
        )
    raise ValueError(f"unknown agent: {agent_name}")
