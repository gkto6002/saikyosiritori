"""JMdict reading extraction, priority ranking, and seed-based dictionary builds."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable

from normalize import normalize_reading


DEFAULT_JMDICT_URL = "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz"
DEFAULT_MIN_LENGTH = 2
DEFAULT_MAX_LENGTH = 12

PRIORITY_LABELS = {
    0: "high",
    1: "medium",
    2: "low",
    3: "none",
}


@dataclass(frozen=True)
class ReadingRecord:
    reading: str
    priority_rank: int
    priority_label: str
    priority_tags: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionStats:
    source_path: str
    min_length: int
    max_length: int
    entry_count: int
    raw_reading_count: int
    valid_normalized_count: int
    duplicate_removed_count: int
    final_unique_count: int
    n_ending_count: int
    priority_counts: dict[str, int]
    start_distribution: dict[str, int]
    end_distribution: dict[str, int]


def download_jmdict(url: str, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        output.write_bytes(response.read())
    return output


def read_csv_records(path: str | Path) -> list[ReadingRecord]:
    with Path(path).open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            return []
        if "reading" not in reader.fieldnames:
            raise ValueError(f"CSV must contain a reading column: {path}")

        records: list[ReadingRecord] = []
        seen: set[str] = set()
        for row in reader:
            if not row.get("reading"):
                continue
            reading = normalize_reading(row["reading"])
            if reading is None or reading in seen:
                continue
            seen.add(reading)

            if row.get("priority_rank", "").isdigit():
                rank = int(row["priority_rank"])
                if rank not in PRIORITY_LABELS:
                    rank = 3
            else:
                rank = 3
            tags = tuple(tag for tag in row.get("priority_tags", "").split("|") if tag)
            records.append(
                ReadingRecord(
                    reading=reading,
                    priority_rank=rank,
                    priority_label=row.get("priority_label") or PRIORITY_LABELS[rank],
                    priority_tags=tags,
                )
            )
        return records


def _open_xml(path: str | Path) -> BinaryIO:
    source = Path(path)
    if source.suffix == ".gz":
        return gzip.open(source, "rb")
    return source.open("rb")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_named(element: ET.Element, name: str) -> Iterable[ET.Element]:
    for child in element:
        if _local_name(child.tag) == name:
            yield child


def _find_child_text(element: ET.Element, name: str) -> str | None:
    for child in _children_named(element, name):
        return child.text
    return None


def _priority_rank_one(tag: str) -> int:
    if tag in {"news1", "ichi1", "spec1", "gai1"}:
        return 0
    if tag in {"news2", "ichi2", "spec2", "gai2"}:
        return 1
    if tag.startswith("nf") and len(tag) >= 4 and tag[2:].isdigit():
        value = int(tag[2:])
        if 1 <= value <= 5:
            return 0
        if 6 <= value <= 20:
            return 1
        return 2
    return 2


def priority_rank(tags: Iterable[str]) -> int:
    cleaned = [tag for tag in tags if tag]
    if not cleaned:
        return 3
    return min(_priority_rank_one(tag) for tag in cleaned)


def parse_jmdict(
    path: str | Path,
    min_length: int = DEFAULT_MIN_LENGTH,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> tuple[list[ReadingRecord], ExtractionStats]:
    best_by_reading: dict[str, ReadingRecord] = {}
    entry_count = 0
    raw_reading_count = 0
    valid_normalized_count = 0

    with _open_xml(path) as xml_file:
        for _event, element in ET.iterparse(xml_file, events=("end",)):
            if _local_name(element.tag) != "entry":
                continue

            entry_count += 1
            kanji_priority_tags = [
                priority.text or ""
                for kanji_element in _children_named(element, "k_ele")
                for priority in _children_named(kanji_element, "ke_pri")
                if priority.text
            ]

            for reading_element in _children_named(element, "r_ele"):
                raw_reading = _find_child_text(reading_element, "reb")
                if not raw_reading:
                    continue
                raw_reading_count += 1
                normalized = normalize_reading(raw_reading)
                if normalized is None:
                    continue
                if len(normalized) < min_length or len(normalized) > max_length:
                    continue

                valid_normalized_count += 1
                reading_priority_tags = [
                    priority.text or ""
                    for priority in _children_named(reading_element, "re_pri")
                    if priority.text
                ]
                tags = tuple(sorted(set(kanji_priority_tags + reading_priority_tags)))
                rank = priority_rank(tags)
                candidate = ReadingRecord(
                    reading=normalized,
                    priority_rank=rank,
                    priority_label=PRIORITY_LABELS[rank],
                    priority_tags=tags,
                )

                current = best_by_reading.get(normalized)
                if current is None or candidate.priority_rank < current.priority_rank:
                    best_by_reading[normalized] = candidate
                elif current is not None and candidate.priority_rank == current.priority_rank:
                    merged_tags = tuple(sorted(set(current.priority_tags + candidate.priority_tags)))
                    best_by_reading[normalized] = ReadingRecord(
                        reading=normalized,
                        priority_rank=current.priority_rank,
                        priority_label=current.priority_label,
                        priority_tags=merged_tags,
                    )

            element.clear()

    records = sorted(best_by_reading.values(), key=lambda item: (item.priority_rank, item.reading))
    duplicate_removed_count = valid_normalized_count - len(records)
    stats = build_extraction_stats(
        records=records,
        source_path=str(path),
        min_length=min_length,
        max_length=max_length,
        entry_count=entry_count,
        raw_reading_count=raw_reading_count,
        valid_normalized_count=valid_normalized_count,
        duplicate_removed_count=duplicate_removed_count,
    )
    return records, stats


def build_extraction_stats(
    records: list[ReadingRecord],
    source_path: str,
    min_length: int,
    max_length: int,
    entry_count: int = 0,
    raw_reading_count: int = 0,
    valid_normalized_count: int = 0,
    duplicate_removed_count: int = 0,
) -> ExtractionStats:
    priority_counts = Counter(record.priority_label for record in records)
    start_distribution = Counter(record.reading[0] for record in records)
    end_distribution = Counter(record.reading[-1] for record in records)
    return ExtractionStats(
        source_path=source_path,
        min_length=min_length,
        max_length=max_length,
        entry_count=entry_count,
        raw_reading_count=raw_reading_count,
        valid_normalized_count=valid_normalized_count,
        duplicate_removed_count=duplicate_removed_count,
        final_unique_count=len(records),
        n_ending_count=sum(1 for record in records if record.reading.endswith("ん")),
        priority_counts=dict(sorted(priority_counts.items())),
        start_distribution=dict(sorted(start_distribution.items())),
        end_distribution=dict(sorted(end_distribution.items())),
    )


def select_records(
    records: list[ReadingRecord],
    dict_size: int,
    random_seed: int,
    pool_multiplier: int = 1,
) -> list[ReadingRecord]:
    if dict_size <= 0:
        raise ValueError("dict_size must be positive")
    if dict_size > len(records):
        raise ValueError(f"dict_size={dict_size} exceeds available records={len(records)}")

    target_pool_size = min(len(records), max(dict_size, dict_size * pool_multiplier))
    rng = random.Random(random_seed)
    pool: list[ReadingRecord] = []
    for rank in sorted(PRIORITY_LABELS):
        rank_records = [record for record in records if record.priority_rank == rank]
        remaining = target_pool_size - len(pool)
        if remaining <= 0:
            break
        if len(rank_records) <= remaining:
            pool.extend(rank_records)
        else:
            pool.extend(rng.sample(rank_records, remaining))
            break

    selected = rng.sample(pool, dict_size)
    rng.shuffle(selected)
    return selected


def distribution_json(words: Iterable[str], index: int) -> str:
    counts = Counter(word[index] for word in words)
    return json.dumps(dict(sorted(counts.items())), ensure_ascii=False, sort_keys=True)


def write_records_csv(records: list[ReadingRecord], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "reading",
                "start_char",
                "end_char",
                "priority_rank",
                "priority_label",
                "priority_tags",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "reading": record.reading,
                    "start_char": record.reading[0],
                    "end_char": record.reading[-1],
                    "priority_rank": record.priority_rank,
                    "priority_label": record.priority_label,
                    "priority_tags": "|".join(record.priority_tags),
                }
            )


def write_json(data: object, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_and_write_dataset(
    records: list[ReadingRecord],
    dict_size: int,
    random_seed: int,
    output_path: str | Path,
    pool_multiplier: int = 3,
) -> list[ReadingRecord]:
    selected = select_records(
        records=records,
        dict_size=dict_size,
        random_seed=random_seed,
        pool_multiplier=pool_multiplier,
    )
    write_records_csv(selected, output_path)
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--url", default=DEFAULT_JMDICT_URL)
    download_parser.add_argument("--output", default="data/raw/JMdict_e.gz")

    build_parser = subparsers.add_parser("build")
    source_group = build_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--jmdict")
    source_group.add_argument("--input-csv")
    source_group.add_argument("--records", dest="input_csv")
    build_parser.add_argument("--output", required=True)
    build_parser.add_argument("--metadata-output")
    build_parser.add_argument("--dict-size", type=int, required=True)
    build_parser.add_argument("--random-seed", type=int, default=0)
    build_parser.add_argument("--min-length", type=int, default=DEFAULT_MIN_LENGTH)
    build_parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    build_parser.add_argument("--pool-multiplier", type=int, default=1)

    extract_parser = subparsers.add_parser("extract-all")
    extract_parser.add_argument("--jmdict", required=True)
    extract_parser.add_argument("--output", required=True)
    extract_parser.add_argument("--metadata-output")
    extract_parser.add_argument("--min-length", type=int, default=DEFAULT_MIN_LENGTH)
    extract_parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)

    master_parser = subparsers.add_parser(
        "build-master",
        help="Build the stage-one information-preserving JMdict master dictionary.",
    )
    master_parser.add_argument("--input", required=True, help="JMdict XML or .gz input path")
    master_parser.add_argument("--output", required=True, help="Master dictionary JSONL output path")
    master_parser.add_argument("--metadata-output", help="Metadata JSON output path")
    master_parser.add_argument("--statistics-output", help="Statistics JSON output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "download":
        output = download_jmdict(args.url, args.output)
        print(f"downloaded={output}")
        return

    if args.command == "build-master":
        from master_dictionary import run_cli

        raise SystemExit(run_cli(args))

    if args.command == "extract-all":
        records, stats = parse_jmdict(
            args.jmdict,
            min_length=args.min_length,
            max_length=args.max_length,
        )
        write_records_csv(records, args.output)
        if args.metadata_output:
            write_json(asdict(stats), args.metadata_output)
        print(f"records={len(records)}")
        print(f"output={args.output}")
        return

    if args.input_csv:
        records = read_csv_records(args.input_csv)
        stats = build_extraction_stats(
            records=records,
            source_path=args.input_csv,
            min_length=args.min_length,
            max_length=args.max_length,
            valid_normalized_count=len(records),
        )
    else:
        records, stats = parse_jmdict(
            args.jmdict,
            min_length=args.min_length,
            max_length=args.max_length,
        )

    selected = build_and_write_dataset(
        records=records,
        dict_size=args.dict_size,
        random_seed=args.random_seed,
        output_path=args.output,
        pool_multiplier=args.pool_multiplier,
    )
    if args.metadata_output:
        metadata = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_stats": asdict(stats),
            "dict_size": args.dict_size,
            "random_seed": args.random_seed,
            "pool_multiplier": args.pool_multiplier,
            "selected_n_ending_count": sum(1 for record in selected if record.reading.endswith("ん")),
            "selected_start_distribution": json.loads(
                distribution_json((record.reading for record in selected), 0)
            ),
            "selected_end_distribution": json.loads(
                distribution_json((record.reading for record in selected), -1)
            ),
        }
        write_json(metadata, args.metadata_output)
    print(f"available_records={len(records)}")
    print(f"selected_records={len(selected)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
