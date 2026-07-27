"""Run resumable, serial experiments used by the research presentation."""

from __future__ import annotations

import argparse
import csv
import fcntl
import itertools
import json
import math
import statistics
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agents import (
    AlphaBetaAgent,
    BeamAlphaBetaAgent,
    BeamPVSAgent,
    FullAlphaBetaAgent,
    GreedyAgent,
    MinimaxAgent,
    MonteCarloAgent,
    PVSAgent,
    RandomAgent,
)
from match import MatchResult, simulate_runtime_match
from run_graph_control_comparison import (
    append_jsonl,
    file_sha256,
    git_commit,
    read_jsonl,
    source_fingerprint,
    stable_hash,
    write_csv,
)
from run_search_parameter_tuning import decision_row, restore_position
from runtime_dictionary import RuntimeDictionary
from runtime_state import AIEdgeState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/presentation_experiments"
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "data/dictionaries"
FORMAT_VERSION = "presentation_experiments_v1"
FINAL_AGENTS = (
    "selective_alpha_beta",
    "pvs",
    "beam_alpha_beta",
    "beam_pvs",
)
INITIAL_AGENTS = (
    "random",
    "monte_carlo",
    "greedy",
    "minimax",
    "full_alpha_beta",
    "selective_alpha_beta",
)


