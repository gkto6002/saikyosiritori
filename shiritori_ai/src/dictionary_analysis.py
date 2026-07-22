"""Analyze experiment dictionaries and their character-level directed graphs."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Iterable

from experiment_dictionary import (
    detail_records,
    filter_ranked_pool,
    rank_noun_pool,
    read_jsonl,
)
from runtime_dictionary import RuntimeDictionary


def basic_statistics(
    runtime: RuntimeDictionary,
    details: list[dict[str, object]],
) -> dict[str, object]:
    if len(details) != runtime.word_count:
        raise ValueError("details word count does not match RuntimeDictionary")
    lengths = [int(record["normalized_length"]) for record in details]
    priority_counts = Counter(str(record.get("priority_level", 1)) for record in details)
    start_counts = Counter(runtime.id_to_char[start_id] for start_id in runtime.word_start_ids)
    end_counts = Counter(runtime.id_to_char[end_id] for end_id in runtime.word_end_ids)
    return {
        "word_count": runtime.word_count,
        "minimum_normalized_length": min(lengths) if lengths else None,
        "maximum_normalized_length": max(lengths) if lengths else None,
        "average_normalized_length": statistics.fmean(lengths) if lengths else None,
        "median_normalized_length": statistics.median(lengths) if lengths else None,
        "normalized_length_word_counts": dict(
            sorted(Counter(str(value) for value in lengths).items(), key=lambda item: int(item[0]))
        ),
        "priority_level_word_counts": dict(sorted(priority_counts.items())),
        "start_char_word_counts": dict(sorted(start_counts.items())),
        "end_char_word_counts": dict(sorted(end_counts.items())),
        "n_ending_word_count": end_counts.get("ん", 0),
    }


def _directed_adjacency(runtime: RuntimeDictionary) -> tuple[list[set[int]], list[set[int]]]:
    outgoing = [set() for _ in range(runtime.char_count)]
    incoming = [set() for _ in range(runtime.char_count)]
    for start_id in range(runtime.char_count):
        for end_id in runtime.available_end_ids(start_id):
            outgoing[start_id].add(end_id)
            incoming[end_id].add(start_id)
    return outgoing, incoming


def strongly_connected_components(outgoing: list[set[int]]) -> list[list[int]]:
    """Return deterministic Tarjan strongly connected components."""

    index = 0
    indices = [-1] * len(outgoing)
    lowlinks = [0] * len(outgoing)
    stack: list[int] = []
    on_stack = [False] * len(outgoing)
    components: list[list[int]] = []

    def visit(vertex: int) -> None:
        nonlocal index
        indices[vertex] = index
        lowlinks[vertex] = index
        index += 1
        stack.append(vertex)
        on_stack[vertex] = True
        for neighbor in sorted(outgoing[vertex]):
            if indices[neighbor] == -1:
                visit(neighbor)
                lowlinks[vertex] = min(lowlinks[vertex], lowlinks[neighbor])
            elif on_stack[neighbor]:
                lowlinks[vertex] = min(lowlinks[vertex], indices[neighbor])
        if lowlinks[vertex] == indices[vertex]:
            component: list[int] = []
            while True:
                member = stack.pop()
                on_stack[member] = False
                component.append(member)
                if member == vertex:
                    break
            components.append(sorted(component))

    for vertex in range(len(outgoing)):
        if indices[vertex] == -1:
            visit(vertex)
    return sorted(components, key=lambda component: (component[0], len(component)))


def weakly_connected_components(
    outgoing: list[set[int]],
    incoming: list[set[int]],
) -> list[list[int]]:
    remaining = set(range(len(outgoing)))
    components: list[list[int]] = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        component: list[int] = []
        while queue:
            vertex = queue.popleft()
            component.append(vertex)
            for neighbor in sorted(outgoing[vertex] | incoming[vertex]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return components


def graph_statistics(runtime: RuntimeDictionary) -> dict[str, object]:
    outgoing, incoming = _directed_adjacency(runtime)
    out_word_counts = [
        sum(runtime.edge_count(start_id, end_id) for end_id in range(runtime.char_count))
        for start_id in range(runtime.char_count)
    ]
    in_word_counts = [
        sum(runtime.edge_count(start_id, end_id) for start_id in range(runtime.char_count))
        for end_id in range(runtime.char_count)
    ]
    weak_components = weakly_connected_components(outgoing, incoming)
    strong_components = strongly_connected_components(outgoing)
    edge_type_count = sum(bool(count) for count in runtime.initial_edge_counts)
    n_id = runtime.char_to_id.get("ん")
    n_edges = (
        sum(runtime.edge_count(start_id, n_id) for start_id in range(runtime.char_count))
        if n_id is not None
        else 0
    )
    max_out = max(range(runtime.char_count), key=lambda item: (out_word_counts[item], -item), default=None)
    max_in = max(range(runtime.char_count), key=lambda item: (in_word_counts[item], -item), default=None)
    char_rows = [
        {
            "char_id": char_id,
            "char": runtime.id_to_char[char_id],
            "outgoing_word_count": out_word_counts[char_id],
            "incoming_word_count": in_word_counts[char_id],
            "outgoing_end_type_count": len(outgoing[char_id]),
            "incoming_start_type_count": len(incoming[char_id]),
        }
        for char_id in range(runtime.char_count)
    ]
    return {
        "char_count": runtime.char_count,
        "total_edge_count": runtime.word_count,
        "distinct_edge_type_count": edge_type_count,
        "char_degrees": char_rows,
        "no_outgoing_chars": [runtime.id_to_char[index] for index, count in enumerate(out_word_counts) if count == 0],
        "no_incoming_chars": [runtime.id_to_char[index] for index, count in enumerate(in_word_counts) if count == 0],
        "maximum_outgoing": None
        if max_out is None
        else {"char": runtime.id_to_char[max_out], "word_count": out_word_counts[max_out]},
        "maximum_incoming": None
        if max_in is None
        else {"char": runtime.id_to_char[max_in], "word_count": in_word_counts[max_in]},
        "weak_component_count": len(weak_components),
        "strong_component_count": len(strong_components),
        "largest_weak_component_size": max((len(value) for value in weak_components), default=0),
        "largest_strong_component_size": max((len(value) for value in strong_components), default=0),
        "weak_components": [
            [runtime.id_to_char[char_id] for char_id in component] for component in weak_components
        ],
        "strong_components": [
            [runtime.id_to_char[char_id] for char_id in component] for component in strong_components
        ],
        "n_ending_edge_count": n_edges,
        "non_n_ending_edge_count": runtime.word_count - n_edges,
    }


def analyze_dictionary(
    runtime: RuntimeDictionary,
    details: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "dictionary_hash": runtime.dictionary_hash,
        "format_version": runtime.format_version,
        "normalization_version": runtime.normalization_version,
        "basic_statistics": basic_statistics(runtime, details),
        "graph_statistics": graph_statistics(runtime),
    }


def length_limit_comparison(
    ranked_pool: list[dict[str, object]],
    min_length: int,
    max_lengths: Iterable[int],
    requested_size: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for max_length in max_lengths:
        candidates = filter_ranked_pool(ranked_pool, min_length, max_length)
        selected = candidates[:requested_size]
        details = detail_records(selected)
        runtime = RuntimeDictionary.from_detail_records(details)
        basic = basic_statistics(runtime, details)
        graph = graph_statistics(runtime)
        rows.append(
            {
                "min_length": min_length,
                "max_length": max_length,
                "candidate_count": len(candidates),
                "requested_size": requested_size,
                "can_generate_requested_size": len(candidates) >= requested_size,
                "analyzed_word_count": len(selected),
                "average_normalized_length": basic["average_normalized_length"],
                "distinct_edge_type_count": graph["distinct_edge_type_count"],
                "strong_component_count": graph["strong_component_count"],
                "largest_strong_component_size": graph["largest_strong_component_size"],
                "no_outgoing_char_count": len(graph["no_outgoing_chars"]),
                "n_ending_word_count": basic["n_ending_word_count"],
            }
        )
    return rows


def dictionary_size_comparison(
    ranked_pool: list[dict[str, object]],
    min_length: int,
    max_length: int,
    sizes: Iterable[int],
) -> list[dict[str, object]]:
    candidates = filter_ranked_pool(ranked_pool, min_length, max_length)
    rows: list[dict[str, object]] = []
    previous_readings: list[str] = []
    for size in sizes:
        selected = candidates[:size]
        readings = [str(record["normalized_reading"]) for record in selected]
        details = detail_records(selected)
        runtime = RuntimeDictionary.from_detail_records(details)
        graph = graph_statistics(runtime)
        rows.append(
            {
                "requested_size": size,
                "candidate_count": len(candidates),
                "can_generate_requested_size": len(candidates) >= size,
                "actual_word_count": len(selected),
                "contains_previous_dictionary": readings[: len(previous_readings)] == previous_readings,
                "distinct_edge_type_count": graph["distinct_edge_type_count"],
                "strong_component_count": graph["strong_component_count"],
                "largest_strong_component_size": graph["largest_strong_component_size"],
                "n_ending_word_count": graph["n_ending_edge_count"],
            }
        )
        previous_readings = readings
    return rows


def _write_json(value: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(rows: list[dict[str, object]], path: Path, fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def write_analysis_outputs(
    analysis: dict[str, object],
    length_rows: list[dict[str, object]],
    size_rows: list[dict[str, object]],
    output_dir: str | Path,
    generate_plots: bool = True,
) -> dict[str, Path]:
    output = Path(output_dir)
    basic = analysis["basic_statistics"]
    graph = analysis["graph_statistics"]
    assert isinstance(basic, dict) and isinstance(graph, dict)
    paths = {
        "detailed_statistics": output / "detailed_statistics.json",
        "graph_metrics": output / "graph_metrics.json",
        "length_distribution": output / "length_distribution.csv",
        "start_distribution": output / "start_char_distribution.csv",
        "end_distribution": output / "end_char_distribution.csv",
        "char_degrees": output / "char_degrees.csv",
        "length_comparison": output / "length_limit_comparison.csv",
        "size_comparison": output / "dictionary_size_comparison.csv",
    }
    _write_json(analysis, paths["detailed_statistics"])
    _write_json(graph, paths["graph_metrics"])
    _write_csv(
        [{"normalized_length": key, "word_count": value} for key, value in basic["normalized_length_word_counts"].items()],
        paths["length_distribution"],
    )
    _write_csv(
        [{"char": key, "word_count": value} for key, value in basic["start_char_word_counts"].items()],
        paths["start_distribution"],
    )
    _write_csv(
        [{"char": key, "word_count": value} for key, value in basic["end_char_word_counts"].items()],
        paths["end_distribution"],
    )
    _write_csv(list(graph["char_degrees"]), paths["char_degrees"])
    _write_csv(length_rows, paths["length_comparison"])
    _write_csv(size_rows, paths["size_comparison"])
    if generate_plots:
        _write_plots(basic, graph, length_rows, size_rows, output)
    return paths


def _write_plots(
    basic: dict[str, object],
    graph: dict[str, object],
    length_rows: list[dict[str, object]],
    size_rows: list[dict[str, object]],
    output: Path,
) -> None:
    from visualize import ensure_matplotlib

    plt = ensure_matplotlib()

    output.mkdir(parents=True, exist_ok=True)

    def bar_plot(mapping: dict[str, int], title: str, xlabel: str, filename: str) -> None:
        fig, axis = plt.subplots(figsize=(12, 5))
        axis.bar(list(mapping), list(mapping.values()))
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel("word count")
        fig.tight_layout()
        fig.savefig(output / filename, dpi=150)
        plt.close(fig)

    bar_plot(basic["normalized_length_word_counts"], "Normalized length distribution", "length", "length_distribution.png")
    bar_plot(basic["start_char_word_counts"], "Start character frequency", "character", "start_char_frequency.png")
    bar_plot(basic["end_char_word_counts"], "End character frequency", "character", "end_char_frequency.png")

    degree_rows = graph["char_degrees"]
    fig, axis = plt.subplots(figsize=(14, 6))
    positions = list(range(len(degree_rows)))
    axis.bar([value - 0.2 for value in positions], [row["outgoing_word_count"] for row in degree_rows], width=0.4, label="out")
    axis.bar([value + 0.2 for value in positions], [row["incoming_word_count"] for row in degree_rows], width=0.4, label="in")
    axis.set_xticks(positions, [row["char"] for row in degree_rows])
    axis.legend()
    axis.set_title("Incoming and outgoing word counts")
    fig.tight_layout()
    fig.savefig(output / "char_in_out_counts.png", dpi=150)
    plt.close(fig)

    if length_rows:
        fig, axis = plt.subplots(figsize=(8, 5))
        axis.plot([row["max_length"] for row in length_rows], [row["candidate_count"] for row in length_rows], marker="o")
        axis.set_xlabel("maximum length")
        axis.set_ylabel("candidate words")
        axis.set_title("Candidates by maximum length")
        fig.tight_layout()
        fig.savefig(output / "max_length_candidate_count.png", dpi=150)
        plt.close(fig)

    if size_rows:
        fig, axis = plt.subplots(figsize=(8, 5))
        axis.plot([row["requested_size"] for row in size_rows], [row["distinct_edge_type_count"] for row in size_rows], marker="o")
        axis.set_xlabel("dictionary size")
        axis.set_ylabel("distinct edge types")
        axis.set_title("Edge types by dictionary size")
        fig.tight_layout()
        fig.savefig(output / "dictionary_size_edge_types.png", dpi=150)
        plt.close(fig)


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True)
    parser.add_argument("--details", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument("--comparison-size", type=int, default=10000)
    parser.add_argument("--max-lengths", type=_parse_int_list, default=[3, 4, 5, 6, 8, 10, 12])
    parser.add_argument("--sizes", type=_parse_int_list, default=[100, 200, 500, 1000, 3000, 5000, 10000])
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    try:
        runtime = RuntimeDictionary.load(args.runtime)
        details = read_jsonl(args.details)
        master_records = read_jsonl(args.master)
        ranked_pool = rank_noun_pool(master_records, seed=args.seed)
        analysis = analyze_dictionary(runtime, details)
        length_rows = length_limit_comparison(
            ranked_pool,
            min_length=args.min_length,
            max_lengths=args.max_lengths,
            requested_size=args.comparison_size,
        )
        size_rows = dictionary_size_comparison(
            ranked_pool,
            min_length=args.min_length,
            max_length=args.max_length,
            sizes=args.sizes,
        )
        write_analysis_outputs(
            analysis,
            length_rows,
            size_rows,
            args.output,
            generate_plots=not args.no_plots,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    graph = analysis["graph_statistics"]
    print(f"words={runtime.word_count}")
    print(f"chars={runtime.char_count}")
    print(f"edge_types={graph['distinct_edge_type_count']}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
