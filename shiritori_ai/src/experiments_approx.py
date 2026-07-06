"""Large-dictionary approximate-AI tournament experiments."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from agents import build_agent
from dataset import ReadingRecord, parse_jmdict, read_csv_records, select_records, write_json, write_records_csv
from dictionary_stats import DICTIONARY_CHAR_TOTAL_FIELDS, dictionary_char_total_rows
from game import WordGraph
from match import MatchResult, append_jsonl, simulate_match


MATCH_FIELDS = [
    "match_id",
    "dict_size",
    "random_seed",
    "first_agent",
    "second_agent",
    "winner",
    "turn_count",
    "used_word_count",
    "loss_reason",
    "first_total_time_sec",
    "second_total_time_sec",
    "first_avg_time_sec",
    "second_avg_time_sec",
    "first_max_time_sec",
    "second_max_time_sec",
    "first_timeout_count",
    "second_timeout_count",
    "max_moves",
    "max_match_time_sec",
    "match_elapsed_time_sec",
    "history",
]

AGENT_SUMMARY_FIELDS = [
    "agent_name",
    "dict_size",
    "match_count",
    "win_count",
    "loss_count",
    "draw_count",
    "win_rate",
    "average_turn_count",
    "average_used_word_count",
    "average_time_per_move_sec",
    "max_time_sec",
    "timeout_count",
]

MATCH_FLOW_FIELDS = [
    "matchup",
    "first_agent",
    "second_agent",
    "match_id",
    "dict_size",
    "random_seed",
    "winner",
    "loss_reason",
    "turn",
    "player",
    "agent",
    "required_start_char",
    "previous_word",
    "word",
    "start_char",
    "end_char",
    "next_required_start_char",
    "elapsed_time_sec",
    "timed_out",
    "score",
    "chain_so_far",
]

AGENT_END_CHAR_FIELDS = [
    "agent_name",
    "dict_size",
    "end_char",
    "move_count",
    "move_rate",
    "timeout_count",
    "average_elapsed_time_sec",
    "ended_with_n_count",
]

FIRST_PLAYER_BY_SIZE_FIELDS = [
    "dict_size",
    "match_count",
    "first_win_count",
    "second_win_count",
    "draw_count",
    "first_win_rate",
]

TOP_END_CHAR_FIELDS = [
    "dict_size",
    "rank",
    "end_char",
    "move_count",
    "move_rate",
    "ended_with_n_count",
    "average_elapsed_time_sec",
]


def write_rows(path: str | Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def result_to_row(match_id: str, dict_size: int, random_seed: int, result: MatchResult) -> dict[str, object]:
    row = result.to_csv_row()
    row["match_id"] = match_id
    row["dict_size"] = dict_size
    row["random_seed"] = random_seed
    return row


def summarize_agents(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        dict_size = int(row["dict_size"])
        buckets[(str(row["first_agent"]), dict_size)].append({**row, "side": "first"})
        buckets[(str(row["second_agent"]), dict_size)].append({**row, "side": "second"})

    summaries: list[dict[str, object]] = []
    for (agent_name, dict_size), agent_rows in sorted(buckets.items()):
        wins = 0
        losses = 0
        draws = 0
        total_time = 0.0
        total_moves = 0
        max_time = 0.0
        timeouts = 0
        turn_counts = []
        used_counts = []

        for row in agent_rows:
            side = row["side"]
            winner = row["winner"]
            if winner == "draw":
                draws += 1
            elif winner == side:
                wins += 1
            else:
                losses += 1

            if side == "first":
                total_time += float(row["first_total_time_sec"])
                total_moves += max(0, (int(row["turn_count"]) + 1) // 2)
                max_time = max(max_time, float(row["first_max_time_sec"]))
                timeouts += int(row["first_timeout_count"])
            else:
                total_time += float(row["second_total_time_sec"])
                total_moves += int(row["turn_count"]) // 2
                max_time = max(max_time, float(row["second_max_time_sec"]))
                timeouts += int(row["second_timeout_count"])

            turn_counts.append(int(row["turn_count"]))
            used_counts.append(int(row["used_word_count"]))

        match_count = len(agent_rows)
        summaries.append(
            {
                "agent_name": agent_name,
                "dict_size": dict_size,
                "match_count": match_count,
                "win_count": wins,
                "loss_count": losses,
                "draw_count": draws,
                "win_rate": f"{wins / match_count:.6f}" if match_count else "0.000000",
                "average_turn_count": f"{statistics.mean(turn_counts):.6f}" if turn_counts else "0.000000",
                "average_used_word_count": f"{statistics.mean(used_counts):.6f}" if used_counts else "0.000000",
                "average_time_per_move_sec": f"{total_time / total_moves:.6f}" if total_moves else "0.000000",
                "max_time_sec": f"{max_time:.6f}",
                "timeout_count": timeouts,
            }
        )
    return summaries


def build_match_flow_rows(
    result: MatchResult,
    match_id: str,
    dict_size: int,
    random_seed: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    chain: list[str] = []
    matchup = f"{result.first_agent} vs {result.second_agent}"
    for turn in result.history:
        chain.append(str(turn["word"]))
        rows.append(
            {
                "matchup": matchup,
                "first_agent": result.first_agent,
                "second_agent": result.second_agent,
                "match_id": match_id,
                "dict_size": dict_size,
                "random_seed": random_seed,
                "winner": result.winner,
                "loss_reason": result.loss_reason,
                "turn": turn["turn"],
                "player": turn["player"],
                "agent": turn["agent"],
                "required_start_char": turn.get("required_start_char", ""),
                "previous_word": turn.get("previous_word", ""),
                "word": turn["word"],
                "start_char": turn["start_char"],
                "end_char": turn["end_char"],
                "next_required_start_char": turn.get("next_required_start_char", ""),
                "elapsed_time_sec": turn["elapsed_time_sec"],
                "timed_out": turn["timed_out"],
                "score": turn["score"],
                "chain_so_far": " -> ".join(chain),
            }
        )
    return rows


def build_match_flow_json_row(
    result: MatchResult,
    match_id: str,
    dict_size: int,
    random_seed: int,
) -> dict[str, object]:
    words = [str(turn["word"]) for turn in result.history]
    return {
        "matchup": f"{result.first_agent} vs {result.second_agent}",
        "first_agent": result.first_agent,
        "second_agent": result.second_agent,
        "match_id": match_id,
        "dict_size": dict_size,
        "random_seed": random_seed,
        "winner": result.winner,
        "loss_reason": result.loss_reason,
        "turn_count": result.turn_count,
        "used_word_count": result.used_word_count,
        "word_chain": words,
        "flow_text": " -> ".join(words),
        "turns": result.history,
    }


def summarize_agent_end_chars(flow_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    totals: dict[tuple[str, int], int] = defaultdict(int)
    buckets: dict[tuple[str, int, str], dict[str, float]] = defaultdict(
        lambda: {"move_count": 0.0, "timeout_count": 0.0, "elapsed_time_sec": 0.0}
    )

    for row in flow_rows:
        agent_name = str(row["agent"])
        dict_size = int(row["dict_size"])
        end_char = str(row["end_char"])
        totals[(agent_name, dict_size)] += 1
        bucket = buckets[(agent_name, dict_size, end_char)]
        bucket["move_count"] += 1
        bucket["elapsed_time_sec"] += float(row["elapsed_time_sec"])
        if str(row["timed_out"]) == "True" or row["timed_out"] is True:
            bucket["timeout_count"] += 1

    rows: list[dict[str, object]] = []
    for (agent_name, dict_size, end_char), bucket in sorted(buckets.items()):
        move_count = int(bucket["move_count"])
        total = totals[(agent_name, dict_size)]
        rows.append(
            {
                "agent_name": agent_name,
                "dict_size": dict_size,
                "end_char": end_char,
                "move_count": move_count,
                "move_rate": f"{move_count / total:.6f}" if total else "0.000000",
                "timeout_count": int(bucket["timeout_count"]),
                "average_elapsed_time_sec": f"{bucket['elapsed_time_sec'] / move_count:.6f}" if move_count else "0.000000",
                "ended_with_n_count": move_count if end_char == "ん" else 0,
            }
        )
    return rows


def summarize_first_player_by_size(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for dict_size in sorted({int(row["dict_size"]) for row in rows}):
        size_rows = [row for row in rows if int(row["dict_size"]) == dict_size]
        first_wins = sum(1 for row in size_rows if row["winner"] == "first")
        second_wins = sum(1 for row in size_rows if row["winner"] == "second")
        draws = sum(1 for row in size_rows if row["winner"] == "draw")
        match_count = len(size_rows)
        summaries.append(
            {
                "dict_size": dict_size,
                "match_count": match_count,
                "first_win_count": first_wins,
                "second_win_count": second_wins,
                "draw_count": draws,
                "first_win_rate": f"{first_wins / match_count:.6f}" if match_count else "0.000000",
            }
        )
    return summaries


def summarize_top_end_chars(
    flow_rows: list[dict[str, object]],
    top_n: int,
) -> list[dict[str, object]]:
    totals: dict[int, int] = defaultdict(int)
    buckets: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"move_count": 0.0, "ended_with_n_count": 0.0, "elapsed_time_sec": 0.0}
    )
    for row in flow_rows:
        dict_size = int(row["dict_size"])
        end_char = str(row["end_char"])
        totals[dict_size] += 1
        bucket = buckets[(dict_size, end_char)]
        bucket["move_count"] += 1
        bucket["elapsed_time_sec"] += float(row["elapsed_time_sec"])
        if end_char == "ん":
            bucket["ended_with_n_count"] += 1

    rows: list[dict[str, object]] = []
    for dict_size in sorted(totals):
        candidates = [
            (end_char, bucket)
            for (size, end_char), bucket in buckets.items()
            if size == dict_size
        ]
        candidates.sort(key=lambda item: (-item[1]["move_count"], item[0]))
        for rank, (end_char, bucket) in enumerate(candidates[:top_n], start=1):
            move_count = int(bucket["move_count"])
            rows.append(
                {
                    "dict_size": dict_size,
                    "rank": rank,
                    "end_char": end_char,
                    "move_count": move_count,
                    "move_rate": f"{move_count / totals[dict_size]:.6f}" if totals[dict_size] else "0.000000",
                    "ended_with_n_count": int(bucket["ended_with_n_count"]),
                    "average_elapsed_time_sec": f"{bucket['elapsed_time_sec'] / move_count:.6f}" if move_count else "0.000000",
                }
            )
    return rows


def load_records(args: argparse.Namespace) -> tuple[list[ReadingRecord], dict[str, object]]:
    if args.records:
        return read_csv_records(args.records), {"source": args.records, "mode": "records_csv"}
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
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 3000, 5000, 10000])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0])
    parser.add_argument("--agents", nargs="+", default=["random", "greedy", "minimax", "monte_carlo"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output-dir", default="results/approx")
    parser.add_argument("--dataset-dir", default="data/generated/approx")
    parser.add_argument("--time-limit-sec", type=float, default=4.0)
    parser.add_argument("--max-moves", type=int)
    parser.add_argument("--max-match-time-sec", type=float, default=960.0)
    parser.add_argument("--minimax-depth", type=int, default=3)
    parser.add_argument("--branch-limit", type=int, default=20)
    parser.add_argument("--monte-carlo-candidates", type=int, default=20)
    parser.add_argument("--monte-carlo-playouts", type=int, default=10)
    parser.add_argument("--monte-carlo-max-moves", type=int, default=200)
    parser.add_argument("--pool-multiplier", type=int, default=1)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument("--top-end-chars", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    dataset_dir = Path(args.dataset_dir) if args.dataset_dir else None
    output_dir.mkdir(parents=True, exist_ok=True)
    if dataset_dir is not None:
        dataset_dir.mkdir(parents=True, exist_ok=True)

    records, source_metadata = load_records(args)
    match_rows: list[dict[str, object]] = []
    flow_rows: list[dict[str, object]] = []
    flow_json_rows: list[dict[str, object]] = []
    dictionary_char_rows: list[dict[str, object]] = []
    jsonl_path = output_dir / "match_logs.jsonl"
    if jsonl_path.exists():
        jsonl_path.unlink()

    for dict_size in args.sizes:
        max_moves = args.max_moves if args.max_moves is not None else min(dict_size, 3000)
        for random_seed in args.seeds:
            selected = select_records(records, dict_size, random_seed, pool_multiplier=args.pool_multiplier)
            if dataset_dir is not None:
                write_records_csv(selected, dataset_dir / f"D{dict_size}_seed{random_seed}.csv")
            graph = WordGraph.from_words([record.reading for record in selected])
            dictionary_char_rows.extend(dictionary_char_total_rows(graph, dict_size, random_seed))

            for first_name, second_name in itertools.product(args.agents, repeat=2):
                for repetition in range(args.repetitions):
                    match_id = f"D{dict_size}_seed{random_seed}_{first_name}_vs_{second_name}_{repetition}"
                    first_agent = build_agent(
                        first_name,
                        time_limit_sec=args.time_limit_sec,
                        random_seed=random_seed * 100_000 + repetition * 100 + 1,
                        minimax_depth=args.minimax_depth,
                        branch_limit=args.branch_limit,
                        monte_carlo_candidates=args.monte_carlo_candidates,
                        monte_carlo_playouts=args.monte_carlo_playouts,
                        monte_carlo_max_moves=args.monte_carlo_max_moves,
                    )
                    second_agent = build_agent(
                        second_name,
                        time_limit_sec=args.time_limit_sec,
                        random_seed=random_seed * 100_000 + repetition * 100 + 2,
                        minimax_depth=args.minimax_depth,
                        branch_limit=args.branch_limit,
                        monte_carlo_candidates=args.monte_carlo_candidates,
                        monte_carlo_playouts=args.monte_carlo_playouts,
                        monte_carlo_max_moves=args.monte_carlo_max_moves,
                    )
                    result = simulate_match(
                        graph=graph,
                        first_agent=first_agent,
                        second_agent=second_agent,
                        max_moves=max_moves,
                        max_match_time_sec=args.max_match_time_sec,
                        match_id=match_id,
                    )
                    row = result_to_row(match_id, dict_size, random_seed, result)
                    match_rows.append(row)
                    flow_rows.extend(build_match_flow_rows(result, match_id, dict_size, random_seed))
                    flow_json_rows.append(build_match_flow_json_row(result, match_id, dict_size, random_seed))
                    append_jsonl(
                        [{"match_id": match_id, "history": result.history, "loss_reason": result.loss_reason}],
                        jsonl_path,
                    )
                    print(
                        f"{match_id}: winner={result.winner} turns={result.turn_count} "
                        f"reason={result.loss_reason}"
                    )

    summary_rows = summarize_agents(match_rows)
    end_char_rows = summarize_agent_end_chars(flow_rows)
    first_player_rows = summarize_first_player_by_size(match_rows)
    top_end_char_rows = summarize_top_end_chars(flow_rows, top_n=args.top_end_chars)
    write_rows(output_dir / "matches.csv", MATCH_FIELDS, match_rows)
    write_rows(output_dir / "agent_summary.csv", AGENT_SUMMARY_FIELDS, summary_rows)
    write_rows(output_dir / "match_flow.csv", MATCH_FLOW_FIELDS, flow_rows)
    write_rows(output_dir / "agent_end_char_stats.csv", AGENT_END_CHAR_FIELDS, end_char_rows)
    write_rows(output_dir / "first_player_by_size.csv", FIRST_PLAYER_BY_SIZE_FIELDS, first_player_rows)
    write_rows(output_dir / "top_end_chars.csv", TOP_END_CHAR_FIELDS, top_end_char_rows)
    write_rows(output_dir / "dictionary_char_totals.csv", DICTIONARY_CHAR_TOTAL_FIELDS, dictionary_char_rows)
    flow_json_path = output_dir / "match_flow.jsonl"
    if flow_json_path.exists():
        flow_json_path.unlink()
    append_jsonl(flow_json_rows, flow_json_path)
    write_json(
        {
            "source": source_metadata,
            "sizes": args.sizes,
            "seeds": args.seeds,
            "agents": args.agents,
            "repetitions": args.repetitions,
            "time_limit_sec": args.time_limit_sec,
            "max_moves": args.max_moves,
            "default_max_moves_policy": "min(dict_size, 3000)",
            "max_match_time_sec": args.max_match_time_sec,
            "minimax_depth": args.minimax_depth,
            "branch_limit": args.branch_limit,
            "monte_carlo_candidates": args.monte_carlo_candidates,
            "monte_carlo_playouts": args.monte_carlo_playouts,
            "monte_carlo_max_moves": args.monte_carlo_max_moves,
            "pool_multiplier": args.pool_multiplier,
            "top_end_chars": args.top_end_chars,
        },
        output_dir / "approx_config.json",
    )


if __name__ == "__main__":
    main()
