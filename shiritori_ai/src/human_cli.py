"""Command-line human-vs-AI shiritori."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from agents import GameState, build_agent
from dataset import parse_jmdict, read_csv_records, select_records
from game import WordGraph, normalize_game_char
from normalize import normalize_reading


def load_graph(args: argparse.Namespace) -> WordGraph:
    if args.words:
        records = read_csv_records(args.words)
    else:
        records, _stats = parse_jmdict(args.jmdict, min_length=args.min_length, max_length=args.max_length)
        records = select_records(records, args.dict_size, args.random_seed, pool_multiplier=args.pool_multiplier)
    return WordGraph.from_words([record.reading for record in records[: args.dict_size]])


def show_candidates(graph: WordGraph, current_char: str | None, used_ids: set[int], limit: int = 20) -> None:
    if current_char is None:
        candidates = [word_id for word_id in range(len(graph.words)) if word_id not in used_ids]
    else:
        candidates = graph.available_word_ids_set(current_char, used_ids)
    words = [graph.words[word_id] for word_id in candidates[:limit]]
    print("候補:", "、".join(words) if words else "なし")


def validate_human_move(
    graph: WordGraph,
    reading_to_id: dict[str, int],
    raw_input: str,
    current_char: str | None,
    used_ids: set[int],
) -> tuple[int | None, str | None]:
    normalized = normalize_reading(raw_input)
    if normalized is None:
        return None, "読みを正規化できません"
    if normalized not in reading_to_id:
        return None, "辞書に存在しません"

    word_id = reading_to_id[normalized]
    if word_id in used_ids:
        return None, "すでに使用済みです"
    if current_char is not None and normalize_game_char(normalized[0]) != normalize_game_char(current_char):
        return None, f"現在の文字「{current_char}」から始まっていません"
    return word_id, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--words", help="CSV file with readings")
    source_group.add_argument("--jmdict", help="JMdict XML or .gz")
    parser.add_argument("--dict-size", type=int, default=1000)
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument("--pool-multiplier", type=int, default=1)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument("--agent", choices=["random", "greedy", "minimax", "monte_carlo"], default="greedy")
    parser.add_argument("--human-first", action="store_true")
    parser.add_argument("--time-limit-sec", type=float, default=0.5)
    parser.add_argument("--show-candidates", action="store_true")
    parser.add_argument("--history-output", default="results/human/human_match_history.json")
    parser.add_argument("--minimax-depth", type=int, default=3)
    parser.add_argument("--branch-limit", type=int, default=20)
    parser.add_argument("--monte-carlo-candidates", type=int, default=20)
    parser.add_argument("--monte-carlo-playouts", type=int, default=10)
    parser.add_argument("--monte-carlo-max-moves", type=int, default=200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = load_graph(args)
    reading_to_id = graph.word_id_by_reading()
    ai = build_agent(
        args.agent,
        time_limit_sec=args.time_limit_sec,
        random_seed=args.random_seed,
        minimax_depth=args.minimax_depth,
        branch_limit=args.branch_limit,
        monte_carlo_candidates=args.monte_carlo_candidates,
        monte_carlo_playouts=args.monte_carlo_playouts,
        monte_carlo_max_moves=args.monte_carlo_max_moves,
    )

    used_ids: set[int] = set()
    current_char: str | None = None
    last_word: str | None = None
    history: list[dict[str, object]] = []
    ai_total_time = 0.0
    ai_max_time = 0.0
    ai_move_count = 0
    human_turn = args.human_first
    winner = ""
    reason = ""

    print(f"辞書サイズ: {len(graph.words)}")
    print(f"AI: {ai.name}")

    while True:
        print()
        print(f"現在の文字: {current_char if current_char is not None else '任意'}")
        print(f"直前の読み: {last_word if last_word is not None else 'なし'}")
        print(f"使用済み語数: {len(used_ids)}")

        legal_moves = (
            [word_id for word_id in range(len(graph.words)) if word_id not in used_ids]
            if current_char is None
            else graph.available_word_ids_set(current_char, used_ids)
        )
        if not legal_moves:
            winner = "AI" if human_turn else "human"
            reason = "no_legal_move"
            break

        if human_turn:
            if args.show_candidates:
                show_candidates(graph, current_char, used_ids)
            while True:
                raw = input("読みを入力してください: ")
                word_id, error = validate_human_move(graph, reading_to_id, raw, current_char, used_ids)
                if error is None and word_id is not None:
                    break
                print(f"不正な手: {error}")
            player = "human"
        else:
            state = GameState(current_char=current_char, used_ids=frozenset(used_ids))
            decision = ai.choose_move(graph, state)
            word_id = decision.word_id
            if word_id is None:
                winner = "human"
                reason = "ai_no_move"
                break
            ai_total_time += decision.elapsed_time_sec
            ai_max_time = max(ai_max_time, decision.elapsed_time_sec)
            ai_move_count += 1
            print(f"AIの手: {graph.words[word_id]}")
            print(f"AI思考時間: {decision.elapsed_time_sec:.6f} 秒")
            player = "ai"

        assert word_id is not None
        word = graph.words[word_id]
        used_ids.add(word_id)
        last_word = word
        history.append(
            {
                "turn": len(history) + 1,
                "player": player,
                "word": word,
                "start_char": graph.start_chars[word_id],
                "end_char": graph.end_chars[word_id],
            }
        )

        if graph.end_chars[word_id] == "ん":
            winner = "AI" if human_turn else "human"
            reason = "ended_with_n"
            break

        current_char = graph.end_chars[word_id]
        human_turn = not human_turn

    print()
    print(f"勝者: {winner}")
    print(f"手数: {len(history)}")
    print(f"使用単語数: {len(used_ids)}")
    print(f"敗因: {reason}")
    print(f"AI合計思考時間: {ai_total_time:.6f} 秒")
    print(f"AI平均思考時間: {(ai_total_time / ai_move_count) if ai_move_count else 0.0:.6f} 秒")
    print("使用単語列:", " -> ".join(row["word"] for row in history))

    output = Path(args.history_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "winner": winner,
                "turn_count": len(history),
                "used_word_count": len(used_ids),
                "loss_reason": reason,
                "ai_total_time_sec": ai_total_time,
                "ai_average_time_sec": (ai_total_time / ai_move_count) if ai_move_count else 0.0,
                "ai_max_time_sec": ai_max_time,
                "history": history,
                "saved_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
