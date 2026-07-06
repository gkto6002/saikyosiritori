from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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


if __name__ == "__main__":
    unittest.main()
