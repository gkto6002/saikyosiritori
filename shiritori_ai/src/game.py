"""Graph representation for finite-dictionary shiritori."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class WordGraph:
    words: tuple[str, ...]
    start_chars: tuple[str, ...]
    end_chars: tuple[str, ...]
    by_start: dict[str, tuple[int, ...]]

    @classmethod
    def from_words(cls, words: list[str] | tuple[str, ...]) -> "WordGraph":
        indexed_by_start: dict[str, list[int]] = defaultdict(list)
        start_chars: list[str] = []
        end_chars: list[str] = []

        for index, word in enumerate(words):
            if len(word) < 2:
                raise ValueError(f"word must contain at least two kana: {word!r}")
            start_char = normalize_game_char(word[0])
            end_char = normalize_game_char(word[-1])
            start_chars.append(start_char)
            end_chars.append(end_char)
            indexed_by_start[start_char].append(index)

        by_start = {char: tuple(indices) for char, indices in indexed_by_start.items()}
        return cls(tuple(words), tuple(start_chars), tuple(end_chars), by_start)

    @classmethod
    def from_csv(cls, path: str | Path) -> "WordGraph":
        return cls.from_words(load_words_from_csv(path))

    def subset(self, size: int) -> "WordGraph":
        if size < 0:
            raise ValueError("size must be non-negative")
        return WordGraph.from_words(list(self.words[:size]))

    def available_word_ids(self, current_char: str, used_mask: int) -> list[int]:
        return self.available_word_ids_mask(current_char, used_mask)

    def available_word_ids_mask(self, current_char: str, used_mask: int) -> list[int]:
        normalized_char = normalize_game_char(current_char)
        return [
            word_id
            for word_id in self.by_start.get(normalized_char, ())
            if not (used_mask & (1 << word_id))
        ]

    def available_word_ids_set(self, current_char: str, used_ids: set[int]) -> list[int]:
        normalized_char = normalize_game_char(current_char)
        return [
            word_id
            for word_id in self.by_start.get(normalized_char, ())
            if word_id not in used_ids
        ]

    def count_available_words_mask(self, current_char: str, used_mask: int) -> int:
        return len(self.available_word_ids_mask(current_char, used_mask))

    def count_available_words_set(self, current_char: str, used_ids: set[int]) -> int:
        return len(self.available_word_ids_set(current_char, used_ids))

    def count_available_words(self, current_char: str, used_mask: int) -> int:
        return self.count_available_words_mask(current_char, used_mask)

    def word_id_by_reading(self) -> dict[str, int]:
        return {word: index for index, word in enumerate(self.words)}

    def n_ending_word_count(self) -> int:
        return sum(1 for end_char in self.end_chars if end_char == "ん")

    def start_distribution(self) -> dict[str, int]:
        return _distribution(self.start_chars)

    def end_distribution(self) -> dict[str, int]:
        return _distribution(self.end_chars)


def _distribution(chars: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for char in chars:
        counts[char] += 1
    return dict(sorted(counts.items()))


def normalize_game_char(char: str) -> str:
    """Canonicalize equivalent kana for shiritori graph transitions."""

    return "お" if char == "を" else char


def load_words_from_csv(path: str | Path) -> list[str]:
    """Load a CSV file with a reading column."""

    with Path(path).open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            return []
        if "reading" not in reader.fieldnames:
            raise ValueError(f"CSV must contain a reading column: {path}")
        return [row["reading"] for row in reader if row.get("reading")]
