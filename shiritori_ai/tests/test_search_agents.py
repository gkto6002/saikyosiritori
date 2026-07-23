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
    RiskLevel,
    edge_position_metrics,
    evaluate_edge_candidate,
    evaluate_ordering_score,
    evaluate_word_candidate,
    risk_level_for_metrics,
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
                    list(state.remaining_word_counts),
                    list(state.remaining_safe_word_counts),
                    list(state.active_edge_type_counts),
                    list(state.active_safe_edge_type_counts),
                    list(state.destination_masks),
                    list(state.safe_destination_masks),
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
                        state.remaining_word_counts,
                        state.remaining_safe_word_counts,
                        state.active_edge_type_counts,
                        state.active_safe_edge_type_counts,
                        state.destination_masks,
                        state.safe_destination_masks,
                    ),
                    before,
                )
                state.assert_aggregates_consistent()

    def test_all_search_agents_share_soft_timeout_depth_rules(self) -> None:
        for agent_class in SEARCH_AGENT_CLASSES:
            with self.subTest(agent=agent_class.__name__):
                agent = agent_class(
                    depth=3,
                    adaptive_depth=True,
                    min_depth=1,
                    depth_recovery_turns=5,
                )
                agent._record_depth_result(True)
                self.assertEqual(agent.current_depth, 2)
                agent._record_depth_result(False, 0.85)
                self.assertEqual(agent.current_depth, 2)
                self.assertEqual(agent._non_timeout_streak, 0)
                for _ in range(4):
                    agent._record_depth_result(False, 0.5)
                self.assertEqual(agent.current_depth, 2)
                agent._record_depth_result(False, 0.5)
                self.assertEqual(agent.current_depth, 3)
                agent._record_depth_result(False, 0.91)
                self.assertEqual(agent.current_depth, 2)

    def test_search_agents_use_lightweight_default_limits(self) -> None:
        for agent in [
            MinimaxAgent(time_limit_sec=10.0, depth=1, adaptive_depth=False),
            AlphaBetaAgent(time_limit_sec=10.0, depth=1, adaptive_depth=False),
            AggressivePVSAgent(time_limit_sec=10.0, depth=1, adaptive_depth=False),
        ]:
            with self.subTest(agent=agent.name):
                self.assertEqual(agent.branch_limit, 12)
        self.assertEqual(AlphaBetaAgent().depth, 3)
        self.assertEqual(AggressivePVSAgent().depth, 3)
        self.assertEqual(BeamNegamaxAgent().depth, 4)
        self.assertEqual(BeamNegamaxAgent().beam_widths, (12, 8, 4, 2))

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
        self.assertEqual(
            pvs.extra["research_rate"],
            pvs.extra["research_count"] / pvs.extra["null_window_searches"],
        )
        self.assertEqual(
            (
                runtime.id_to_char[pvs.start_id],
                runtime.id_to_char[pvs.end_id],
            ),
            ("う", "え"),
        )

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

        limited = AlphaBetaAgent(
            time_limit_sec=10.0,
            depth=1,
            branch_limit=1,
            adaptive_depth=False,
        ).choose_edge(AIEdgeState.initial(runtime))
        self.assertEqual((limited.start_id, limited.end_id), (a_id, i_id))

    def test_ordering_evaluation_never_runs_survival_search(self) -> None:
        runtime = self.runtime(["あい", "いう", "うあ"])
        state = AIEdgeState.initial(runtime)
        a_id = runtime.char_to_id["あ"]
        i_id = runtime.char_to_id["い"]
        with patch(
            "search_common._combine_survival_samples",
            side_effect=AssertionError("survival search must not run"),
        ):
            evaluation = evaluate_ordering_score(state, a_id, i_id)
        self.assertFalse(evaluation.immediate_loss)
        self.assertEqual(evaluation.survival_score, 0.0)
        state.assert_aggregates_consistent()

    def test_risk_levels_select_normal_simple_and_full_survival(self) -> None:
        cases = [
            (
                "normal",
                [
                    "あい", "あかい", "あさい",
                    "あう", "あかう", "あさう",
                    "あえ", "あかえ", "あさえ",
                    "あお", "あかお", "あさお",
                    "いか",
                ],
                RiskLevel.NORMAL,
                0,
                0,
            ),
            (
                "caution",
                ["あい", "あかい", "あう", "あかう", "あえ", "あお", "いか"],
                RiskLevel.CAUTION,
                1,
                0,
            ),
            (
                "danger",
                ["あい", "あう", "あえ", "あお", "いか"],
                RiskLevel.DANGER,
                0,
                1,
            ),
            (
                "critical",
                ["あい", "あう", "いか"],
                RiskLevel.CRITICAL,
                0,
                1,
            ),
        ]
        for name, words, expected_risk, simple_count, full_count in cases:
            with self.subTest(risk=name):
                runtime = self.runtime(words)
                state = AIEdgeState.initial(runtime)
                a_id = runtime.char_to_id["あ"]
                i_id = runtime.char_to_id["い"]
                state.required_char_id = a_id
                metrics = edge_position_metrics(state)
                self.assertEqual(risk_level_for_metrics(metrics), expected_risk)
                stats = SearchStats()
                evaluation = evaluate_edge_candidate(
                    state,
                    a_id,
                    i_id,
                    stats=stats,
                )
                self.assertEqual(stats.simple_survival_evaluations, simple_count)
                self.assertEqual(stats.full_survival_evaluations, full_count)
                if expected_risk is RiskLevel.NORMAL:
                    self.assertEqual(evaluation.survival_weight, 0.0)
                state.assert_aggregates_consistent()

    def test_search_extra_contains_timing_and_evaluation_counters(self) -> None:
        runtime = self.runtime(["あい", "あう", "いあ", "うあ"])
        decision = AlphaBetaAgent(
            time_limit_sec=10.0,
            depth=2,
            branch_limit=12,
            adaptive_depth=False,
        ).choose_edge(AIEdgeState.initial(runtime))
        required = {
            "ordering_time_sec",
            "evaluation_time_sec",
            "search_time_sec",
            "total_search_time_sec",
            "nodes_searched",
            "leaf_evaluations",
            "ordering_evaluations",
            "full_survival_evaluations",
            "simple_survival_evaluations",
            "completed_root_moves",
            "effective_depth",
            "next_depth",
            "timed_out",
        }
        self.assertTrue(required.issubset(decision.extra))
        self.assertGreaterEqual(decision.extra["ordering_time_sec"], 0.0)
        self.assertGreaterEqual(decision.extra["evaluation_time_sec"], 0.0)

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
        self.assertEqual(approx.branch_limit, 12)
        self.assertEqual(approx.alpha_beta_depth, 3)
        self.assertEqual(approx.aggressive_pvs_depth, 3)
        self.assertEqual(approx.depth_recovery_turns, 5)

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
