from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AlphaBetaAgent,
    DEFAULT_TIME_LIMIT_SEC,
    GameState,
    GreedyAgent,
    MinimaxAgent,
    MonteCarloAgent,
    RandomAgent,
    build_agent,
)
from experiments_approx import (  # noqa: E402
    AI_MATCH_TIME_LIMIT_SEC,
    build_match_flow_rows,
    parse_args as parse_approx_args,
    rows_without_self_matches,
    summarize_agent_end_chars,
    summarize_agents,
    summarize_first_player_by_size,
    summarize_top_end_chars,
)
from dictionary_stats import dictionary_char_total_rows  # noqa: E402
from game import WordGraph  # noqa: E402
from human_cli import parse_args as parse_human_args  # noqa: E402
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

    def test_each_agent_returns_move_on_small_dictionary(self) -> None:
        graph = WordGraph.from_words(["あい", "いぬ", "ぬの", "のり", "りんご", "ごん"])
        state = GameState(current_char=None, used_ids=frozenset())
        agents = [
            RandomAgent(time_limit_sec=0.01, random_seed=1),
            GreedyAgent(time_limit_sec=0.01),
            MinimaxAgent(time_limit_sec=0.01, depth=2, branch_limit=4),
            MonteCarloAgent(time_limit_sec=0.01, random_seed=1, candidate_limit=4, playouts_per_move=2),
            AlphaBetaAgent(time_limit_sec=0.01, depth=2, branch_limit=4),
            build_agent("alpha_beta", time_limit_sec=0.01, minimax_depth=2, branch_limit=4),
        ]
        for agent in agents:
            with self.subTest(agent=agent.name):
                decision = agent.choose_move(graph, state)
                self.assertIsNotNone(decision.word_id)
                self.assertIn(decision.word_id, range(len(graph.words)))

    def test_adaptive_depth_decreases_after_timeout(self) -> None:
        graph = WordGraph.from_words(["あい", "いあ"])
        state = GameState(current_char=None, used_ids=frozenset())
        agent = MinimaxAgent(time_limit_sec=0.0, depth=2, branch_limit=2)
        decision = agent.choose_move(graph, state)
        self.assertTrue(decision.timed_out)
        self.assertEqual(decision.extra["effective_depth"], 2)
        self.assertEqual(agent.current_depth, 1)

    def test_alpha_beta_default_depth_is_four(self) -> None:
        agent = build_agent("alpha_beta")
        self.assertIsInstance(agent, AlphaBetaAgent)
        self.assertEqual(agent.depth, 4)
        self.assertEqual(AlphaBetaAgent().depth, 4)

    def test_default_turn_timeouts(self) -> None:
        self.assertEqual(DEFAULT_TIME_LIMIT_SEC, 2.0)
        self.assertEqual(AI_MATCH_TIME_LIMIT_SEC, 4.0)
        self.assertEqual(GreedyAgent().time_limit_sec, 2.0)
        self.assertEqual(MinimaxAgent().time_limit_sec, 2.0)
        self.assertEqual(MonteCarloAgent().time_limit_sec, 2.0)
        self.assertEqual(build_agent("greedy").time_limit_sec, 2.0)

        with patch.object(sys, "argv", ["human_cli.py", "--words", "dummy.csv"]):
            self.assertEqual(parse_human_args().time_limit_sec, 2.0)
        with patch.object(sys, "argv", ["experiments_approx.py", "--records", "dummy.csv"]):
            self.assertEqual(parse_approx_args().time_limit_sec, 4.0)

    def test_alpha_beta_depth_can_be_configured_independently(self) -> None:
        agent = build_agent("alpha_beta", minimax_depth=3, alpha_beta_depth=2)
        self.assertIsInstance(agent, AlphaBetaAgent)
        self.assertEqual(agent.depth, 2)

    def test_agents_return_none_without_legal_moves(self) -> None:
        graph = WordGraph.from_words(["あい"])
        state = GameState(current_char="か", used_ids=frozenset())
        for agent in [GreedyAgent(), MinimaxAgent(), MonteCarloAgent(), AlphaBetaAgent()]:
            with self.subTest(agent=agent.name):
                self.assertIsNone(agent.choose_move(graph, state).word_id)

    def test_agents_do_not_crash_when_only_n_ending_move_exists(self) -> None:
        graph = WordGraph.from_words(["あん"])
        state = GameState(current_char="あ", used_ids=frozenset())
        for agent in [GreedyAgent(), MinimaxAgent(), MonteCarloAgent(), AlphaBetaAgent()]:
            with self.subTest(agent=agent.name):
                decision = agent.choose_move(graph, state)
                self.assertEqual(decision.word_id, 0)

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
            second_agent=RandomAgent(time_limit_sec=0.01, random_seed=1),
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
                    "first_agent": result.first_agent,
                    "second_agent": result.second_agent,
                    "winner": result.winner,
                }
            ]
        )
        top_end_rows = summarize_top_end_chars(flow_rows, top_n=5)
        self.assertEqual(len(flow_rows), result.turn_count)
        self.assertEqual(flow_rows[0]["matchup"], "greedy vs random")
        self.assertIn("chain_so_far", flow_rows[0])
        self.assertTrue(any(row["agent_name"] == "greedy" for row in stats_rows))
        self.assertEqual(first_player_rows[0]["match_count"], 1)
        self.assertGreaterEqual(len(top_end_rows), 1)

    def test_self_matches_are_excluded_from_win_statistics(self) -> None:
        rows = [
            {
                "dict_size": 3,
                "first_agent": "greedy",
                "second_agent": "greedy",
                "winner": "first",
                "turn_count": 3,
                "used_word_count": 3,
                "first_total_time_sec": 0.1,
                "second_total_time_sec": 0.1,
                "first_max_time_sec": 0.1,
                "second_max_time_sec": 0.1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
            },
            {
                "dict_size": 3,
                "first_agent": "greedy",
                "second_agent": "random",
                "winner": "first",
                "turn_count": 3,
                "used_word_count": 3,
                "first_total_time_sec": 0.1,
                "second_total_time_sec": 0.1,
                "first_max_time_sec": 0.1,
                "second_max_time_sec": 0.1,
                "first_timeout_count": 0,
                "second_timeout_count": 0,
            },
        ]
        self.assertEqual(len(rows_without_self_matches(rows)), 1)
        summary_rows = summarize_agents(rows)
        greedy_row = next(row for row in summary_rows if row["agent_name"] == "greedy")
        self.assertEqual(greedy_row["match_count"], 1)
        self.assertEqual(greedy_row["win_count"], 1)


if __name__ == "__main__":
    unittest.main()
