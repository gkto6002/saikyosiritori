"""Match simulation for approximate AI and human-vs-AI modes."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agents import BaseAgent, GameState
from game import WordGraph


@dataclass
class PlayerTiming:
    total_time_sec: float = 0.0
    max_time_sec: float = 0.0
    move_count: int = 0
    timeout_count: int = 0

    @property
    def average_time_sec(self) -> float:
        if self.move_count == 0:
            return 0.0
        return self.total_time_sec / self.move_count

    def add(self, elapsed_time_sec: float, timed_out: bool) -> None:
        self.total_time_sec += elapsed_time_sec
        self.max_time_sec = max(self.max_time_sec, elapsed_time_sec)
        self.move_count += 1
        if timed_out:
            self.timeout_count += 1


@dataclass
class MatchResult:
    dict_size: int
    first_agent: str
    second_agent: str
    winner: str
    turn_count: int
    used_word_count: int
    loss_reason: str
    first_total_time_sec: float
    second_total_time_sec: float
    first_avg_time_sec: float
    second_avg_time_sec: float
    first_max_time_sec: float
    second_max_time_sec: float
    first_timeout_count: int
    second_timeout_count: int
    max_moves: int
    max_match_time_sec: float
    match_elapsed_time_sec: float
    history: list[dict[str, object]] = field(default_factory=list)

    def to_csv_row(self) -> dict[str, object]:
        row = asdict(self)
        row["history"] = json.dumps(self.history, ensure_ascii=False)
        return row


def simulate_match(
    graph: WordGraph,
    first_agent: BaseAgent,
    second_agent: BaseAgent,
    max_moves: int,
    max_match_time_sec: float,
    match_id: str = "",
) -> MatchResult:
    agents = [first_agent, second_agent]
    timings = [PlayerTiming(), PlayerTiming()]
    used_ids: set[int] = set()
    current_char: str | None = None
    previous_word: str | None = None
    history: list[dict[str, object]] = []
    started = time.perf_counter()
    winner = "draw"
    loss_reason = "max_moves_reached"

    for turn_index in range(max_moves):
        elapsed_match = time.perf_counter() - started
        if elapsed_match >= max_match_time_sec:
            winner = "draw"
            loss_reason = "match_timeout"
            break

        player_index = turn_index % 2
        agent = agents[player_index]
        legal_moves = (
            [word_id for word_id in range(len(graph.words)) if word_id not in used_ids]
            if current_char is None
            else graph.available_word_ids_set(current_char, used_ids)
        )
        if not legal_moves:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "no_legal_move"
            break

        state = GameState(current_char=current_char, used_ids=frozenset(used_ids))
        decision = agent.choose_move(graph, state)
        timings[player_index].add(decision.elapsed_time_sec, decision.timed_out)

        if decision.word_id is None or decision.word_id not in legal_moves:
            winner = "second" if player_index == 0 else "first"
            loss_reason = "invalid_ai_move"
            break

        word_id = decision.word_id
        word = graph.words[word_id]
        required_start_char = current_char if current_char is not None else "ANY"
        used_ids.add(word_id)
        history.append(
            {
                "match_id": match_id,
                "turn": turn_index + 1,
                "player": "first" if player_index == 0 else "second",
                "agent": agent.name,
                "required_start_char": required_start_char,
                "previous_word": previous_word or "",
                "word_id": word_id,
                "word": word,
                "start_char": graph.start_chars[word_id],
                "end_char": graph.end_chars[word_id],
                "next_required_start_char": "" if graph.end_chars[word_id] == "ん" else graph.end_chars[word_id],
                "elapsed_time_sec": round(decision.elapsed_time_sec, 6),
                "timed_out": decision.timed_out,
                "score": decision.score,
            }
        )

        if graph.end_chars[word_id] == "ん":
            winner = "second" if player_index == 0 else "first"
            loss_reason = "ended_with_n"
            break

        previous_word = word
        current_char = graph.end_chars[word_id]
    else:
        winner = "draw"
        loss_reason = "max_moves_reached"

    match_elapsed = time.perf_counter() - started
    return MatchResult(
        dict_size=len(graph.words),
        first_agent=first_agent.name,
        second_agent=second_agent.name,
        winner=winner,
        turn_count=len(history),
        used_word_count=len(used_ids),
        loss_reason=loss_reason,
        first_total_time_sec=timings[0].total_time_sec,
        second_total_time_sec=timings[1].total_time_sec,
        first_avg_time_sec=timings[0].average_time_sec,
        second_avg_time_sec=timings[1].average_time_sec,
        first_max_time_sec=timings[0].max_time_sec,
        second_max_time_sec=timings[1].max_time_sec,
        first_timeout_count=timings[0].timeout_count,
        second_timeout_count=timings[1].timeout_count,
        max_moves=max_moves,
        max_match_time_sec=max_match_time_sec,
        match_elapsed_time_sec=match_elapsed,
        history=history,
    )


def append_jsonl(rows: list[dict[str, object]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as jsonl_file:
        for row in rows:
            jsonl_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
