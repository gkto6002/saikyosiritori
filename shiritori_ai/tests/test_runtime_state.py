from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    AlphaBetaAgent,
    GreedyAgent,
    MinimaxAgent,
    MonteCarloAgent,
    RandomAgent,
)
from match import simulate_runtime_match  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import (  # noqa: E402
    AIEdgeState,
    HumanRuntimeState,
)


def make_runtime(words: list[str]) -> RuntimeDictionary:
    records = [
        {
            "word_id": word_id,
            "normalized_reading": word,
            "normalized_length": len(word),
            "start_char": word[0],
            "end_char": word[-1],
            "ends_with_n": word.endswith("ん"),
        }
        for word_id, word in enumerate(words)
    ]
    return RuntimeDictionary.from_detail_records(records)


class AIEdgeStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = make_runtime(["いい", "いあい", "いうい", "いか", "かん"])
        self.i_id = self.runtime.char_to_id["い"]

    def test_apply_and_undo_restore_all_state(self) -> None:
        state = AIEdgeState.initial(self.runtime)
        original_counts = list(state.edge_counts)
        original_masks = list(state.active_end_masks)
        state.apply_edge(self.i_id, self.i_id)
        state.undo_edge()
        self.assertIsNone(state.required_char_id)
        self.assertEqual(state.edge_counts, original_counts)
        self.assertEqual(state.active_end_masks, original_masks)
        self.assertEqual(state.edge_history, [])

    def test_same_edge_can_be_used_to_capacity_and_bits_toggle(self) -> None:
        state = AIEdgeState.initial(self.runtime)
        edge_index = self.runtime.edge_index(self.i_id, self.i_id)
        self.assertEqual(state.edge_counts[edge_index], 3)
        for _ in range(3):
            state.apply_edge(self.i_id, self.i_id)
        self.assertEqual(state.edge_counts[edge_index], 0)
        self.assertFalse(state.active_end_masks[self.i_id] & (1 << self.i_id))
        with self.assertRaises(ValueError):
            state.apply_edge(self.i_id, self.i_id)
        state.undo_edge()
        self.assertEqual(state.edge_counts[edge_index], 1)
        self.assertTrue(state.active_end_masks[self.i_id] & (1 << self.i_id))

    def test_ai_state_contains_no_word_data(self) -> None:
        state = AIEdgeState.initial(self.runtime)
        self.assertFalse(hasattr(state, "runtime"))
        self.assertFalse(hasattr(state.edge_dictionary, "word_readings"))
        self.assertFalse(hasattr(state.edge_dictionary, "word_to_id"))
        self.assertFalse(hasattr(state.edge_dictionary, "bucket_word_ids"))

    def test_counts_and_available_end_ids(self) -> None:
        state = AIEdgeState.initial(self.runtime)
        self.assertEqual(state.legal_word_count(), self.runtime.word_count)
        state.apply_edge(self.i_id, self.i_id)
        self.assertEqual(state.legal_word_count(), 3)
        self.assertEqual(
            set(state.available_end_ids()),
            {self.runtime.char_to_id["い"], self.runtime.char_to_id["か"]},
        )


class HumanRuntimeStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = make_runtime(["いい", "いあい", "いうい", "いか", "かん"])

    def test_input_validation_and_middle_bucket_use(self) -> None:
        state = HumanRuntimeState.initial(self.runtime)
        invalid = state.submit_human_reading("abc")
        self.assertEqual(invalid.error_code, "contains_non_hiragana")
        outside = state.submit_human_reading("いぬ")
        self.assertEqual(outside.error_code, "not_in_dictionary")

        accepted = state.submit_human_reading("イアイ")
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.word_id, 1)
        repeated = state.submit_human_reading("いあい")
        self.assertEqual(repeated.error_code, "already_used")
        wrong_start = state.submit_human_reading("かん")
        self.assertEqual(wrong_start.error_code, "wrong_start_char")
        state.assert_consistent()

    def test_ai_skips_a_human_used_word_inside_bucket(self) -> None:
        state = HumanRuntimeState.initial(self.runtime)
        self.assertEqual(state.submit_human_reading("いあい").word_id, 1)
        i_id = self.runtime.char_to_id["い"]
        first_ai = state.choose_ai_word(i_id, i_id)
        second_ai = state.choose_ai_word(i_id, i_id)
        self.assertEqual((first_ai, second_ai), (0, 2))
        self.assertEqual(state.used_word_ids, {0, 1, 2})
        state.assert_consistent()

    def test_edge_search_state_is_isolated_and_ai_move_becomes_one_word(self) -> None:
        state = HumanRuntimeState.initial(self.runtime)
        search_state = state.edge_search_state()
        decision = GreedyAgent(time_limit_sec=1.0).choose_edge(search_state)
        self.assertIsNotNone(decision.start_id)
        self.assertIsNotNone(decision.end_id)
        self.assertEqual(state.used_word_ids, set())
        assert decision.start_id is not None and decision.end_id is not None
        word_id = state.choose_ai_word(decision.start_id, decision.end_id)
        self.assertIn(word_id, state.used_word_ids)
        self.assertEqual(state.word_history, [word_id])
        state.assert_consistent()


class EdgeAgentIntegrationTest(unittest.TestCase):
    def test_every_agent_returns_a_legal_edge_without_mutating_state(self) -> None:
        runtime = make_runtime(["あい", "いあ", "いん"])
        agents = [
            RandomAgent(time_limit_sec=1.0),
            GreedyAgent(time_limit_sec=1.0),
            MinimaxAgent(time_limit_sec=1.0, depth=2, branch_limit=5),
            AlphaBetaAgent(time_limit_sec=1.0, depth=2, branch_limit=5),
            MonteCarloAgent(
                time_limit_sec=1.0,
                candidate_limit=5,
                playouts_per_move=2,
                max_playout_moves=10,
            ),
        ]
        for agent in agents:
            with self.subTest(agent=agent.name):
                state = AIEdgeState.initial(runtime)
                before_counts = list(state.edge_counts)
                before_masks = list(state.active_end_masks)
                decision = agent.choose_edge(state)
                self.assertIsNotNone(decision.start_id)
                self.assertIsNotNone(decision.end_id)
                assert decision.start_id is not None and decision.end_id is not None
                self.assertGreater(
                    state.edge_counts[
                        state.edge_dictionary.edge_index(
                            decision.start_id,
                            decision.end_id,
                        )
                    ],
                    0,
                )
                self.assertEqual(state.edge_counts, before_counts)
                self.assertEqual(state.active_end_masks, before_masks)
                self.assertEqual(state.edge_history, [])

    def test_runtime_match_history_contains_edges_and_no_words(self) -> None:
        runtime = make_runtime(["あい", "いあ", "いん"])
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            RandomAgent(random_seed=0),
            RandomAgent(random_seed=1),
            max_moves=10,
            max_match_time_sec=5.0,
        )
        self.assertTrue(result.history)
        self.assertTrue(all("edge_index" in row for row in result.history))
        self.assertTrue(all("word" not in row for row in result.history))
        self.assertTrue(all("word_id" not in row for row in result.history))
        self.assertEqual(result.used_word_count, len(result.history))


if __name__ == "__main__":
    unittest.main()
