from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from runtime_dictionary import RuntimeDictionary  # noqa: E402


def details(words: list[str]) -> list[dict[str, object]]:
    return [
        {
            "word_id": word_id,
            "normalized_reading": word,
            "normalized_length": len(word),
            "start_char": word[0],
            "end_char": word[-1],
            "ends_with_n": word.endswith("ん"),
        }
        for word_id, word in enumerate(words)
    ]


class RuntimeDictionaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.words = ["あい", "あん", "いあ", "おし", "をし", "しお"]
        self.runtime = RuntimeDictionary.from_detail_records(details(self.words), dictionary_hash="test")

    def test_character_ids_are_sorted_and_game_normalized(self) -> None:
        self.assertEqual(self.runtime.id_to_char, tuple(sorted(self.runtime.id_to_char)))
        self.assertNotIn("を", self.runtime.char_to_id)
        self.assertEqual(
            self.runtime.word_start_ids[self.words.index("をし")],
            self.runtime.char_to_id["お"],
        )

    def test_every_word_belongs_to_one_bucket_and_edge_totals_match(self) -> None:
        self.assertEqual(sum(self.runtime.initial_edge_counts), self.runtime.word_count)
        bucketed = [
            word_id
            for start_id in range(self.runtime.char_count)
            for end_id in range(self.runtime.char_count)
            for word_id in self.runtime.bucket(start_id, end_id)
        ]
        self.assertEqual(sorted(bucketed), list(range(self.runtime.word_count)))
        for start_id in range(self.runtime.char_count):
            for end_id in range(self.runtime.char_count):
                self.assertEqual(
                    len(self.runtime.bucket(start_id, end_id)),
                    self.runtime.edge_count(start_id, end_id),
                )

    def test_available_end_ids_and_active_masks(self) -> None:
        start_id = self.runtime.char_to_id["あ"]
        expected = {self.runtime.char_to_id["い"], self.runtime.char_to_id["ん"]}
        self.assertEqual(set(self.runtime.available_end_ids(start_id)), expected)
        mask = self.runtime.initial_active_end_masks[start_id]
        self.assertEqual({index for index in range(self.runtime.char_count) if mask & (1 << index)}, expected)

    def test_empty_and_n_ending_buckets(self) -> None:
        a_id = self.runtime.char_to_id["あ"]
        n_id = self.runtime.char_to_id["ん"]
        self.assertEqual(self.runtime.bucket(a_id, n_id), (1,))
        self.assertEqual(self.runtime.bucket(n_id, a_id), ())

    def test_old_word_graph_has_identical_counts(self) -> None:
        comparison = self.runtime.compare_word_graph(self.runtime.to_word_graph())
        self.assertTrue(all(comparison.values()), comparison)

    def test_serialization_is_stable(self) -> None:
        second = RuntimeDictionary.from_detail_records(details(self.words), dictionary_hash="test")
        self.assertEqual(self.runtime.to_dict(), second.to_dict())
        with tempfile.TemporaryDirectory() as tmp_dir:
            first_path = Path(tmp_dir) / "first.json"
            second_path = Path(tmp_dir) / "second.json"
            self.runtime.save(first_path)
            second.save(second_path)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            loaded = RuntimeDictionary.load(first_path)
        self.assertEqual(loaded, self.runtime)

    def test_details_jsonl_preserves_word_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "details.jsonl"
            path.write_text(
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in details(self.words)),
                encoding="utf-8",
            )
            loaded = RuntimeDictionary.from_details_jsonl(path)
        self.assertEqual(loaded.word_readings, tuple(self.words))
        self.assertEqual(loaded.word_to_id, {word: word_id for word_id, word in enumerate(self.words)})


if __name__ == "__main__":
    unittest.main()
