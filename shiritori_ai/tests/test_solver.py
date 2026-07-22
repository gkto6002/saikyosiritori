from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments_exact import all_seed_runs_timed_out, parse_args as parse_exact_args  # noqa: E402
from game import WordGraph  # noqa: E402
from solver import ShiritoriSolver  # noqa: E402


class ShiritoriSolverTest(unittest.TestCase):
    def test_no_available_word_is_losing(self) -> None:
        graph = WordGraph.from_words(["あい"])
        solver = ShiritoriSolver(graph)
        self.assertFalse(solver.solve("か", 0))

    def test_word_ending_with_n_is_not_a_winning_move(self) -> None:
        graph = WordGraph.from_words(["あん"])
        solver = ShiritoriSolver(graph)
        self.assertFalse(solver.solve("あ", 0))
        self.assertIsNone(solver.get_best_move("あ", 0))

    def test_position_with_move_to_opponent_loss_is_winning(self) -> None:
        graph = WordGraph.from_words(["あい", "いん"])
        solver = ShiritoriSolver(graph)
        self.assertTrue(solver.solve("あ", 0))
        self.assertEqual(solver.get_best_move("あ", 0), "あい")

    def test_first_move_ending_with_n_is_losing(self) -> None:
        graph = WordGraph.from_words(["りん"])
        solver = ShiritoriSolver(graph)
        result = solver.analyze_first_moves()[0]
        self.assertEqual(result.result, "lose")

    def test_exact_experiment_defaults_auto_size_until_all_seed_timeouts(self) -> None:
        with patch.object(sys, "argv", ["experiments_exact.py", "--records", "dummy.csv"]):
            args = parse_exact_args()

        self.assertIsNone(args.sizes)
        self.assertEqual(args.size_start, 100)
        self.assertEqual(args.size_step, 50)
        self.assertEqual(args.seeds, [0, 1, 2])

    def test_exact_experiment_can_still_use_fixed_sizes_and_seeds(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "experiments_exact.py",
                "--records",
                "dummy.csv",
                "--sizes",
                "100",
                "200",
                "--seeds",
                "3",
                "4",
            ],
        ):
            args = parse_exact_args()

        self.assertEqual(args.sizes, [100, 200])
        self.assertEqual(args.seeds, [3, 4])

    def test_all_seed_runs_timed_out_requires_every_seed_to_timeout(self) -> None:
        self.assertTrue(
            all_seed_runs_timed_out(
                [{"timed_out": True}, {"timed_out": True}, {"timed_out": True}],
                seed_count=3,
            )
        )
        self.assertFalse(
            all_seed_runs_timed_out(
                [{"timed_out": True}, {"timed_out": False}, {"timed_out": True}],
                seed_count=3,
            )
        )
        self.assertFalse(all_seed_runs_timed_out([{"timed_out": True}], seed_count=3))


if __name__ == "__main__":
    unittest.main()
