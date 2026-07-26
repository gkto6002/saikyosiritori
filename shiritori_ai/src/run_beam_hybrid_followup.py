"""Run resumable AlphaBeta matches against Beam hybrid parameter variants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents import AlphaBetaAgent, BeamAlphaBetaAgent, BeamPVSAgent
from match import simulate_runtime_match
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
from runtime_dictionary import RuntimeDictionary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "data/dictionaries"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/beam_hybrid_followup"
FORMAT_VERSION = "beam_hybrid_followup_v1"
ALPHA_CONFIG_ID = "alpha_beta_reference"
BASE_WIDTHS = (8, 6, 4, 2)
WIDE_WIDTHS = (12, 8, 4, 2)


def variant_specs() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for agent in ("beam_alpha_beta", "beam_pvs"):
        for suffix, initial_depth, max_depth, widths in (
            ("baseline", 7, 8, BASE_WIDTHS),
            ("deep", 8, 9, BASE_WIDTHS),
            ("wide", 7, 8, WIDE_WIDTHS),
            ("deep_wide", 8, 9, WIDE_WIDTHS),
        ):
            config_id = f"{agent}_{suffix}"
            result[config_id] = {
                "config_id": config_id,
                "agent": agent,
                "initial_depth": initial_depth,
                "max_depth": max_depth,
                "beam_widths": list(widths),
            }
    return result


VARIANT_SPECS = variant_specs()
DEFAULT_VARIANTS = tuple(VARIANT_SPECS)


def parse_int_csv(value: str) -> tuple[int, ...]:
    try:
        values = tuple(
            dict.fromkeys(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be integers") from exc
    if not values or any(seed < 0 for seed in values):
        raise argparse.ArgumentTypeError("seeds must be non-negative integers")
    return values


def parse_variant_csv(value: str) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(item.strip() for item in value.split(",") if item.strip())
    )
    unknown = sorted(set(values) - set(VARIANT_SPECS))
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown variants: "
            + ",".join(unknown)
            + "; choices="
            + ",".join(DEFAULT_VARIANTS)
        )
    if not values:
        raise argparse.ArgumentTypeError("at least one variant is required")
    return values


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary-size", type=int, default=10000)
    parser.add_argument(
        "--seeds",
        type=parse_int_csv,
        default=tuple(range(10)),
        help="default: 0,1,2,3,4,5,6,7,8,9",
    )
    parser.add_argument(
        "--variants",
        type=parse_variant_csv,
        default=DEFAULT_VARIANTS,
        help="comma-separated subset; default: all eight variants",
    )
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--time-limit-sec", type=float, default=1.0)
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--max-match-time-sec", type=float, default=300.0)
    parser.add_argument("--match-limit", type=int)
    args = parser.parse_args(argv)
    if (
        args.dictionary_size <= 0
        or args.time_limit_sec <= 0
        or args.max_moves <= 0
        or args.max_match_time_sec <= 0
        or (args.match_limit is not None and args.match_limit <= 0)
    ):
        parser.error("sizes, limits, and optional match limit must be positive")
    return args


def adaptive_common(time_limit_sec: float) -> dict[str, Any]:
    return {
        "time_limit_sec": time_limit_sec,
        "adaptive_depth": True,
        "min_depth": 1,
        "depth_recovery_turns": 2,
        "depth_decrease_ratio": 0.95,
        "depth_recovery_ratio": 0.6,
        "depth_step": 1,
        "timeout_decreases_depth": True,
        "target_time_sec": time_limit_sec * 0.6,
    }


def build_configured_agent(
    config_id: str,
    *,
    time_limit_sec: float,
    random_seed: int,
):
    common = {
        **adaptive_common(time_limit_sec),
        "random_seed": random_seed,
    }
    if config_id == ALPHA_CONFIG_ID:
        return AlphaBetaAgent(
            **common,
            depth=5,
            max_depth=7,
            branch_limit=8,
        )
    spec = VARIANT_SPECS[config_id]
    agent_class = (
        BeamAlphaBetaAgent
        if spec["agent"] == "beam_alpha_beta"
        else BeamPVSAgent
    )
    return agent_class(
        **common,
        depth=int(spec["initial_depth"]),
        max_depth=int(spec["max_depth"]),
        beam_widths=tuple(int(value) for value in spec["beam_widths"]),
    )


def runtime_path(runtime_dir: Path, dictionary_size: int, seed: int) -> Path:
    return runtime_dir / f"D{dictionary_size}_L2-12_seed{seed}.runtime.json"


def expected_jobs(
    seeds: tuple[int, ...],
    variants: tuple[str, ...],
) -> list[tuple[int, str, bool]]:
    return [
        (seed, variant, hybrid_first)
        for seed in seeds
        for variant in variants
        for hybrid_first in (True, False)
    ]


def experiment_config(args: argparse.Namespace) -> dict[str, Any]:
    selected_specs = {
        variant: VARIANT_SPECS[variant] for variant in args.variants
    }
    return {
        "format_version": FORMAT_VERSION,
        "dictionary_size": int(args.dictionary_size),
        "dictionary_seeds": list(args.seeds),
        "alpha_beta": {
            "config_id": ALPHA_CONFIG_ID,
            "initial_depth": 5,
            "max_depth": 7,
            "branch_limit": 8,
        },
        "variants": selected_specs,
        "adaptive_profile": {
            "min_depth": 1,
            "depth_recovery_turns": 2,
            "depth_decrease_ratio": 0.95,
            "depth_recovery_ratio": 0.6,
            "depth_step": 1,
            "timeout_decreases_depth": True,
            "target_time_ratio": 0.6,
        },
        "time_limit_sec": float(args.time_limit_sec),
        "max_moves": int(args.max_moves),
        "max_match_time_sec": float(args.max_match_time_sec),
        "candidate_unit": "directed_edge_type_with_multiplicity",
    }


def run(args: argparse.Namespace) -> Path:
    config = experiment_config(args)
    config_hash = stable_hash(config)
    commit_id = git_commit()
    fingerprint = source_fingerprint()
    run_hash = stable_hash(
        {
            "commit_id": commit_id,
            "source_fingerprint": fingerprint,
            "experiment_config_hash": config_hash,
        }
    )
    output = (
        args.output_root
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
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    raw_path = output / "raw_matches.jsonl"
    rows = read_jsonl(raw_path)
    if len(rows) != len({str(row["match_id"]) for row in rows}):
        raise ValueError("raw result contains duplicate match IDs")
    completed = {
        str(row["match_id"])
        for row in rows
        if row.get("commit_id") == commit_id
        and row.get("source_fingerprint") == fingerprint
        and row.get("experiment_config_hash") == config_hash
    }
    jobs = expected_jobs(tuple(args.seeds), tuple(args.variants))
    new_matches = 0
    for index, (seed, variant, hybrid_first) in enumerate(jobs, start=1):
        first_config = variant if hybrid_first else ALPHA_CONFIG_ID
        second_config = ALPHA_CONFIG_ID if hybrid_first else variant
        match_id = (
            f"D{args.dictionary_size}_seed{seed}_"
            f"{first_config}_vs_{second_config}"
        )
        if match_id in completed:
            continue
        if args.match_limit is not None and new_matches >= args.match_limit:
            break
        path = runtime_path(args.runtime_dir, args.dictionary_size, seed)
        if not path.is_file():
            raise FileNotFoundError(
                f"runtime dictionary not found: {path}\n"
                "先にexperiment_dictionary.pyで同じsize/seedを生成してください。"
            )
        runtime = RuntimeDictionary.load(path)
        # Use the same seat seed across variants so parameter changes, rather
        # than unrelated tie-breaking seeds, are the primary difference.
        first_seed = seed * 1000 + 1
        second_seed = seed * 1000 + 2
        first_agent = build_configured_agent(
            first_config,
            time_limit_sec=args.time_limit_sec,
            random_seed=first_seed,
        )
        second_agent = build_configured_agent(
            second_config,
            time_limit_sec=args.time_limit_sec,
            random_seed=second_seed,
        )
        result = simulate_runtime_match(
            runtime.to_edge_dictionary(),
            first_agent,
            second_agent,
            max_moves=min(args.max_moves, runtime.word_count),
            max_match_time_sec=args.max_match_time_sec,
            match_id=match_id,
        )
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
                "first_config_id": first_config,
                "second_config_id": second_config,
                "hybrid_config_id": variant,
            }
        )
        append_jsonl(raw_path, record)
        rows.append(record)
        completed.add(match_id)
        new_matches += 1
        print(
            f"[{len(completed)}/{len(jobs)}] {match_id}: "
            f"{result.winner}, {result.turn_count} turns",
            flush=True,
        )

    rows = read_jsonl(raw_path)
    write_csv(
        output / "raw_matches.csv",
        [{key: value for key, value in row.items() if key != "history"} for row in rows],
    )
    completion = {
        "expected_match_count": len(jobs),
        "completed_match_count": len(rows),
        "unique_match_count": len({str(row["match_id"]) for row in rows}),
        "duplicate_match_count": len(rows)
        - len({str(row["match_id"]) for row in rows}),
        "complete": len(rows) == len(jobs),
    }
    (output / "completion.json").write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return output


def main() -> None:
    try:
        run(parse_args())
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
