from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dictionary_analysis import (  # noqa: E402
    analyze_dictionary,
    dictionary_size_comparison,
    length_limit_comparison,
    write_analysis_outputs,
)
from experiment_dictionary import detail_records, rank_noun_pool  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402


def master_record(reading: str, priority: int = 3) -> dict[str, object]:
    return {
        "normalized_reading": reading,
        "normalized_length": len(reading),
        "start_char": reading[0],
        "end_char": reading[-1],
        "ends_with_n": reading.endswith("ん"),
        "priority_level": priority,
        "priority_tags": [],
        "entry_ids": [],
        "has_noun_sense": True,
    }


class DictionaryAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.master = [
            master_record("あい", 3),
            master_record("いあ", 3),
            master_record("あん", 2),
            master_record("うえ", 1),
        ]
        self.details = detail_records(self.master)
        self.runtime = RuntimeDictionary.from_detail_records(self.details, dictionary_hash="known")
        self.analysis = analyze_dictionary(self.runtime, self.details)

    def test_distribution_totals_match_word_count(self) -> None:
        basic = self.analysis["basic_statistics"]
        self.assertEqual(sum(basic["normalized_length_word_counts"].values()), 4)
        self.assertEqual(sum(basic["start_char_word_counts"].values()), 4)
        self.assertEqual(sum(basic["end_char_word_counts"].values()), 4)
        graph = self.analysis["graph_statistics"]
        self.assertEqual(sum(row["outgoing_word_count"] for row in graph["char_degrees"]), 4)
        self.assertEqual(sum(row["incoming_word_count"] for row in graph["char_degrees"]), 4)

    def test_known_strong_and_weak_components(self) -> None:
        graph = self.analysis["graph_statistics"]
        self.assertEqual(graph["strong_component_count"], 4)
        self.assertEqual(graph["largest_strong_component_size"], 2)
        self.assertEqual(graph["weak_component_count"], 2)
        self.assertEqual(graph["largest_weak_component_size"], 3)
        self.assertEqual(graph["n_ending_edge_count"], 1)
        self.assertEqual(graph["non_n_ending_edge_count"], 3)

    def test_length_and_size_comparison_rows(self) -> None:
        expanded_master = self.master + [master_record("かきく", 1), master_record("さしすせ", 1)]
        ranked = rank_noun_pool(expanded_master, seed=0)
        length_rows = length_limit_comparison(ranked, 2, [2, 3, 4], requested_size=5)
        self.assertEqual([row["candidate_count"] for row in length_rows], [4, 5, 6])
        self.assertEqual(
            [row["can_generate_requested_size"] for row in length_rows],
            [False, True, True],
        )
        size_rows = dictionary_size_comparison(ranked, 2, 4, [2, 4, 6])
        self.assertTrue(all(row["contains_previous_dictionary"] for row in size_rows))

    def test_outputs_are_generated_and_json_is_stable(self) -> None:
        ranked = rank_noun_pool(self.master, seed=0)
        length_rows = length_limit_comparison(ranked, 2, [2], 3)
        size_rows = dictionary_size_comparison(ranked, 2, 2, [2, 4])
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first"
            second = Path(tmp_dir) / "second"
            first_paths = write_analysis_outputs(
                self.analysis,
                length_rows,
                size_rows,
                first,
                generate_plots=False,
            )
            second_paths = write_analysis_outputs(
                self.analysis,
                length_rows,
                size_rows,
                second,
                generate_plots=False,
            )
            self.assertTrue(all(path.is_file() for path in first_paths.values()))
            self.assertEqual(
                first_paths["detailed_statistics"].read_bytes(),
                second_paths["detailed_statistics"].read_bytes(),
            )
            self.assertGreater(len(first_paths["length_comparison"].read_text(encoding="utf-8").splitlines()), 1)
            self.assertGreater(len(first_paths["size_comparison"].read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
