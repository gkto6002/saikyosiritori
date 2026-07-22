"""Small-dictionary exact-analysis experiments."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from dataset import (
    ReadingRecord,
    distribution_json,
    parse_jmdict,
    read_csv_records,
    select_records,
    write_json,
    write_records_csv,
)
from dictionary_stats import DICTIONARY_CHAR_TOTAL_FIELDS, dictionary_char_total_rows
from exact_solver import AnalysisLimitExceeded, FirstMoveResult, ShiritoriSolver
from game import WordGraph


DEFAULT_SIZE_START = 100
DEFAULT_SIZE_STEP = 50
DEFAULT_SEED_COUNT = 3

EXACT_RUN_FIELDS = [
    "dict_size",
    "random_seed",
    "searched_state_count",
    "memo_size",
    "elapsed_time_sec",
    "timed_out",
    "limit_reason",
    "is_first_player_win",
    "winning_first_move_count",
    "losing_first_move_count",
    "n_ending_count",
    "start_distribution",
    "end_distribution",
]

EXACT_SUMMARY_FIELDS = [
    "dict_size",
    "seed_count",
    "completed_seed_count",
    "searched_state_count_mean",
    "searched_state_count_stdev",
    "elapsed_time_sec_mean",
    "elapsed_time_sec_stdev",
    "first_player_win_rate",
    "winning_first_move_count_mean",
    "winning_first_move_count_stdev",
]

FIRST_MOVE_FIELDS = [
    "dict_size",
    "random_seed",
    "word",
    "start_char",
    "end_char",
    "result",
    "opponent_reply_count",
    "searched_state_count_after_move",
]

CHAR_STATS_FIELDS = [
    "dict_size",
    "random_seed",
    "char",
    "start_count",
    "end_count",
    "win_move_count_to_char",
    "total_move_count_to_char",
    "win_rate_to_char",
]


def write_rows(path: str | Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: list[float]) -> str:
    return f"{statistics.mean(values):.6f}" if values else ""


def _stdev(values: list[float]) -> str:
    if len(values) <= 1:
        return "0.000000" if values else ""
    return f"{statistics.stdev(values):.6f}"


def first_move_rows(
    dict_size: int,
    random_seed: int,
    results: list[FirstMoveResult],
) -> list[dict[str, object]]:
    return [
        {
            "dict_size": dict_size,
            "random_seed": random_seed,
            "word": result.word,
            "start_char": result.start_char,
            "end_char": result.end_char,
            "result": result.result,
            "opponent_reply_count": result.opponent_reply_count,
            "searched_state_count_after_move": result.searched_state_count_after_move,
        }
        for result in sorted(
            results,
            key=lambda item: (not item.is_winning, item.opponent_reply_count, item.word),
        )
    ]


def char_stats_rows(
    dict_size: int,
    random_seed: int,
    graph: WordGraph,
    first_moves: list[FirstMoveResult],
) -> list[dict[str, object]]:
    chars = sorted(set(graph.start_chars) | set(graph.end_chars))
    rows: list[dict[str, object]] = []
    for char in chars:
        total_to_char = sum(1 for result in first_moves if result.end_char == char)
        wins_to_char = sum(
            1 for result in first_moves if result.end_char == char and result.is_winning
        )
        rows.append(
            {
                "dict_size": dict_size,
                "random_seed": random_seed,
                "char": char,
                "start_count": graph.start_chars.count(char),
                "end_count": graph.end_chars.count(char),
                "win_move_count_to_char": wins_to_char,
                "total_move_count_to_char": total_to_char,
                "win_rate_to_char": f"{wins_to_char / total_to_char:.6f}" if total_to_char else "0.000000",
            }
        )
    return rows


def run_one_exact(
    records: list[ReadingRecord],
    dict_size: int,
    random_seed: int,
    max_states: int | None,
    timeout_sec: float | None,
    pool_multiplier: int,
    dataset_dir: Path | None,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    selected = select_records(records, dict_size, random_seed, pool_multiplier=pool_multiplier)
    if dataset_dir is not None:
        write_records_csv(selected, dataset_dir / f"D{dict_size}_seed{random_seed}.csv")

    graph = WordGraph.from_words([record.reading for record in selected])
    solver = ShiritoriSolver(graph, max_states=max_states, timeout_sec=timeout_sec)
    started = time.perf_counter()
    timed_out = False
    limit_reason = ""
    first_results: list[FirstMoveResult] = []

    try:
        first_results = solver.analyze_first_moves(reset_between_moves=False)
    except AnalysisLimitExceeded as exc:
        timed_out = True
        limit_reason = exc.reason

    elapsed = time.perf_counter() - started
    if first_results and not timed_out:
        winning_count: object = sum(1 for result in first_results if result.is_winning)
        losing_count: object = len(first_results) - int(winning_count)
        first_player_win: object = int(winning_count) > 0
    else:
        winning_count = ""
        losing_count = ""
        first_player_win = ""

    run_row = {
        "dict_size": dict_size,
        "random_seed": random_seed,
        "searched_state_count": solver.count_states(),
        "memo_size": len(solver.memo),
        "elapsed_time_sec": f"{elapsed:.6f}",
        "timed_out": timed_out,
        "limit_reason": limit_reason,
        "is_first_player_win": first_player_win,
        "winning_first_move_count": winning_count,
        "losing_first_move_count": losing_count,
        "n_ending_count": graph.n_ending_word_count(),
        "start_distribution": distribution_json(graph.words, 0),
        "end_distribution": distribution_json(graph.words, -1),
    }

    return (
        run_row,
        first_move_rows(dict_size, random_seed, first_results),
        char_stats_rows(dict_size, random_seed, graph, first_results),
        dictionary_char_total_rows(graph, dict_size, random_seed),
    )


def summarize_runs(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for dict_size in sorted({int(row["dict_size"]) for row in rows}):
        size_rows = [row for row in rows if int(row["dict_size"]) == dict_size]
        completed = [row for row in size_rows if not row["timed_out"] and row["winning_first_move_count"] != ""]
        state_counts = [float(row["searched_state_count"]) for row in completed]
        elapsed = [float(row["elapsed_time_sec"]) for row in completed]
        winning_counts = [float(row["winning_first_move_count"]) for row in completed]
        win_rate = (
            sum(1 for row in completed if str(row["is_first_player_win"]) == "True") / len(completed)
            if completed
            else ""
        )
        summaries.append(
            {
                "dict_size": dict_size,
                "seed_count": len(size_rows),
                "completed_seed_count": len(completed),
                "searched_state_count_mean": _mean(state_counts),
                "searched_state_count_stdev": _stdev(state_counts),
                "elapsed_time_sec_mean": _mean(elapsed),
                "elapsed_time_sec_stdev": _stdev(elapsed),
                "first_player_win_rate": f"{win_rate:.6f}" if win_rate != "" else "",
                "winning_first_move_count_mean": _mean(winning_counts),
                "winning_first_move_count_stdev": _stdev(winning_counts),
            }
        )
    return summaries


def default_seeds(seed_count: int) -> list[int]:
    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    return list(range(seed_count))


def all_seed_runs_timed_out(size_rows: list[dict[str, object]], seed_count: int) -> bool:
    return len(size_rows) == seed_count and all(bool(row["timed_out"]) for row in size_rows)


def load_records(args: argparse.Namespace) -> tuple[list[ReadingRecord], dict[str, object]]:
    if args.records:
        records = read_csv_records(args.records)
        return records, {"source": args.records, "mode": "records_csv"}
    records, stats = parse_jmdict(
        args.jmdict,
        min_length=args.min_length,
        max_length=args.max_length,
    )
    return records, {"source": args.jmdict, "mode": "jmdict", "stats": asdict(stats)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--jmdict")
    source_group.add_argument("--records")
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=None,
        help=(
            "Explicit dictionary sizes. Omit this to start at --size-start and "
            "increase by --size-step until every seed times out at the same size."
        ),
    )
    parser.add_argument("--size-start", type=int, default=DEFAULT_SIZE_START)
    parser.add_argument("--size-step", type=int, default=DEFAULT_SIZE_STEP)
    parser.add_argument(
        "--max-size",
        type=int,
        default=None,
        help="Optional upper bound for automatic size growth.",
    )
    parser.add_argument("--seed-count", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=None,
        help="Explicit seeds. Omit this to use 0..--seed-count-1.",
    )
    parser.add_argument("--output-dir", default="results/exact")
    parser.add_argument("--dataset-dir", default="data/generated/exact")
    parser.add_argument(
        "--max-states",
        type=int,
        default=None,
        help="Maximum searched states. Omit or set 0 to rely on timeout only.",
    )
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--pool-multiplier", type=int, default=1)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=12)
    args = parser.parse_args()

    if args.sizes is not None and any(size <= 0 for size in args.sizes):
        parser.error("--sizes values must be positive")
    if args.size_start <= 0:
        parser.error("--size-start must be positive")
    if args.size_step <= 0:
        parser.error("--size-step must be positive")
    if args.max_size is not None and args.max_size <= 0:
        parser.error("--max-size must be positive")
    if args.max_size is not None and args.max_size < args.size_start:
        parser.error("--max-size must be greater than or equal to --size-start")

    if args.seeds is None:
        try:
            args.seeds = default_seeds(args.seed_count)
        except ValueError as exc:
            parser.error(str(exc))
    elif not args.seeds:
        parser.error("--seeds must contain at least one seed")

    return args


def run_size_exact(
    records: list[ReadingRecord],
    dict_size: int,
    seeds: list[int],
    max_states: int | None,
    timeout_sec: float | None,
    pool_multiplier: int,
    dataset_dir: Path | None,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    size_run_rows: list[dict[str, object]] = []
    size_first_move_rows: list[dict[str, object]] = []
    size_char_stats_rows: list[dict[str, object]] = []
    size_dictionary_char_rows: list[dict[str, object]] = []

    for random_seed in seeds:
        run_row, move_rows, stats_rows, dictionary_rows = run_one_exact(
            records=records,
            dict_size=dict_size,
            random_seed=random_seed,
            max_states=max_states,
            timeout_sec=timeout_sec,
            pool_multiplier=pool_multiplier,
            dataset_dir=dataset_dir,
        )
        size_run_rows.append(run_row)
        size_first_move_rows.extend(move_rows)
        size_char_stats_rows.extend(stats_rows)
        size_dictionary_char_rows.extend(dictionary_rows)
        print(
            f"D{dict_size}_seed{random_seed}: states={run_row['searched_state_count']} "
            f"timeout={run_row['timed_out']}"
        )

    return size_run_rows, size_first_move_rows, size_char_stats_rows, size_dictionary_char_rows


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    dataset_dir = Path(args.dataset_dir) if args.dataset_dir else None
    if dataset_dir is not None:
        dataset_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    records, source_metadata = load_records(args)
    max_states = args.max_states if args.max_states and args.max_states > 0 else None
    run_rows: list[dict[str, object]] = []
    all_first_move_rows: list[dict[str, object]] = []
    all_char_stats_rows: list[dict[str, object]] = []
    all_dictionary_char_rows: list[dict[str, object]] = []
    stop_reason = "fixed_sizes_completed" if args.sizes is not None else ""
    size_mode = "fixed" if args.sizes is not None else "until_all_seeds_timeout"

    if args.sizes is not None:
        sizes_to_run = args.sizes
        for dict_size in sizes_to_run:
            size_rows, move_rows, stats_rows, dictionary_rows = run_size_exact(
                records=records,
                dict_size=dict_size,
                seeds=args.seeds,
                max_states=max_states,
                timeout_sec=args.timeout_sec,
                pool_multiplier=args.pool_multiplier,
                dataset_dir=dataset_dir,
            )
            run_rows.extend(size_rows)
            all_first_move_rows.extend(move_rows)
            all_char_stats_rows.extend(stats_rows)
            all_dictionary_char_rows.extend(dictionary_rows)
    else:
        dict_size = args.size_start
        while True:
            if dict_size > len(records):
                stop_reason = "available_records_exhausted"
                print(f"stop: dict_size={dict_size} exceeds available records={len(records)}")
                break

            size_rows, move_rows, stats_rows, dictionary_rows = run_size_exact(
                records=records,
                dict_size=dict_size,
                seeds=args.seeds,
                max_states=max_states,
                timeout_sec=args.timeout_sec,
                pool_multiplier=args.pool_multiplier,
                dataset_dir=dataset_dir,
            )
            run_rows.extend(size_rows)
            all_first_move_rows.extend(move_rows)
            all_char_stats_rows.extend(stats_rows)
            all_dictionary_char_rows.extend(dictionary_rows)

            if all_seed_runs_timed_out(size_rows, len(args.seeds)):
                stop_reason = "all_seeds_timed_out"
                print(f"stop: all {len(args.seeds)} seeds timed out at D{dict_size}")
                break

            next_size = dict_size + args.size_step
            if args.max_size is not None and next_size > args.max_size:
                stop_reason = "max_size_reached"
                print(f"stop: next dict_size={next_size} exceeds max_size={args.max_size}")
                break
            dict_size = next_size

    summary_rows = summarize_runs(run_rows)
    write_rows(output_dir / "exact_runs.csv", EXACT_RUN_FIELDS, run_rows)
    write_rows(output_dir / "exact_summary_by_size.csv", EXACT_SUMMARY_FIELDS, summary_rows)
    write_rows(output_dir / "first_move_results.csv", FIRST_MOVE_FIELDS, all_first_move_rows)
    write_rows(output_dir / "char_stats.csv", CHAR_STATS_FIELDS, all_char_stats_rows)
    write_rows(output_dir / "dictionary_char_totals.csv", DICTIONARY_CHAR_TOTAL_FIELDS, all_dictionary_char_rows)
    write_json(
        {
            "source": source_metadata,
            "size_mode": size_mode,
            "sizes": sorted({int(row["dict_size"]) for row in run_rows}),
            "requested_sizes": args.sizes,
            "size_start": args.size_start,
            "size_step": args.size_step,
            "max_size": args.max_size,
            "stop_reason": stop_reason,
            "seeds": args.seeds,
            "seed_count": len(args.seeds),
            "max_states": max_states,
            "timeout_sec": args.timeout_sec,
            "pool_multiplier": args.pool_multiplier,
        },
        output_dir / "exact_config.json",
    )


if __name__ == "__main__":
    main()
