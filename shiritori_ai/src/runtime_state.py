"""Mutable edge-count states layered on top of an immutable RuntimeDictionary."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents import BaseAgent, GameState, MoveDecision
from normalize import normalize_reading_with_reason
from runtime_dictionary import RuntimeDictionary


@dataclass
class AIEdgeState:
    runtime: RuntimeDictionary
    required_char_id: int | None
    edge_counts: list[int]
    active_end_masks: list[int]
    edge_history: list[tuple[int, int]] = field(default_factory=list)
    _required_history: list[int | None] = field(default_factory=list, repr=False)

    @classmethod
    def initial(cls, runtime: RuntimeDictionary) -> "AIEdgeState":
        return cls(
            runtime=runtime,
            required_char_id=None,
            edge_counts=list(runtime.initial_edge_counts),
            active_end_masks=list(runtime.initial_active_end_masks),
        )

    def available_edges(self) -> list[tuple[int, int]]:
        if self.required_char_id is not None:
            return [
                (self.required_char_id, end_id)
                for end_id in self.runtime.available_end_ids(
                    self.required_char_id,
                    self.active_end_masks,
                )
            ]
        return [
            (start_id, end_id)
            for start_id in range(self.runtime.char_count)
            for end_id in self.runtime.available_end_ids(start_id, self.active_end_masks)
        ]

    def available_end_ids(self) -> list[int]:
        if self.required_char_id is not None:
            return self.runtime.available_end_ids(self.required_char_id, self.active_end_masks)
        mask = 0
        for start_mask in self.active_end_masks:
            mask |= start_mask
        result: list[int] = []
        while mask:
            least_bit = mask & -mask
            result.append(least_bit.bit_length() - 1)
            mask ^= least_bit
        return result

    def legal_word_count(self) -> int:
        if self.required_char_id is None:
            return sum(self.edge_counts)
        row_start = self.required_char_id * self.runtime.char_count
        return sum(self.edge_counts[row_start : row_start + self.runtime.char_count])

    def legal_end_count(self) -> int:
        return len(self.available_end_ids())

    def apply_edge(self, start_id: int, end_id: int) -> None:
        if self.required_char_id is not None and start_id != self.required_char_id:
            raise ValueError(
                f"edge start_id={start_id} does not match required_char_id={self.required_char_id}"
            )
        edge_index = self.runtime.edge_index(start_id, end_id)
        if self.edge_counts[edge_index] <= 0:
            raise ValueError(f"edge ({start_id}, {end_id}) has no remaining words")
        self._required_history.append(self.required_char_id)
        self.edge_counts[edge_index] -= 1
        if self.edge_counts[edge_index] == 0:
            self.active_end_masks[start_id] &= ~(1 << end_id)
        self.edge_history.append((start_id, end_id))
        self.required_char_id = end_id

    def undo_edge(self) -> tuple[int, int]:
        if not self.edge_history:
            raise ValueError("cannot undo an empty edge history")
        start_id, end_id = self.edge_history.pop()
        edge_index = self.runtime.edge_index(start_id, end_id)
        was_zero = self.edge_counts[edge_index] == 0
        self.edge_counts[edge_index] += 1
        if self.edge_counts[edge_index] > self.runtime.initial_edge_counts[edge_index]:
            raise AssertionError("undo would exceed the initial edge count")
        if was_zero:
            self.active_end_masks[start_id] |= 1 << end_id
        self.required_char_id = self._required_history.pop()
        return start_id, end_id

    def materialized_word_ids(self) -> list[int]:
        return assign_words_to_edge_history(self.runtime, self.edge_history)


def assign_words_to_edge_history(
    runtime: RuntimeDictionary,
    edge_history: list[tuple[int, int]],
) -> list[int]:
    cursors: dict[int, int] = {}
    assigned: list[int] = []
    for start_id, end_id in edge_history:
        edge_index = runtime.edge_index(start_id, end_id)
        cursor = cursors.get(edge_index, 0)
        bucket = runtime.bucket(start_id, end_id)
        if cursor >= len(bucket):
            raise ValueError(f"edge history exceeds bucket size for ({start_id}, {end_id})")
        assigned.append(bucket[cursor])
        cursors[edge_index] = cursor + 1
    return assigned


@dataclass(frozen=True)
class HumanMoveResult:
    word_id: int | None
    normalized_reading: str | None
    error_code: str | None
    message: str | None

    @property
    def accepted(self) -> bool:
        return self.word_id is not None


@dataclass
class HumanRuntimeState:
    runtime: RuntimeDictionary
    required_char_id: int | None
    edge_counts: list[int]
    active_end_masks: list[int]
    used_word_ids: set[int]
    bucket_cursors: list[int]
    word_history: list[int]

    @classmethod
    def initial(cls, runtime: RuntimeDictionary) -> "HumanRuntimeState":
        return cls(
            runtime=runtime,
            required_char_id=None,
            edge_counts=list(runtime.initial_edge_counts),
            active_end_masks=list(runtime.initial_active_end_masks),
            used_word_ids=set(),
            bucket_cursors=[0] * (runtime.char_count * runtime.char_count),
            word_history=[],
        )

    def submit_human_reading(self, raw_reading: str) -> HumanMoveResult:
        normalization = normalize_reading_with_reason(raw_reading)
        if not normalization.succeeded:
            return HumanMoveResult(
                None,
                None,
                normalization.failure_reason,
                f"読みを正規化できません: {normalization.failure_reason}",
            )
        normalized = normalization.normalized
        assert normalized is not None
        word_id = self.runtime.word_to_id.get(normalized)
        if word_id is None:
            return HumanMoveResult(None, normalized, "not_in_dictionary", "辞書に存在しません")
        if word_id in self.used_word_ids:
            return HumanMoveResult(None, normalized, "already_used", "すでに使用済みです")
        start_id = self.runtime.word_start_ids[word_id]
        if self.required_char_id is not None and start_id != self.required_char_id:
            required = self.runtime.id_to_char[self.required_char_id]
            return HumanMoveResult(
                None,
                normalized,
                "wrong_start_char",
                f"現在の文字「{required}」から始まっていません",
            )
        self.apply_word_id(word_id)
        return HumanMoveResult(word_id, normalized, None, None)

    def apply_word_id(self, word_id: int) -> None:
        if word_id < 0 or word_id >= self.runtime.word_count:
            raise IndexError(f"word_id out of range: {word_id}")
        if word_id in self.used_word_ids:
            raise ValueError(f"word_id={word_id} is already used")
        start_id = self.runtime.word_start_ids[word_id]
        end_id = self.runtime.word_end_ids[word_id]
        if self.required_char_id is not None and start_id != self.required_char_id:
            raise ValueError("word does not start with the required character")
        edge_index = self.runtime.edge_index(start_id, end_id)
        if self.edge_counts[edge_index] <= 0:
            raise AssertionError("edge count is already zero for an unused word")
        self.used_word_ids.add(word_id)
        self.word_history.append(word_id)
        self.edge_counts[edge_index] -= 1
        if self.edge_counts[edge_index] == 0:
            self.active_end_masks[start_id] &= ~(1 << end_id)
        self.required_char_id = end_id

    def choose_ai_word(self, start_id: int, end_id: int) -> int:
        if self.required_char_id is not None and start_id != self.required_char_id:
            raise ValueError("AI edge does not start with the required character")
        edge_index = self.runtime.edge_index(start_id, end_id)
        if self.edge_counts[edge_index] <= 0:
            raise ValueError("AI edge has no remaining words")
        bucket = self.runtime.bucket(start_id, end_id)
        cursor = self.bucket_cursors[edge_index]
        while cursor < len(bucket) and bucket[cursor] in self.used_word_ids:
            cursor += 1
        if cursor >= len(bucket):
            raise AssertionError("edge count indicates a word remains, but the bucket is exhausted")
        word_id = bucket[cursor]
        self.bucket_cursors[edge_index] = cursor + 1
        self.apply_word_id(word_id)
        return word_id

    def assert_consistent(self) -> None:
        for start_id in range(self.runtime.char_count):
            expected_mask = 0
            for end_id in range(self.runtime.char_count):
                edge_index = self.runtime.edge_index(start_id, end_id)
                unused = sum(
                    word_id not in self.used_word_ids
                    for word_id in self.runtime.bucket(start_id, end_id)
                )
                if self.edge_counts[edge_index] != unused:
                    raise AssertionError(
                        f"edge ({start_id}, {end_id}) count={self.edge_counts[edge_index]} unused={unused}"
                    )
                if unused:
                    expected_mask |= 1 << end_id
            if self.active_end_masks[start_id] != expected_mask:
                raise AssertionError(f"active end mask mismatch for start_id={start_id}")
        if len(self.used_word_ids) != len(self.word_history):
            raise AssertionError("word history and used set have different sizes")


@dataclass(frozen=True)
class RuntimeEdgeDecision:
    start_id: int | None
    end_id: int | None
    move_decision: MoveDecision


class RuntimeAgentAdapter:
    """Call an unchanged word-ID agent from an edge-count AI state."""

    def __init__(self, runtime: RuntimeDictionary) -> None:
        self.runtime = runtime
        self.graph = runtime.to_word_graph()

    def choose_edge(self, agent: BaseAgent, state: AIEdgeState) -> RuntimeEdgeDecision:
        used_word_ids = frozenset(state.materialized_word_ids())
        current_char = (
            None
            if state.required_char_id is None
            else self.runtime.id_to_char[state.required_char_id]
        )
        decision = agent.choose_move(
            self.graph,
            GameState(current_char=current_char, used_ids=used_word_ids),
        )
        if decision.word_id is None:
            return RuntimeEdgeDecision(None, None, decision)
        word_id = decision.word_id
        if word_id in used_word_ids:
            return RuntimeEdgeDecision(None, None, decision)
        start_id = self.runtime.word_start_ids[word_id]
        end_id = self.runtime.word_end_ids[word_id]
        if state.required_char_id is not None and start_id != state.required_char_id:
            return RuntimeEdgeDecision(None, None, decision)
        if state.edge_counts[self.runtime.edge_index(start_id, end_id)] <= 0:
            return RuntimeEdgeDecision(None, None, decision)
        return RuntimeEdgeDecision(start_id, end_id, decision)
