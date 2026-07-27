from __future__ import annotations

import sys
import unittest
from itertools import combinations
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from create_final_presentation_figures import (  # noqa: E402
    board_adaptive_match_summary,
    board_adaptive_summary,
    canonical_settings,
    direct_result,
    same_depth_effect,
)
from run_presentation_experiments import experiment_config  # noqa: E402


class FinalPresentationFiguresTest(unittest.TestCase):
    def test_canonical_settings_match_equivalent_manifests(self) -> None:
        presentation = {"config": experiment_config(range(10, 20))}
        followup = {
            "config": {
                "dictionary_size": 10000,
                "time_limit_sec": 1.0,
                "max_moves": 1000,
                "adaptive_profile": {
                    "target_time_ratio": 0.6,
                    "depth_decrease_ratio": 0.95,
                    "depth_recovery_ratio": 0.6,
                    "depth_recovery_turns": 2,
                },
                "variants": {
                    "beam_alpha_beta_deep_wide": {
                        "initial_depth": 8,
                        "max_depth": 9,
                        "beam_widths": [12, 8, 4, 2],
                    }
                },
                "alpha_beta": {
                    "initial_depth": 5,
                    "max_depth": 7,
                    "branch_limit": 8,
                },
            }
        }
        first, second = canonical_settings(presentation, followup)
        self.assertEqual(first, second)

    def test_direct_result_combines_sources_and_seats(self) -> None:
        current = [
            {
                "match_id": "current1",
                "first_target": "beam_alpha_beta",
                "second_target": "selective_alpha_beta",
                "winner": "first",
                "dictionary_seed": 10,
            },
            {
                "match_id": "current2",
                "first_target": "selective_alpha_beta",
                "second_target": "beam_alpha_beta",
                "winner": "first",
                "dictionary_seed": 10,
            },
        ]
        earlier = [
            {
                "match_id": "earlier1",
                "hybrid_config_id": "beam_alpha_beta_deep_wide",
                "first_config_id": "beam_alpha_beta_deep_wide",
                "second_config_id": "alpha_beta_reference",
                "winner": "first",
                "dictionary_seed": 0,
            },
            {
                "match_id": "earlier2",
                "hybrid_config_id": "beam_alpha_beta_deep_wide",
                "first_config_id": "alpha_beta_reference",
                "second_config_id": "beam_alpha_beta_deep_wide",
                "winner": "second",
                "dictionary_seed": 0,
            },
        ]
        result = direct_result(current, earlier)
        self.assertEqual(result["games"], 4)
        self.assertEqual(result["beam_alpha_beta_wins"], 3)
        self.assertEqual(result["selective_alpha_beta_wins"], 1)
        self.assertEqual(result["beam_alpha_beta_first_count"], 2)
        self.assertEqual(result["selective_alpha_beta_first_count"], 2)
        self.assertEqual(result["duplicate_match_id_count"], 0)

    def test_same_depth_effect_is_recalculated_from_rows(self) -> None:
        rows = []
        for agent, elapsed, nodes in (
            ("beam_negamax", 2.0, 100),
            ("beam_alpha_beta", 0.5, 25),
        ):
            rows.extend(
                {
                    "agent": agent,
                    "elapsed_time_sec": elapsed,
                    "nodes_searched": nodes,
                }
                for _ in range(14)
            )
        result = same_depth_effect(rows)
        self.assertAlmostEqual(result["time_reduction_rate"], 0.75)
        self.assertAlmostEqual(result["node_reduction_rate"], 0.75)

    def test_board_adaptive_profiles_remain_separate(self) -> None:
        positions = [
            {
                "position_id": f"p{index}",
                "seed": 0,
                "runtime": "D10000_L2-12_seed0.runtime.json",
            }
            for index in range(50)
        ]
        profiles = (
            "reference",
            "fixed_beam_alpha_beta",
            "gap_conservative",
            "gap_responsive",
            "proof_strict",
            "proof_moderate",
        )
        rows = []
        for profile in profiles:
            for index in range(50):
                rows.append(
                    {
                        "profile": profile,
                        "position_id": f"p{index}",
                        "selected_edge": [0, index % 2],
                        "timed_out": (
                            profile == "reference" and index == 49
                        ),
                        "completed_root_moves": 1,
                        "selected_root_candidate_count": 1,
                        "effective_depth": (
                            10 if profile == "reference" else 8
                        ),
                    }
                )
        summary, validation = board_adaptive_summary(rows, positions)
        self.assertEqual(len(summary), 5)
        self.assertEqual(
            [row["profile"] for row in summary[-2:]],
            ["proof_strict", "proof_moderate"],
        )
        self.assertTrue(validation["same_position_ids_for_all_profiles"])
        self.assertEqual(
            validation["stable_reference_position_count"],
            49,
        )

    def test_board_adaptive_round_robin_has_equal_denominators(self) -> None:
        agents = (
            "fixed_beam_alpha_beta",
            "gap_conservative",
            "gap_responsive",
            "proof_strict",
            "proof_moderate",
        )
        rows = []
        for left, right in combinations(agents, 2):
            for seed in range(5):
                for first, second in ((left, right), (right, left)):
                    rows.append(
                        {
                            "match_id": f"{seed}_{first}_{second}",
                            "dictionary_seed": seed,
                            "first_agent": first,
                            "second_agent": second,
                            "winner": "first",
                            "loss_reason": "ended_with_n",
                            "invalid_move_count": 0,
                            "dictionary_size": 10000,
                            "decision_time_sec": 0.3,
                            "max_moves": 1000,
                            "max_match_time_sec": 90.0,
                            "candidate_depth": 8,
                            "candidate_max_depth": 9,
                            "beam_widths": [12, 8, 4, 2],
                            "adaptive_depth": True,
                        }
                    )
        summary, validation = board_adaptive_match_summary(rows)
        self.assertEqual(len(summary), 5)
        self.assertTrue(validation["all_profiles_have_40_games"])
        self.assertTrue(validation["all_profiles_have_balanced_seats"])
        self.assertEqual(validation["match_count"], 100)


if __name__ == "__main__":
    unittest.main()
