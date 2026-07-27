"""Memoized edge-only complete solver for finite-dictionary shiritori."""

from __future__ import annotations

import time
from dataclasses import dataclass

from runtime_dictionary import EdgeDictionary


class AnalysisLimitExceeded(RuntimeError):
    """Raised when complete analysis exceeds a configured limit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FirstMoveResult:
    edge_index: int
    start_id: int
    end_id: int
    start_char: str
    end_char: str
    edge_count: int
    is_winning: bool
    opponent_reply_count: int
    searched_state_count_after_move: int

    @property
    def result(self) -> str:
        return "win" if self.is_winning else "lose"


class ShiritoriSolver:
    """Solve positions represented by (required_char_id, edge_usage_code)."""

    def __init__(
        self,
        edge_dictionary: EdgeDictionary,
        max_states: int | None = None,
        timeout_sec: float | None = None,
        move_ordering: str = "natural",
    ) -> None:
        if move_ordering not in {"natural", "opponent_mobility"}:
            raise ValueError(
                "move_ordering must be natural or opponent_mobility"
            )
        self.edge_dictionary = edge_dictionary
        self.max_states = max_states
        self.timeout_sec = timeout_sec
        self.move_ordering = move_ordering
        self.memo: dict[tuple[int, int], bool] = {}
        self.best_edge: dict[tuple[int, int], int | None] = {}
        self.searched_state_count = 0
        self.ordering_evaluation_count = 0
        self.last_first_move_results: list[FirstMoveResult] = []
        self._started_at: float | None = None

        edge_indices: list[int] = []
        edge_start_ids: list[int] = []
        edge_end_ids: list[int] = []
        capacities: list[int] = []
        edges_by_start: list[list[int]] = [
            [] for _ in range(edge_dictionary.char_count)
        ]
        for start_id in range(edge_dictionary.char_count):
            for end_id in range(edge_dictionary.char_count):
                edge_index = edge_dictionary.edge_index(start_id, end_id)
                capacity = edge_dictionary.initial_edge_counts[edge_index]
                if capacity <= 0:
                    continue
                compact_edge_id = len(edge_indices)
                edge_indices.append(edge_index)
                edge_start_ids.append(start_id)
                edge_end_ids.append(end_id)
                capacities.append(capacity)
                edges_by_start[start_id].append(compact_edge_id)

        multipliers: list[int] = []
        multiplier = 1
        for capacity in capacities:
            multipliers.append(multiplier)
            multiplier *= capacity + 1

        self.edge_indices = tuple(edge_indices)
        self.edge_start_ids = tuple(edge_start_ids)
        self.edge_end_ids = tuple(edge_end_ids)
        self.edge_capacities = tuple(capacities)
        self.edge_usage_multipliers = tuple(multipliers)
        self.edges_by_start = tuple(tuple(bucket) for bucket in edges_by_start)
        self.edge_type_count = len(edge_indices)
        self.terminal_char_id = edge_dictionary.char_to_id.get("ん")

    def reset_memo(self) -> None:
        self.memo.clear()
        self.best_edge.clear()
        self.searched_state_count = 0
        self.ordering_evaluation_count = 0
        self.last_first_move_results = []
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

    def _used_count(self, compact_edge_id: int, edge_usage_code: int) -> int:
        multiplier = self.edge_usage_multipliers[compact_edge_id]
        radix = self.edge_capacities[compact_edge_id] + 1
        return (edge_usage_code // multiplier) % radix

    def remaining_edge_count(self, compact_edge_id: int, edge_usage_code: int) -> int:
        return self.edge_capacities[compact_edge_id] - self._used_count(
            compact_edge_id,
            edge_usage_code,
        )

    def count_available_edge_instances(
        self,
        required_char_id: int,
        edge_usage_code: int,
    ) -> int:
        return sum(
            self.remaining_edge_count(compact_edge_id, edge_usage_code)
            for compact_edge_id in self.edges_by_start[required_char_id]
        )

    def _ordered_available_edges(
        self,
        required_char_id: int,
        edge_usage_code: int,
    ) -> list[int]:
        available = [
            compact_edge_id
            for compact_edge_id in self.edges_by_start[required_char_id]
            if self.remaining_edge_count(
                compact_edge_id, edge_usage_code
            )
            > 0
            and self.edge_end_ids[compact_edge_id]
            != self.terminal_char_id
        ]
        if self.move_ordering == "natural" or len(available) < 2:
            return available

        def mobility_key(compact_edge_id: int) -> tuple[int, int, int, int]:
            next_code = (
                edge_usage_code
                + self.edge_usage_multipliers[compact_edge_id]
            )
            end_id = self.edge_end_ids[compact_edge_id]
            safe_words = 0
            safe_types = 0
            all_words = 0
            for reply_id in self.edges_by_start[end_id]:
                remaining = self.remaining_edge_count(reply_id, next_code)
                if remaining <= 0:
                    continue
                all_words += remaining
                if self.edge_end_ids[reply_id] != self.terminal_char_id:
                    safe_words += remaining
                    safe_types += 1
            self.ordering_evaluation_count += 1
            return (
                safe_words,
                safe_types,
                all_words,
                self.edge_indices[compact_edge_id],
            )

        return sorted(available, key=mobility_key)

    def solve(self, required_char_id: int, edge_usage_code: int = 0) -> bool:
        """Return True if the player to move is winning from this position."""

        state = (required_char_id, edge_usage_code)
        if state in self.memo:
            return self.memo[state]

        self._check_limits()
        self.searched_state_count += 1

        for compact_edge_id in self._ordered_available_edges(
            required_char_id, edge_usage_code
        ):
            end_id = self.edge_end_ids[compact_edge_id]
            next_code = edge_usage_code + self.edge_usage_multipliers[compact_edge_id]
            opponent_is_winning = self.solve(end_id, next_code)
            if not opponent_is_winning:
                self.memo[state] = True
                self.best_edge[state] = self.edge_indices[compact_edge_id]
                return True

        self.memo[state] = False
        self.best_edge[state] = None
        return False

    def get_best_edge_index(
        self,
        required_char_id: int,
        edge_usage_code: int = 0,
    ) -> int | None:
        state = (required_char_id, edge_usage_code)
        if state not in self.memo:
            self.solve(required_char_id, edge_usage_code)
        return self.best_edge.get(state)

    def get_best_edge(
        self,
        required_char_id: int,
        edge_usage_code: int = 0,
    ) -> tuple[int, int] | None:
        edge_index = self.get_best_edge_index(required_char_id, edge_usage_code)
        if edge_index is None:
            return None
        return divmod(edge_index, self.edge_dictionary.char_count)

    def analyze_first_moves(
        self,
        reset_between_moves: bool = False,
        stop_on_first_win: bool = True,
    ) -> list[FirstMoveResult]:
        """Analyze first edges, stopping as soon as one winning edge is found."""

        results: list[FirstMoveResult] = []
        self.last_first_move_results = results
        for compact_edge_id, edge_index in enumerate(self.edge_indices):
            if reset_between_moves:
                self.reset_memo()
                self.last_first_move_results = results

            before_count = self.searched_state_count
            start_id = self.edge_start_ids[compact_edge_id]
            end_id = self.edge_end_ids[compact_edge_id]
            edge_usage_code = self.edge_usage_multipliers[compact_edge_id]

            if end_id == self.terminal_char_id:
                is_winning = False
                opponent_reply_count = 0
            else:
                opponent_is_winning = self.solve(end_id, edge_usage_code)
                is_winning = not opponent_is_winning
                opponent_reply_count = self.count_available_edge_instances(
                    end_id,
                    edge_usage_code,
                )

            if reset_between_moves:
                searched_after_move = self.searched_state_count
            else:
                searched_after_move = self.searched_state_count - before_count

            result = FirstMoveResult(
                edge_index=edge_index,
                start_id=start_id,
                end_id=end_id,
                start_char=self.edge_dictionary.id_to_char[start_id],
                end_char=self.edge_dictionary.id_to_char[end_id],
                edge_count=self.edge_capacities[compact_edge_id],
                is_winning=is_winning,
                opponent_reply_count=opponent_reply_count,
                searched_state_count_after_move=searched_after_move,
            )
            results.append(result)

            if stop_on_first_win and result.is_winning:
                break

        return results
