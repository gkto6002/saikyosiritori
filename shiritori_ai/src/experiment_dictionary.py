"""Build reproducible noun experiment dictionaries from the master JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from normalize import NORMALIZATION_VERSION


FORMAT_VERSION = "experiment_dictionary_v1"


class InsufficientCandidatesError(ValueError):
    def __init__(self, candidate_count: int, requested_count: int) -> None:
        self.candidate_count = candidate_count
        self.requested_count = requested_count
        self.shortage_count = requested_count - candidate_count
        super().__init__(
            f"candidate words={candidate_count}, requested words={requested_count}, "
            f"shortage={self.shortage_count}; use --allow-smaller to permit a smaller dictionary"
        )


@dataclass(frozen=True)
class ExperimentDictionaryArtifact:
    dictionary_name: str
    text_path: Path
    details_path: Path
    metadata_path: Path
    statistics_path: Path
    requested_size: int
    actual_size: int
    candidate_count: int


def read_jsonl(path: str | Path) -> list[dict[str, object]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"JSONL input does not exist: {source}")
    records: list[dict[str, object]] = []
    with source.open("r", encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number} of {source}: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} of {source} is not a JSON object")
            records.append(value)
    return records


def rank_noun_pool(
    master_records: Iterable[dict[str, object]],
    seed: int,
) -> list[dict[str, object]]:
    """Return one stable priority-first ordering shared by all experiments."""

    by_priority: dict[int, list[dict[str, object]]] = {3: [], 2: [], 1: []}
    seen: set[str] = set()
    for record in master_records:
        reading = str(record.get("normalized_reading", ""))
        if not reading or not bool(record.get("has_noun_sense")):
            continue
        if reading in seen:
            raise ValueError(f"duplicate normalized_reading in master dictionary: {reading}")
        seen.add(reading)
        level = int(record.get("priority_level", 1))
        if level not in by_priority:
            level = 1
        by_priority[level].append(record)

    rng = random.Random(seed)
    ranked: list[dict[str, object]] = []
    for level in (3, 2, 1):
        group = sorted(by_priority[level], key=lambda record: str(record["normalized_reading"]))
        rng.shuffle(group)
        ranked.extend(group)
    return ranked


def filter_ranked_pool(
    ranked_pool: Iterable[dict[str, object]],
    min_length: int,
    max_length: int,
) -> list[dict[str, object]]:
    if min_length <= 0:
        raise ValueError("min_length must be positive")
    if max_length < min_length:
        raise ValueError("max_length must be greater than or equal to min_length")
    return [
        record
        for record in ranked_pool
        if min_length <= int(record["normalized_length"]) <= max_length
    ]


def select_ranked_records(
    ranked_pool: Iterable[dict[str, object]],
    size: int,
    min_length: int,
    max_length: int,
    allow_smaller: bool = False,
) -> tuple[list[dict[str, object]], int]:
    if size <= 0:
        raise ValueError("size must be positive")
    candidates = filter_ranked_pool(ranked_pool, min_length=min_length, max_length=max_length)
    if len(candidates) < size and not allow_smaller:
        raise InsufficientCandidatesError(len(candidates), size)
    return candidates[:size], len(candidates)


def detail_records(selected: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for word_id, record in enumerate(selected):
        details.append(
            {
                "word_id": word_id,
                "normalized_reading": str(record["normalized_reading"]),
                "normalized_length": int(record["normalized_length"]),
                "start_char": str(record["start_char"]),
                "end_char": str(record["end_char"]),
                "ends_with_n": bool(record["ends_with_n"]),
                "priority_level": int(record["priority_level"]),
                "priority_tags": list(record.get("priority_tags", [])),
                "source_entry_ids": list(record.get("entry_ids", [])),
            }
        )
    return details


def experiment_statistics(
    details: list[dict[str, object]],
    candidate_count: int,
) -> dict[str, object]:
    lengths = [int(record["normalized_length"]) for record in details]
    return {
        "candidate_count": candidate_count,
        "word_count": len(details),
        "priority_level_word_counts": dict(
            sorted(Counter(str(record["priority_level"]) for record in details).items())
        ),
        "normalized_length_word_counts": dict(
            sorted(
                Counter(str(length) for length in lengths).items(),
                key=lambda item: int(item[0]),
            )
        ),
        "start_char_word_counts": dict(
            sorted(Counter(str(record["start_char"]) for record in details).items())
        ),
        "end_char_word_counts": dict(
            sorted(Counter(str(record["end_char"]) for record in details).items())
        ),
        "n_ending_word_count": sum(bool(record["ends_with_n"]) for record in details),
        "minimum_normalized_length": min(lengths) if lengths else None,
        "maximum_normalized_length": max(lengths) if lengths else None,
        "average_normalized_length": (sum(lengths) / len(lengths)) if lengths else None,
    }


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(text)
        os.replace(temporary_name, path)
    except OSError:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _write_json(data: object, path: Path) -> None:
    _atomic_write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        path,
    )


def _write_jsonl(records: Iterable[dict[str, object]], path: Path) -> None:
    _atomic_write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        path,
    )


def write_experiment_dictionary(
    master_path: str | Path,
    ranked_pool: list[dict[str, object]],
    output_dir: str | Path,
    size: int,
    min_length: int,
    max_length: int,
    seed: int,
    allow_smaller: bool = False,
    master_sha256: str | None = None,
) -> ExperimentDictionaryArtifact:
    selected, candidate_count = select_ranked_records(
        ranked_pool,
        size=size,
        min_length=min_length,
        max_length=max_length,
        allow_smaller=allow_smaller,
    )
    details = detail_records(selected)
    output = Path(output_dir)
    dictionary_name = f"D{size}_L{min_length}-{max_length}_seed{seed}"
    text_path = output / f"{dictionary_name}.txt"
    details_path = output / f"{dictionary_name}.jsonl"
    metadata_path = output / f"{dictionary_name}.metadata.json"
    statistics_path = output / f"{dictionary_name}.stats.json"

    _atomic_write_text("".join(f"{record['normalized_reading']}\n" for record in details), text_path)
    _write_jsonl(details, details_path)
    statistics = experiment_statistics(details, candidate_count=candidate_count)
    _write_json(statistics, statistics_path)
    metadata = {
        "dictionary_name": dictionary_name,
        "master_dictionary_sha256": master_sha256 or _sha256(master_path),
        "generation_conditions": {
            "has_noun_sense": True,
            "min_length": min_length,
            "max_length": max_length,
            "seed": seed,
            "requested_size": size,
            "allow_smaller": allow_smaller,
        },
        "min_length": min_length,
        "max_length": max_length,
        "seed": seed,
        "requested_word_count": size,
        "actual_word_count": len(details),
        "candidate_word_count": candidate_count,
        "dictionary_sha256": _sha256(text_path),
        "details_sha256": _sha256(details_path),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "format_version": FORMAT_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "text_file_name": text_path.name,
        "details_file_name": details_path.name,
        "statistics_file_name": statistics_path.name,
    }
    _write_json(metadata, metadata_path)
    return ExperimentDictionaryArtifact(
        dictionary_name=dictionary_name,
        text_path=text_path,
        details_path=details_path,
        metadata_path=metadata_path,
        statistics_path=statistics_path,
        requested_size=size,
        actual_size=len(details),
        candidate_count=candidate_count,
    )


def build_experiment_dictionaries(
    master_path: str | Path,
    output_dir: str | Path,
    sizes: Iterable[int],
    max_lengths: Iterable[int],
    seed: int,
    min_length: int = 2,
    allow_smaller: bool = False,
) -> list[ExperimentDictionaryArtifact]:
    master_records = read_jsonl(master_path)
    ranked_pool = rank_noun_pool(master_records, seed=seed)
    master_sha256 = _sha256(master_path)
    artifacts: list[ExperimentDictionaryArtifact] = []
    for max_length in max_lengths:
        for size in sizes:
            artifacts.append(
                write_experiment_dictionary(
                    master_path=master_path,
                    ranked_pool=ranked_pool,
                    output_dir=output_dir,
                    size=size,
                    min_length=min_length,
                    max_length=max_length,
                    seed=seed,
                    allow_smaller=allow_smaller,
                    master_sha256=master_sha256,
                )
            )
    return artifacts


def _parse_int_list(value: str) -> list[int]:
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one integer is required")
    return values


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True, help="Master dictionary JSONL")
    size_group = parser.add_mutually_exclusive_group(required=True)
    size_group.add_argument("--size", type=int)
    size_group.add_argument("--sizes", type=_parse_int_list)
    length_group = parser.add_mutually_exclusive_group()
    length_group.add_argument("--max-length", type=int, default=12)
    length_group.add_argument("--max-lengths", type=_parse_int_list)
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--allow-smaller", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    sizes = args.sizes if args.sizes is not None else [args.size]
    max_lengths = args.max_lengths if args.max_lengths is not None else [args.max_length]
    try:
        artifacts = build_experiment_dictionaries(
            master_path=args.master,
            output_dir=args.output,
            sizes=sizes,
            max_lengths=max_lengths,
            seed=args.seed,
            min_length=args.min_length,
            allow_smaller=args.allow_smaller,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    for artifact in artifacts:
        print(
            f"dictionary={artifact.dictionary_name} requested={artifact.requested_size} "
            f"actual={artifact.actual_size} candidates={artifact.candidate_count}"
        )


if __name__ == "__main__":
    main()
