from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dataset import ReadingRecord, parse_jmdict, priority_rank, read_csv_records, select_records  # noqa: E402


class DatasetTest(unittest.TestCase):
    def test_priority_rank(self) -> None:
        self.assertEqual(priority_rank(["news1"]), 0)
        self.assertEqual(priority_rank(["nf05"]), 0)
        self.assertEqual(priority_rank(["ichi2"]), 1)
        self.assertEqual(priority_rank(["nf20"]), 1)
        self.assertEqual(priority_rank(["nf21"]), 2)
        self.assertEqual(priority_rank([]), 3)

    def test_parse_jmdict_reb_priority_and_deduplication(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<JMdict>
  <entry>
    <k_ele><keb>林檎</keb><ke_pri>news1</ke_pri></k_ele>
    <r_ele><reb>リンゴ</reb></r_ele>
  </entry>
  <entry>
    <r_ele><reb>りんご</reb></r_ele>
  </entry>
  <entry>
    <r_ele><reb>ゲーム</reb><re_pri>nf08</re_pri></r_ele>
  </entry>
  <entry>
    <r_ele><reb>abc</reb></r_ele>
  </entry>
</JMdict>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "JMdict_test.xml"
            path.write_text(xml, encoding="utf-8")
            records, stats = parse_jmdict(path)

        by_reading = {record.reading: record for record in records}
        self.assertIn("りんご", by_reading)
        self.assertEqual(by_reading["りんご"].priority_rank, 0)
        self.assertIn("げえむ", by_reading)
        self.assertEqual(by_reading["げえむ"].priority_rank, 1)
        self.assertNotIn("abc", by_reading)
        self.assertEqual(stats.raw_reading_count, 4)
        self.assertEqual(stats.final_unique_count, 2)

    def test_read_csv_records_normalizes_equivalent_kana(self) -> None:
        csv_text = """reading,start_char,end_char,priority_rank,priority_label,priority_tags
らゔ,ら,ゔ,0,high,news1
ゔあいおりん,ゔ,ん,0,high,gai1
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "records.csv"
            path.write_text(csv_text, encoding="utf-8")
            records = read_csv_records(path)

        self.assertEqual([record.reading for record in records], ["らぶ", "ぶあいおりん"])

    def test_select_records_is_seed_reproducible(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?><JMdict>
<entry><r_ele><reb>あい</reb><re_pri>news1</re_pri></r_ele></entry>
<entry><r_ele><reb>いえ</reb><re_pri>news1</re_pri></r_ele></entry>
<entry><r_ele><reb>うえ</reb><re_pri>news1</re_pri></r_ele></entry>
<entry><r_ele><reb>えき</reb><re_pri>news1</re_pri></r_ele></entry>
</JMdict>"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "JMdict_test.xml"
            path.write_text(xml, encoding="utf-8")
            records, _stats = parse_jmdict(path)

        first = select_records(records, 3, random_seed=7)
        second = select_records(records, 3, random_seed=7)
        self.assertEqual(first, second)

    def test_select_records_prefers_high_priority_by_default(self) -> None:
        records = [
            ReadingRecord(f"あ{i}", 0, "high", ("news1",))
            for i in range(5)
        ] + [
            ReadingRecord(f"い{i}", 3, "none", ())
            for i in range(20)
        ]
        selected = select_records(records, 4, random_seed=0)
        self.assertEqual({record.priority_label for record in selected}, {"high"})


if __name__ == "__main__":
    unittest.main()
