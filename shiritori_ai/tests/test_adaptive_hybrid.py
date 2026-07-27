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
    DynamicProofExtensionBeamAlphaBetaAgent,
    DecisiveBeamAlphaBetaAgent,
    EndgameExactHybridAgent,
    IntegratedAdaptiveHybridAgent,
    ProofExtensionBeamAlphaBetaAgent,
    ResearchAdaptiveBeamAgent,
    ScoreGapDynamicBeamAlphaBetaAgent,
    SelectiveProofAlphaBetaAgent,
    build_adaptive_hybrid_agent,
    adaptive_hybrid_config_from_args,
    add_adaptive_hybrid_cli_arguments,
    position_scale,
)
from agents import (  # noqa: E402
    BeamAlphaBetaAgent,
    SearchStats,
    SearchTimeout,
    build_agent,
)
from exact_solver import AnalysisLimitExceeded, ShiritoriSolver  # noqa: E402
from search_common import CandidateEvaluation  # noqa: E402
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
        width_counts = decision.extra["dynamic_beam_width_counts"]
        for ply, selected in maximums.items():
            widths = [
                int(key.split(":", 1)[1])
                for key in width_counts
                if int(key.split(":", 1)[0]) == int(ply)
            ]
            self.assertLessEqual(int(selected), max(widths))
        self.assertTrue(any(int(ply) >= 1 for ply in maximums))
        self.assertTrue(
            any(
                int(ply) >= 1
                for ply in decision.extra["beam_pruned_counts_by_ply"]
            )
        )

    def test_dynamic_alpha_beta_and_pvs_share_recursive_width_policy(self) -> None:
        config = AdaptiveHybridConfig(
            no_prune_threshold=1,
            medium_branch_threshold=2,
            high_branch_threshold=3,
            medium_beam_width=2,
            high_beam_width=2,
            very_high_beam_width=2,
            ply_width_caps=(2, 2, 1),
            exact_max_reachable_words=1,
            exact_max_edge_types=1,
            exact_max_vertices=1,
            exact_max_state_estimate=1,
        )
        class TrackingAlphaBeta(DynamicBeamAlphaBetaAgent):
            def __init__(self, *args, **kwargs):
                self.width_calls = []
                super().__init__(*args, **kwargs)

            def _record_dynamic_width(
                self, candidate_count, selected_count, width, ply, stats
            ):
                self.width_calls.append(
                    (candidate_count, selected_count, width, ply)
                )
                return super()._record_dynamic_width(
                    candidate_count, selected_count, width, ply, stats
                )

        class TrackingPVS(DynamicBeamPVSAgent):
            def __init__(self, *args, **kwargs):
                self.width_calls = []
                super().__init__(*args, **kwargs)

            def _record_dynamic_width(
                self, candidate_count, selected_count, width, ply, stats
            ):
                self.width_calls.append(
                    (candidate_count, selected_count, width, ply)
                )
                return super()._record_dynamic_width(
                    candidate_count, selected_count, width, ply, stats
                )

        extras = []
        for cls in (TrackingAlphaBeta, TrackingPVS):
            agent = cls(
                depth=4,
                max_depth=4,
                time_limit_sec=2.0,
                adaptive_depth=False,
                beam_widths=(9, 9, 9),
                adaptive_config=config,
            )
            decision = agent.choose_edge(AIEdgeState.initial(runtime()))
            extras.append(decision.extra)
            self.assertTrue(
                any(ply >= 1 for _c, _s, _w, ply in agent.width_calls)
            )
            self.assertTrue(
                all(selected <= width for _c, selected, width, _p in agent.width_calls)
            )
            self.assertTrue(
                all(
                    selected == candidates
                    for candidates, selected, width, _p in agent.width_calls
                    if candidates <= width
                )
            )
            self.assertIn(1, decision.extra["beam_widths_used"])
            for ply, selected in decision.extra[
                "beam_max_selected_by_ply"
            ].items():
                self.assertLessEqual(
                    selected,
                    decision.extra["beam_widths_used"][ply],
                )
        self.assertEqual(
            extras[0]["beam_widths_used"],
            extras[1]["beam_widths_used"],
        )

    def test_dynamic_pvs_records_research_and_widths(self) -> None:
        decision = DynamicBeamPVSAgent(
            **self.common()
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(decision.extra["search_mode"], "dynamic_beam_pvs")
        self.assertTrue(decision.extra["dynamic_beam_width_counts"])
        self.assertIn("research_count", decision.extra)

    def test_score_gap_dynamic_beam_runs_below_root_and_respects_width(self) -> None:
        decision = ScoreGapDynamicBeamAlphaBetaAgent(
            depth=4,
            max_depth=4,
            time_limit_sec=2.0,
            adaptive_depth=False,
            beam_widths=(5, 4, 3, 2),
            adaptive_config=AdaptiveHybridConfig(
                score_gap_min_widths=(2, 2, 1, 1),
                score_gap_max_widths=(6, 5, 3, 2),
            ),
        ).choose_edge(AIEdgeState.initial(runtime()))
        counts = decision.extra["beam_score_gap_counts_by_ply"]
        self.assertTrue(any(int(ply) >= 1 for ply in counts))
        for ply, selected in decision.extra[
            "beam_max_selected_by_ply"
        ].items():
            used = [
                int(key.split(":", 1)[1])
                for key in decision.extra["dynamic_beam_width_counts"]
                if key != "previous_best_retained"
                and int(key.split(":", 1)[0]) == int(ply)
            ]
            self.assertLessEqual(int(selected), max(used))

    def test_score_gap_dynamic_beam_retains_previous_best(self) -> None:
        agent = ScoreGapDynamicBeamAlphaBetaAgent(
            **self.common(),
            adaptive_config=AdaptiveHybridConfig(
                score_gap_wide_threshold=1.0,
                score_gap_narrow_threshold=2.0,
                score_gap_min_widths=(2, 2),
                score_gap_max_widths=(3, 2),
            ),
        )
        edges = [(0, index) for index in range(4)]
        evaluation = lambda score: CandidateEvaluation(
            total_score=score,
            attack_score=score,
            survival_score=0.0,
            survival_weight=0.0,
            immediate_win=False,
            immediate_loss=False,
        )
        evaluations = {
            edge: evaluation(float(100 - index * 10))
            for index, edge in enumerate(edges)
        }
        agent._previous_root_best = edges[-1]
        selected = agent._select_ordered_edge_candidates(
            edges,
            candidate_count=len(edges),
            ply=0,
            stats=SearchStats(),
            evaluations=evaluations,
        )
        self.assertEqual(len(selected), 2)
        self.assertIn(edges[-1], selected)

    def test_fixed_beam_does_not_use_score_gap_policy(self) -> None:
        decision = BeamAlphaBetaAgent(**self.common()).choose_edge(
            AIEdgeState.initial(runtime())
        )
        self.assertFalse(decision.extra["beam_score_gap_counts_by_ply"])

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
        stats.research_count = 0
        _mode, _reason, predicted = agent._next_mode(
            "beam_pvs", stats, 0.15, 0.10, 10.0
        )
        self.assertAlmostEqual(predicted, 0.225)

    def test_research_runs_one_internal_iterative_controller(self) -> None:
        agent = ResearchAdaptiveBeamAgent(
            depth=4,
            max_depth=4,
            time_limit_sec=10.0,
            adaptive_depth=False,
            beam_widths=(4, 3, 2),
            adaptive_config=AdaptiveHybridConfig(iterative_start_depth=7),
        )
        state = AIEdgeState.initial(runtime())
        edge = state.available_edges()[0]
        calls: list[tuple[int, str]] = []

        def fake_run(_state, _edges, depth, mode, _deadline):
            calls.append((depth, mode))
            stats = SearchStats(
                nodes_searched=depth,
                null_window_search_count=10,
                research_count=2 if depth == 3 else 0,
            )
            return edge, float(depth), stats, True

        with patch.object(agent, "_run_depth", side_effect=fake_run):
            decision = agent.choose_edge(state)
        self.assertEqual([depth for depth, _mode in calls], [3, 4])
        self.assertEqual(decision.extra["depth_control"],
                         "single_internal_iterative_deepening")
        self.assertEqual(len(decision.extra["mode_history"]), 2)
        self.assertEqual(decision.extra["mode_switch_count"], 1)

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

    def test_proof_extension_runs_at_nontrivial_frontier(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["あい", "あう", "いえ", "いお", "えか", "おか", "かき", "きん"]
        )
        config = AdaptiveHybridConfig(
            exact_max_reachable_words=6,
            exact_max_edge_types=6,
            exact_max_vertices=6,
            exact_max_state_estimate=10_000,
            exact_max_states=10_000,
            exact_time_fraction=0.8,
            exact_time_cap_sec=1.0,
            exact_normal_time_reserve_sec=0.01,
        )
        decision = ProofExtensionBeamAlphaBetaAgent(
            depth=1,
            max_depth=1,
            time_limit_sec=2.0,
            adaptive_depth=False,
            beam_widths=(20, 20),
            adaptive_config=config,
        ).choose_edge(AIEdgeState.initial(small))
        events = decision.extra["exact_call_events"]
        frontier = [
            event
            for event in events
            if event["location"] == "frontier"
            and event["status"] == "complete"
        ]
        self.assertTrue(frontier)
        self.assertTrue(
            any(event["multiple_legal_edges"] for event in frontier)
        )
        self.assertGreater(
            decision.extra["exact_nontrivial_success_count"], 0
        )
        self.assertEqual(decision.extra["exact_root_call_count"], 0)

    def test_proof_extension_interruption_uses_heuristic_fallback(self) -> None:
        state = AIEdgeState.initial(runtime())
        config = AdaptiveHybridConfig(
            exact_max_reachable_words=100,
            exact_max_edge_types=100,
            exact_max_vertices=100,
            exact_max_state_estimate=10**9,
            exact_time_fraction=0.8,
            exact_time_cap_sec=1.0,
            exact_normal_time_reserve_sec=0.01,
        )
        agent = ProofExtensionBeamAlphaBetaAgent(
            **self.common(), adaptive_config=config
        )
        with patch(
            "adaptive_hybrid.ShiritoriSolver.analyze_first_moves",
            side_effect=AnalysisLimitExceeded("timeout"),
        ):
            decision = agent.choose_edge(state)
        self.assertIn(
            (decision.start_id, decision.end_id), state.available_edges()
        )
        self.assertGreater(decision.extra["exact_fallback_count"], 0)
        self.assertGreater(decision.extra["exact_timeout_count"], 0)

    def test_frontier_proof_changes_root_to_exact_winning_move(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["おえ", "きく", "おく", "えう", "きえ", "えお", "うお", "くえ"]
        )
        common = {
            "depth": 1,
            "max_depth": 1,
            "time_limit_sec": 2.0,
            "adaptive_depth": False,
            "beam_widths": (50, 50),
            "random_seed": 0,
        }
        baseline = BeamAlphaBetaAgent(**common).choose_edge(
            AIEdgeState.initial(small)
        )
        proof = ProofExtensionBeamAlphaBetaAgent(
            **common,
            adaptive_config=AdaptiveHybridConfig(
                exact_max_reachable_words=6,
                exact_max_edge_types=6,
                exact_max_vertices=8,
                exact_max_state_estimate=100_000,
                exact_max_states=100_000,
                exact_time_fraction=0.8,
                exact_time_cap_sec=1.0,
                exact_normal_time_reserve_sec=0.01,
            ),
        ).choose_edge(AIEdgeState.initial(small))
        baseline_edge = (baseline.start_id, baseline.end_id)
        proof_edge = (proof.start_id, proof.end_id)
        self.assertNotEqual(baseline_edge, proof_edge)
        exact = ShiritoriSolver(small.to_edge_dictionary())
        outcomes = {
            (row.start_id, row.end_id): row.is_winning
            for row in exact.analyze_first_moves(stop_on_first_win=False)
        }
        self.assertFalse(outcomes[baseline_edge])
        self.assertTrue(outcomes[proof_edge])
        self.assertEqual(proof.extra["exact_root_call_count"], 0)
        self.assertGreater(
            proof.extra["exact_nontrivial_success_count"], 0
        )

    def test_dynamic_proof_is_reproducible_and_legal(self) -> None:
        first = DynamicProofExtensionBeamAlphaBetaAgent(
            **self.common()
        ).choose_edge(AIEdgeState.initial(runtime()))
        second = DynamicProofExtensionBeamAlphaBetaAgent(
            **self.common()
        ).choose_edge(AIEdgeState.initial(runtime()))
        self.assertEqual(
            (first.start_id, first.end_id, first.score),
            (second.start_id, second.end_id, second.score),
        )

    def test_selective_proof_chooses_exact_winning_competitive_move(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["おえ", "きく", "おく", "えう", "きえ", "えお", "うお", "くえ"]
        )
        config = AdaptiveHybridConfig(
            exact_max_reachable_words=20,
            exact_max_edge_types=20,
            exact_max_vertices=20,
            exact_max_state_estimate=1_000_000,
            exact_max_states=100_000,
            exact_time_fraction=0.5,
            exact_time_cap_sec=1.0,
            exact_normal_time_reserve_sec=0.0,
            selective_proof_candidate_limit=3,
            selective_proof_max_calls=3,
        )
        decision = SelectiveProofAlphaBetaAgent(
            depth=1,
            max_depth=1,
            time_limit_sec=2.0,
            adaptive_depth=False,
            beam_widths=(50, 50),
            random_seed=0,
            adaptive_config=config,
        ).choose_edge(AIEdgeState.initial(small))
        outcomes = {
            (row.start_id, row.end_id): row.is_winning
            for row in ShiritoriSolver(
                small.to_edge_dictionary()
            ).analyze_first_moves(stop_on_first_win=False)
        }
        self.assertTrue(outcomes[(decision.start_id, decision.end_id)])
        self.assertTrue(decision.extra["root_choice_changed_by_exact"])
        self.assertGreater(
            decision.extra["exact_nontrivial_success_count"], 0
        )

    def test_selective_proof_interruption_keeps_normal_result(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["おえ", "きく", "おく", "えう", "きえ", "えお", "うお", "くえ"]
        )
        common = {
            "depth": 1,
            "max_depth": 1,
            "time_limit_sec": 2.0,
            "adaptive_depth": False,
            "beam_widths": (50, 50),
            "random_seed": 0,
        }
        baseline = BeamAlphaBetaAgent(**common).choose_edge(
            AIEdgeState.initial(small)
        )
        config = AdaptiveHybridConfig(
            exact_max_reachable_words=20,
            exact_max_edge_types=20,
            exact_max_vertices=20,
            exact_max_state_estimate=1_000_000,
            exact_time_fraction=0.5,
            exact_time_cap_sec=1.0,
            exact_normal_time_reserve_sec=0.0,
        )
        with patch(
            "adaptive_hybrid.ShiritoriSolver.solve",
            side_effect=AnalysisLimitExceeded("timeout"),
        ):
            decision = SelectiveProofAlphaBetaAgent(
                **common, adaptive_config=config
            ).choose_edge(AIEdgeState.initial(small))
        self.assertEqual(
            (decision.start_id, decision.end_id),
            (baseline.start_id, baseline.end_id),
        )
        self.assertEqual(decision.extra["exact_success_count"], 0)
        self.assertGreater(decision.extra["exact_timeout_count"], 0)

    def test_decisive_agent_uses_mobility_ordered_exact_search(self) -> None:
        small = RuntimeDictionary.from_readings(
            ["おえ", "きく", "おく", "えう", "きえ", "えお", "うお", "くえ"]
        )
        decision = DecisiveBeamAlphaBetaAgent(
            depth=1,
            max_depth=1,
            time_limit_sec=2.0,
            adaptive_depth=False,
            beam_widths=(50, 50),
            adaptive_config=AdaptiveHybridConfig(
                exact_max_reachable_words=20,
                exact_max_edge_types=20,
                exact_max_vertices=20,
                exact_max_state_estimate=1_000_000,
                exact_max_states=100_000,
                exact_time_fraction=0.5,
                exact_time_cap_sec=1.0,
                exact_normal_time_reserve_sec=0.0,
            ),
        ).choose_edge(AIEdgeState.initial(small))
        complete = [
            event
            for event in decision.extra["exact_call_events"]
            if event["status"] == "complete" and not event["trivial"]
        ]
        self.assertTrue(complete)
        self.assertTrue(
            all(
                event["exact_move_ordering"] == "opponent_mobility"
                for event in complete
            )
        )
        self.assertTrue(decision.extra["terminal_pressure"])
        self.assertTrue(decision.extra["exact_forced_win"])
        self.assertEqual(
            decision.extra["exact_forced_win_edge"],
            [decision.start_id, decision.end_id],
        )

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
