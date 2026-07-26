from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import AlphaBetaAgent, BeamAlphaBetaAgent, BeamPVSAgent  # noqa: E402
from analyze_beam_hybrid_followup import (  # noqa: E402
    summarize_by_seed,
    summarize_variants,
)
from run_beam_hybrid_followup import (  # noqa: E402
    ALPHA_CONFIG_ID,
    DEFAULT_VARIANTS,
    VARIANT_SPECS,
    build_configured_agent,
    expected_jobs,
    parse_args,
)


class BeamHybridFollowupTest(unittest.TestCase):
    def test_eight_variants_cover_depth_width_and_combined_changes(self) -> None:
        self.assertEqual(8, len(DEFAULT_VARIANTS))
        for agent in ("beam_alpha_beta", "beam_pvs"):
            expected = {
                f"{agent}_baseline": (7, 8, [8, 6, 4, 2]),
                f"{agent}_deep": (8, 9, [8, 6, 4, 2]),
                f"{agent}_wide": (7, 8, [12, 8, 4, 2]),
                f"{agent}_deep_wide": (8, 9, [12, 8, 4, 2]),
            }
            for config_id, values in expected.items():
                spec = VARIANT_SPECS[config_id]
                self.assertEqual(values, (
                    spec["initial_depth"],
                    spec["max_depth"],
                    spec["beam_widths"],
                ))

    def test_configured_agents_use_selected_adaptive_settings(self) -> None:
        alpha = build_configured_agent(
            ALPHA_CONFIG_ID,
            time_limit_sec=1.0,
            random_seed=0,
        )
        beam_alpha = build_configured_agent(
            "beam_alpha_beta_deep_wide",
            time_limit_sec=1.0,
            random_seed=0,
        )
        beam_pvs = build_configured_agent(
            "beam_pvs_deep",
            time_limit_sec=1.0,
            random_seed=0,
        )
        self.assertIsInstance(alpha, AlphaBetaAgent)
        self.assertIsInstance(beam_alpha, BeamAlphaBetaAgent)
        self.assertIsInstance(beam_pvs, BeamPVSAgent)
        self.assertEqual((5, 7), (alpha.initial_depth, alpha.max_depth))
        self.assertEqual((8, 9), (
            beam_alpha.initial_depth,
            beam_alpha.max_depth,
        ))
        self.assertEqual((12, 8, 4, 2), beam_alpha.beam_widths)
        self.assertEqual((8, 9), (
            beam_pvs.initial_depth,
            beam_pvs.max_depth,
        ))
        for agent in (alpha, beam_alpha, beam_pvs):
            self.assertTrue(agent.adaptive_depth)
            self.assertEqual(0.6, agent.target_time_sec)
            self.assertEqual(0.95, agent.depth_decrease_ratio)
            self.assertEqual(0.6, agent.depth_recovery_ratio)
            self.assertEqual(2, agent.depth_recovery_turns)

    def test_ten_seed_full_matrix_has_160_unique_matches(self) -> None:
        jobs = expected_jobs(tuple(range(10)), DEFAULT_VARIANTS)
        self.assertEqual(160, len(jobs))
        self.assertEqual(160, len(set(jobs)))

    def test_cli_accepts_variant_subset_and_match_limit(self) -> None:
        args = parse_args(
            [
                "--seeds",
                "0,3",
                "--variants",
                "beam_alpha_beta_deep,beam_pvs_deep_wide",
                "--match-limit",
                "2",
            ]
        )
        self.assertEqual((0, 3), args.seeds)
        self.assertEqual(
            ("beam_alpha_beta_deep", "beam_pvs_deep_wide"),
            args.variants,
        )
        self.assertEqual(2, args.match_limit)

    def test_analysis_summarizes_variant_and_seed_results(self) -> None:
        matches = [
            {
                "dictionary_seed": 0,
                "hybrid_config_id": "beam_alpha_beta_deep",
                "first_config_id": "beam_alpha_beta_deep",
                "second_config_id": ALPHA_CONFIG_ID,
                "winner": "first",
                "history": [
                    {
                        "player": "first",
                        "elapsed_time_sec": 0.1,
                        "nodes_searched": 10,
                        "effective_depth": 9,
                        "timed_out": False,
                        "depth_changed": False,
                    },
                    {
                        "player": "second",
                        "elapsed_time_sec": 0.2,
                        "nodes_searched": 20,
                        "effective_depth": 6,
                        "timed_out": False,
                        "depth_changed": True,
                    },
                ],
            },
            {
                "dictionary_seed": 0,
                "hybrid_config_id": "beam_alpha_beta_deep",
                "first_config_id": ALPHA_CONFIG_ID,
                "second_config_id": "beam_alpha_beta_deep",
                "winner": "first",
                "history": [],
            },
        ]
        specs = {
            "beam_alpha_beta_deep": VARIANT_SPECS[
                "beam_alpha_beta_deep"
            ]
        }
        row = summarize_variants(matches, specs)[0]
        self.assertEqual(2, row["games"])
        self.assertEqual(1, row["hybrid_wins"])
        self.assertEqual(1, row["alpha_beta_wins"])
        self.assertEqual(0.5, row["hybrid_win_rate"])
        self.assertEqual(9.0, row["hybrid_mean_effective_depth"])
        seed = summarize_by_seed(matches, specs)[0]
        self.assertEqual(0.5, seed["hybrid_win_rate"])
        self.assertEqual(1, seed["alpha_beta_wins"])
        self.assertEqual(0, seed["draws"])

    def test_seed_summary_does_not_count_draw_as_alpha_beta_win(self) -> None:
        config_id = "beam_pvs_wide"
        match = {
            "dictionary_seed": 2,
            "hybrid_config_id": config_id,
            "first_config_id": config_id,
            "second_config_id": ALPHA_CONFIG_ID,
            "winner": "draw",
        }
        row = summarize_by_seed(
            [match],
            {config_id: VARIANT_SPECS[config_id]},
        )[0]
        self.assertEqual(0, row["hybrid_wins"])
        self.assertEqual(0, row["alpha_beta_wins"])
        self.assertEqual(1, row["draws"])


if __name__ == "__main__":
    unittest.main()
