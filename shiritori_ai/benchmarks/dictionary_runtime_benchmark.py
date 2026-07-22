"""Non-gating benchmark comparing WordGraph operations with RuntimeDictionary."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from game import WordGraph  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState, HumanRuntimeState  # noqa: E402


def elapsed(callable_, repetitions: int) -> float:
    started = time.perf_counter()
    for _ in range(repetitions):
        callable_()
    return time.perf_counter() - started


def deep_size(value: object, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(deep_size(key, seen) + deep_size(item, seen) for key, item in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(deep_size(item, seen) for item in value)
    elif hasattr(value, "__dict__"):
        size += deep_size(vars(value), seen)
    return size


def benchmark(
    details_path: str | Path,
    repetitions: int = 1000,
    text_path: str | Path | None = None,
    runtime_path: str | Path | None = None,
) -> dict[str, object]:
    details = Path(details_path)
    started = time.perf_counter()
    runtime = RuntimeDictionary.from_details_jsonl(details)
    runtime_build_sec = time.perf_counter() - started

    started = time.perf_counter()
    graph = runtime.to_word_graph()
    word_graph_build_sec = time.perf_counter() - started
    comparison = runtime.compare_word_graph(graph)
    if not all(comparison.values()):
        raise AssertionError(f"old/new mismatch: {comparison}")

    start_id = max(
        range(runtime.char_count),
        key=lambda value: len(runtime.word_ids_for_start(value)),
        default=0,
    )
    start_char = runtime.id_to_char[start_id] if runtime.char_count else ""
    used_ids: set[int] = set()
    old_legal_sec = elapsed(lambda: graph.available_word_ids_set(start_char, used_ids), repetitions)
    new_legal_sec = elapsed(lambda: runtime.word_ids_for_start(start_id), repetitions)
    old_end_ids_sec = elapsed(
        lambda: sorted({graph.end_chars[word_id] for word_id in graph.available_word_ids_set(start_char, used_ids)}),
        repetitions,
    )
    new_end_ids_sec = elapsed(lambda: runtime.available_end_ids(start_id), repetitions)
    edge_copy_sec = elapsed(lambda: list(runtime.initial_edge_counts), repetitions)

    ai_state = AIEdgeState.initial(runtime)
    start_for_edge, end_for_edge = ai_state.available_edges()[0]
    apply_undo_sec = elapsed(
        lambda: (ai_state.apply_edge(start_for_edge, end_for_edge), ai_state.undo_edge()),
        repetitions,
    )
    old_used = set(range(min(1000, runtime.word_count)))
    old_state_copy_sec = elapsed(lambda: set(old_used), repetitions)
    runtime_state_copy_sec = elapsed(
        lambda: (list(ai_state.edge_counts), list(ai_state.active_end_masks)),
        repetitions,
    )

    old_dictionary_load_sec = None
    if text_path is not None:
        started = time.perf_counter()
        WordGraph.from_text(text_path)
        old_dictionary_load_sec = time.perf_counter() - started
    runtime_dictionary_load_sec = None
    if runtime_path is not None:
        started = time.perf_counter()
        RuntimeDictionary.load(runtime_path)
        runtime_dictionary_load_sec = time.perf_counter() - started

    human_state = HumanRuntimeState.initial(runtime)
    runtime_state_memory = (
        deep_size(ai_state.edge_counts)
        + deep_size(ai_state.active_end_masks)
        + deep_size(ai_state.edge_history)
    )
    human_state_memory = (
        deep_size(human_state.edge_counts)
        + deep_size(human_state.active_end_masks)
        + deep_size(human_state.used_word_ids)
        + deep_size(human_state.bucket_cursors)
        + deep_size(human_state.word_history)
    )
    return {
        "word_count": runtime.word_count,
        "char_count": runtime.char_count,
        "runtime_build_sec": runtime_build_sec,
        "word_graph_build_sec": word_graph_build_sec,
        "repetitions": repetitions,
        "benchmark_start_char": start_char,
        "benchmark_start_word_count": len(runtime.word_ids_for_start(start_id)) if runtime.char_count else 0,
        "old_legal_enumeration_total_sec": old_legal_sec,
        "runtime_legal_enumeration_total_sec": new_legal_sec,
        "old_end_enumeration_total_sec": old_end_ids_sec,
        "runtime_end_enumeration_total_sec": new_end_ids_sec,
        "edge_counts_copy_total_sec": edge_copy_sec,
        "apply_undo_total_sec": apply_undo_sec,
        "old_state_copy_total_sec": old_state_copy_sec,
        "runtime_state_copy_total_sec": runtime_state_copy_sec,
        "old_dictionary_load_sec": old_dictionary_load_sec,
        "runtime_dictionary_load_sec": runtime_dictionary_load_sec,
        "word_graph_memory_bytes_approx": deep_size(graph),
        "runtime_dictionary_memory_bytes_approx": deep_size(runtime),
        "old_used_set_1000_memory_bytes_approx": deep_size(old_used),
        "ai_edge_state_mutable_memory_bytes_approx": runtime_state_memory,
        "human_runtime_state_mutable_memory_bytes_approx": human_state_memory,
        "old_new_comparison": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--details", required=True)
    parser.add_argument("--repetitions", type=int, default=1000)
    parser.add_argument("--text")
    parser.add_argument("--runtime")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark(args.details, args.repetitions, text_path=args.text, runtime_path=args.runtime)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
