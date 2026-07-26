from __future__ import annotations

import sys
import unittest
import argparse
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from adaptive_hybrid import (  # noqa: E402
    ADAPTIVE_HYBRID_AGENT_NAMES,
    AdaptiveHybridConfig,
    BranchSwitchAlphaBetaAgent,
    DynamicBeamAlphaBetaAgent,
    DynamicBeamPVSAgent,
    EndgameExactHybridAgent,
    IntegratedAdaptiveHybridAgent,
    ResearchAdaptiveBeamAgent,
    build_adaptive_hybrid_agent,
    adaptive_hybrid_config_from_args,
    add_adaptive_hybrid_cli_arguments,
    position_scale,
)
from agents import SearchStats, SearchTimeout, build_agent  # noqa: E402
from exact_solver import AnalysisLimitExceeded  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


def runtime() -> RuntimeDictionary:
    return RuntimeDictionary.from_readings(
        [
            "あい",
            "あう",
            "あえ",
            "いあ",
            "いう",
            "いえ",
            "うあ",
            "うい",
            "えあ",
            "えん",
        ]
    )


def snapshot(state: AIEdgeState) -> tuple[object, ...]:
    return (
        state.required_char_id,
        tuple(state.edge_counts),
        tuple(state.active_end_masks),
        tuple(state.edge_history),
        tuple(state.remaining_word_counts),
    )


