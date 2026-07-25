from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from run_search_parameter_tuning import (  # noqa: E402
    ADAPTIVE_PROFILES,
    BASELINES,
    _correlation,
    build_agent,
    build_match_jobs,
    depth_six_is_safe,
    fixed_configs,
    matching_depth_six,
    parse_args,
    runtime_paths,
)


class SearchParameterTuningTest(unittest.TestCase):
    def test_fixed_configs_cover_requested_ranges(self) -> None:
        configs = fixed_configs()
        ids = {row["config_id"] for row in configs}
        self.assertEqual(30, len(configs))
        for agent in ("alpha_beta", "pvs"):
            for depth in (5, 6, 7):
                for branch in (8, 12, 16):
                    self.assertIn(f"{agent}_d{depth}_b{branch}", ids)
        for depth in (5, 6, 7):
            self.assertIn(f"beam_negamax_d{depth}_w8-6-4-2", ids)

    def test_baselines_match_d5000_comparison(self) -> None:
        self.assertEqual("alpha_beta_d5_b8", BASELINES["alpha_beta"]["config_id"])
        self.assertEqual("pvs_d5_b8", BASELINES["pvs"]["config_id"])
        self.assertEqual(
            "beam_negamax_d5_w8-6-4-2",
            BASELINES["beam_negamax"]["config_id"],
        )

    def test_depth_seven_gate_uses_matching_depth_six(self) -> None:
        config = {
            "agent": "beam_negamax",
            "depth": 7,
            "beam_widths": (12, 8, 6, 4),
        }
        self.assertEqual(
            "beam_negamax_d6_w12-8-6-4",
            matching_depth_six(config),
        )
        safe = {
            "timeout_rate": 0.2,
            "p95_time_sec": 0.9,
            "mean_root_completion_rate": 0.5,
        }
        self.assertTrue(depth_six_is_safe(safe, 1.0))
        self.assertFalse(
            depth_six_is_safe({**safe, "timeout_rate": 0.21}, 1.0)
        )

    def test_correlation_is_deterministic(self) -> None:
        self.assertEqual(1.0, _correlation([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]))
        self.assertIsNone(_correlation([1.0], [2.0]))

    def test_adaptive_profiles_raise_maximum_and_use_soft_target(self) -> None:
        config = {
            "config_id": "alpha_beta_d5_b8",
            "agent": "alpha_beta",
            "depth": 5,
            "branch_limit": 8,
        }
        fixed = build_agent(config, 1.0, ADAPTIVE_PROFILES["fixed"])
        adaptive = build_agent(config, 1.0, ADAPTIVE_PROFILES["standard"])
        self.assertEqual(5, fixed.initial_depth)
        self.assertEqual(5, fixed.max_depth)
        self.assertEqual(1.0, fixed.target_time_sec)
        self.assertEqual(5, adaptive.initial_depth)
        self.assertEqual(7, adaptive.max_depth)
        self.assertEqual(0.4, adaptive.target_time_sec)

    def test_dictionary_size_selects_matching_runtime_files(self) -> None:
        paths = runtime_paths(PROJECT_ROOT / "data/dictionaries", 50000)
        self.assertEqual(3, len(paths))
        self.assertEqual(
            "D50000_L2-12_seed0.runtime.json",
            paths[0].name,
        )
        self.assertEqual(
            "D50000_L2-12_seed2.runtime.json",
            paths[-1].name,
        )

    def test_large_dictionary_selection_transfer_cli(self) -> None:
        args = parse_args(
            [
                "--full",
                "--stage",
                "adaptive",
                "--dictionary-size",
                "50000",
                "--selection-from",
                "results/search_parameter_tuning/source",
                "--max-moves",
                "3000",
                "--max-match-time-sec",
                "600",
                "--match-plan",
                "pilot",
                "--match-seeds",
                "0",
                "--match-limit",
                "3",
            ]
        )
        self.assertEqual(50000, args.dictionary_size)
        self.assertEqual(
            Path("results/search_parameter_tuning/source"),
            args.selection_from,
        )
        self.assertEqual("pilot", args.match_plan)
        self.assertEqual([0], args.match_seeds)
        self.assertEqual(3, args.match_limit)

    def test_pilot_match_plan_has_only_twelve_primary_comparisons(self) -> None:
        selected = {
            agent: BASELINES[agent]
            for agent in ("alpha_beta", "pvs", "beam_negamax")
        }
        adaptive = {
            agent: {"profile": "standard"}
            for agent in ("alpha_beta", "pvs", "beam_negamax")
        }
        pilot = build_match_jobs(selected, adaptive, plan="pilot")
        full = build_match_jobs(selected, adaptive, plan="full")
        self.assertEqual(12, len(pilot))
        self.assertEqual(18, len(full))
        self.assertNotIn(
            ("baseline_alpha_beta", "improved_fixed_alpha_beta"),
            pilot,
        )


if __name__ == "__main__":
    unittest.main()
