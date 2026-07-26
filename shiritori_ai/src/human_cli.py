"""Command-line human-vs-AI shiritori."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from agents import DEFAULT_BEAM_WIDTHS, DEFAULT_TIME_LIMIT_SEC, build_agent
from dataset import parse_jmdict, read_csv_records, select_records
from runtime_dictionary import RuntimeDictionary
from runtime_state import HumanRuntimeState


def load_runtime(args: argparse.Namespace) -> RuntimeDictionary:
    if args.runtime:
        return RuntimeDictionary.load(args.runtime)
    if args.words:
        records = read_csv_records(args.words)
    else:
        records, _stats = parse_jmdict(args.jmdict, min_length=args.min_length, max_length=args.max_length)
        records = select_records(records, args.dict_size, args.random_seed, pool_multiplier=args.pool_multiplier)
    return RuntimeDictionary.from_readings(
        record.reading for record in records[: args.dict_size]
    )


def show_candidates(state: HumanRuntimeState, limit: int = 20) -> None:
    candidates = [
        word_id
        for word_id in range(state.runtime.word_count)
        if word_id not in state.used_word_ids
        and (
            state.required_char_id is None
            or state.runtime.word_start_ids[word_id] == state.required_char_id
        )
    ]
    words = [state.runtime.word_readings[word_id] for word_id in candidates[:limit]]
    print("候補:", "、".join(words) if words else "なし")


def parse_beam_widths(value: str) -> tuple[int, ...]:
    try:
        widths = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("beam widths must be comma-separated integers") from exc
    if not widths or any(width <= 0 for width in widths):
        raise argparse.ArgumentTypeError("beam widths must be positive")
    return widths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--runtime", help="RuntimeDictionary JSON (recommended)")
    source_group.add_argument("--words", help="CSV file with readings")
    source_group.add_argument("--jmdict", help="JMdict XML or .gz")
    parser.add_argument("--dict-size", type=int, default=1000)
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument("--pool-multiplier", type=int, default=1)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument(
        "--agent",
        choices=[
            "random",
            "greedy",
            "graph_control",
            "minimax",
            "monte_carlo",
            "alpha_beta",
            "full_alpha_beta",
            "beam_negamax",
            "pvs",
            "aggressive_pvs",
            "graph_pvs",
            "beam_alpha_beta",
            "beam_pvs",
        ],
        default="greedy",
    )
    parser.add_argument("--human-first", action="store_true")
    parser.add_argument("--time-limit-sec", type=float, default=DEFAULT_TIME_LIMIT_SEC)
    parser.add_argument("--show-candidates", action="store_true")
    parser.add_argument("--history-output", default="results/human/human_match_history.json")
    parser.add_argument("--minimax-depth", type=int, default=3)
    parser.add_argument("--alpha-beta-depth", type=int, default=3)
    parser.add_argument("--beam-negamax-depth", type=int, default=4)
    parser.add_argument("--aggressive-pvs-depth", type=int, default=3)
    parser.add_argument(
        "--hybrid-depth",
        type=int,
        help="Depth for GraphPVS/BeamAlphaBeta/BeamPVS",
    )
    parser.add_argument("--beam-widths", type=parse_beam_widths, default=DEFAULT_BEAM_WIDTHS)
    parser.add_argument("--branch-limit", type=int, default=12)
    parser.add_argument(
        "--adaptive-depth",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-depth", type=int, default=1)
    parser.add_argument("--depth-recovery-turns", type=int, default=5)
    parser.add_argument("--depth-decrease-ratio", type=float, default=0.9)
    parser.add_argument("--depth-recovery-ratio", type=float, default=0.5)
    parser.add_argument("--depth-step", type=int, default=1)
    parser.add_argument("--adaptive-max-depth-increment", type=int, default=0)
    parser.add_argument(
        "--target-time-sec",
        type=float,
        help="Soft target used for depth control; defaults to --time-limit-sec",
    )
    parser.add_argument(
        "--timeout-decreases-depth",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--monte-carlo-candidates", type=int, default=20)
    parser.add_argument("--monte-carlo-playouts", type=int, default=10)
    parser.add_argument("--monte-carlo-max-moves", type=int, default=200)
    args = parser.parse_args()
    if args.hybrid_depth is not None and args.hybrid_depth <= 0:
        parser.error("--hybrid-depth must be positive")
    if args.adaptive_max_depth_increment < 0:
        parser.error("--adaptive-max-depth-increment must be non-negative")
    if args.target_time_sec is not None and (
        args.target_time_sec <= 0 or args.target_time_sec > args.time_limit_sec
    ):
        parser.error("--target-time-sec must be positive and no greater than --time-limit-sec")
    return args


def main() -> None:
    args = parse_args()
    runtime = load_runtime(args)
    state = HumanRuntimeState.initial(runtime)
    ai = build_agent(
        args.agent,
        time_limit_sec=args.time_limit_sec,
        random_seed=args.random_seed,
        minimax_depth=args.minimax_depth,
        alpha_beta_depth=args.alpha_beta_depth,
        branch_limit=args.branch_limit,
        beam_negamax_depth=args.beam_negamax_depth,
        beam_widths=args.beam_widths,
        aggressive_pvs_depth=args.aggressive_pvs_depth,
        hybrid_depth=args.hybrid_depth,
        adaptive_depth=args.adaptive_depth,
        min_depth=args.min_depth,
        depth_recovery_turns=args.depth_recovery_turns,
        depth_decrease_ratio=args.depth_decrease_ratio,
        depth_recovery_ratio=args.depth_recovery_ratio,
        depth_step=args.depth_step,
        timeout_decreases_depth=args.timeout_decreases_depth,
        adaptive_max_depth_increment=args.adaptive_max_depth_increment,
        target_time_sec=args.target_time_sec,
        monte_carlo_candidates=args.monte_carlo_candidates,
        monte_carlo_playouts=args.monte_carlo_playouts,
        monte_carlo_max_moves=args.monte_carlo_max_moves,
    )

    last_word: str | None = None
    history: list[dict[str, object]] = []
    ai_total_time = 0.0
    ai_max_time = 0.0
    ai_move_count = 0
    human_turn = args.human_first
    winner = ""
    reason = ""

    print(f"辞書サイズ: {runtime.word_count}")
    print(f"AI: {ai.name}")

    while True:
        print()
        current_char = (
            None
            if state.required_char_id is None
            else runtime.id_to_char[state.required_char_id]
        )
        print(f"現在の文字: {current_char if current_char is not None else '任意'}")
        print(f"直前の読み: {last_word if last_word is not None else 'なし'}")
        print(f"使用済み語数: {len(state.used_word_ids)}")

        if state.edge_search_state().legal_word_count() == 0:
            winner = "AI" if human_turn else "human"
            reason = "no_legal_move"
            break

        decision_extra: dict[str, object] = {}
        decision_timed_out = False
        decision_score: float | None = None
        if human_turn:
            if args.show_candidates:
                show_candidates(state)
            while True:
                raw = input("読みを入力してください: ")
                human_result = state.submit_human_reading(raw)
                if human_result.accepted:
                    word_id = human_result.word_id
                    break
                print(f"不正な手: {human_result.message}")
            player = "human"
        else:
            decision = ai.choose_edge(state.edge_search_state())
            if decision.start_id is None or decision.end_id is None:
                winner = "human"
                reason = "ai_no_move"
                break
            word_id = state.choose_ai_word(decision.start_id, decision.end_id)
            ai_total_time += decision.elapsed_time_sec
            ai_max_time = max(ai_max_time, decision.elapsed_time_sec)
            ai_move_count += 1
            decision_extra = decision.extra
            decision_timed_out = decision.timed_out
            decision_score = decision.score
            print(f"AIの手: {runtime.word_readings[word_id]}")
            print(f"AI思考時間: {decision.elapsed_time_sec:.6f} 秒")
            player = "ai"

        assert word_id is not None
        word = runtime.word_readings[word_id]
        last_word = word
        history.append(
            {
                "turn": len(history) + 1,
                "player": player,
                "word": word,
                "start_char": runtime.id_to_char[runtime.word_start_ids[word_id]],
                "end_char": runtime.id_to_char[runtime.word_end_ids[word_id]],
                "timed_out": decision_timed_out,
                "score": decision_score,
                "decision_extra": decision_extra,
            }
        )

        if runtime.id_to_char[runtime.word_end_ids[word_id]] == "ん":
            winner = "AI" if human_turn else "human"
            reason = "ended_with_n"
            break

        human_turn = not human_turn

    print()
    print(f"勝者: {winner}")
    print(f"手数: {len(history)}")
    print(f"使用単語数: {len(state.used_word_ids)}")
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
                "used_word_count": len(state.used_word_ids),
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
