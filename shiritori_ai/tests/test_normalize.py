from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from normalize import normalize_reading, normalize_readings  # noqa: E402


class NormalizeReadingTest(unittest.TestCase):
    def test_katakana_to_hiragana(self) -> None:
        self.assertEqual(normalize_reading("リンゴ"), "りんご")

    def test_small_kana_are_expanded(self) -> None:
        self.assertEqual(normalize_reading("きゃく"), "きやく")
        self.assertEqual(normalize_reading("ふぁいる"), "ふあいる")

    def test_small_tsu_is_expanded(self) -> None:
        self.assertEqual(normalize_reading("がっこう"), "がつこう")

    def test_long_vowel_mark_uses_previous_vowel(self) -> None:
        self.assertEqual(normalize_reading("コーヒー"), "こおひい")
        self.assertEqual(normalize_reading("ゲーム"), "げえむ")
        self.assertEqual(normalize_reading("スーパー"), "すうぱあ")

    def test_voiced_and_unvoiced_kana_remain_distinct(self) -> None:
        self.assertEqual(normalize_reading("がく"), "がく")
        self.assertEqual(normalize_reading("かく"), "かく")
        self.assertNotEqual(normalize_reading("がく"), normalize_reading("かく"))

    def test_duplicates_are_removed(self) -> None:
        self.assertEqual(normalize_readings(["リンゴ", "りんご", "ゴリラ"]), ["りんご", "ごりら"])

    def test_unsupported_characters_are_rejected(self) -> None:
        self.assertIsNone(normalize_reading("abc"))
        self.assertIsNone(normalize_reading("ゲーム2"))
        self.assertIsNone(normalize_reading("あ"))


if __name__ == "__main__":
    unittest.main()
