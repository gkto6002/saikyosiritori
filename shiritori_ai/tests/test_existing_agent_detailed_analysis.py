from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agents import GreedyAgent  # noqa: E402
from existing_agent_detailed_analysis import (  # noqa: E402
    aggregate_beam,
    aggregate_length,
    aggregate_matchups,
    aggregate_turn_metrics,
    analyze_caution_survival,
    classify_beam_losses,
    continue_from_state,
    percentile,
    select_representatives,
    validate_final_matches,
)
from run_existing_agent_analysis import parse_args  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402


def match(
    first: str,
    second: str,
    winner: str,
    *,
    size: int = 1000,
    seed: int = 0,
    turns: int = 10,
) -> dict[str, object]:
    return {
        "runtime": f"D{size}_seed{seed}",
        "dict_size": size,
        "seed": seed,
        "first_agent": first,
        "second_agent": second,
        "winner": winner,
        "turn_count": turns,
        "loss_reason": "no_legal_move",
        "first_avg_time_sec": 0.1,
        "second_avg_time_sec": 0.2,
        "first_timeout_count": 0,
        "second_timeout_count": 0,
    }


class ExistingAgentDetailedAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matches = [
            match("alpha_beta", "pvs", "first", turns=10),
            match("pvs", "alpha_beta", "second", turns=20),
            match("alpha_beta", "beam_negamax", "second", size=3000, seed=1, turns=30),
        ]

    def test_validation_accepts_unique_matches(self) -> None:
        result = validate_final_matches(self.matches)
        self.assertTrue(result["valid"])
        self.assertEqual(result["match_count"], 3)

    def test_validation_rejects_duplicate_deterministic_match(self) -> None:
        result = validate_final_matches([self.matches[0], dict(self.matches[0])])
        self.assertFalse(result["valid"])
        self.assertTrue(result["duplicate_keys"])

    def test_direct_matchup_credits_winner_and_seat(self) -> None:
        rows = aggregate_matchups(self.matches)["direct"]
        alpha_pvs = next(
            row
            for row in rows
            if row["agent"] == "alpha_beta" and row["opponent"] == "pvs"
        )
        self.assertEqual(alpha_pvs["games"], 2)
        self.assertEqual(alpha_pvs["wins"], 2)
        self.assertEqual(alpha_pvs["first_win_rate"], 1.0)
        self.assertEqual(alpha_pvs["second_win_rate"], 1.0)

    def test_dictionary_size_and_seed_groups_are_separate(self) -> None:
        result = aggregate_matchups(self.matches)
        self.assertEqual(
            {row["dict_size"] for row in result["by_size"]}, {1000, 3000}
        )
        self.assertIn(
            (3000, 1),
            {(row["dict_size"], row["seed"]) for row in result["by_seed"]},
        )

    def test_paired_seat_result_is_two_wins(self) -> None:
        paired = aggregate_matchups(self.matches)["paired_seats"]
        row = next(
            row
            for row in paired
            if {row["left_agent"], row["right_agent"]}
            == {"alpha_beta", "pvs"}
        )
        self.assertIn(row["left_result"], {"two_wins", "two_losses"})

    def test_length_statistics_and_percentile(self) -> None:
        rows = aggregate_length(self.matches)
        alpha = next(
            row
            for row in rows
            if row["agent"] == "alpha_beta" and row["outcome"] == "all"
        )
        self.assertEqual(alpha["games"], 3)
        self.assertEqual(alpha["max_turns"], 30)
        self.assertEqual(percentile([1, 2, 3, 4], 0.95), 4)

    def test_risk_and_pvs_research_aggregation(self) -> None:
        turn = {
            "match_id": "m",
            "turn": 1,
            "dict_size": 1000,
            "agent": "pvs",
            "risk_level": "danger",
            "effective_depth": 5,
            "phase": "late",
            "candidate_bucket": "1-8",
            "agent_won": True,
            "elapsed_time_sec": 0.1,
            "nodes_searched": 10,
            "research_count": 2,
            "null_window_searches": 20,
            "research_rate": 0.1,
            "root_candidate_count": 4,
        }
        result = aggregate_turn_metrics([turn])
        self.assertEqual(result["by_agent_risk"][0]["risk_level"], "danger")
        self.assertEqual(result["pvs_research"][0]["research_count"], 2)

    def test_beam_reference_retention_by_risk(self) -> None:
        rows = [
            {
                "risk_level": "normal",
                "dict_size": 1000,
                "phase": "early",
                "candidate_count": 20,
                "same_edge": False,
                "beam_won": False,
                **{f"top_{width}": width >= 12 for width in (2, 4, 6, 8, 12, 16)},
            }
        ]
        summary = aggregate_beam(rows)
        normal = next(
            row
            for row in summary
            if row["group_type"] == "risk" and row["group"] == "normal"
        )
        self.assertEqual(normal["top_8_reference_retention_rate"], 0.0)
        self.assertEqual(normal["top_12_reference_retention_rate"], 1.0)

    def test_beam_loss_cause_uses_first_dropped_reference(self) -> None:
        traces = [
            {
                "match_id": "m",
                "dict_size": 1000,
                "seed": 0,
                "first_agent": "beam_negamax",
                "second_agent": "alpha_beta",
                "winner_agent": "alpha_beta",
                "turn_count": 10,
            }
        ]
        positions = [
            {
                "match_id": "m",
                "turn": 3,
                "reference_rank": 9,
                "same_edge": False,
                "risk_level": "normal",
                "candidate_count": 20,
                "reference_edge": "あ→い",
                "beam_edge": "あ→う",
            }
        ]
        result = classify_beam_losses(traces, positions)
        self.assertEqual(result[0]["cause"], "reference_excluded_by_root_width")

    def test_counterfactual_continuation_restores_input_state(self) -> None:
        runtime = RuntimeDictionary.from_readings(["あい", "いう", "うあ", "あん"])
        state = AIEdgeState.initial(runtime)
        snapshot = (
            state.required_char_id,
            tuple(state.edge_counts),
            tuple(state.active_end_masks),
        )
        result = continue_from_state(
            state,
            GreedyAgent(time_limit_sec=1.0),
            GreedyAgent(time_limit_sec=1.0),
            0,
            10,
        )
        self.assertIn(result["winner"], {"first", "second", "draw"})
        self.assertEqual(
            snapshot,
            (
                state.required_char_id,
                tuple(state.edge_counts),
                tuple(state.active_end_masks),
            ),
        )

    def test_representatives_reference_existing_matches(self) -> None:
        traces = [
            {
                "match_id": "short",
                "first_agent": "alpha_beta",
                "second_agent": "beam_negamax",
                "winner_agent": "alpha_beta",
                "turn_count": 2,
                "history": [],
            },
            {
                "match_id": "long",
                "first_agent": "beam_negamax",
                "second_agent": "alpha_beta",
                "winner_agent": "beam_negamax",
                "turn_count": 20,
                "history": [],
            },
        ]
        selected = select_representatives(traces, [], [])
        existing = {trace["match_id"] for trace in traces}
        self.assertTrue(
            all(value is None or value in existing for value in selected.values())
        )

    def test_quick_and_individual_stage_parse(self) -> None:
        args = parse_args(["--quick", "--stage", "beam-analysis"])
        self.assertTrue(args.quick)
        self.assertEqual(args.stage, "beam-analysis")


if __name__ == "__main__":
    unittest.main()
