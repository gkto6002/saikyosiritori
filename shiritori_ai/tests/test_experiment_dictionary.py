from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiment_dictionary import (  # noqa: E402
    InsufficientCandidatesError,
    build_experiment_dictionaries,
    build_experiment_dictionaries_for_seeds,
    detail_records,
    parse_args,
    rank_noun_pool,
    select_ranked_records,
)
from game import WordGraph  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402


def record(
    reading: str,
    priority: int,
    pos_tags: list[str],
    *,
    entry_id: int,
) -> dict[str, object]:
    return {
        "normalized_reading": reading,
        "normalized_length": len(reading),
        "start_char": reading[0],
        "end_char": reading[-1],
        "ends_with_n": reading.endswith("ん"),
        "priority_level": priority,
        "priority_tags": [f"p{priority}"],
        "entry_ids": [entry_id],
        "pos_tags": pos_tags,
        "has_noun_sense": bool(set(pos_tags) & {"n", "n-adv", "n-t", "n-pref", "n-suf", "num", "pn"}),
    }


class ExperimentDictionaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.master = [
            record("あい", 3, ["n"], entry_id=1),
            record("いえ", 3, ["n", "v1"], entry_id=2),
            record("うみ", 3, ["n"], entry_id=3),
            record("えき", 3, ["n"], entry_id=4),
            record("おと", 3, ["n"], entry_id=5),
            record("かさ", 3, ["n"], entry_id=6),
            record("きもの", 2, ["n"], entry_id=7),
            record("くるま", 2, ["n"], entry_id=8),
            record("けん", 1, ["n"], entry_id=9),
            record("こえる", 3, ["v1"], entry_id=10),
        ]

    def test_nouns_and_mixed_senses_are_included_but_verb_only_is_excluded(self) -> None:
        ranked = rank_noun_pool(self.master, seed=0)
        readings = {str(item["normalized_reading"]) for item in ranked}
        self.assertIn("あい", readings)
        self.assertIn("いえ", readings)
        self.assertNotIn("こえる", readings)

    def test_length_boundary_deduplication_and_priority_order(self) -> None:
        ranked = rank_noun_pool(self.master, seed=0)
        selected, candidate_count = select_ranked_records(ranked, 7, 2, 2)
        self.assertEqual(candidate_count, 7)
        self.assertEqual(len(selected), 7)
        self.assertTrue(all(int(item["normalized_length"]) <= 2 for item in selected))
        self.assertNotIn("きもの", {item["normalized_reading"] for item in selected})
        levels = [int(item["priority_level"]) for item in selected]
        self.assertEqual(levels, sorted(levels, reverse=True))
        self.assertEqual(len({item["normalized_reading"] for item in selected}), len(selected))

    def test_seed_is_reproducible_and_changes_within_priority_group(self) -> None:
        first = [item["normalized_reading"] for item in rank_noun_pool(self.master, seed=7)]
        second = [item["normalized_reading"] for item in rank_noun_pool(self.master, seed=7)]
        other = [item["normalized_reading"] for item in rank_noun_pool(self.master, seed=8)]
        self.assertEqual(first, second)
        self.assertNotEqual(first[:6], other[:6])

    def test_size_prefixes_are_nested(self) -> None:
        ranked = rank_noun_pool(self.master, seed=3)
        small, _ = select_ranked_records(ranked, 3, 2, 5)
        large, _ = select_ranked_records(ranked, 7, 2, 5)
        self.assertEqual(
            [item["normalized_reading"] for item in small],
            [item["normalized_reading"] for item in large[:3]],
        )

    def test_shortage_requires_allow_smaller(self) -> None:
        ranked = rank_noun_pool(self.master, seed=0)
        with self.assertRaises(InsufficientCandidatesError) as raised:
            select_ranked_records(ranked, 20, 2, 5)
        self.assertEqual(raised.exception.candidate_count, 9)
        self.assertEqual(raised.exception.shortage_count, 11)
        selected, count = select_ranked_records(ranked, 20, 2, 5, allow_smaller=True)
        self.assertEqual(len(selected), count)

    def test_detail_word_ids_and_existing_word_graph_text_loader(self) -> None:
        ranked = rank_noun_pool(self.master, seed=0)
        selected, _ = select_ranked_records(ranked, 4, 2, 5)
        details = detail_records(selected)
        self.assertEqual([item["word_id"] for item in details], [0, 1, 2, 3])
        self.assertEqual(details[0]["source_entry_ids"], selected[0]["entry_ids"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "words.txt"
            path.write_text("".join(f"{item['normalized_reading']}\n" for item in details), encoding="utf-8")
            graph = WordGraph.from_text(path)
        self.assertEqual(graph.words, tuple(item["normalized_reading"] for item in details))

    def test_files_are_stable_and_batch_sizes_keep_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            master_path = root / "master.jsonl"
            master_path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in self.master),
                encoding="utf-8",
            )
            first_dir = root / "first"
            second_dir = root / "second"
            first = build_experiment_dictionaries(master_path, first_dir, [3, 6], [5], seed=4)
            second = build_experiment_dictionaries(master_path, second_dir, [3, 6], [5], seed=4)

            self.assertEqual(first[0].text_path.read_bytes(), second[0].text_path.read_bytes())
            self.assertEqual(first[0].details_path.read_bytes(), second[0].details_path.read_bytes())
            self.assertEqual(first[0].runtime_path.read_bytes(), second[0].runtime_path.read_bytes())
            self.assertEqual(first[0].words_csv_path.read_bytes(), second[0].words_csv_path.read_bytes())
            self.assertEqual(first[0].edges_csv_path.read_bytes(), second[0].edges_csv_path.read_bytes())
            small_words = first[0].text_path.read_text(encoding="utf-8").splitlines()
            large_words = first[1].text_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(small_words, large_words[:3])

    def test_runtime_and_review_views_are_generated_with_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            master_path = root / "master.jsonl"
            master_path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in self.master),
                encoding="utf-8",
            )
            artifact = build_experiment_dictionaries(
                master_path, root / "output", [6], [5], seed=0
            )[0]

            runtime = RuntimeDictionary.load(artifact.runtime_path)
            with artifact.words_csv_path.open(encoding="utf-8", newline="") as source:
                word_rows = list(csv.DictReader(source))
            with artifact.edges_csv_path.open(encoding="utf-8", newline="") as source:
                edge_rows = list(csv.DictReader(source))
            metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
            statistics = json.loads(artifact.statistics_path.read_text(encoding="utf-8"))

        self.assertEqual(runtime.word_count, artifact.actual_size)
        self.assertEqual(len(word_rows), runtime.word_count)
        self.assertEqual(sum(int(row["word_count"]) for row in edge_rows), runtime.word_count)
        self.assertEqual(metadata["runtime_file_name"], artifact.runtime_path.name)
        self.assertEqual(metadata["words_csv_file_name"], artifact.words_csv_path.name)
        self.assertEqual(metadata["edges_csv_file_name"], artifact.edges_csv_path.name)
        self.assertEqual(
            statistics["runtime_distinct_edge_type_count"],
            len(edge_rows),
        )

    def test_batch_seeds_generate_distinct_runtime_dictionaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            master_path = root / "master.jsonl"
            master_path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in self.master),
                encoding="utf-8",
            )
            artifacts = build_experiment_dictionaries_for_seeds(
                master_path,
                root / "output",
                sizes=[6],
                max_lengths=[5],
                seeds=[4, 5],
            )

            self.assertEqual(
                [item.dictionary_name for item in artifacts],
                ["D6_L2-5_seed4", "D6_L2-5_seed5"],
            )
            self.assertNotEqual(
                artifacts[0].text_path.read_bytes(),
                artifacts[1].text_path.read_bytes(),
            )
            self.assertTrue(all(item.runtime_path.is_file() for item in artifacts))

    def test_cli_accepts_multiple_seeds_and_preserves_seed_zero_default(self) -> None:
        batch = parse_args(
            [
                "--master",
                "master.jsonl",
                "--size",
                "50000",
                "--seeds",
                "0,1,2",
                "--output",
                "out",
            ]
        )
        self.assertEqual(batch.seeds, [0, 1, 2])

        default = parse_args(
            [
                "--master",
                "master.jsonl",
                "--size",
                "50000",
                "--output",
                "out",
            ]
        )
        self.assertEqual(default.seed, 0)


if __name__ == "__main__":
    unittest.main()
