"""Shared dictionary-quality statistics for experiments."""

from __future__ import annotations

from game import WordGraph
from runtime_dictionary import EdgeDictionary


DICTIONARY_CHAR_TOTAL_FIELDS = [
    "dict_size",
    "random_seed",
    "char",
    "start_count",
    "end_count",
    "total_count",
    "start_rate",
    "end_rate",
    "total_rate",
]


def dictionary_char_total_rows(
    graph: WordGraph,
    dict_size: int,
    random_seed: int,
) -> list[dict[str, object]]:
    start_counts = graph.start_distribution()
    end_counts = graph.end_distribution()
    chars = sorted(set(start_counts) | set(end_counts))
    word_count = len(graph.words)
    total_positions = word_count * 2

    rows: list[dict[str, object]] = []
    for char in chars:
        start_count = start_counts.get(char, 0)
        end_count = end_counts.get(char, 0)
        total_count = start_count + end_count
        rows.append(
            {
                "dict_size": dict_size,
                "random_seed": random_seed,
                "char": char,
                "start_count": start_count,
                "end_count": end_count,
                "total_count": total_count,
                "start_rate": f"{start_count / word_count:.6f}" if word_count else "0.000000",
                "end_rate": f"{end_count / word_count:.6f}" if word_count else "0.000000",
                "total_rate": f"{total_count / total_positions:.6f}" if total_positions else "0.000000",
            }
        )
    return rows


def edge_dictionary_char_total_rows(
    dictionary: EdgeDictionary,
    dict_size: int,
    random_seed: int,
) -> list[dict[str, object]]:
    """Build the same distribution directly from edge multiplicities."""

    word_count = dictionary.edge_instance_count
    total_positions = word_count * 2
    rows: list[dict[str, object]] = []
    for char_id, char in enumerate(dictionary.id_to_char):
        start_count = sum(
            dictionary.edge_count(char_id, end_id)
            for end_id in range(dictionary.char_count)
        )
        end_count = sum(
            dictionary.edge_count(start_id, char_id)
            for start_id in range(dictionary.char_count)
        )
        if start_count == 0 and end_count == 0:
            continue
        total_count = start_count + end_count
        rows.append(
            {
                "dict_size": dict_size,
                "random_seed": random_seed,
                "char": char,
                "start_count": start_count,
                "end_count": end_count,
                "total_count": total_count,
                "start_rate": f"{start_count / word_count:.6f}" if word_count else "0.000000",
                "end_rate": f"{end_count / word_count:.6f}" if word_count else "0.000000",
                "total_rate": f"{total_count / total_positions:.6f}" if total_positions else "0.000000",
            }
        )
    return rows
