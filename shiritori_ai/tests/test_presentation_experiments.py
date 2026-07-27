from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AlphaBetaAgent,
    BeamAlphaBetaAgent,
    BeamPVSAgent,
    FullAlphaBetaAgent,
    MinimaxAgent,
    PVSAgent,
)
from analyze_presentation_experiments import (  # noqa: E402
    fixed_comparison_summary,
    validate_match_rows,
    wilson_interval,
)
from run_presentation_experiments import (  # noqa: E402
    build_presentation_agent,
    expected_match_jobs,
    experiment_config,
)


class PresentationExperimentsTest(unittest.TestCase):
    def test_expected_match_counts_are_120_and_90(self) -> None:
        config = experiment_config(range(10, 20))
        self.assertEqual(len(expected_match_jobs(config, "final4")), 120)
        self.assertEqual(len(expected_match_jobs(config, "initial6")), 90)

    def test_adopted_agent_settings_are_unchanged(self) -> None:
        config = experiment_config(range(10, 20))
        selective = build_presentation_agent(
            "selective_alpha_beta", config, 1
        )
        pvs = build_presentation_agent("pvs", config, 1)
        beam_ab = build_presentation_agent(
            "beam_alpha_beta", config, 1
        )
        beam_pvs = build_presentation_agent("beam_pvs", config, 1)
        minimax = build_presentation_agent("minimax", config, 1)
        full = build_presentation_agent("full_alpha_beta", config, 1)

        self.assertIsInstance(selective, AlphaBetaAgent)
        self.assertNotIsInstance(selective, FullAlphaBetaAgent)
        self.assertEqual((selective.depth, selective.max_depth), (5, 7))
        self.assertEqual(selective.branch_limit, 8)
        self.assertIsInstance(pvs, PVSAgent)
        self.assertEqual((pvs.depth, pvs.max_depth), (5, 7))
        self.assertEqual(pvs.branch_limit, 8)
        self.assertIsInstance(beam_ab, BeamAlphaBetaAgent)
        self.assertEqual((beam_ab.depth, beam_ab.max_depth), (8, 9))
        self.assertEqual(beam_ab.beam_widths, (12, 8, 4, 2))
        self.assertIsInstance(beam_pvs, BeamPVSAgent)
        self.assertEqual((beam_pvs.depth, beam_pvs.max_depth), (8, 9))
        self.assertEqual(beam_pvs.beam_widths, (12, 8, 4, 2))
        self.assertIsInstance(minimax, MinimaxAgent)
        self.assertFalse(minimax.adaptive_depth)
        self.assertEqual(minimax.depth, 3)
        self.assertIsInstance(full, FullAlphaBetaAgent)
        self.assertFalse(full.adaptive_depth)
        self.assertEqual(full.depth, 4)

    def test_validation_detects_complete_seat_swap(self) -> None:
        rows = [
            {
                "match_id": "forward",
                "dictionary_seed": 10,
                "first_target": "a",
                "second_target": "b",
                "winner": "first",
                "loss_reason": "no_legal_move",
                "first_timeout_count": 0,
                "second_timeout_count": 0,
                "history": [],
            },
            {
                "match_id": "reverse",
                "dictionary_seed": 10,
                "first_target": "b",
                "second_target": "a",
                "winner": "second",
                "loss_reason": "no_legal_move",
                "first_timeout_count": 0,
                "second_timeout_count": 0,
                "history": [],
            },
        ]
        validation = validate_match_rows(rows, 2, ("a", "b"), (10,))
        self.assertTrue(validation["complete"])
        self.assertEqual(validation["duplicate_count"], 0)
        self.assertEqual(validation["missing_seat_pairs"], [])

    def test_representative_depth_uses_completion_not_agreement(self) -> None:
        rows = []
        for depth, full_completed in ((3, 5), (4, 4), (5, 3)):
            for index in range(5):
                complete = index < full_completed
                common = {
                    "depth": depth,
                    "position_id": f"p{index}",
                    "elapsed_time_sec": 0.1,
                    "nodes_searched": 10,
                    "selected_root_candidate_count": 2,
                    "completed_root_moves": 2 if complete else 1,
                    "timed_out": not complete,
                    "score": 1.0,
                }
                rows.append(
                    {
                        **common,
                        "config_id": f"full_d{depth}",
                        "agent": "full_alpha_beta",
                        "selected_edge": "0→1",
                    }
                )
                rows.append(
                    {
                        **common,
                        "config_id": f"selective_d{depth}",
                        "agent": "selective_alpha_beta",
                        "selected_edge": "9→9" if depth == 4 else "0→1",
                        "timed_out": False,
                        "completed_root_moves": 2,
                    }
                )
        _summary, representative = fixed_comparison_summary(rows)
        self.assertEqual(representative, 4)

    def test_wilson_interval_contains_observed_rate(self) -> None:
        low, high = wilson_interval(7, 10)
        self.assertLess(low, 0.7)
        self.assertGreater(high, 0.7)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 1.0)


if __name__ == "__main__":
    unittest.main()
