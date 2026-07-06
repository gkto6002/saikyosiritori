from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import GreedyAgent, RandomAgent  # noqa: E402
from experiments_approx import (  # noqa: E402
    build_match_flow_rows,
    summarize_agent_end_chars,
    summarize_first_player_by_size,
    summarize_top_end_chars,
)
from dictionary_stats import dictionary_char_total_rows  # noqa: E402
from game import WordGraph  # noqa: E402
from match import simulate_match  # noqa: E402


class AgentsMatchTest(unittest.TestCase):
    def test_o_and_wo_are_same_transition_character(self) -> None:
        graph = WordGraph.from_words(["ところを", "おもち", "をことてん"])
        self.assertEqual(graph.end_chars[0], "お")
        self.assertEqual(graph.start_chars[1], "お")
        self.assertEqual(graph.start_chars[2], "お")
        self.assertEqual(
            [graph.words[word_id] for word_id in graph.available_word_ids_set("を", {0})],
            ["おもち", "をことてん"],
        )
        char_rows = dictionary_char_total_rows(graph, dict_size=3, random_seed=0)
        o_row = next(row for row in char_rows if row["char"] == "お")
        self.assertEqual(o_row["start_count"], 2)
        self.assertEqual(o_row["end_count"], 1)
        self.assertEqual(o_row["total_count"], 3)

    def test_approximate_agents_can_finish_match_and_record_timing(self) -> None:
        graph = WordGraph.from_words(["あい", "いぬ", "ぬの", "のり", "りんご", "ごん"])
        result = simulate_match(
            graph=graph,
            first_agent=GreedyAgent(time_limit_sec=0.01),
            second_agent=RandomAgent(time_limit_sec=0.01, random_seed=1),
            max_moves=20,
            max_match_time_sec=5.0,
        )

        self.assertIn(result.winner, {"first", "second", "draw"})
        self.assertGreaterEqual(result.turn_count, 1)
        self.assertGreaterEqual(result.first_total_time_sec, 0.0)
        self.assertGreaterEqual(result.second_total_time_sec, 0.0)
        self.assertIn("required_start_char", result.history[0])

    def test_match_timeout_is_distinct_from_turn_timeout(self) -> None:
        graph = WordGraph.from_words(["あい", "いあ"])
        result = simulate_match(
            graph=graph,
            first_agent=GreedyAgent(time_limit_sec=1.0),
            second_agent=GreedyAgent(time_limit_sec=1.0),
            max_moves=100,
            max_match_time_sec=0.0,
        )
        self.assertEqual(result.loss_reason, "match_timeout")
        self.assertEqual(result.winner, "draw")

    def test_match_flow_and_end_char_stats_are_generated(self) -> None:
        graph = WordGraph.from_words(["あい", "いぬ", "ぬん"])
        result = simulate_match(
            graph=graph,
            first_agent=GreedyAgent(time_limit_sec=0.01),
            second_agent=GreedyAgent(time_limit_sec=0.01),
            max_moves=10,
            max_match_time_sec=5.0,
            match_id="test",
        )
        flow_rows = build_match_flow_rows(result, "test", len(graph.words), 0)
        stats_rows = summarize_agent_end_chars(flow_rows)
        first_player_rows = summarize_first_player_by_size(
            [
                {
                    "dict_size": len(graph.words),
                    "winner": result.winner,
                }
            ]
        )
        top_end_rows = summarize_top_end_chars(flow_rows, top_n=5)
        self.assertEqual(len(flow_rows), result.turn_count)
        self.assertEqual(flow_rows[0]["matchup"], "greedy vs greedy")
        self.assertIn("chain_so_far", flow_rows[0])
        self.assertTrue(any(row["agent_name"] == "greedy" for row in stats_rows))
        self.assertEqual(first_player_rows[0]["match_count"], 1)
        self.assertGreaterEqual(len(top_end_rows), 1)


if __name__ == "__main__":
    unittest.main()