def parse_int_csv(value: str) -> tuple[int, ...]:
    try:
        values = tuple(
            dict.fromkeys(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "seeds must be comma-separated integers"
        ) from exc
    if not values or any(value < 0 for value in values):
        raise argparse.ArgumentTypeError("seeds must be non-negative")
    return values


def experiment_config(
    seeds: Iterable[int] = range(10, 20),
    *,
    time_limit_sec: float = 1.0,
    fixed_time_limit_sec: float = 5.0,
    max_moves: int = 1000,
    max_match_time_sec: float = 300.0,
) -> dict[str, Any]:
    selected_seeds = tuple(seeds)
    if len(selected_seeds) < 3:
        initial_seeds = selected_seeds
    else:
        initial_seeds = selected_seeds[:3]
    adaptive = {
        "adaptive_depth": True,
        "target_time_sec": time_limit_sec * 0.6,
        "depth_decrease_ratio": 0.95,
        "depth_recovery_ratio": 0.6,
        "depth_recovery_turns": 2,
        "depth_step": 1,
        "timeout_decreases_depth": True,
    }
    return {
        "format_version": FORMAT_VERSION,
        "dictionary_size": 10000,
        "dictionary_min_length": 2,
        "dictionary_max_length": 12,
        "confirmation_seeds": list(selected_seeds),
        "initial_comparison_seeds": list(initial_seeds),
        "time_limit_sec": time_limit_sec,
        "fixed_position_time_limit_sec": fixed_time_limit_sec,
        "max_moves": max_moves,
        "max_match_time_sec": max_match_time_sec,
        "execution": "serial",
        "final_agents": list(FINAL_AGENTS),
        "initial_agents": list(INITIAL_AGENTS),
        "settings": {
            "selective_alpha_beta": {
                **adaptive,
                "initial_depth": 5,
                "max_depth": 7,
                "branch_limit": 8,
            },
            "pvs": {
                **adaptive,
                "initial_depth": 5,
                "max_depth": 7,
                "branch_limit": 8,
            },
            "beam_alpha_beta": {
                **adaptive,
                "initial_depth": 8,
                "max_depth": 9,
                "beam_widths": [12, 8, 4, 2],
            },
            "beam_pvs": {
                **adaptive,
                "initial_depth": 8,
                "max_depth": 9,
                "beam_widths": [12, 8, 4, 2],
            },
            "random": {"random_seeded": True},
            "monte_carlo": {
                "candidate_limit": 20,
                "playouts_per_move": 10,
                "max_playout_moves": 200,
            },
            "greedy": {"search_depth": 1},
            "minimax": {
                "depth": 3,
                "branch_limit": 8,
                "adaptive_depth": False,
            },
            "full_alpha_beta": {
                "depth": 4,
                "branch_limit": None,
                "adaptive_depth": False,
            },
        },
        "fixed_position_comparison": {
            "position_count": 50,
            "positions_per_seed": 5,
            "depths": [3, 4, 5],
            "selective_branch_limit": 12,
            "adaptive_depth": False,
        },
        "selection_sources": {
            "search_agents": (
                "results/search_parameter_tuning/f5a877380b91/"
                "adaptive/selected.json"
            ),
            "beam_agents": (
                "results/beam_hybrid_followup/D10000/c86fc7661da6"
            ),
            "seed_selection": (
                "beam setting selected on seeds 0-9; confirmation uses 10-19"
            ),
        },
    }


def runtime_path(runtime_dir: Path, seed: int) -> Path:
    return runtime_dir / f"D10000_L2-12_seed{seed}.runtime.json"


def adaptive_common(config: dict[str, Any], name: str) -> dict[str, Any]:
    settings = config["settings"][name]
    return {
        "time_limit_sec": float(config["time_limit_sec"]),
        "depth": int(settings["initial_depth"]),
        "max_depth": int(settings["max_depth"]),
        "adaptive_depth": True,
        "min_depth": 1,
        "target_time_sec": float(settings["target_time_sec"]),
        "depth_decrease_ratio": float(settings["depth_decrease_ratio"]),
        "depth_recovery_ratio": float(settings["depth_recovery_ratio"]),
        "depth_recovery_turns": int(settings["depth_recovery_turns"]),
        "depth_step": int(settings["depth_step"]),
        "timeout_decreases_depth": bool(
            settings["timeout_decreases_depth"]
        ),
    }


def build_presentation_agent(
    name: str,
    config: dict[str, Any],
    random_seed: int,
):
    time_limit = float(config["time_limit_sec"])
    if name == "selective_alpha_beta":
        common = adaptive_common(config, name)
        return AlphaBetaAgent(
            **common,
            branch_limit=int(config["settings"][name]["branch_limit"]),
        )
    if name == "pvs":
        common = adaptive_common(config, name)
        return PVSAgent(
            **common,
            branch_limit=int(config["settings"][name]["branch_limit"]),
        )
    if name == "beam_alpha_beta":
        common = adaptive_common(config, name)
        return BeamAlphaBetaAgent(
            **common,
            beam_widths=tuple(config["settings"][name]["beam_widths"]),
        )
    if name == "beam_pvs":
        common = adaptive_common(config, name)
        return BeamPVSAgent(
            **common,
            beam_widths=tuple(config["settings"][name]["beam_widths"]),
        )
    if name == "random":
        return RandomAgent(
            time_limit_sec=time_limit,
            random_seed=random_seed,
        )
    if name == "monte_carlo":
        settings = config["settings"][name]
        return MonteCarloAgent(
            time_limit_sec=time_limit,
            random_seed=random_seed,
            candidate_limit=int(settings["candidate_limit"]),
            playouts_per_move=int(settings["playouts_per_move"]),
            max_playout_moves=int(settings["max_playout_moves"]),
        )
    if name == "greedy":
        return GreedyAgent(time_limit_sec=time_limit)
    if name == "minimax":
        settings = config["settings"][name]
        return MinimaxAgent(
            time_limit_sec=time_limit,
            depth=int(settings["depth"]),
            max_depth=int(settings["depth"]),
            branch_limit=int(settings["branch_limit"]),
            adaptive_depth=False,
        )
    if name == "full_alpha_beta":
        settings = config["settings"][name]
        return FullAlphaBetaAgent(
            time_limit_sec=time_limit,
            depth=int(settings["depth"]),
            max_depth=int(settings["depth"]),
            adaptive_depth=False,
        )
    raise ValueError(f"unknown presentation agent: {name}")


def expected_match_jobs(
    config: dict[str, Any],
    stage: str,
) -> list[tuple[int, str, str]]:
    if stage == "final4":
        seeds = config["confirmation_seeds"]
        agents = config["final_agents"]
    elif stage == "initial6":
        seeds = config["initial_comparison_seeds"]
        agents = config["initial_agents"]
    else:
        raise ValueError(f"not a match stage: {stage}")
    return [
        (int(seed), first, second)
        for seed in seeds
        for first, second in itertools.permutations(agents, 2)
    ]


def _turn_sum(result: MatchResult, side: str, field: str) -> float:
    return sum(
        float(turn[field])
        for turn in result.history
        if turn["player"] == side and turn.get(field) not in ("", None)
    )


def match_record(
    result: MatchResult,
    *,
    stage: str,
    match_id: str,
    first_target: str,
    second_target: str,
    seed: int,
    runtime: Path,
    dictionary_file_hash: str,
    dictionary_hash: str,
    match_seed: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = asdict(result)
    row.update(
        {
            "stage": stage,
            "match_id": match_id,
            "first_target": first_target,
            "second_target": second_target,
            "dictionary_seed": seed,
            "runtime": str(runtime.resolve()),
            "dictionary_file_sha256": dictionary_file_hash,
            "dictionary_hash": dictionary_hash,
            "match_seed": match_seed,
            "commit_id": manifest["commit_id"],
            "source_fingerprint": manifest["source_fingerprint"],
            "experiment_config_hash": manifest[
                "experiment_config_hash"
            ],
            "invalid_move_count": int(
                result.loss_reason == "invalid_ai_move"
            ),
        }
    )
    for side in ("first", "second"):
        turns = [
            turn for turn in result.history if turn["player"] == side
        ]
        row[f"{side}_nodes_searched"] = _turn_sum(
            result, side, "nodes_searched"
        )
        row[f"{side}_cutoff_count"] = _turn_sum(
            result, side, "cutoff_count"
        )
        row[f"{side}_beam_pruned_move_count"] = _turn_sum(
            result, side, "beam_pruned_move_count"
        )
        null_windows = _turn_sum(
            result, side, "null_window_search_count"
        )
        if not null_windows:
            null_windows = _turn_sum(
                result, side, "null_window_searches"
            )
        row[f"{side}_null_window_search_count"] = null_windows
        row[f"{side}_research_count"] = _turn_sum(
            result, side, "research_count"
        )
        depths = [
            float(turn["effective_depth"])
            for turn in turns
            if turn.get("effective_depth") not in ("", None)
        ]
        row[f"{side}_mean_effective_depth"] = (
            statistics.fmean(depths) if depths else 0.0
        )
        row[f"{side}_depth_change_count"] = sum(
            bool(turn.get("depth_changed")) for turn in turns
        )
    return row


def run_match_stage(
    output: Path,
    config: dict[str, Any],
    manifest: dict[str, Any],
    runtime_dir: Path,
    stage: str,
    job_limit: int | None,
) -> list[dict[str, Any]]:
    raw_path = output / stage / "raw_matches.jsonl"
    rows = read_jsonl(raw_path)
    ids = [str(row["match_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{stage} contains duplicate match IDs")
    completed = set(ids)
    jobs = expected_match_jobs(config, stage)
    new_count = 0
    for index, (seed, first, second) in enumerate(jobs, 1):
        match_id = f"D10000_seed{seed}_{first}_vs_{second}"
        if match_id in completed:
            continue
        if job_limit is not None and new_count >= job_limit:
            break
        path = runtime_path(runtime_dir, seed)
        if not path.is_file():
            raise FileNotFoundError(
                f"runtime dictionary not found: {path}\n"
                "experiment_dictionary.pyでD10000 L2-12を生成してください。"
            )
        runtime = RuntimeDictionary.load(path)
        match_seed = seed * 1_000_000 + index
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            build_presentation_agent(first, config, match_seed * 2 + 1),
            build_presentation_agent(second, config, match_seed * 2 + 2),
            max_moves=min(int(config["max_moves"]), runtime.word_count),
            max_match_time_sec=float(config["max_match_time_sec"]),
            match_id=match_id,
        )
        row = match_record(
            result,
            stage=stage,
            match_id=match_id,
            first_target=first,
            second_target=second,
            seed=seed,
            runtime=path,
            dictionary_file_hash=file_sha256(path),
            dictionary_hash=runtime.dictionary_hash,
            match_seed=match_seed,
            manifest=manifest,
        )
        append_jsonl(raw_path, row)
        rows.append(row)
        completed.add(match_id)
        new_count += 1
        print(
            f"[{stage} {len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )
    rows = read_jsonl(raw_path)
    rows.sort(key=lambda row: str(row["match_id"]))
    write_csv(
        output / stage / "raw_matches.csv",
        [
            {key: value for key, value in row.items() if key != "history"}
            for row in rows
        ],
    )
    return rows


def _state_for_prefix(
    runtime: RuntimeDictionary,
    history: list[dict[str, Any]],
    turn: int,
) -> AIEdgeState:
    state = AIEdgeState.initial(runtime.to_edge_dictionary())
    for item in history[:turn]:
        state.apply_edge(int(item["start_id"]), int(item["end_id"]))
    return state


def _position(
    runtime_path_value: Path,
    seed: int,
    history: list[dict[str, Any]],
    turn: int,
    category: str,
    score_gap: float | None = None,
) -> dict[str, Any]:
    runtime = RuntimeDictionary.load(runtime_path_value)
    state = _state_for_prefix(runtime, history, turn)
    remaining = state.legal_word_count()
    return {
        "position_id": f"seed{seed}_{category}_t{turn}",
        "runtime": str(runtime_path_value.resolve()),
        "seed": seed,
        "split": "presentation_confirmation",
        "turn": turn,
        "edge_history": [
            [int(item["start_id"]), int(item["end_id"])]
            for item in history[:turn]
        ],
        "remaining_word_count": sum(state.edge_counts),
        "legal_edge_count": len(state.available_edges()),
        "legal_word_count": remaining,
        "risk_level": (
            "high"
            if remaining >= 100
            else "medium"
            if remaining >= 20
            else "low"
        ),
        "category": category,
        "baseline_top_score_gap": score_gap,
    }


def _score_gap(
    runtime: RuntimeDictionary,
    history: list[dict[str, Any]],
    turn: int,
) -> float:
    state = _state_for_prefix(runtime, history, turn)
    decision = BeamAlphaBetaAgent(
        time_limit_sec=0.25,
        depth=3,
        max_depth=3,
        adaptive_depth=False,
        beam_widths=(12, 8, 4, 2),
    ).choose_edge(state)
    scores = sorted(
        (
            float(row["score"])
            for row in decision.extra.get("root_search_scores", [])
        ),
        reverse=True,
    )
    return scores[0] - scores[1] if len(scores) >= 2 else math.inf


def extract_fixed_positions(
    output: Path,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    destination = output / "fixed_positions.json"
    if destination.is_file():
        positions = json.loads(destination.read_text(encoding="utf-8"))
        if len(positions) == int(
            config["fixed_position_comparison"]["position_count"]
        ):
            return positions
    rows = read_jsonl(output / "final4/raw_matches.jsonl")
    expected = len(expected_match_jobs(config, "final4"))
    if len(rows) != expected:
        raise RuntimeError(
            f"fixed positions require completed final4 matches: "
            f"{len(rows)}/{expected}"
        )
    positions: list[dict[str, Any]] = []
    for seed in config["confirmation_seeds"]:
        seed_rows = [
            row for row in rows if int(row["dictionary_seed"]) == int(seed)
        ]
        source = max(
            seed_rows,
            key=lambda row: (len(row["history"]), str(row["match_id"])),
        )
        history = source["history"]
        if len(history) < 5:
            raise RuntimeError(f"seed {seed} has no usable long match")
        runtime_value = Path(source["runtime"])
        runtime = RuntimeDictionary.load(runtime_value)
        final_turn = max(0, len(history) - 5)
        basic = {
            "opening": 0,
            "middle": len(history) // 2,
            "endgame": final_turn,
        }
        sampled = sorted(
            {
                min(final_turn, round(final_turn * index / 19))
                for index in range(20)
            }
        )
        legal_counts = {
            turn: len(
                _state_for_prefix(runtime, history, turn).available_edges()
            )
            for turn in sampled
        }
        used = set(basic.values())
        high_branch = max(
            (turn for turn in sampled if turn not in used),
            key=lambda turn: (legal_counts[turn], -turn),
        )
        basic["high_branch"] = high_branch
        used.add(high_branch)
        gaps = {
            turn: _score_gap(runtime, history, turn)
            for turn in sampled
            if turn not in used
            and len(
                _state_for_prefix(runtime, history, turn).available_edges()
            )
            >= 2
        }
        close_turn = min(
            gaps,
            key=lambda turn: (gaps[turn], turn),
        )
        basic["close_scores"] = close_turn
        for category, turn in basic.items():
            positions.append(
                _position(
                    runtime_value,
                    int(seed),
                    history,
                    turn,
                    category,
                    gaps.get(turn),
                )
            )
    positions.sort(
        key=lambda row: (
            int(row["seed"]),
            str(row["category"]),
            int(row["turn"]),
        )
    )
    destination.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return positions


def fixed_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    branch = int(
        config["fixed_position_comparison"]["selective_branch_limit"]
    )
    result: list[dict[str, Any]] = []
    for depth in config["fixed_position_comparison"]["depths"]:
        result.extend(
            [
                {
                    "config_id": f"full_alpha_beta_d{depth}",
                    "agent": "full_alpha_beta",
                    "depth": int(depth),
                    "branch_limit": None,
                },
                {
                    "config_id": (
                        f"selective_alpha_beta_d{depth}_b{branch}"
                    ),
                    "agent": "selective_alpha_beta",
                    "depth": int(depth),
                    "branch_limit": branch,
                },
            ]
        )
    return result


def run_fixed_comparison(
    output: Path,
    config: dict[str, Any],
    job_limit: int | None,
) -> list[dict[str, Any]]:
    positions = extract_fixed_positions(output, config)
    configs = fixed_configs(config)
    raw_path = output / "fixed_comparison/raw_runs.jsonl"
    rows = read_jsonl(raw_path)
    completed = {
        (str(row["config_id"]), str(row["position_id"])) for row in rows
    }
    expected = len(positions) * len(configs)
    new_count = 0
    for agent_config in configs:
        for position in positions:
            key = (
                str(agent_config["config_id"]),
                str(position["position_id"]),
            )
            if key in completed:
                continue
            if job_limit is not None and new_count >= job_limit:
                break
            _runtime, state = restore_position(position)
            common = {
                "time_limit_sec": float(
                    config["fixed_position_time_limit_sec"]
                ),
                "depth": int(agent_config["depth"]),
                "max_depth": int(agent_config["depth"]),
                "adaptive_depth": False,
            }
            if agent_config["agent"] == "full_alpha_beta":
                agent = FullAlphaBetaAgent(**common)
            else:
                agent = AlphaBetaAgent(
                    **common,
                    branch_limit=int(agent_config["branch_limit"]),
                )
            decision = agent.choose_edge(state)
            state.assert_aggregates_consistent()
            row = decision_row(
                agent_config,
                position,
                decision,
                profile_name="presentation_fixed",
            )
            append_jsonl(raw_path, row)
            rows.append(row)
            completed.add(key)
            new_count += 1
            print(
                f"[fixed {len(completed)}/{expected}] "
                f"{agent_config['config_id']} {position['position_id']}: "
                f"{decision.elapsed_time_sec:.4f}s"
                + (" timeout" if decision.timed_out else ""),
                flush=True,
            )
        if job_limit is not None and new_count >= job_limit:
            break
    rows = read_jsonl(raw_path)
    rows.sort(key=lambda row: (row["config_id"], row["position_id"]))
    write_csv(output / "fixed_comparison/raw_runs.csv", rows)
    return rows


def validation_summary(
    rows: list[dict[str, Any]],
    expected_count: int,
) -> dict[str, Any]:
    ids = [str(row["match_id"]) for row in rows]
    missing_values = sum(
        value is None
        for row in rows
        for key, value in row.items()
        if key != "history"
    )
    return {
        "expected_count": expected_count,
        "actual_count": len(rows),
        "unique_count": len(set(ids)),
        "duplicate_count": len(ids) - len(set(ids)),
        "invalid_move_count": sum(
            int(row.get("invalid_move_count", 0)) for row in rows
        ),
        "match_timeout_count": sum(
            row.get("loss_reason") == "match_timeout" for row in rows
        ),
        "max_moves_count": sum(
            row.get("loss_reason") == "max_moves_reached" for row in rows
        ),
        "missing_scalar_value_count": missing_values,
        "complete": len(rows) == expected_count,
    }


def write_completion(output: Path, config: dict[str, Any]) -> None:
    final_rows = read_jsonl(output / "final4/raw_matches.jsonl")
    initial_rows = read_jsonl(output / "initial6/raw_matches.jsonl")
    fixed_rows = read_jsonl(
        output / "fixed_comparison/raw_runs.jsonl"
    )
    fixed_expected = (
        int(config["fixed_position_comparison"]["position_count"])
        * len(fixed_configs(config))
    )
    value = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "final4": validation_summary(
            final_rows, len(expected_match_jobs(config, "final4"))
        ),
        "initial6": validation_summary(
            initial_rows, len(expected_match_jobs(config, "initial6"))
        ),
        "fixed_comparison": {
            "expected_count": fixed_expected,
            "actual_count": len(fixed_rows),
            "unique_count": len(
                {
                    (row["config_id"], row["position_id"])
                    for row in fixed_rows
                }
            ),
            "duplicate_count": len(fixed_rows)
            - len(
                {
                    (row["config_id"], row["position_id"])
                    for row in fixed_rows
                }
            ),
            "complete": len(fixed_rows) == fixed_expected,
        },
    }
    value["complete"] = all(
        value[stage]["complete"]
        for stage in ("final4", "initial6", "fixed_comparison")
    )
    (output / "completion.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("final4", "initial6", "positions", "fixed", "all"),
        default="all",
    )
    parser.add_argument(
        "--seeds",
        type=parse_int_csv,
        default=tuple(range(10, 20)),
    )
    parser.add_argument(
        "--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR
    )
    parser.add_argument(
        "--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT
    )
    parser.add_argument("--resume-run", type=Path)
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument(
        "--fixed-time-limit-sec", type=float, default=5.0
    )
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument(
        "--max-match-time-sec", type=float, default=300.0
    )
    parser.add_argument(
        "--job-limit",
        type=int,
        help="run at most this many new jobs, without changing run identity",
    )
    args = parser.parse_args(argv)
    if (
        len(args.seeds) < 3
        or args.time_limit_sec <= 0
        or args.fixed_time_limit_sec <= 0
        or args.max_moves <= 0
        or args.max_match_time_sec <= 0
        or (args.job_limit is not None and args.job_limit <= 0)
    ):
        parser.error(
            "at least three seeds and positive limits are required"
        )
    return args


def main() -> None:
    args = parse_args()
    config = experiment_config(
        args.seeds,
        time_limit_sec=args.time_limit_sec,
        fixed_time_limit_sec=args.fixed_time_limit_sec,
        max_moves=args.max_moves,
        max_match_time_sec=args.max_match_time_sec,
    )
    config_hash = stable_hash(config)
    fingerprint = source_fingerprint()
    commit = git_commit()
    run_hash = stable_hash(
        {
            "format_version": FORMAT_VERSION,
            "config": config,
            "commit_id": commit,
            "source_fingerprint": fingerprint,
        }
    )[:12]
    output = (
        args.resume_run.resolve()
        if args.resume_run is not None
        else args.output_root.resolve() / run_hash
    )
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"experiment is already running: {output}") from exc

    manifest_path = output / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stable_hash(manifest["config"]) != config_hash:
            raise ValueError("resume configuration does not match manifest")
        manifest["last_resumed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        dictionaries = {}
        for seed in config["confirmation_seeds"]:
            path = runtime_path(args.runtime_dir, int(seed))
            if not path.is_file():
                raise FileNotFoundError(f"missing runtime dictionary: {path}")
            runtime = RuntimeDictionary.load(path)
            dictionaries[str(seed)] = {
                "path": str(path.resolve()),
                "file_sha256": file_sha256(path),
                "dictionary_hash": runtime.dictionary_hash,
                "word_count": runtime.word_count,
            }
        manifest = {
            "format_version": FORMAT_VERSION,
            "run_hash": run_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "commit_id": commit,
            "source_fingerprint": fingerprint,
            "experiment_config_hash": config_hash,
            "config": config,
            "dictionaries": dictionaries,
            "seed_audit": {
                "selection_seeds": list(range(0, 10)),
                "confirmation_seeds": list(config["confirmation_seeds"]),
                "basis": (
                    "BeamAlphaBeta final setting was selected in "
                    "c86fc7661da6 using dictionary seeds 0-9."
                ),
            },
        }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    started = time.perf_counter()
    if args.stage in {"final4", "all"}:
        run_match_stage(
            output,
            config,
            manifest,
            args.runtime_dir,
            "final4",
            args.job_limit,
        )
    if args.stage in {"initial6", "all"}:
        run_match_stage(
            output,
            config,
            manifest,
            args.runtime_dir,
            "initial6",
            args.job_limit,
        )
    if args.stage in {"positions", "all"}:
        positions = extract_fixed_positions(output, config)
        print(f"[positions] {len(positions)} positions", flush=True)
    if args.stage in {"fixed", "all"}:
        run_fixed_comparison(output, config, args.job_limit)
    write_completion(output, config)
    manifest["last_stage"] = args.stage
    manifest["last_invocation_elapsed_time_sec"] = (
        time.perf_counter() - started
    )
    manifest["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
