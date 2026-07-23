"""Mutable edge-count states layered on top of an immutable RuntimeDictionary."""

from __future__ import annotations

from dataclasses import dataclass, field

from normalize import normalize_reading_with_reason
from runtime_dictionary import EdgeDictionary, RuntimeDictionary


@dataclass
class AIEdgeState:
    edge_dictionary: EdgeDictionary
    required_char_id: int | None
    edge_counts: list[int]
    active_end_masks: list[int]
    edge_history: list[tuple[int, int]] = field(default_factory=list)
    _required_history: list[int | None] = field(default_factory=list, repr=False)
    remaining_word_counts: list[int] = field(default_factory=list)
    remaining_safe_word_counts: list[int] = field(default_factory=list)
    active_edge_type_counts: list[int] = field(default_factory=list)
    active_safe_edge_type_counts: list[int] = field(default_factory=list)
    destination_masks: list[int] = field(default_factory=list)
    safe_destination_masks: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        char_count = self.edge_dictionary.char_count
        aggregate_lengths = (
            len(self.remaining_word_counts),
            len(self.remaining_safe_word_counts),
            len(self.active_edge_type_counts),
            len(self.active_safe_edge_type_counts),
            len(self.destination_masks),
            len(self.safe_destination_masks),
        )
        if aggregate_lengths == (char_count,) * 6:
            return
        if any(aggregate_lengths):
            raise ValueError("AIEdgeState aggregate arrays must all match char_count")
        (
            self.remaining_word_counts,
            self.remaining_safe_word_counts,
            self.active_edge_type_counts,
            self.active_safe_edge_type_counts,
            self.destination_masks,
            self.safe_destination_masks,
        ) = self._recalculate_aggregates()

    @classmethod
    def initial(cls, runtime: RuntimeDictionary | EdgeDictionary) -> "AIEdgeState":
        edge_dictionary = (
            runtime.to_edge_dictionary()
            if isinstance(runtime, RuntimeDictionary)
            else runtime
        )
        return cls(
            edge_dictionary=edge_dictionary,
            required_char_id=None,
            edge_counts=list(edge_dictionary.initial_edge_counts),
            active_end_masks=list(edge_dictionary.initial_active_end_masks),
        )

    def available_edges(self) -> list[tuple[int, int]]:
        if self.required_char_id is not None:
            return [
                (self.required_char_id, end_id)
                for end_id in self.edge_dictionary.available_end_ids(
                    self.required_char_id,
                    self.active_end_masks,
                )
            ]
        return [
            (start_id, end_id)
            for start_id in range(self.edge_dictionary.char_count)
            for end_id in self.edge_dictionary.available_end_ids(start_id, self.active_end_masks)
        ]

    def available_end_ids(self) -> list[int]:
        if self.required_char_id is not None:
            return self.edge_dictionary.available_end_ids(
                self.required_char_id,
                self.active_end_masks,
            )
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
            return sum(self.remaining_word_counts)
        return self.remaining_word_counts[self.required_char_id]

    def legal_end_count(self) -> int:
        return len(self.available_end_ids())

    def _recalculate_aggregates(
        self,
    ) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
        char_count = self.edge_dictionary.char_count
        n_id = self.edge_dictionary.char_to_id.get("ん")
        remaining_words = [0] * char_count
        remaining_safe_words = [0] * char_count
        active_edge_types = [0] * char_count
        active_safe_edge_types = [0] * char_count
        destination_masks = [0] * char_count
        safe_destination_masks = [0] * char_count
        for start_id in range(char_count):
            row_start = start_id * char_count
            for end_id in range(char_count):
                count = self.edge_counts[row_start + end_id]
                if count <= 0:
                    continue
                bit = 1 << end_id
                remaining_words[start_id] += count
                active_edge_types[start_id] += 1
                destination_masks[start_id] |= bit
                if end_id != n_id:
                    remaining_safe_words[start_id] += count
                    active_safe_edge_types[start_id] += 1
                    safe_destination_masks[start_id] |= bit
        return (
            remaining_words,
            remaining_safe_words,
            active_edge_types,
            active_safe_edge_types,
            destination_masks,
            safe_destination_masks,
        )

    def assert_aggregates_consistent(self) -> None:
        expected = self._recalculate_aggregates()
        actual = (
            self.remaining_word_counts,
            self.remaining_safe_word_counts,
            self.active_edge_type_counts,
            self.active_safe_edge_type_counts,
            self.destination_masks,
            self.safe_destination_masks,
        )
        if actual != expected:
            raise AssertionError("AIEdgeState aggregate values do not match edge_counts")
        if self.active_end_masks != self.destination_masks:
            raise AssertionError("active_end_masks and destination_masks differ")

    def apply_edge(self, start_id: int, end_id: int) -> None:
        if self.required_char_id is not None and start_id != self.required_char_id:
            raise ValueError(
                f"edge start_id={start_id} does not match required_char_id={self.required_char_id}"
            )
        edge_index = self.edge_dictionary.edge_index(start_id, end_id)
        old_count = self.edge_counts[edge_index]
        if old_count <= 0:
            raise ValueError(f"edge ({start_id}, {end_id}) has no remaining words")
        self._required_history.append(self.required_char_id)
        self.edge_counts[edge_index] = old_count - 1
        self.remaining_word_counts[start_id] -= 1
        n_id = self.edge_dictionary.char_to_id.get("ん")
        if end_id != n_id:
            self.remaining_safe_word_counts[start_id] -= 1
        if old_count == 1:
            bit = 1 << end_id
            self.active_edge_type_counts[start_id] -= 1
            self.destination_masks[start_id] &= ~bit
            self.active_end_masks[start_id] &= ~bit
            if end_id != n_id:
                self.active_safe_edge_type_counts[start_id] -= 1
                self.safe_destination_masks[start_id] &= ~bit
        self.edge_history.append((start_id, end_id))
        self.required_char_id = end_id

    def undo_edge(self) -> tuple[int, int]:
        if not self.edge_history:
            raise ValueError("cannot undo an empty edge history")
        start_id, end_id = self.edge_history.pop()
        edge_index = self.edge_dictionary.edge_index(start_id, end_id)
        old_count = self.edge_counts[edge_index]
        new_count = old_count + 1
        if new_count > self.edge_dictionary.initial_edge_counts[edge_index]:
            raise AssertionError("undo would exceed the initial edge count")
        self.edge_counts[edge_index] = new_count
        self.remaining_word_counts[start_id] += 1
        n_id = self.edge_dictionary.char_to_id.get("ん")
        if end_id != n_id:
            self.remaining_safe_word_counts[start_id] += 1
        if old_count == 0:
            bit = 1 << end_id
            self.active_edge_type_counts[start_id] += 1
            self.destination_masks[start_id] |= bit
            self.active_end_masks[start_id] |= bit
            if end_id != n_id:
                self.active_safe_edge_type_counts[start_id] += 1
                self.safe_destination_masks[start_id] |= bit
        self.required_char_id = self._required_history.pop()
        return start_id, end_id


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

    def edge_search_state(self) -> AIEdgeState:
        """Return an isolated word-free state for AI search."""

        return AIEdgeState(
            edge_dictionary=self.runtime.to_edge_dictionary(),
            required_char_id=self.required_char_id,
            edge_counts=list(self.edge_counts),
            active_end_masks=list(self.active_end_masks),
        )

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