class AdaptiveHybridTest(unittest.TestCase):
    def common(self) -> dict[str, object]:
        return {
            "depth": 3,
            "max_depth": 4,
            "time_limit_sec": 2.0,
            "adaptive_depth": False,
            "random_seed": 17,
            "beam_widths": (5, 4, 3, 2),
        }

    def test_all_agents_return_legal_reproducible_without_mutation(self) -> None:
        for name in ADAPTIVE_HYBRID_AGENT_NAMES:
            with self.subTest(agent=name):
                first_state = AIEdgeState.initial(runtime())
                before = snapshot(first_state)
                legal = set(first_state.available_edges())
                first = build_adaptive_hybrid_agent(
                    name, **self.common()
                ).choose_edge(first_state)
                second = build_adaptive_hybrid_agent(
                    name, **self.common()
                ).choose_edge(AIEdgeState.initial(runtime()))
                self.assertIn((first.start_id, first.end_id), legal)
                self.assertEqual(
                    (first.start_id, first.end_id, first.score),
                    (second.start_id, second.end_id, second.score),
                )
                self.assertEqual(snapshot(first_state), before)
                first_state.assert_aggregates_consistent()

    def test_all_agents_support_adaptive_depth(self) -> None:
        for name in ADAPTIVE_HYBRID_AGENT_NAMES:
            with self.subTest(agent=name):
                agent = build_adaptive_hybrid_agent(
                    name,
                    adaptive_config=AdaptiveHybridConfig(
                        exact_max_reachable_words=1,
                        exact_max_edge_types=1,
                        exact_max_vertices=1,
                        exact_max_state_estimate=1,
                    ),
                    depth=3,
                    max_depth=5,
                    time_limit_sec=2.0,
                    adaptive_depth=True,
                    beam_widths=(4, 3, 2),
                )
                decision = agent.choose_edge(AIEdgeState.initial(runtime()))
                self.assertIsNotNone(decision.start_id)
                self.assertIn("effective_depth", decision.extra)

    def test_branch_switch_uses_both_modes(self) -> None:
        state = AIEdgeState.initial(runtime())
        full = BranchSwitchAlphaBetaAgent(
            **self.common(),
            adaptive_config=AdaptiveHybridConfig(
                branch_switch_threshold=20
            ),
        ).choose_edge(state)
        beam = BranchSwitchAlphaBetaAgent(
            **self.common(),
            adaptive_config=AdaptiveHybridConfig(
                branch_switch_threshold=1
            ),
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(full.extra["search_mode"], "alpha_beta_full")
        self.assertEqual(beam.extra["search_mode"], "beam_alpha_beta")

    def test_dynamic_width_policy_and_recording(self) -> None:
        config = AdaptiveHybridConfig(
            no_prune_threshold=3,
            medium_branch_threshold=10,
            high_branch_threshold=20,
            medium_beam_width=8,
            high_beam_width=6,
            very_high_beam_width=4,
            ply_width_caps=(9, 5, 2),
        )
        agent = DynamicBeamAlphaBetaAgent(
            **self.common(), adaptive_config=config
        )
        self.assertEqual(agent._dynamic_width(3, 0), 3)
        self.assertEqual(agent._dynamic_width(10, 0), 8)
        self.assertEqual(agent._dynamic_width(20, 1), 5)
        self.assertEqual(agent._dynamic_width(100, 2), 2)
        decision = agent.choose_edge(AIEdgeState.initial(runtime()))
        maximums = decision.extra["beam_max_selected_by_ply"]
        for ply, selected in maximums.items():
            cap = config.ply_width_caps[
                min(int(ply), len(config.ply_width_caps) - 1)
            ]
            self.assertLessEqual(int(selected), cap)

    def test_dynamic_pvs_records_research_and_widths(self) -> None:
        decision = DynamicBeamPVSAgent(
            **self.common()
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(decision.extra["search_mode"], "dynamic_beam_pvs")
        self.assertTrue(decision.extra["dynamic_beam_width_counts"])
        self.assertIn("research_count", decision.extra)

    def test_research_policy_switches_on_research_or_budget(self) -> None:
        agent = ResearchAdaptiveBeamAgent(**self.common())
        stats = SearchStats(
            null_window_search_count=10,
            research_count=2,
        )
        mode, reason, _predicted = agent._next_mode(
            "beam_pvs", stats, 0.1, 0.05, 1.0
        )
        self.assertEqual(mode, "beam_alpha_beta")
        self.assertEqual(reason, "pvs_research_rate_above_threshold")
        stats.research_count = 0
        mode, reason, _predicted = agent._next_mode(
            "beam_pvs", stats, 0.9, 0.3, 0.1
        )
        self.assertEqual(mode, "beam_alpha_beta")
        self.assertEqual(
            reason, "predicted_next_depth_exceeds_safe_budget"
        )

    def test_iterative_timeout_keeps_last_completed_move(self) -> None:
        agent = ResearchAdaptiveBeamAgent(
            depth=8,
            max_depth=8,
            time_limit_sec=10.0,
            adaptive_depth=False,
            beam_widths=(4, 3, 2),
        )
        state = AIEdgeState.initial(runtime())
        first_edge = state.available_edges()[0]
        calls = 0

        def fake_run(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return first_edge, 12.0, SearchStats(nodes_searched=3), True
            raise SearchTimeout

        with patch.object(agent, "_run_depth", side_effect=fake_run):
            decision = agent.choose_edge(state)
        self.assertEqual((decision.start_id, decision.end_id), first_edge)
        self.assertTrue(decision.timed_out)
        self.assertEqual(decision.extra["completed_iterative_depth"], 7)
        self.assertEqual(decision.extra["fallback_count"], 1)
        state.assert_aggregates_consistent()

    def test_exact_endgame_matches_solver_and_records_success(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["あい", "いう", "うえ", "えん"]
        )
        state = AIEdgeState.initial(small)
        decision = EndgameExactHybridAgent(
            **self.common()
        ).choose_edge(state)
        self.assertIn(
            (decision.start_id, decision.end_id), state.available_edges()
        )
        self.assertEqual(decision.extra["search_mode"], "exact_endgame")
        self.assertEqual(decision.extra["exact_success_count"], 1)
        self.assertGreater(decision.extra["exact_state_count"], 0)

    def test_exact_limit_falls_back_to_legal_move(self) -> None:
        agent = EndgameExactHybridAgent(**self.common())
        state = AIEdgeState.initial(runtime())
        with patch(
            "adaptive_hybrid.ShiritoriSolver.analyze_first_moves",
            side_effect=AnalysisLimitExceeded("timeout"),
        ):
            decision = agent.choose_edge(state)
        self.assertIn(
            (decision.start_id, decision.end_id), state.available_edges()
        )
        self.assertEqual(decision.extra["search_mode"], "exact_fallback")
        self.assertEqual(decision.extra["exact_timeout_count"], 1)
        self.assertEqual(decision.extra["fallback_count"], 1)

    def test_large_position_skips_exact(self) -> None:
        config = AdaptiveHybridConfig(
            exact_max_reachable_words=1,
            exact_max_edge_types=1,
            exact_max_vertices=1,
            exact_max_state_estimate=1,
        )
        decision = EndgameExactHybridAgent(
            **self.common(), adaptive_config=config
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(decision.extra["exact_attempt_count"], 0)
        self.assertFalse(decision.extra["exact_gate"]["eligible"])
        self.assertEqual(decision.extra["search_mode"], "beam_alpha_beta")

    def test_integrated_agent_exposes_exact_and_non_exact_modes(self) -> None:
        exact = IntegratedAdaptiveHybridAgent(
            **self.common()
        ).choose_edge(
            AIEdgeState.initial(
                RuntimeDictionary.from_readings(["あい", "いん"])
            )
        )
        self.assertEqual(exact.extra["search_mode"], "exact_endgame")
        config = AdaptiveHybridConfig(
            branch_switch_threshold=20,
            exact_max_reachable_words=1,
            exact_max_edge_types=1,
            exact_max_vertices=1,
            exact_max_state_estimate=1,
        )
        non_exact = IntegratedAdaptiveHybridAgent(
            **self.common(), adaptive_config=config
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(non_exact.extra["exact_attempt_count"], 0)
        self.assertEqual(non_exact.extra["search_mode"], "alpha_beta_full")

    def test_position_scale_is_read_only(self) -> None:
        state = AIEdgeState.initial(runtime())
        before = snapshot(state)
        scale = position_scale(state)
        self.assertEqual(scale.legal_edge_types, len(state.available_edges()))
        self.assertEqual(snapshot(state), before)

    def test_factory_routes_all_new_names(self) -> None:
        for name in ADAPTIVE_HYBRID_AGENT_NAMES:
            agent = build_agent(
                name,
                hybrid_depth=2,
                adaptive_max_depth_increment=0,
                time_limit_sec=1.0,
                adaptive_depth=False,
                beam_widths=(3, 2),
            )
            self.assertEqual(agent.name, name)

    def test_all_threshold_families_are_cli_configurable(self) -> None:
        parser = argparse.ArgumentParser()
        add_adaptive_hybrid_cli_arguments(parser)
        args = parser.parse_args(
            [
                "--dynamic-ply-width-caps",
                "9,5,2",
                "--pvs-time-growth-limit",
                "2.5",
            ]
        )
        config = adaptive_hybrid_config_from_args(args)
        self.assertEqual(config.ply_width_caps, (9, 5, 2))
        self.assertEqual(config.pvs_time_growth_limit, 2.5)


if __name__ == "__main__":
    unittest.main()
