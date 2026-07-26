"""Run resumable tuning, final, or fixed-position adaptive-hybrid experiments."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from adaptive_hybrid import (
    ADAPTIVE_HYBRID_AGENT_NAMES,
    AdaptiveHybridConfig,
    build_adaptive_hybrid_agent,
)
from agents import AlphaBetaAgent, BeamAlphaBetaAgent, BeamPVSAgent
from match import simulate_runtime_match
from run_full_alpha_beta_comparison import load_positions
from run_graph_control_comparison import (
    append_jsonl,
    file_sha256,
    git_commit,
    read_jsonl,
    result_record,
    source_fingerprint,
    stable_hash,
    write_csv,
)
from run_search_parameter_tuning import decision_row, restore_position
from runtime_dictionary import RuntimeDictionary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "data/dictionaries"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/position_adaptive_hybrid_v2"
DEFAULT_POSITIONS = (
    PROJECT_ROOT
    / "results/search_parameter_tuning/f5a877380b91/fixed_positions.json"
)
FORMAT_VERSION = "position_adaptive_hybrid_v2"
BASELINES = ("alpha_beta", "beam_alpha_beta", "beam_pvs")
NEW_AGENTS = ADAPTIVE_HYBRID_AGENT_NAMES
ALL_AGENTS = BASELINES + NEW_AGENTS
VERIFY_AGENTS = (
    "dynamic_beam_alpha_beta",
    "dynamic_beam_pvs",
)
TUNING_AGENTS = (
    "alpha_beta",
    "beam_pvs",
    "dynamic_beam_alpha_beta",
    "dynamic_beam_pvs",
    "endgame_exact_hybrid",
    "proof_extension_beam_alpha_beta",
    "research_adaptive_beam",
    "dynamic_proof_extension_beam_alpha_beta",
)
TUNING_BASELINES = ("alpha_beta", "beam_pvs")
TUNABLE_AGENTS = tuple(
    agent for agent in TUNING_AGENTS if agent not in TUNING_BASELINES
)
FINAL_AGENTS = (
    "dynamic_beam_alpha_beta",
    "proof_extension_beam_alpha_beta",
    "dynamic_proof_extension_beam_alpha_beta",
)
VERIFY_SEEDS = (0,)
TUNE_SEEDS = tuple(range(5))
FINAL_SEEDS = tuple(range(10, 40))


def tuning_profiles() -> dict[str, AdaptiveHybridConfig]:
    balanced = AdaptiveHybridConfig()
    return {
        "conservative": replace(
            balanced,
            branch_switch_threshold=16,
            no_prune_threshold=8,
            medium_branch_threshold=30,
            high_branch_threshold=50,
            high_beam_width=10,
            very_high_beam_width=8,
            pvs_research_rate_threshold=0.03,
            next_depth_safety_ratio=0.75,
            exact_max_reachable_words=24,
            exact_max_edge_types=14,
            exact_max_vertices=10,
            exact_max_state_estimate=80_000,
            exact_max_states=80_000,
            exact_time_fraction=0.15,
            exact_time_cap_sec=0.15,
        ),
        "balanced": balanced,
    }


PROFILES = tuning_profiles()


def parse_int_csv(value: str) -> tuple[int, ...]:
    try:
        result = tuple(
            dict.fromkeys(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be integers") from exc
    if not result or any(seed < 0 for seed in result):
        raise argparse.ArgumentTypeError("seeds must be non-negative")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("verify", "tune", "final", "fixed"),
        required=True,
    )
    parser.add_argument("--dictionary-size", type=int, default=10000)
    parser.add_argument("--seeds", type=parse_int_csv)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--positions", type=Path, default=DEFAULT_POSITIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--selection-from", type=Path)
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--max-match-time-sec", type=float, default=300.0)
    parser.add_argument("--match-limit", type=int)
    parser.add_argument("--position-limit", type=int)
    parser.add_argument(
        "--confirm-d10000",
        action="store_true",
        help="required safety switch when dictionary-size is 10000 or larger",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="run the matching analyzer after this invocation",
    )
    args = parser.parse_args(argv)
    if args.dictionary_size <= 0 or args.time_limit_sec <= 0:
        parser.error("dictionary size and time limit must be positive")
    if args.max_moves <= 0 or args.max_match_time_sec <= 0:
        parser.error("match limits must be positive")
    if args.match_limit is not None and args.match_limit <= 0:
        parser.error("--match-limit must be positive")
    if args.position_limit is not None and args.position_limit <= 0:
        parser.error("--position-limit must be positive")
    if args.dictionary_size >= 10000 and not args.confirm_d10000:
        parser.error(
            "D10000以上の実験には --confirm-d10000 が必要です"
        )
    if args.stage in {"final", "fixed"} and args.selection_from is None:
        parser.error("--selection-from is required for final/fixed stages")
    return args


def selected_profile(path: Path) -> tuple[str, AdaptiveHybridConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    name = str(data["selected_profile"])
    if name not in PROFILES:
        raise ValueError(f"unknown selected profile: {name}")
    stored = data.get("config")
    if stored and isinstance(stored.get("ply_width_caps"), list):
        stored = {**stored, "ply_width_caps": tuple(stored["ply_width_caps"])}
    config = AdaptiveHybridConfig(**stored) if stored else PROFILES[name]
    return name, config


def stage_seeds(args: argparse.Namespace) -> tuple[int, ...]:
    if args.seeds is not None:
        return tuple(args.seeds)
    if args.stage == "verify":
        return VERIFY_SEEDS
    return TUNE_SEEDS if args.stage == "tune" else FINAL_SEEDS


def verify_jobs(
    seeds: tuple[int, ...],
) -> list[tuple[int, str, str]]:
    return [
        (seed, first, second)
        for seed in seeds
        for agent in VERIFY_AGENTS
        for first, second in (
            ("beam_alpha_beta", agent),
            (agent, "beam_alpha_beta"),
        )
    ]


def tuning_jobs(
    seeds: tuple[int, ...],
) -> list[tuple[int, str, str, bool]]:
    baseline_jobs = [
        (seed, "balanced", agent, adaptive_first)
        for seed in seeds
        for agent in TUNING_BASELINES
        for adaptive_first in (True, False)
    ]
    profile_jobs = [
        (seed, profile, agent, adaptive_first)
        for seed in seeds
        for profile in PROFILES
        for agent in TUNABLE_AGENTS
        for adaptive_first in (True, False)
    ]
    return baseline_jobs + profile_jobs


def final_pairs() -> tuple[tuple[str, str], ...]:
    return tuple(
        (agent, "beam_alpha_beta") for agent in FINAL_AGENTS
    )


def final_jobs(
    seeds: tuple[int, ...],
) -> list[tuple[int, str, str]]:
    return [
        (seed, first, second)
        for seed in seeds
        for pair in final_pairs()
        for first, second in (pair, tuple(reversed(pair)))
    ]


def runtime_path(
    runtime_dir: Path,
    dictionary_size: int,
    seed: int,
) -> Path:
    return runtime_dir / f"D{dictionary_size}_L2-12_seed{seed}.runtime.json"


def _search_common(time_limit_sec: float, random_seed: int) -> dict[str, Any]:
    return {
        "time_limit_sec": time_limit_sec,
        "random_seed": random_seed,
        "adaptive_depth": True,
        "min_depth": 1,
        "depth_recovery_turns": 2,
        "depth_decrease_ratio": 0.95,
        "depth_recovery_ratio": 0.6,
        "depth_step": 1,
        "timeout_decreases_depth": True,
        "target_time_sec": time_limit_sec * 0.6,
    }


def build_experiment_agent(
    name: str,
    *,
    time_limit_sec: float,
    random_seed: int,
    adaptive_config: AdaptiveHybridConfig,
    fixed_depth: int | None = None,
):
    adaptive = fixed_depth is None
    common = _search_common(time_limit_sec, random_seed)
    if not adaptive:
        common.update(
            {
                "adaptive_depth": False,
                "target_time_sec": None,
            }
        )
    if name == "alpha_beta":
        depth = fixed_depth or 5
        return AlphaBetaAgent(
            **common,
            depth=depth,
            max_depth=depth if fixed_depth else 7,
            branch_limit=8,
        )
    if name == "beam_alpha_beta":
        depth = fixed_depth or 8
        return BeamAlphaBetaAgent(
            **common,
            depth=depth,
            max_depth=depth if fixed_depth else 9,
            beam_widths=(12, 8, 4, 2),
        )
    if name == "beam_pvs":
        depth = fixed_depth or 8
        return BeamPVSAgent(
            **common,
            depth=depth,
            max_depth=depth if fixed_depth else 9,
            beam_widths=(12, 8, 4, 2),
        )
    depth = fixed_depth or 8
    return build_adaptive_hybrid_agent(
        name,
        adaptive_config=adaptive_config,
        **common,
        depth=depth,
        max_depth=depth if fixed_depth else 9,
        beam_widths=(12, 8, 4, 2),
    )


def experiment_config(
    args: argparse.Namespace,
    *,
    profile_name: str | None,
    adaptive_config: AdaptiveHybridConfig | None,
) -> dict[str, Any]:
    seeds = stage_seeds(args)
    expected = (
        len(verify_jobs(seeds))
        if args.stage == "verify"
        else len(tuning_jobs(seeds))
        if args.stage == "tune"
        else len(final_jobs(seeds))
        if args.stage == "final"
        else 0
    )
    return {
        "format_version": FORMAT_VERSION,
        "stage": args.stage,
        "dictionary_size": args.dictionary_size,
        "dictionary_seeds": list(seeds),
        "time_limit_sec": args.time_limit_sec,
        "max_moves": args.max_moves,
        "max_match_time_sec": args.max_match_time_sec,
        "profile_name": profile_name,
        "adaptive_config": (
            asdict(adaptive_config) if adaptive_config is not None else None
        ),
        "tuning_profiles": (
            {name: asdict(config) for name, config in PROFILES.items()}
            if args.stage == "tune"
            else None
        ),
        "agents": list(ALL_AGENTS),
        "final_pairs": (
            [list(pair) for pair in final_pairs()]
            if args.stage == "final"
            else None
        ),
        "expected_match_count": expected,
        "fixed_positions": (
            str(args.positions.resolve()) if args.stage == "fixed" else None
        ),
        "candidate_unit": "directed_edge_type_with_multiplicity",
    }


def _run_identity(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> tuple[Path, dict[str, Any], str, str, str]:
    commit_id = git_commit()
    fingerprint = source_fingerprint()
    config_hash = stable_hash(config)
    run_hash = stable_hash(
        {
            "commit_id": commit_id,
            "source_fingerprint": fingerprint,
            "experiment_config_hash": config_hash,
        }
    )
    output = (
        args.output_root
        / args.stage
        / f"D{args.dictionary_size}"
        / run_hash[:12]
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "commit_id": commit_id,
        "source_fingerprint": fingerprint,
        "experiment_config_hash": config_hash,
        "run_hash": run_hash,
        "config": config,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output, manifest, commit_id, fingerprint, config_hash


def run_matches(
    args: argparse.Namespace,
    *,
    profile_name: str | None,
    adaptive_config: AdaptiveHybridConfig | None,
) -> Path:
    config = experiment_config(
        args,
        profile_name=profile_name,
        adaptive_config=adaptive_config,
    )
    output, _manifest, commit_id, fingerprint, config_hash = _run_identity(
        args, config
    )
    if args.stage == "verify":
        normalized_jobs = [
            (seed, "balanced", first, second)
            for seed, first, second in verify_jobs(stage_seeds(args))
        ]
    elif args.stage == "tune":
        jobs = tuning_jobs(stage_seeds(args))
        normalized_jobs = [
            (
                seed,
                profile,
                agent if adaptive_first else "beam_alpha_beta",
                "beam_alpha_beta" if adaptive_first else agent,
            )
            for seed, profile, agent, adaptive_first in jobs
        ]
    else:
        normalized_jobs = [
            (seed, profile_name or "selected", first, second)
            for seed, first, second in final_jobs(stage_seeds(args))
        ]
    estimated_seconds_per_match = min(
        45.0, float(args.max_match_time_sec)
    )
    estimated_hours = (
        len(normalized_jobs) * estimated_seconds_per_match / 3600.0
    )
    print(
        f"expected matches: {len(normalized_jobs)} "
        f"(rough estimate: {estimated_hours:.1f} hours at 45 sec/match)",
        flush=True,
    )

    raw_path = output / "raw_matches.jsonl"
    rows = read_jsonl(raw_path)
    completed = {str(row["match_id"]) for row in rows}
    new_count = 0
    for index, (seed, profile, first_name, second_name) in enumerate(
        normalized_jobs, start=1
    ):
        match_id = (
            f"D{args.dictionary_size}_seed{seed}_{profile}_"
            f"{first_name}_vs_{second_name}"
        )
        if match_id in completed:
            continue
        if args.match_limit is not None and new_count >= args.match_limit:
            break
        path = runtime_path(args.runtime_dir, args.dictionary_size, seed)
        if not path.is_file():
            raise FileNotFoundError(
                f"runtime dictionary not found: {path}\n"
                "experiment_dictionary.pyで同じsize/seedを先に生成してください。"
            )
        runtime = RuntimeDictionary.load(path)
        selected_config = (
            PROFILES[profile]
            if args.stage in {"verify", "tune"}
            else adaptive_config
        )
        assert selected_config is not None
        first = build_experiment_agent(
            first_name,
            time_limit_sec=args.time_limit_sec,
            random_seed=seed * 1000 + 1,
            adaptive_config=selected_config,
        )
        second = build_experiment_agent(
            second_name,
            time_limit_sec=args.time_limit_sec,
            random_seed=seed * 1000 + 2,
            adaptive_config=selected_config,
        )
        try:
            result = simulate_runtime_match(
                runtime.to_edge_dictionary(),
                first,
                second,
                max_moves=min(args.max_moves, runtime.word_count),
                max_match_time_sec=args.max_match_time_sec,
                match_id=match_id,
            )
        except Exception as exc:
            append_jsonl(
                output / "failures.jsonl",
                {
                    "match_id": match_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            print(f"[{index}/{len(normalized_jobs)}] FAILED {match_id}: {exc}")
            continue
        record = result_record(
            result,
            match_id=match_id,
            runtime_path_value=path,
            dictionary_seed=seed,
            match_seed=seed * 1000,
            repetition=0,
            commit_id=commit_id,
            source_hash=fingerprint,
            config_hash=config_hash,
            dictionary_file_hash=file_sha256(path),
            dictionary_hash=runtime.dictionary_hash,
        )
        record.update(
            {
                "stage": args.stage,
                "profile_name": profile,
                "first_config_id": f"{profile}:{first_name}",
                "second_config_id": f"{profile}:{second_name}",
            }
        )
        append_jsonl(raw_path, record)
        rows.append(record)
        completed.add(match_id)
        new_count += 1
        print(
            f"[{len(completed)}/{len(normalized_jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )

    rows = read_jsonl(raw_path)
    write_csv(
        output / "raw_matches.csv",
        [
            {key: value for key, value in row.items() if key != "history"}
            for row in rows
        ],
    )
    completion = {
        "expected_match_count": len(normalized_jobs),
        "completed_match_count": len(rows),
        "unique_match_count": len(
            {str(row["match_id"]) for row in rows}
        ),
        "failed_match_count": len(
            read_jsonl(output / "failures.jsonl")
        ),
        "complete": len(rows) == len(normalized_jobs),
    }
    (output / "completion.json").write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return output


def run_fixed(
    args: argparse.Namespace,
    *,
    profile_name: str,
    adaptive_config: AdaptiveHybridConfig,
) -> Path:
    config = experiment_config(
        args,
        profile_name=profile_name,
        adaptive_config=adaptive_config,
    )
    output, _manifest, _commit, _fingerprint, _config_hash = _run_identity(
        args, config
    )
    positions = load_positions(args.positions)
    if args.position_limit is not None:
        positions = positions[: args.position_limit]
    jobs = [(agent, position) for agent in ALL_AGENTS for position in positions]
    print(f"expected fixed decisions: {len(jobs)}", flush=True)
    raw_path = output / "fixed_runs.jsonl"
    rows = read_jsonl(raw_path)
    completed = {
        (str(row["agent"]), str(row["position_id"])) for row in rows
    }
    new_count = 0
    for index, (name, position) in enumerate(jobs, start=1):
        key = (name, str(position["position_id"]))
        if key in completed:
            continue
        if args.match_limit is not None and new_count >= args.match_limit:
            break
        _runtime, state = restore_position(position)
        agent = build_experiment_agent(
            name,
            time_limit_sec=args.time_limit_sec,
            random_seed=0,
            adaptive_config=adaptive_config,
            fixed_depth=8,
        )
        decision = agent.choose_edge(state)
        state.assert_aggregates_consistent()
        row = decision_row(
            {
                "config_id": f"{profile_name}:{name}",
                "agent": name,
                "depth": 8,
                "branch_limit": 8 if name == "alpha_beta" else None,
                "beam_widths": (12, 8, 4, 2),
            },
            position,
            decision,
            profile_name="fixed_position_adaptive",
        )
        row["decision_extra"] = decision.extra
        for field in (
            "search_mode",
            "mode_history",
            "switch_reason",
            "mode_counts",
            "mode_switch_count",
            "completed_iterative_depth",
            "iterative_start_depth",
            "iterative_target_depth",
            "depth_control",
            "dynamic_beam_width_counts",
            "beam_candidate_counts_by_ply",
            "beam_selected_counts_by_ply",
            "beam_pruned_counts_by_ply",
            "beam_ordering_calls_by_ply",
            "beam_max_selected_by_ply",
            "position_scale",
            "exact_gate",
            "exact_attempt_count",
            "exact_success_count",
            "exact_timeout_count",
            "exact_limit_count",
            "exact_state_count",
            "exact_result",
            "exact_call_events",
            "exact_root_call_count",
            "exact_frontier_call_count",
            "exact_trivial_success_count",
            "exact_nontrivial_success_count",
            "exact_memo_hit_count",
            "exact_total_time_sec",
            "exact_fallback_count",
            "root_selected_move_had_exact_proof",
            "root_choice_changed_by_exact",
            "fallback_count",
        ):
            row[field] = decision.extra.get(field, "")
        append_jsonl(raw_path, row)
        rows.append(row)
        completed.add(key)
        new_count += 1
        print(
            f"[{len(completed)}/{len(jobs)}] {name} "
            f"{position['position_id']}: {decision.elapsed_time_sec:.4f}s",
            flush=True,
        )
    rows = read_jsonl(raw_path)
    write_csv(
        output / "fixed_runs.csv",
        [
            {key: value for key, value in row.items() if key != "decision_extra"}
            for row in rows
        ],
    )
    (output / "completion.json").write_text(
        json.dumps(
            {
                "expected_decision_count": len(jobs),
                "completed_decision_count": len(rows),
                "complete": len(rows) == len(jobs),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return output


def main() -> None:
    try:
        args = parse_args()
        if args.stage in {"verify", "tune"}:
            output = run_matches(
                args,
                profile_name=None,
                adaptive_config=None,
            )
            if args.analyze:
                from analyze_position_adaptive_hybrid_experiment import analyze

                print(analyze(output))
            return
        assert args.selection_from is not None
        profile_name, config = selected_profile(args.selection_from)
        if args.stage == "fixed":
            output = run_fixed(
                args,
                profile_name=profile_name,
                adaptive_config=config,
            )
        else:
            output = run_matches(
                args,
                profile_name=profile_name,
                adaptive_config=config,
            )
        if args.analyze:
            from analyze_position_adaptive_hybrid_experiment import analyze

            print(analyze(output))
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
