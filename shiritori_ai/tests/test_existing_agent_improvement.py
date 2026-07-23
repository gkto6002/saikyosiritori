from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "benchmarks"))

from existing_agents_benchmark import percentile, write_csv  # noqa: E402
from existing_agent_analysis import _agent_rows  # noqa: E402
from run_existing_agent_improvement import (  # noqa: E402
    parse_args,
    source_fingerprint,
    tuning_configs,
)


class ExistingAgentImprovementTest(unittest.TestCase):
    def test_quick_mode_and_individual_stage_parse(self) -> None:
        args = parse_args(["--quick", "--stage", "tuning"])
        self.assertTrue(args.quick)
        self.assertFalse(args.full)
        self.assertEqual(args.stage, "tuning")

    def test_full_tuning_grid_contains_all_required_settings(self) -> None:
        configs = tuning_configs(quick=False)
        alpha = [row for row in configs if row["agent"] == "alpha_beta"]
        pvs = [row for row in configs if row["agent"] == "pvs"]
        beam = [row for row in configs if row["agent"] == "beam_negamax"]
        self.assertEqual(len(alpha), 9)
        self.assertEqual(len(pvs), 9)
        self.assertEqual(len(beam), 4)
        self.assertEqual({row["depth"] for row in alpha}, {3, 4, 5})
        self.assertEqual({row["branch_limit"] for row in pvs}, {8, 12, 16})

    def test_percentile_uses_nearest_rank(self) -> None:
        self.assertEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95), 5.0)

    def test_csv_writer_accepts_heterogeneous_setting_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.csv"
            write_csv(path, [{"depth": 4, "branch_limit": 12}, {"depth": 5, "beam_widths": "12,8"}])
            header = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(header, "depth,branch_limit,beam_widths")

    def test_source_fingerprint_tracks_worktree_source(self) -> None:
        fingerprint = source_fingerprint()
        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)

    def test_final_match_aggregation_credits_both_seats(self) -> None:
        matches = [
            {
                "first_agent": "alpha_beta",
                "second_agent": "pvs",
                "winner": "first",
                "first_avg_time_sec": 0.1,
                "second_avg_time_sec": 0.2,
                "first_timeout_count": 0,
                "second_timeout_count": 1,
            },
            {
                "first_agent": "pvs",
                "second_agent": "alpha_beta",
                "winner": "second",
                "first_avg_time_sec": 0.3,
                "second_avg_time_sec": 0.1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
            },
        ]
        summary = {row["agent"]: row for row in _agent_rows(matches)}
        self.assertEqual(summary["alpha_beta"]["wins"], 2)
        self.assertEqual(summary["alpha_beta"]["games"], 2)
        self.assertEqual(summary["pvs"]["wins"], 0)
        self.assertEqual(summary["pvs"]["internal_timeout_count"], 1)


if __name__ == "__main__":
    unittest.main()
