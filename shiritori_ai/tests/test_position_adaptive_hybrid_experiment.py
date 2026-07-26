from __future__ import annotations

import json
import contextlib
import io
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from adaptive_hybrid import AdaptiveHybridConfig  # noqa: E402
from analyze_position_adaptive_hybrid_experiment import (  # noqa: E402
    analyze,
    anchor_results,
    direct_results,
    fixed_agreement,
    fixed_summary,
    select_profile,
)
from run_position_adaptive_hybrid_experiment import (  # noqa: E402
    FINAL_SEEDS,
    NEW_AGENTS,
    PROFILES,
    TUNING_AGENTS,
    TUNING_BASELINES,
    TUNABLE_AGENTS,
    TUNE_SEEDS,
    VERIFY_SEEDS,
    final_jobs,
    final_pairs,
    parse_args,
    selected_profile,
    tuning_jobs,
    verify_jobs,
)


class PositionAdaptiveExperimentTest(unittest.TestCase):
    def test_d10000_requires_explicit_confirmation(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(["--stage", "verify", "--dictionary-size", "10000"])
        args = parse_args(
            [
                "--stage",
                "verify",
                "--dictionary-size",
                "10000",
                "--confirm-d10000",
            ]
        )
        self.assertTrue(args.confirm_d10000)

    def test_tuning_and_final_design_counts_and_seed_split(self) -> None:
        self.assertEqual(len(verify_jobs(VERIFY_SEEDS)), 4)
        self.assertEqual(len(tuning_jobs(TUNE_SEEDS)), 140)
        self.assertEqual(len(final_pairs()), 3)
        self.assertEqual(len(final_jobs(FINAL_SEEDS)), 180)
        self.assertTrue(set(TUNE_SEEDS).isdisjoint(FINAL_SEEDS))
        for seed in TUNE_SEEDS:
            for profile in PROFILES:
                for agent in TUNABLE_AGENTS:
                    relevant = [
                        job
                        for job in tuning_jobs((seed,))
                        if job[1] == profile and job[2] == agent
                    ]
                    self.assertEqual(len(relevant), 2)
            for agent in TUNING_BASELINES:
                relevant = [
                    job
                    for job in tuning_jobs((seed,))
                    if job[2] == agent
                ]
                self.assertEqual(len(relevant), 2)
                self.assertTrue(
                    all(job[1] == "balanced" for job in relevant)
                )

    def test_profile_selection_prefers_win_rate_then_safety(self) -> None:
        rows = [
            {
                "profile": "conservative",
                "new_agent_games": 10,
                "new_agent_win_rate": 0.6,
                "timeout_count": 0,
                "mean_decision_time_sec": 0.4,
            },
            {
                "profile": "balanced",
                "new_agent_games": 10,
                "new_agent_win_rate": 0.7,
                "timeout_count": 2,
                "mean_decision_time_sec": 0.3,
            },
            {
                "profile": "aggressive",
                "new_agent_games": 10,
                "new_agent_win_rate": 0.7,
                "timeout_count": 3,
                "mean_decision_time_sec": 0.2,
            },
        ]
        selected = select_profile(rows)
        self.assertEqual(selected["selected_profile"], "balanced")
        self.assertEqual(selected["config"], asdict(PROFILES["balanced"]))

    def test_selected_profile_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "selection.json"
            path.write_text(
                json.dumps(
                    {
                        "selected_profile": "balanced",
                        "config": asdict(AdaptiveHybridConfig()),
                    }
                ),
                encoding="utf-8",
            )
            name, config = selected_profile(path)
        self.assertEqual(name, "balanced")
        self.assertEqual(config, AdaptiveHybridConfig())

    def test_direct_results_are_seat_independent(self) -> None:
        rows = direct_results(
            [
                {
                    "first_agent": "a",
                    "second_agent": "b",
                    "winner": "first",
                },
                {
                    "first_agent": "b",
                    "second_agent": "a",
                    "winner": "second",
                },
            ]
        )
        self.assertEqual(rows[0]["left_wins"], 2)
        self.assertEqual(rows[0]["right_wins"], 0)
        self.assertEqual(rows[0]["seed_cluster_count"], 2)

    def test_anchor_results_orient_challenger_in_both_seats(self) -> None:
        rows = anchor_results(
            [
                {
                    "first_agent": "challenger",
                    "second_agent": "beam_alpha_beta",
                    "winner": "first",
                },
                {
                    "first_agent": "beam_alpha_beta",
                    "second_agent": "challenger",
                    "winner": "second",
                },
            ]
        )
        self.assertEqual(rows[0]["wins"], 2)
        self.assertEqual(rows[0]["decisive_win_rate"], 1.0)

    def test_fixed_summary_and_move_agreement(self) -> None:
        rows = [
            {
                "agent": "beam_alpha_beta",
                "position_id": "p1",
                "start_id": 1,
                "end_id": 2,
                "elapsed_time_sec": 0.1,
                "nodes_searched": 10,
                "effective_depth": 8,
            },
            {
                "agent": "dynamic_beam_alpha_beta",
                "position_id": "p1",
                "start_id": 1,
                "end_id": 2,
                "elapsed_time_sec": 0.05,
                "nodes_searched": 5,
                "effective_depth": 8,
            },
        ]
        summary = fixed_summary(rows)
        self.assertTrue(
            all(row["legal_decision_rate"] == 1.0 for row in summary)
        )
        agreement = fixed_agreement(rows)
        self.assertEqual(agreement[0]["same_move_rate"], 1.0)

    def test_analyzer_writes_tuning_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(
                json.dumps({"config": {"stage": "tune"}}),
                encoding="utf-8",
            )
            matches = []
            for profile in PROFILES:
                for index, agent in enumerate(NEW_AGENTS):
                    matches.append(
                        {
                            "profile_name": profile,
                            "first_agent": agent,
                            "second_agent": "beam_alpha_beta",
                            "winner": "first"
                            if profile == "balanced"
                            else "second",
                            "history": [
                                {
                                    "player": "first",
                                    "elapsed_time_sec": 0.01,
                                    "nodes_searched": 1,
                                    "effective_depth": 2,
                                }
                            ],
                        }
                    )
            with (root / "raw_matches.jsonl").open(
                "w", encoding="utf-8"
            ) as output:
                for match in matches:
                    output.write(json.dumps(match) + "\n")
            destination = analyze(root)
            selection = json.loads(
                (destination / "selected_profile.json").read_text()
            )
            self.assertEqual(selection["selected_profile"], "balanced")
            self.assertTrue((destination / "agent_summary.csv").is_file())
            self.assertTrue((destination / "win_rate.png").is_file())


if __name__ == "__main__":
    unittest.main()
