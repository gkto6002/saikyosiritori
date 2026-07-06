"""Memoized complete solver for small finite-dictionary shiritori."""

from __future__ import annotations

import time
from dataclasses import dataclass

from game import WordGraph


class AnalysisLimitExceeded(RuntimeError):
    """Raised when complete analysis exceeds a configured limit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FirstMoveResult:
    word: str
    word_id: int
    start_char: str
    end_char: str
    is_winning: bool
    opponent_reply_count: int
    searched_state_count_after_move: int

    @property
    def result(self) -> str:
        return "win" if self.is_winning else "lose"


class ShiritoriSolver:
    """Solve positions represented by (current_char, used_mask)."""

    def __init__(
        self,
        graph: WordGraph,
        max_states: int | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.graph = graph
        self.max_states = max_states
        self.timeout_sec = timeout_sec
        self.memo: dict[tuple[str, int], bool] = {}
        self.best_move: dict[tuple[str, int], int | None] = {}
        self.searched_state_count = 0
        self._started_at: float | None = None

    def reset_memo(self) -> None:
        self.memo.clear()
        self.best_move.clear()
        self.searched_state_count = 0
        self._started_at = None

    def count_states(self) -> int:
        return self.searched_state_count

    def _check_limits(self) -> None:
        if self._started_at is None:
            self._started_at = time.perf_counter()

        if self.max_states is not None and self.searched_state_count >= self.max_states:
            raise AnalysisLimitExceeded(f"max_states exceeded: {self.max_states}")

        if self.timeout_sec is not None:
            elapsed = time.perf_counter() - self._started_at
            if elapsed >= self.timeout_sec:
                raise AnalysisLimitExceeded(f"timeout exceeded: {self.timeout_sec} sec")

    def solve(self, current_char: str, used_mask: int) -> bool:
        """Return True if the player to move is winning from this position."""

        state = (current_char, used_mask)
        if state in self.memo:
            return self.memo[state]

        self._check_limits()
        self.searched_state_count += 1

        available_moves = self.graph.available_word_ids_mask(current_char, used_mask)
        if not available_moves:
            self.memo[state] = False
            self.best_move[state] = None
            return False

        for word_id in available_moves:
            end_char = self.graph.end_chars[word_id]
            if end_char == "ん":
                continue

            next_mask = used_mask | (1 << word_id)
            opponent_is_winning = self.solve(end_char, next_mask)
            if not opponent_is_winning:
                self.memo[state] = True
                self.best_move[state] = word_id
                return True

        self.memo[state] = False
        self.best_move[state] = None
        return False

    def get_best_move_index(self, current_char: str, used_mask: int) -> int | None:
        state = (current_char, used_mask)
        if state not in self.memo:
            self.solve(current_char, used_mask)
        return self.best_move.get(state)

    def get_best_move(self, current_char: str, used_mask: int) -> str | None:
        word_id = self.get_best_move_index(current_char, used_mask)
        if word_id is None:
            return None
        return self.graph.words[word_id]

    def analyze_first_moves(self, reset_between_moves: bool = False) -> list[FirstMoveResult]:
        """Analyze every word as a fixed first move."""

        results: list[FirstMoveResult] = []
        for word_id, word in enumerate(self.graph.words):
            if reset_between_moves:
                self.reset_memo()

            before_count = self.searched_state_count
            start_char = self.graph.start_chars[word_id]
            end_char = self.graph.end_chars[word_id]
            used_mask = 1 << word_id

            if end_char == "ん":
                is_winning = False
                opponent_reply_count = 0
            else:
                opponent_is_winning = self.solve(end_char, used_mask)
                is_winning = not opponent_is_winning
                opponent_reply_count = self.graph.count_available_words_mask(end_char, used_mask)

            if reset_between_moves:
                searched_after_move = self.searched_state_count
            else:
                searched_after_move = self.searched_state_count - before_count

            results.append(
                FirstMoveResult(
                    word=word,
                    word_id=word_id,
                    start_char=start_char,
                    end_char=end_char,
                    is_winning=is_winning,
                    opponent_reply_count=opponent_reply_count,
                    searched_state_count_after_move=searched_after_move,
                )
            )

        return results
