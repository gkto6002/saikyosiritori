from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AggressivePVSAgent,
    AlphaBetaAgent,
    BeamNegamaxAgent,
    MinimaxAgent,
    MonteCarloAgent,
    SearchStats,
    SearchTimeout,
    build_agent,
)
from experiments_approx import parse_args as parse_approx_args  # noqa: E402
from game import WordGraph  # noqa: E402
from human_cli import parse_args as parse_human_args  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402
from search_common import (  # noqa: E402
    GameState,
    edge_position_metrics,
    evaluate_edge_candidate,
    evaluate_word_candidate,
    survival_weight_for_metrics,
)


SEARCH_AGENT_CLASSES = [
    MinimaxAgent,
    AlphaBetaAgent,
    BeamNegamaxAgent,
    AggressivePVSAgent,
]


class SearchAgentTest(unittest.TestCase):
    @staticmethod
    def runtime(words: list[str]) -> RuntimeDictionary:
        return RuntimeDictionary.from_readings(words)

    def test_timeout_restores_edge_state_and_is_not_zero_score(self) -> None:
        runtime = self.runtime(["あい", "あう", "いあ", "うあ", "いん"])
        method_names = {
            MinimaxAgent: "_edge_negamax",
            AlphaBetaAgent: "_edge_negamax_alpha_beta",
            BeamNegamaxAgent: "_edge_negamax",
            AggressivePVSAgent: "_pvs_edge",
        }
        for agent_class in SEARCH_AGENT_CLASSES:
            with self.subTest(agent=agent_class.__name__):
                state = AIEdgeState.initial(runtime)
                before = (
                    state.required_char_id,
                    list(state.edge_counts),
                    list(state.active_end_masks),
                    list(state.edge_history),
                )
                agent = agent_class(time_limit_sec=10.0, depth=2)
                with patch.object(
                    agent,
                    method_names[agent_class],
                    side_effect=SearchTimeout,
                ):
                    decision = agent.choose_edge(state)
                self.assertTrue(decision.timed_out)
                self.assertNotEqual(decision.score, 0.0)
                self.assertEqual(decision.extra["completed_root_moves"], 0)
                self.assertEqual(
                    (
                        state.required_char_id,
                        state.edge_counts,
                        state.active_end_masks,
                        state.edge_history,
                    ),
                    before,
                )

    def test_all_search_agents_share_adaptive_depth_rules(self) -> None:
        for agent_class in SEARCH_AGENT_CLASSES:
            with self.subTest(agent=agent_class.__name__):
                agent = agent_class(
                    depth=3,
                    adaptive_depth=True,
                    min_depth=1,
                    depth_recovery_turns=3,
                )
                agent._record_depth_result(True)
                self.assertEqual(agent.current_depth, 2)
                agent._record_depth_result(False)
                agent._record_depth_result(False)
                self.assertEqual(agent.current_depth, 2)
                agent._record_depth_result(False)
                self.assertEqual(agent.current_depth, 3)

    def test_minimax_and_alpha_beta_do_not_limit_candidates_by_default(self) -> None:
        runtime = self.runtime(["あい", "あう", "あえ", "いん", "うん", "えん"])
        edge_type_count = len(AIEdgeState.initial(runtime).available_edges())
        for agent in [
            MinimaxAgent(time_limit_sec=10.0, depth=1, adaptive_depth=False),
            AlphaBetaAgent(time_limit_sec=10.0, depth=1, adaptive_depth=False),
        ]:
            with self.subTest(agent=agent.name):
                self.assertIsNone(agent.branch_limit)
                decision = agent.choose_edge(AIEdgeState.initial(runtime))
                self.assertFalse(decision.timed_out)
                self.assertEqual(decision.extra["completed_root_moves"], edge_type_count)

    def test_beam_negamax_prunes_by_beam_only(self) -> None:
        runtime = self.runtime(["あい", "あう", "あえ", "いん", "うん", "えん"])
        agent = BeamNegamaxAgent(
            time_limit_sec=10.0,
            depth=1,
            beam_widths=(2,),
            adaptive_depth=False,
        )
        decision = agent.choose_edge(AIEdgeState.initial(runtime))
        self.assertEqual(decision.extra["completed_root_moves"], 2)
        self.assertGreater(decision.extra["beam_pruned_move_count"], 0)
        self.assertEqual(decision.extra["cutoff_count"], 0)
        self.assertEqual(decision.extra["pruned_move_count"], 0)

    def test_pvs_matches_alpha_beta_and_uses_null_window_and_research(self) -> None:
        words = ["いう", "えあ", "あえ", "うえ", "うう", "あい"]
        runtime = self.runtime(words)
        alpha_beta = AlphaBetaAgent(
            time_limit_sec=10.0, depth=4, adaptive_depth=False
        ).choose_edge(AIEdgeState.initial(runtime))
        pvs = AggressivePVSAgent(
            time_limit_sec=10.0, depth=4, adaptive_depth=False
        ).choose_edge(AIEdgeState.initial(runtime))
        self.assertEqual((pvs.start_id, pvs.end_id), (alpha_beta.start_id, alpha_beta.end_id))
        self.assertEqual(pvs.score, alpha_beta.score)
        self.assertGreater(pvs.extra["null_window_search_count"], 0)
        self.assertGreater(pvs.extra["research_count"], 0)

    def test_immediate_win_is_preferred(self) -> None:
        runtime = self.runtime(["あい", "あう", "うあ"])
        state = AIEdgeState.initial(runtime)
        a_id = runtime.char_to_id["あ"]
        i_id = runtime.char_to_id["い"]
        u_id = runtime.char_to_id["う"]
        winning = evaluate_edge_candidate(state, a_id, i_id)
        continuing = evaluate_edge_candidate(state, a_id, u_id)
        self.assertTrue(winning.immediate_win)
        self.assertGreater(winning.total_score, continuing.total_score)

    def test_shorter_win_and_longer_loss_are_preferred(self) -> None:
        win_runtime = self.runtime(["あい", "かく", "くけ", "けこ"])
        state = AIEdgeState.initial(win_runtime)
        agent = MinimaxAgent(time_limit_sec=10.0, depth=6, adaptive_depth=False)
        stats = SearchStats()
        deadline = time.perf_counter() + 10.0
        short_win = agent._score_edge(
            state,
            win_runtime.char_to_id["あ"],
            win_runtime.char_to_id["い"],
            6,
            deadline,
            stats,
        )
        long_win = agent._score_edge(
            state,
            win_runtime.char_to_id["か"],
            win_runtime.char_to_id["く"],
            6,
            deadline,
            stats,
        )
        self.assertGreater(short_win, long_win)

        loss_runtime = self.runtime(["あい", "いう", "かき", "きく", "くけ", "けこ"])
        loss_state = AIEdgeState.initial(loss_runtime)
        short_loss = agent._score_edge(
            loss_state,
            loss_runtime.char_to_id["あ"],
            loss_runtime.char_to_id["い"],
            6,
            deadline,
            SearchStats(),
        )
        long_loss = agent._score_edge(
            loss_state,
            loss_runtime.char_to_id["か"],
            loss_runtime.char_to_id["き"],
            6,
            deadline,
            SearchStats(),
        )
        self.assertGreater(long_loss, short_loss)

    def test_normal_position_keeps_attack_priority(self) -> None:
        words = [
            "かあ", "うか", "かえ", "えお", "いえ", "おあ", "ああ",
            "えか", "かん", "おん", "おか", "うん", "おえ", "えい",
        ]
        graph = WordGraph.from_words(words)
        state = GameState(None)
        attack = evaluate_word_candidate(graph, state, words.index("かあ"))
        survival = evaluate_word_candidate(graph, state, words.index("うか"))
        self.assertEqual(attack.survival_weight, 0.15)
        self.assertGreater(attack.attack_score, survival.attack_score)
        self.assertLess(attack.survival_score, survival.survival_score)
        self.assertGreater(attack.total_score, survival.total_score)

    def test_critical_position_prefers_survival_then_attack(self) -> None:
        words = ["かえ", "あえ", "かん", "うえ", "いお", "うい", "かい", "あか", "ええ", "えん"]
        graph = WordGraph.from_words(words)
        state = GameState("あ")
        durable = evaluate_word_candidate(graph, state, words.index("あか"))
        attacking = evaluate_word_candidate(graph, state, words.index("あえ"))
        self.assertEqual(durable.survival_weight, 1.5)
        self.assertGreater(durable.survival_score, attacking.survival_score)
        self.assertGreater(durable.total_score, attacking.total_score)

        equal_words = ["おえ", "いか", "かお", "うあ", "あお", "えん", "かん", "おう", "えあ", "えお"]
        equal_graph = WordGraph.from_words(equal_words)
        equal_state = GameState("お")
        stronger_attack = evaluate_word_candidate(
            equal_graph, equal_state, equal_words.index("おう")
        )
        weaker_attack = evaluate_word_candidate(
            equal_graph, equal_state, equal_words.index("おえ")
        )
        self.assertEqual(stronger_attack.survival_score, weaker_attack.survival_score)
        self.assertGreater(stronger_attack.attack_score, weaker_attack.attack_score)
        self.assertGreater(stronger_attack.total_score, weaker_attack.total_score)

    def test_one_safe_edge_type_is_critical_even_with_many_words(self) -> None:
        runtime = self.runtime(["あい", "あかい", "あさい", "あたい"])
        state = AIEdgeState.initial(runtime)
        state.required_char_id = runtime.char_to_id["あ"]
        metrics = edge_position_metrics(state)
        self.assertEqual(metrics.safe_word_count, 4)
        self.assertEqual(metrics.safe_edge_type_count, 1)
        self.assertEqual(survival_weight_for_metrics(metrics), 1.5)

    def test_monte_carlo_round_robin_counts_are_balanced(self) -> None:
        runtime = self.runtime(["あい", "あう", "あえ", "いあ", "うあ", "えあ"])
        decision = MonteCarloAgent(
            time_limit_sec=10.0,
            random_seed=7,
            candidate_limit=6,
            playouts_per_move=4,
            max_playout_moves=5,
        ).choose_edge(AIEdgeState.initial(runtime))
        counts = decision.extra["playout_counts"]
        self.assertEqual(decision.extra["playout_schedule"], "round_robin")
        self.assertLessEqual(max(counts) - min(counts), 1)

    def test_new_agents_are_available_from_factory(self) -> None:
        self.assertIsInstance(build_agent("beam_negamax"), BeamNegamaxAgent)
        self.assertIsInstance(build_agent("aggressive_pvs"), AggressivePVSAgent)

    def test_new_agents_and_search_options_are_available_in_clis(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "experiments_approx.py",
                "--runtime",
                "D100.runtime.json",
                "--agents",
                "beam_negamax",
                "aggressive_pvs",
                "--beam-widths",
                "8,4,2",
            ],
        ):
            approx = parse_approx_args()
        self.assertEqual(approx.agents, ["beam_negamax", "aggressive_pvs"])
        self.assertEqual(approx.beam_widths, (8, 4, 2))
        self.assertIsNone(approx.branch_limit)

        with patch.object(
            sys,
            "argv",
            [
                "human_cli.py",
                "--runtime",
                "D100.runtime.json",
                "--agent",
                "aggressive_pvs",
            ],
        ):
            human = parse_human_args()
        self.assertEqual(human.agent, "aggressive_pvs")


if __name__ == "__main__":
    unittest.main()
