from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "jmdict_master_fixture.xml"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from master_dictionary import build_master_dictionary, generate_master_records, run_cli  # noqa: E402
from jmdict_tags import has_noun_tag  # noqa: E402


class MasterDictionaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records, cls.statistics = generate_master_records(FIXTURE)
        cls.by_reading = {record["normalized_reading"]: record for record in cls.records}

    def test_normalization_lengths_and_boundaries(self) -> None:
        game = self.by_reading["げえむ"]
        self.assertEqual(game["normalized_length"], 3)
        self.assertEqual(game["original_reading_lengths"], {"ゲーム": 4})
        self.assertEqual(game["start_char"], "げ")
        self.assertEqual(game["end_char"], "む")
        self.assertTrue(game["has_specialized_sense"])

        self.assertIn("きやく", self.by_reading)
        self.assertIn("いえじずぶ", self.by_reading)
        self.assertTrue(self.by_reading["みかん"]["ends_with_n"])
        self.assertEqual(self.by_reading["みかん"]["end_char"], "ん")
        self.assertNotIn("abc", self.by_reading)

    def test_duplicate_merge_preserves_sources_and_priorities(self) -> None:
        leader = self.by_reading["りいだあ"]
        self.assertEqual(leader["entry_ids"], [100, 101])
        self.assertEqual(leader["original_readings"], ["りいだあ", "リーダー"])
        self.assertEqual(leader["spellings"], ["指導者"])
        self.assertEqual(leader["priority_tags"], ["news1", "nf08", "nf11"])
        self.assertEqual(leader["priority_level"], 3)
        self.assertEqual(leader["reading_info_tags"], ["gikun"])
        self.assertEqual(leader["kanji_info_tags"], ["iK"])
        self.assertEqual({source["entry_id"] for source in leader["sources"]}, {100, 101})

    def test_reading_and_sense_restrictions_are_applied(self) -> None:
        today = self.by_reading["きよう"]
        morning = self.by_reading["けさ"]

        self.assertEqual(today["spellings"], ["今日"])
        self.assertEqual(morning["spellings"], ["今朝"])
        self.assertEqual(today["pos_tags"], ["n"])
        self.assertEqual(morning["pos_tags"], ["adj-na"])
        self.assertTrue(today["has_archaic_sense"])
        self.assertFalse(morning["has_archaic_sense"])

        today_senses = today["applicable_senses"]
        self.assertEqual([sense["sense_number"] for sense in today_senses], [1, 2])
        self.assertTrue(all(sense["reading"] == "きょう" for sense in today_senses))
        self.assertTrue(all(sense["pos_tags"] == ["n"] for sense in today_senses))
        self.assertTrue(all(sense["applicable_spellings"] == ["今日"] for sense in today_senses))

        morning_senses = morning["applicable_senses"]
        self.assertEqual([sense["sense_number"] for sense in morning_senses], [3])
        self.assertEqual(morning_senses[0]["applicable_spellings"], ["今朝"])

    def test_derived_classifications_use_only_applicable_senses(self) -> None:
        variant = self.by_reading["いえじずぶ"]
        self.assertTrue(variant["has_verb_sense"])
        self.assertTrue(variant["has_obsolete_sense"])
        self.assertTrue(variant["has_rare_sense"])
        self.assertTrue(variant["has_dialect_sense"])
        self.assertEqual(variant["dialect_tags"], ["ksb"])

        tokyo = self.by_reading["とうきよう"]
        self.assertTrue(tokyo["has_noun_sense"])
        self.assertEqual(tokyo["pos_tags"], ["pn"])
        self.assertEqual(tokyo["spellings"], [])
        self.assertEqual(tokyo["priority_tags"], ["news2"])
        self.assertEqual(tokyo["priority_level"], 2)

    def test_noun_tag_definition_excludes_suru_tag_alone(self) -> None:
        self.assertTrue(has_noun_tag(["n"]))
        self.assertTrue(has_noun_tag(["n-adv"]))
        self.assertTrue(has_noun_tag(["n-t"]))
        self.assertTrue(has_noun_tag(["n-pref"]))
        self.assertTrue(has_noun_tag(["n-suf"]))
        self.assertTrue(has_noun_tag(["num"]))
        self.assertTrue(has_noun_tag(["pn"]))
        self.assertFalse(has_noun_tag(["vs"]))

    def test_statistics_include_failures_merges_and_length_distribution(self) -> None:
        stats = self.statistics
        self.assertEqual(stats["entry_count"], 9)
        self.assertEqual(stats["kanji_spelling_count"], 4)
        self.assertEqual(stats["reading_count"], 10)
        self.assertEqual(stats["reading_candidate_count"], 10)
        self.assertEqual(stats["normalization_success_count"], 9)
        self.assertEqual(stats["normalization_failure_count"], 1)
        self.assertEqual(stats["normalization_failure_reasons"], {"contains_non_hiragana": 1})
        self.assertEqual(stats["duplicate_merge_count"], 1)
        self.assertEqual(stats["post_merge_word_count"], 8)
        self.assertEqual(stats["noun_candidate_count"], 6)
        self.assertEqual(stats["normalized_length_word_counts"], {"2": 1, "3": 4, "4": 1, "5": 2})
        self.assertEqual(stats["minimum_normalized_length"], 2)
        self.assertEqual(stats["maximum_normalized_length"], 5)
        self.assertEqual(stats["average_normalized_length"], 3.5)

    def test_jsonl_and_sidecars_are_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = Path(tmp_dir) / "first.jsonl"
            second = Path(tmp_dir) / "second.jsonl"
            first_result = build_master_dictionary(FIXTURE, first)
            second_result = build_master_dictionary(FIXTURE, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            lines = first.read_text(encoding="utf-8").splitlines()
            parsed = [json.loads(line) for line in lines]
            self.assertEqual(
                [record["normalized_reading"] for record in parsed],
                sorted(record["normalized_reading"] for record in parsed),
            )
            self.assertEqual(first_result.metadata["normalization_version"], "legacy_v1")
            self.assertEqual(first_result.metadata["master_dictionary_sha256"], second_result.metadata["master_dictionary_sha256"])
            self.assertTrue((Path(tmp_dir) / "first.metadata.json").is_file())
            self.assertTrue((Path(tmp_dir) / "first.stats.json").is_file())

    def test_cli_reports_missing_malformed_and_unwritable_paths(self) -> None:
        def args(input_path: Path, output_path: Path) -> argparse.Namespace:
            return argparse.Namespace(
                input=str(input_path),
                output=str(output_path),
                metadata_output=None,
                statistics_output=None,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = run_cli(args(root / "missing.xml", root / "missing.jsonl"))
            self.assertEqual(exit_code, 2)
            self.assertIn("does not exist", stderr.getvalue())

            malformed = root / "malformed.xml"
            malformed.write_text("<JMdict><entry>", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = run_cli(args(malformed, root / "malformed.jsonl"))
            self.assertEqual(exit_code, 2)
            self.assertIn("XML is malformed", stderr.getvalue())

            parent_is_file = root / "not-a-directory"
            parent_is_file.write_text("occupied", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = run_cli(args(FIXTURE, parent_is_file / "master.jsonl"))
            self.assertEqual(exit_code, 2)
            self.assertIn("failed to build master dictionary", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
