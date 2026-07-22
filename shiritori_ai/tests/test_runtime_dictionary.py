from __future__ import annotations

import csv
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

    def test_ranked_prefix_edge_dictionary_uses_only_prefix_words(self) -> None:
        prefix_size = 3
        prefix_edges = self.runtime.to_edge_dictionary(word_count=prefix_size)
        independently_built = RuntimeDictionary.from_readings(
            self.words[:prefix_size]
        ).to_edge_dictionary()

        self.assertEqual(prefix_edges.edge_instance_count, prefix_size)
        for start_char in independently_built.id_to_char:
            for end_char in independently_built.id_to_char:
                expected = independently_built.edge_count(
                    independently_built.char_to_id[start_char],
                    independently_built.char_to_id[end_char],
                )
                actual = prefix_edges.edge_count(
                    prefix_edges.char_to_id[start_char],
                    prefix_edges.char_to_id[end_char],
                )
                self.assertEqual(actual, expected)

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

    def test_word_and_edge_review_csvs_are_complete_and_stable(self) -> None:
        word_rows = self.runtime.word_view_rows()
        edge_rows = self.runtime.edge_view_rows()
        self.assertEqual(len(word_rows), self.runtime.word_count)
        self.assertEqual(sum(int(row["word_count"]) for row in edge_rows), self.runtime.word_count)
        self.assertEqual(
            [(row["start_id"], row["end_id"]) for row in edge_rows],
            sorted((row["start_id"], row["end_id"]) for row in edge_rows),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first_words = root / "first.words.csv"
            first_edges = root / "first.edges.csv"
            second_words = root / "second.words.csv"
            second_edges = root / "second.edges.csv"
            self.runtime.export_review_csvs(first_words, first_edges)
            self.runtime.export_review_csvs(second_words, second_edges)
            with first_words.open(encoding="utf-8", newline="") as source:
                saved_words = list(csv.DictReader(source))
            with first_edges.open(encoding="utf-8", newline="") as source:
                saved_edges = list(csv.DictReader(source))

            self.assertEqual(first_words.read_bytes(), second_words.read_bytes())
            self.assertEqual(first_edges.read_bytes(), second_edges.read_bytes())

        self.assertEqual(len(saved_words), self.runtime.word_count)
        self.assertEqual(sum(int(row["word_count"]) for row in saved_edges), self.runtime.word_count)
        first_edge_words = json.loads(saved_edges[0]["words"])
        first_edge_word_ids = json.loads(saved_edges[0]["word_ids"])
        self.assertEqual(
            first_edge_words,
            [self.runtime.word_readings[word_id] for word_id in first_edge_word_ids],
        )


if __name__ == "__main__":
    unittest.main()
