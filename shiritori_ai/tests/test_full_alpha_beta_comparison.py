from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from run_full_alpha_beta_comparison import (  # noqa: E402
    build_comparison_agent,
    build_configs,
    comparison_rows,
    parse_args,
    run_benchmark,
    summarize_comparisons,
    summarize_matches,
)
from runtime_dictionary import RuntimeDictionary  # noqa: E402


class FullAlphaBetaComparisonTest(unittest.TestCase):
    def test_config_matrix_has_full_and_selective_variants(self) -> None:
        configs = build_configs([4, 3, 4], [12, 8])
        self.assertEqual(
            [row["config_id"] for row in configs],
            [
                "full_alpha_beta_d3",
                "selective_alpha_beta_d3_b8",
                "selective_alpha_beta_d3_b12",
                "full_alpha_beta_d4",
                "selective_alpha_beta_d4_b8",
                "selective_alpha_beta_d4_b12",
            ],
        )
        full = build_comparison_agent(configs[0], 1.0)
        selective = build_comparison_agent(configs[1], 1.0)
        self.assertIsNone(full.branch_limit)
        self.assertEqual(8, selective.branch_limit)
        self.assertFalse(full.adaptive_depth)
        self.assertFalse(selective.adaptive_depth)

    def test_cli_supports_staged_benchmark_and_matches(self) -> None:
        args = parse_args(
            [
                "--positions",
                "positions.json",
                "--depths",
                "3",
                "4",
                "--branch-limits",
                "8",
                "16",
                "--stage",
                "matches",
                "--match-limit",
                "2",
            ]
        )
        self.assertEqual([3, 4], args.depths)
        self.assertEqual([8, 16], args.branch_limits)
        self.assertEqual("matches", args.stage)
        self.assertEqual(2, args.match_limit)

    def test_small_benchmark_compares_only_completed_full_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_path = root / "runtime.json"
            RuntimeDictionary.from_readings(
                ["あい", "あう", "あえ", "いあ", "うあ", "えあ"]
            ).save(runtime_path)
            positions = [
                {
                    "position_id": "seed0_t0",
                    "runtime": str(runtime_path),
                    "seed": 0,
                    "split": "tuning",
                    "turn": 0,
                    "edge_history": [],
                    "remaining_word_count": 6,
                    "legal_edge_count": 6,
                    "risk_level": "normal",
                    "category": "early",
                }
            ]
            rows = run_benchmark(
                positions,
                build_configs([2], [2]),
                root / "output",
                10.0,
            )
            self.assertEqual(2, len(rows))
            full = next(row for row in rows if row["agent"] == "full_alpha_beta")
            self.assertEqual(
                full["root_candidate_count"],
                full["selected_root_candidate_count"],
            )
            details = comparison_rows(rows)
            self.assertEqual(1, len(details))
            self.assertTrue(details[0]["comparable"])
            summary = summarize_comparisons(details)
            self.assertEqual(1, summary[0]["comparable_count"])
            self.assertEqual(1.0, summary[0]["full_complete_rate"])

    def test_match_summary_counts_seats_for_each_target(self) -> None:
        rows = [
            {
                "first_target": "full_alpha_beta",
                "second_target": "selective_alpha_beta",
                "winner": "first",
                "first_avg_time_sec": 0.2,
                "second_avg_time_sec": 0.1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
            },
            {
                "first_target": "selective_alpha_beta",
                "second_target": "full_alpha_beta",
                "winner": "first",
                "first_avg_time_sec": 0.1,
                "second_avg_time_sec": 0.2,
                "first_timeout_count": 0,
                "second_timeout_count": 1,
            },
        ]
        summary = {
            row["target"]: row
            for row in summarize_matches(rows)
        }
        self.assertEqual(1, summary["full_alpha_beta"]["wins"])
        self.assertEqual(1, summary["full_alpha_beta"]["losses"])
        self.assertEqual(1, summary["full_alpha_beta"]["timeout_count"])
        self.assertEqual(1, summary["selective_alpha_beta"]["wins"])


if __name__ == "__main__":
    unittest.main()
