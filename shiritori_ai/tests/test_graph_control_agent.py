from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AlphaBetaAgent,
    BeamNegamaxAgent,
    GraphControlAgent,
    GreedyAgent,
    MinimaxAgent,
    PVSAgent,
)
from graph_control import evaluate_applied_candidate, topology_features  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


def make_graph() -> tuple[RuntimeDictionary, AIEdgeState]:
    runtime = RuntimeDictionary.from_readings(
        ["あい", "あかい", "いう", "うあ", "いえ", "えお", "おん"],
        dictionary_hash="graph-control-test",
    )
    return runtime, AIEdgeState.initial(runtime)


class GraphControlFeatureTest(unittest.TestCase):
    def test_parallel_edge_remains_active_until_last_copy(self) -> None:
        runtime, state = make_graph()
        a = runtime.char_to_id["あ"]
        i = runtime.char_to_id["い"]
        index = runtime.edge_index(a, i)
        self.assertEqual(2, state.edge_counts[index])

        state.apply_edge(a, i)
        self.assertEqual(1, state.edge_counts[index])
        self.assertTrue(state.active_end_masks[a] & (1 << i))

        state.required_char_id = a
        state.apply_edge(a, i)
        self.assertEqual(0, state.edge_counts[index])
        self.assertFalse(state.active_end_masks[a] & (1 << i))

    def test_apply_undo_restores_every_state_field(self) -> None:
        runtime, state = make_graph()
        snapshot = (
            state.required_char_id,
            state.edge_counts.copy(),
            state.active_end_masks.copy(),
            state.remaining_word_counts.copy(),
            state.remaining_safe_word_counts.copy(),
            state.active_edge_type_counts.copy(),
            state.active_safe_edge_type_counts.copy(),
            state.edge_history.copy(),
        )
        state.apply_edge(runtime.char_to_id["あ"], runtime.char_to_id["い"])
        state.undo_edge()
        self.assertEqual(snapshot[0], state.required_char_id)
        self.assertEqual(snapshot[1], state.edge_counts)
        self.assertEqual(snapshot[2], state.active_end_masks)
        self.assertEqual(snapshot[3], state.remaining_word_counts)
        self.assertEqual(snapshot[4], state.remaining_safe_word_counts)
        self.assertEqual(snapshot[5], state.active_edge_type_counts)
        self.assertEqual(snapshot[6], state.active_safe_edge_type_counts)
        self.assertEqual(snapshot[7], state.edge_history)

    def test_reachable_and_scc_features(self) -> None:
        runtime, state = make_graph()
        a = runtime.char_to_id["あ"]
        i = runtime.char_to_id["い"]
        state.apply_edge(a, i)
        topology = topology_features(state, i)

        expected_reachable = {
            runtime.char_to_id[c] for c in ("あ", "い", "う", "え", "お", "ん")
        }
        expected_scc = {runtime.char_to_id[c] for c in ("あ", "い", "う")}
        self.assertEqual(expected_reachable, set(topology.reachable_char_ids))
        self.assertEqual(expected_scc, set(topology.scc_char_ids))
        self.assertEqual(6, sum(state.remaining_word_counts[c] for c in topology.reachable_char_ids))

        features = evaluate_applied_candidate(state, a, i, topology)
        self.assertEqual(3, features["raw"]["scc_internal_edge_count"])
        self.assertEqual(1, features["raw"]["scc_exit_edge_count"])

    def test_depth_two_and_three_are_computed(self) -> None:
        runtime, state = make_graph()
        a = runtime.char_to_id["あ"]
        i = runtime.char_to_id["い"]
        state.apply_edge(a, i)
        topology = topology_features(state, i)
        features = evaluate_applied_candidate(state, a, i, topology)
        self.assertGreaterEqual(
            features["raw"]["depth3_char_count"],
            features["raw"]["depth2_char_count"],
        )
        self.assertGreater(features["raw"]["depth2_char_count"], 1)

    def test_dead_end_and_low_degree_rates_are_bounded(self) -> None:
        runtime, state = make_graph()
        a = runtime.char_to_id["あ"]
        i = runtime.char_to_id["い"]
        state.apply_edge(a, i)
        topology = topology_features(state, i)
        features = evaluate_applied_candidate(state, a, i, topology)
        for key in ("dead_end_reach_rate", "low_out_degree_reach_rate"):
            self.assertGreaterEqual(features["raw"][key], 0.0)
            self.assertLessEqual(features["raw"][key], 1.0)


