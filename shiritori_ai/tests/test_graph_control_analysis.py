from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from analyze_graph_control_comparison import (  # noqa: E402
    _format_plot_value,
    aggregate_matches,
    remaining_bin,
    wilson_interval,
)
from run_graph_control_comparison import (  # noqa: E402
    expected_jobs,
    experiment_config,
    parse_args,
)


class GraphControlComparisonTest(unittest.TestCase):
    def test_quick_runs_graph_control_against_every_agent_both_seats(self) -> None:
        config = experiment_config(True, 0.2)
        jobs = expected_jobs(config)
        pairs = {(first, second) for _, _, first, second, _ in jobs}
        for opponent in config["agents"]:
            if opponent == "graph_control":
                continue
            self.assertIn(("graph_control", opponent), pairs)
            self.assertIn((opponent, "graph_control"), pairs)
        self.assertTrue(
            all("graph_control" in {first, second} for first, second in pairs)
        )

    def test_full_has_all_sizes_seeds_and_stochastic_repetitions(self) -> None:
        config = experiment_config(False, 1.0)
        jobs = expected_jobs(config)
        self.assertEqual(2400, len(jobs))
        random_pair = [
            job
            for job in jobs
            if job[0] == 1000
            and job[1] == 0
            and job[2:4] == ("random", "greedy")
        ]
        deterministic_pair = [
            job
            for job in jobs
            if job[0] == 1000
            and job[1] == 0
            and job[2:4] == ("greedy", "minimax")
        ]
        self.assertEqual(5, len(random_pair))
        self.assertEqual(1, len(deterministic_pair))

    def test_d5000_scope_runs_all_agents_and_three_seeds(self) -> None:
        args = parse_args(
            ["--full", "--sizes", "5000", "--seeds", "0,1,2"]
        )
        config = experiment_config(
            False,
            args.time_limit_sec,
            sizes=args.sizes,
            seeds=args.seeds,
            agents=args.agents,
            stochastic_repetitions=args.stochastic_repetitions,
        )
        jobs = expected_jobs(config)
        self.assertEqual("D5000", config["output_scope"])
        self.assertEqual([5000], config["dictionary_sizes"])
        self.assertEqual([0, 1, 2], config["dictionary_seeds"])
        self.assertEqual(480, len(jobs))

    def test_agent_subset_is_available_for_larger_dictionary_followup(self) -> None:
        args = parse_args(
            [
                "--full",
                "--sizes",
                "10000,20000",
                "--agents",
                "alpha_beta,pvs,graph_control",
            ]
        )
        config = experiment_config(
            False,
            args.time_limit_sec,
            sizes=args.sizes,
            seeds=args.seeds,
            agents=args.agents,
        )
        self.assertEqual(
            ["alpha_beta", "pvs", "graph_control"], config["agents"]
        )
        self.assertEqual(36, len(expected_jobs(config)))

    def test_remaining_bins_match_required_boundaries(self) -> None:
        self.assertEqual("80-100%", remaining_bin(0.81))
        self.assertEqual("60-80%", remaining_bin(0.8))
        self.assertEqual("40-60%", remaining_bin(0.6))
        self.assertEqual("20-40%", remaining_bin(0.4))
        self.assertEqual("0-20%", remaining_bin(0.2))

    def test_wilson_interval_contains_observed_rate(self) -> None:
        low, high = wilson_interval(6, 10)
        self.assertLessEqual(low, 0.6)
        self.assertGreaterEqual(high, 0.6)

    def test_plot_value_format_uses_percentages_for_rates(self) -> None:
        self.assertEqual("88.3%", _format_plot_value(0.883, "Win rate"))
        self.assertEqual("1,234", _format_plot_value(1234.0, "Games"))
        self.assertEqual("0.119", _format_plot_value(0.1192, "Seconds"))

    def test_aggregate_credits_winner_to_correct_seat(self) -> None:
        match = {
            "match_id": "m1",
            "dict_size": 10,
            "dictionary_seed": 0,
            "repetition": 0,
            "first_agent": "graph_control",
            "second_agent": "greedy",
            "winner": "second",
            "turn_count": 1,
            "first_timeout_count": 0,
            "second_timeout_count": 0,
            "invalid_move_count": 0,
            "history": [
                {
                    "player": "first",
                    "agent": "graph_control",
                    "elapsed_time_sec": 0.01,
                    "nodes_searched": 0,
                    "ordering_evaluations": 2,
                }
            ],
        }
        overall = {
            row["agent"]: row for row in aggregate_matches([match])["overall"]
        }
        self.assertEqual(0, overall["graph_control"]["wins"])
        self.assertEqual(1, overall["greedy"]["wins"])

    def test_overall_without_random_excludes_whole_random_match(self) -> None:
        matches = [
            {
                "match_id": "random-vs-greedy",
                "dict_size": 10,
                "dictionary_seed": 0,
                "repetition": 0,
                "first_agent": "random",
                "second_agent": "greedy",
                "winner": "second",
                "turn_count": 1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
                "invalid_move_count": 0,
                "history": [],
            },
            {
                "match_id": "minimax-vs-greedy",
                "dict_size": 10,
                "dictionary_seed": 0,
                "repetition": 0,
                "first_agent": "minimax",
                "second_agent": "greedy",
                "winner": "first",
                "turn_count": 1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
                "invalid_move_count": 0,
                "history": [],
            },
        ]
        rows = {
            row["agent"]: row
            for row in aggregate_matches(matches)["overall_without_random"]
        }
        self.assertNotIn("random", rows)
        self.assertEqual(1, rows["minimax"]["games"])
        self.assertEqual(1.0, rows["minimax"]["win_rate"])
        self.assertEqual(1, rows["greedy"]["games"])
        self.assertEqual(0.0, rows["greedy"]["win_rate"])


if __name__ == "__main__":
    unittest.main()
