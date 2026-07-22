from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments_exact import (  # noqa: E402
    all_seed_runs_timed_out,
    parse_args as parse_exact_args,
    run_edge_exact,
)
from game import WordGraph  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from solver import ShiritoriSolver  # noqa: E402


class ShiritoriSolverTest(unittest.TestCase):
    @staticmethod
    def solver(words: list[str]) -> tuple[RuntimeDictionary, ShiritoriSolver]:
        runtime = RuntimeDictionary.from_readings(words)
        return runtime, ShiritoriSolver(runtime.to_edge_dictionary())

    def test_no_available_word_is_losing(self) -> None:
        runtime, solver = self.solver(["あい"])
        self.assertFalse(solver.solve(runtime.char_to_id["い"]))

    def test_word_ending_with_n_is_not_a_winning_move(self) -> None:
        runtime, solver = self.solver(["あん"])
        a_id = runtime.char_to_id["あ"]
        self.assertFalse(solver.solve(a_id))
        self.assertIsNone(solver.get_best_edge(a_id))

    def test_position_with_move_to_opponent_loss_is_winning(self) -> None:
        runtime, solver = self.solver(["あい", "いん"])
        a_id = runtime.char_to_id["あ"]
        i_id = runtime.char_to_id["い"]
        self.assertTrue(solver.solve(a_id))
        self.assertEqual(solver.get_best_edge(a_id), (a_id, i_id))

    def test_first_move_ending_with_n_is_losing(self) -> None:
        _runtime, solver = self.solver(["りん"])
        result = solver.analyze_first_moves()[0]
        self.assertEqual(result.result, "lose")

    def test_parallel_edge_capacity_changes_exact_result(self) -> None:
        one_runtime, one_solver = self.solver(["ああ", "あん"])
        two_runtime, two_solver = self.solver(["ああ", "あかあ", "あん"])
        self.assertTrue(one_solver.solve(one_runtime.char_to_id["あ"]))
        self.assertFalse(two_solver.solve(two_runtime.char_to_id["あ"]))

    def test_first_move_results_are_edge_types_with_multiplicity(self) -> None:
        runtime, solver = self.solver(["あい", "あかい", "いん"])
        results = solver.analyze_first_moves(stop_on_first_win=False)
        self.assertEqual(len(results), 2)
        parallel = next(result for result in results if result.start_char == "あ")
        self.assertEqual(parallel.edge_count, 2)
        self.assertFalse(hasattr(parallel, "word"))
        self.assertFalse(hasattr(parallel, "word_id"))

        run_row, move_rows, _char_rows, _dictionary_rows = run_edge_exact(
            runtime.to_edge_dictionary(),
            dict_size=3,
            random_seed=0,
            max_states=None,
            timeout_sec=None,
        )
        self.assertEqual(len(move_rows), 1)
        self.assertTrue(all("word" not in row and "word_id" not in row for row in move_rows))
        self.assertEqual(run_row["decision_status"], "win_found")
        self.assertEqual(run_row["analyzed_first_edge_type_count"], 1)
        self.assertFalse(run_row["first_move_scan_complete"])
        self.assertEqual(run_row["winning_first_move_count"], 2)
        self.assertEqual(run_row["state_encoding"], "mixed_radix_edge_usage_v1")

    def test_first_move_search_stops_after_first_winning_edge(self) -> None:
        _runtime, solver = self.solver(["あい", "いん", "かん"])
        results = solver.analyze_first_moves()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_winning)
        self.assertEqual(results, solver.last_first_move_results)

    def test_first_move_search_scans_every_edge_to_prove_loss(self) -> None:
        _runtime, solver = self.solver(["あん", "いん"])
        results = solver.analyze_first_moves()

        self.assertEqual(len(results), solver.edge_type_count)
        self.assertFalse(any(result.is_winning for result in results))

    def test_edge_solver_matches_legacy_word_solver_on_small_graph(self) -> None:
        words = ["あい", "あかい", "いあ", "いん", "いす", "すあ"]
        runtime, solver = self.solver(words)
        graph = WordGraph.from_words(words)
        memo: dict[tuple[str, int], bool] = {}

        def legacy_solve(current_char: str, used_mask: int) -> bool:
            state = (current_char, used_mask)
            if state in memo:
                return memo[state]
            for word_id in graph.available_word_ids_mask(current_char, used_mask):
                end_char = graph.end_chars[word_id]
                if end_char == "ん":
                    continue
                if not legacy_solve(end_char, used_mask | (1 << word_id)):
                    memo[state] = True
                    return True
            memo[state] = False
            return False

        for char, char_id in runtime.char_to_id.items():
            self.assertEqual(
                solver.solve(char_id),
                legacy_solve(char, 0),
                char,
            )

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

    def test_exact_experiment_accepts_explicit_runtime_without_length_options(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["experiments_exact.py", "--runtime", "D100.runtime.json"],
        ):
            args = parse_exact_args()
        self.assertEqual(args.runtime, ["D100.runtime.json"])

    def test_exact_experiment_accepts_runtime_prefix_growth(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "experiments_exact.py",
                "--runtime-prefix",
                "D10000.runtime.json",
                "--size-start",
                "100",
                "--size-step",
                "50",
            ],
        ):
            args = parse_exact_args()
        self.assertEqual(args.runtime_prefix, ["D10000.runtime.json"])
        self.assertIsNone(args.sizes)

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