class GraphControlAgentTest(unittest.TestCase):
    def test_n_ending_candidate_is_not_selected_when_safe_move_exists(self) -> None:
        runtime = RuntimeDictionary.from_readings(
            ["あん", "あい", "いう"], dictionary_hash="n-test"
        )
        state = AIEdgeState.initial(runtime)
        state.required_char_id = runtime.char_to_id["あ"]
        edge = GraphControlAgent(time_limit_sec=10.0).choose_edge(state)
        self.assertEqual(runtime.char_to_id["い"], edge.end_id)

    def test_n_ending_candidate_is_kept_when_it_is_the_only_move(self) -> None:
        runtime = RuntimeDictionary.from_readings(["あん"], dictionary_hash="n-only")
        state = AIEdgeState.initial(runtime)
        state.required_char_id = runtime.char_to_id["あ"]
        edge = GraphControlAgent(time_limit_sec=10.0).choose_edge(state)
        self.assertEqual(runtime.char_to_id["ん"], edge.end_id)

    def test_no_legal_move_returns_none(self) -> None:
        runtime = RuntimeDictionary.from_readings(["あい"], dictionary_hash="none")
        state = AIEdgeState.initial(runtime)
        state.required_char_id = runtime.char_to_id["い"]
        self.assertIsNone(GraphControlAgent(time_limit_sec=10.0).choose_edge(state).start_id)

    def test_selection_is_deterministic(self) -> None:
        runtime, state = make_graph()
        state.required_char_id = runtime.char_to_id["い"]
        choices = []
        for _ in range(4):
            decision = GraphControlAgent(time_limit_sec=10.0).choose_edge(state)
            choices.append((decision.start_id, decision.end_id))
        self.assertEqual(1, len(set(choices)))

    def test_candidate_log_and_selected_detail_are_consistent(self) -> None:
        runtime, state = make_graph()
        state.required_char_id = runtime.char_to_id["い"]
        agent = GraphControlAgent(time_limit_sec=10.0)
        decision = agent.choose_edge(state)
        self.assertEqual(len(state.available_edges()), len(agent.last_candidate_details))
        selected = [
            row
            for row in agent.last_candidate_details
            if (row["start_id"], row["end_id"])
            == (decision.start_id, decision.end_id)
        ]
        self.assertEqual(1, len(selected))
        self.assertIn("raw", selected[0])
        self.assertIn("normalized", selected[0])
        self.assertIn("structural_score_range", agent.last_evaluation_summary)

    def test_choose_edge_does_not_change_state(self) -> None:
        runtime, state = make_graph()
        state.required_char_id = runtime.char_to_id["い"]
        before = (
            state.required_char_id,
            state.edge_counts.copy(),
            state.active_end_masks.copy(),
            state.edge_history.copy(),
        )
        GraphControlAgent(time_limit_sec=10.0).choose_edge(state)
        self.assertEqual(before[0], state.required_char_id)
        self.assertEqual(before[1], state.edge_counts)
        self.assertEqual(before[2], state.active_end_masks)
        self.assertEqual(before[3], state.edge_history)

    def test_existing_agents_keep_regression_choice(self) -> None:
        runtime = RuntimeDictionary.from_readings(
            ["あい", "あう", "あえ", "いう", "いえ", "うあ", "うえ", "えあ", "えい", "えん"],
            dictionary_hash="existing-agent-regression",
        )
        expected = {
            GreedyAgent: ("あ", "い"),
            MinimaxAgent: ("う", "え"),
            AlphaBetaAgent: ("う", "え"),
            BeamNegamaxAgent: ("う", "え"),
            PVSAgent: ("う", "え"),
        }
        for agent_type, chars in expected.items():
            kwargs: dict[str, object] = {"time_limit_sec": 10.0}
            if agent_type in (MinimaxAgent, AlphaBetaAgent, PVSAgent):
                kwargs.update(depth=3, branch_limit=None, adaptive_depth=False)
            elif agent_type is BeamNegamaxAgent:
                kwargs.update(depth=3, beam_widths=(12, 12, 12), adaptive_depth=False)
            agent = agent_type(**kwargs)
            edge = agent.choose_edge(AIEdgeState.initial(runtime))
            self.assertEqual(
                (runtime.char_to_id[chars[0]], runtime.char_to_id[chars[1]]),
                (edge.start_id, edge.end_id),
                agent_type.__name__,
            )


if __name__ == "__main__":
    unittest.main()
