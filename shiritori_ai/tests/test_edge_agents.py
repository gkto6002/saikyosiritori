from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import (  # noqa: E402
    GameState,
    edge_greedy_score,
    evaluate_edge_position,
    evaluate_position,
    greedy_move_score,
)
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


class EdgeEvaluationCompatibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.words = ["あい", "あかい", "いあ", "いん", "いす", "すあ"]
        self.runtime = RuntimeDictionary.from_readings(self.words)
        self.graph = self.runtime.to_word_graph()

    def test_greedy_score_matches_word_method_with_parallel_edges(self) -> None:
        edge_state = AIEdgeState.initial(self.runtime)
        word_state = GameState(current_char=None)
        for word_id in range(self.runtime.word_count):
            start_id = self.runtime.word_start_ids[word_id]
            end_id = self.runtime.word_end_ids[word_id]
            self.assertEqual(
                edge_greedy_score(edge_state, start_id, end_id),
                greedy_move_score(self.graph, word_state, word_id),
            )

    def test_position_evaluation_matches_before_and_after_one_edge(self) -> None:
        edge_state = AIEdgeState.initial(self.runtime)
        self.assertEqual(
            evaluate_edge_position(edge_state),
            evaluate_position(self.graph, GameState(current_char=None)),
        )

        used_word_id = self.words.index("あい")
        start_id = self.runtime.word_start_ids[used_word_id]
        end_id = self.runtime.word_end_ids[used_word_id]
        edge_state.apply_edge(start_id, end_id)
        word_state = GameState(current_char="い", used_ids=frozenset({used_word_id}))
        self.assertEqual(
            evaluate_edge_position(edge_state),
            evaluate_position(self.graph, word_state),
        )

    def test_evaluation_does_not_mutate_edge_state(self) -> None:
        state = AIEdgeState.initial(self.runtime)
        before_counts = list(state.edge_counts)
        before_masks = list(state.active_end_masks)
        evaluate_edge_position(state)
        self.assertEqual(state.edge_counts, before_counts)
        self.assertEqual(state.active_end_masks, before_masks)
        self.assertEqual(state.edge_history, [])


if __name__ == "__main__":
    unittest.main()
