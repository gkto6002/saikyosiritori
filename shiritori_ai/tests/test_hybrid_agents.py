from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    BeamAlphaBetaAgent,
    BeamPVSAgent,
    GraphPVSAgent,
    PVSAgent,
    SearchStats,
    SearchTimeout,
    build_agent,
)
from experiments_approx import parse_args as parse_approx_args  # noqa: E402
from human_cli import parse_args as parse_human_args  # noqa: E402
from analyze_hybrid_comparison import (  # noqa: E402
    aggregate_agents,
    aggregate_by_seed,
    write_report,
)
from run_hybrid_agent_benchmark import build_configs  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


class HybridAgentTest(unittest.TestCase):
    @staticmethod
    def runtime() -> RuntimeDictionary:
        return RuntimeDictionary.from_readings(
            [
                "あい",
                "あう",
                "あえ",
                "あお",
                "いあ",
                "いう",
                "いえ",
                "うあ",
                "うい",
                "うえ",
                "えあ",
                "えい",
                "おあ",
                "おう",
            ]
        )

    def test_hybrids_return_legal_reproducible_edges(self) -> None:
        classes = (GraphPVSAgent, BeamAlphaBetaAgent, BeamPVSAgent)
        for agent_class in classes:
            with self.subTest(agent=agent_class.__name__):
                kwargs = {
                    "time_limit_sec": 10.0,
                    "random_seed": 7,
                    "depth": 3,
                    "adaptive_depth": False,
                }
                if agent_class is GraphPVSAgent:
                    kwargs["branch_limit"] = 4
                else:
                    kwargs["beam_widths"] = (4, 3, 2)
                first_state = AIEdgeState.initial(self.runtime())
                legal = set(first_state.available_edges())
                first = agent_class(**kwargs).choose_edge(first_state)
                second = agent_class(**kwargs).choose_edge(
                    AIEdgeState.initial(self.runtime())
                )
                self.assertIn((first.start_id, first.end_id), legal)
                self.assertEqual(
                    (first.start_id, first.end_id, first.score),
                    (second.start_id, second.end_id, second.score),
                )
                first_state.assert_aggregates_consistent()

    def test_hybrid_timeout_restores_state(self) -> None:
        cases = (
            (GraphPVSAgent, "_pvs_edge"),
            (BeamAlphaBetaAgent, "_edge_negamax_alpha_beta"),
            (BeamPVSAgent, "_pvs_edge"),
        )
        for agent_class, method_name in cases:
            with self.subTest(agent=agent_class.__name__):
                state = AIEdgeState.initial(self.runtime())
                before = (
                    state.required_char_id,
                    list(state.edge_counts),
                    list(state.edge_history),
                )
                agent = agent_class(time_limit_sec=10.0, depth=3)
                with patch.object(agent, method_name, side_effect=SearchTimeout):
                    decision = agent.choose_edge(state)
                self.assertTrue(decision.timed_out)
                self.assertEqual(
                    (
                        state.required_char_id,
                        state.edge_counts,
                        state.edge_history,
                    ),
                    before,
                )
                state.assert_aggregates_consistent()

    def test_hybrids_support_adaptive_depth(self) -> None:
        for agent in (
            GraphPVSAgent(depth=3, branch_limit=4, adaptive_depth=True),
            BeamAlphaBetaAgent(
                depth=3, beam_widths=(4, 3, 2), adaptive_depth=True
            ),
            BeamPVSAgent(depth=3, beam_widths=(4, 3, 2), adaptive_depth=True),
        ):
            with self.subTest(agent=agent.name):
                decision = agent.choose_edge(AIEdgeState.initial(self.runtime()))
                self.assertTrue(decision.extra["adaptive_depth"])
                self.assertEqual(3, decision.extra["effective_depth"])
                agent._record_depth_result(True)
                self.assertEqual(2, agent.current_depth)

    def test_beam_hybrids_never_exceed_width_at_any_ply(self) -> None:
        widths = (4, 3, 2)
        for agent in (
            BeamAlphaBetaAgent(
                time_limit_sec=10.0,
                depth=4,
                beam_widths=widths,
                adaptive_depth=False,
            ),
            BeamPVSAgent(
                time_limit_sec=10.0,
                depth=4,
                beam_widths=widths,
                adaptive_depth=False,
            ),
        ):
            with self.subTest(agent=agent.name):
                decision = agent.choose_edge(AIEdgeState.initial(self.runtime()))
                maxima = decision.extra["beam_max_selected_by_ply"]
                self.assertTrue(maxima)
                for ply, selected in maxima.items():
                    expected = widths[min(int(ply), len(widths) - 1)]
                    self.assertLessEqual(int(selected), expected)
                self.assertGreater(decision.extra["beam_pruned_move_count"], 0)

    def test_graph_ordering_changes_pvs_order(self) -> None:
        state = AIEdgeState.initial(self.runtime())
        edges = state.available_edges()
        deadline = time.perf_counter() + 10.0
        baseline, _, _ = PVSAgent(
            depth=2,
            branch_limit=None,
            adaptive_depth=False,
        )._ordered_edges(state, edges, deadline, False, SearchStats(), 0)
        target = baseline[-1]

        def graph_score(_state, start_id, end_id, _weights):
            edge = (start_id, end_id)
            return {
                "score": 100.0 if edge == target else 0.0,
                "immediate_win": False,
                "immediate_loss": False,
            }

        stats = SearchStats()
        with patch("agents.lightweight_ordering_features", side_effect=graph_score):
            ordered, _, _ = GraphPVSAgent(
                depth=2,
                branch_limit=None,
                adaptive_depth=False,
            )._ordered_edges(state, edges, deadline, False, stats, 0)
        self.assertEqual(target, ordered[0])
        self.assertEqual(baseline[0], stats.graph_root_baseline_first)
        self.assertEqual(target, stats.graph_root_ordered_first)
        self.assertEqual(1, stats.graph_ordering_changed_first_count)
        self.assertEqual(len(edges), stats.graph_ordering_evaluations)

    def test_factories_and_clis_include_hybrids(self) -> None:
        self.assertIsInstance(build_agent("graph_pvs"), GraphPVSAgent)
        beam_alpha_beta = build_agent("beam_alpha_beta")
        self.assertIsInstance(beam_alpha_beta, BeamAlphaBetaAgent)
        self.assertEqual((8, 9), (
            beam_alpha_beta.initial_depth,
            beam_alpha_beta.max_depth,
        ))
        self.assertEqual((12, 8, 4, 2), beam_alpha_beta.beam_widths)
        beam_pvs = build_agent("beam_pvs")
        self.assertIsInstance(beam_pvs, BeamPVSAgent)
        self.assertEqual((8, 9), (
            beam_pvs.initial_depth,
            beam_pvs.max_depth,
        ))
        self.assertEqual((12, 8, 4, 2), beam_pvs.beam_widths)
        with patch.object(
            sys,
            "argv",
            [
                "experiments_approx.py",
                "--runtime",
                "D100.runtime.json",
                "--agents",
                "graph_pvs",
                "beam_alpha_beta",
                "beam_pvs",
                "--hybrid-depth",
                "5",
            ],
        ):
            approx = parse_approx_args()
        self.assertEqual(
            ["graph_pvs", "beam_alpha_beta", "beam_pvs"],
            approx.agents,
        )
        self.assertEqual(5, approx.hybrid_depth)
        with patch.object(
            sys,
            "argv",
            [
                "human_cli.py",
                "--runtime",
                "D100.runtime.json",
                "--agent",
                "graph_pvs",
            ],
        ):
            human = parse_human_args()
        self.assertEqual("graph_pvs", human.agent)

    def test_benchmark_matrix_and_match_aggregation_include_hybrids(self) -> None:
        configs = build_configs(
            ["graph_pvs", "beam_alpha_beta", "beam_pvs"],
            5,
            8,
            (8, 6, 4, 2),
        )
        self.assertEqual(
            ["graph_pvs", "beam_alpha_beta", "beam_pvs"],
            [row["agent"] for row in configs],
        )
        matches = [
            {
                "first_agent": "graph_pvs",
                "second_agent": "beam_pvs",
                "winner": "first",
                "turn_count": 2,
                "history": [
                    {
                        "player": "first",
                        "elapsed_time_sec": 0.2,
                        "nodes_searched": 10,
                        "effective_depth": 5,
                        "graph_ordering_calls": 4,
                        "graph_ordering_changed_first_count": 1,
                        "graph_ordering_time_sec": 0.05,
                    },
                    {
                        "player": "second",
                        "elapsed_time_sec": 0.1,
                        "nodes_searched": 8,
                        "effective_depth": 5,
                        "null_window_search_count": 4,
                        "research_count": 1,
                    },
                ],
            }
        ]
        summary = {row["agent"]: row for row in aggregate_agents(matches)}
        self.assertEqual(1, summary["graph_pvs"]["wins"])
        self.assertEqual(0.25, summary["graph_pvs"]["graph_ordering_changed_first_rate"])
        self.assertEqual(0.25, summary["beam_pvs"]["research_rate"])
        self.assertNotIn("graph_control", summary)

    def test_hybrid_report_accepts_agent_subset_and_seed_count(self) -> None:
        matches = [
            {
                "dictionary_seed": 0,
                "first_agent": "pvs",
                "second_agent": "beam_pvs",
                "winner": "second",
                "turn_count": 2,
                "history": [],
            }
        ]
        agents = aggregate_agents(matches)
        benchmark = [
            {
                "agent": name,
                "mean_time_sec": 1.0,
                "mean_nodes": 1.0,
                "mean_graph_ordering_time_sec": 0.0,
                "graph_ordering_changed_first_rate": 0.0,
            }
            for name in (
                "alpha_beta",
                "pvs",
                "beam_negamax",
                "graph_pvs",
                "beam_alpha_beta",
                "beam_pvs",
            )
        ]
        with tempfile.TemporaryDirectory() as temporary:
            report = write_report(
                Path(temporary),
                agents,
                [],
                benchmark,
                [],
                dictionary_seed_count=10,
                seed_rows=aggregate_by_seed(matches),
            )
            text = report.read_text(encoding="utf-8")
        self.assertIn("10辞書seed", text)
        self.assertNotIn("graph_pvs 対局中再探索率", text)
        seed_rows = aggregate_by_seed(matches)
        self.assertEqual(2, len(seed_rows))
        self.assertEqual(
            {"beam_pvs": 1.0, "pvs": 0.0},
            {str(row["agent"]): row["win_rate"] for row in seed_rows},
        )


if __name__ == "__main__":
    unittest.main()
