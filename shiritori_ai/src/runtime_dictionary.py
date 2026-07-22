"""Immutable search-oriented dictionary built from experiment detail JSONL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from game import WordGraph, normalize_game_char
from normalize import NORMALIZATION_VERSION


FORMAT_VERSION = "runtime_dictionary_v1"


@dataclass(frozen=True)
class EdgeDictionary:
    """Word-free directed multigraph view used by AI-vs-AI search."""

    dictionary_hash: str
    normalization_version: str
    char_to_id: dict[str, int]
    id_to_char: tuple[str, ...]
    char_count: int
    edge_instance_count: int
    initial_edge_counts: tuple[int, ...]
    initial_active_end_masks: tuple[int, ...]

    def edge_index(self, start_id: int, end_id: int) -> int:
        self._validate_char_id(start_id)
        self._validate_char_id(end_id)
        return start_id * self.char_count + end_id

    def edge_count(
        self,
        start_id: int,
        end_id: int,
        counts: list[int] | tuple[int, ...] | None = None,
    ) -> int:
        values = self.initial_edge_counts if counts is None else counts
        return int(values[self.edge_index(start_id, end_id)])

    def available_end_ids(
        self,
        start_id: int,
        active_end_masks: list[int] | tuple[int, ...] | None = None,
    ) -> list[int]:
        self._validate_char_id(start_id)
        masks = self.initial_active_end_masks if active_end_masks is None else active_end_masks
        mask = int(masks[start_id])
        result: list[int] = []
        while mask:
            least_bit = mask & -mask
            result.append(least_bit.bit_length() - 1)
            mask ^= least_bit
        return result

    def _validate_char_id(self, char_id: int) -> None:
        if char_id < 0 or char_id >= self.char_count:
            raise IndexError(f"character ID out of range: {char_id}")


@dataclass(frozen=True)
class RuntimeDictionary:
    format_version: str
    dictionary_hash: str
    normalization_version: str
    char_to_id: dict[str, int]
    id_to_char: tuple[str, ...]
    char_count: int
    word_count: int
    word_readings: tuple[str, ...]
    word_to_id: dict[str, int]
    word_lengths: tuple[int, ...]
    word_start_ids: tuple[int, ...]
    word_end_ids: tuple[int, ...]
    initial_edge_counts: tuple[int, ...]
    bucket_offsets: tuple[int, ...]
    bucket_word_ids: tuple[int, ...]
    initial_active_end_masks: tuple[int, ...]

    @classmethod
    def from_readings(
        cls,
        readings: Iterable[str],
        dictionary_hash: str = "",
        normalization_version: str = NORMALIZATION_VERSION,
    ) -> "RuntimeDictionary":
        records: list[dict[str, object]] = []
        for word_id, reading in enumerate(readings):
            if not reading:
                raise ValueError(f"word_id={word_id} has an empty reading")
            records.append(
                {
                    "word_id": word_id,
                    "normalized_reading": reading,
                    "normalized_length": len(reading),
                    "start_char": reading[0],
                    "end_char": reading[-1],
                    "ends_with_n": reading.endswith("ん"),
                }
            )
        return cls.from_detail_records(
            records,
            dictionary_hash=dictionary_hash,
            normalization_version=normalization_version,
        )

    @classmethod
    def from_detail_records(
        cls,
        records: Iterable[dict[str, object]],
        dictionary_hash: str = "",
        normalization_version: str = NORMALIZATION_VERSION,
    ) -> "RuntimeDictionary":
        details = list(records)
        readings: list[str] = []
        lengths: list[int] = []
        raw_start_chars: list[str] = []
        raw_end_chars: list[str] = []
        seen: set[str] = set()
        for expected_word_id, record in enumerate(details):
            word_id = int(record["word_id"])
            if word_id != expected_word_id:
                raise ValueError(
                    f"word_id must be consecutive and match input order: expected={expected_word_id}, actual={word_id}"
                )
            reading = str(record["normalized_reading"])
            if reading in seen:
                raise ValueError(f"duplicate normalized_reading: {reading}")
            if not reading:
                raise ValueError(f"word_id={word_id} has an empty reading")
            seen.add(reading)
            length = int(record["normalized_length"])
            if length != len(reading):
                raise ValueError(
                    f"normalized_length mismatch for {reading!r}: stored={length}, actual={len(reading)}"
                )
            start_char = normalize_game_char(str(record["start_char"]))
            end_char = normalize_game_char(str(record["end_char"]))
            if start_char != normalize_game_char(reading[0]) or end_char != normalize_game_char(reading[-1]):
                raise ValueError(f"start/end character mismatch for {reading!r}")
            readings.append(reading)
            lengths.append(length)
            raw_start_chars.append(start_char)
            raw_end_chars.append(end_char)

        id_to_char = tuple(sorted(set(raw_start_chars) | set(raw_end_chars)))
        char_to_id = {char: char_id for char_id, char in enumerate(id_to_char)}
        char_count = len(id_to_char)
        start_ids = tuple(char_to_id[char] for char in raw_start_chars)
        end_ids = tuple(char_to_id[char] for char in raw_end_chars)
        edge_count_size = char_count * char_count
        edge_counts = [0] * edge_count_size
        bucket_lists: list[list[int]] = [[] for _ in range(edge_count_size)]
        for word_id, (start_id, end_id) in enumerate(zip(start_ids, end_ids)):
            edge_index = start_id * char_count + end_id
            edge_counts[edge_index] += 1
            bucket_lists[edge_index].append(word_id)

        bucket_offsets = [0]
        bucket_word_ids: list[int] = []
        for bucket in bucket_lists:
            bucket_word_ids.extend(bucket)
            bucket_offsets.append(len(bucket_word_ids))

        active_masks: list[int] = []
        for start_id in range(char_count):
            mask = 0
            for end_id in range(char_count):
                if edge_counts[start_id * char_count + end_id] > 0:
                    mask |= 1 << end_id
            active_masks.append(mask)

        runtime = cls(
            format_version=FORMAT_VERSION,
            dictionary_hash=dictionary_hash,
            normalization_version=normalization_version,
            char_to_id=char_to_id,
            id_to_char=id_to_char,
            char_count=char_count,
            word_count=len(readings),
            word_readings=tuple(readings),
            word_to_id={reading: word_id for word_id, reading in enumerate(readings)},
            word_lengths=tuple(lengths),
            word_start_ids=start_ids,
            word_end_ids=end_ids,
            initial_edge_counts=tuple(edge_counts),
            bucket_offsets=tuple(bucket_offsets),
            bucket_word_ids=tuple(bucket_word_ids),
            initial_active_end_masks=tuple(active_masks),
        )
        runtime.validate()
        return runtime

    @classmethod
    def from_details_jsonl(cls, path: str | Path) -> "RuntimeDictionary":
        source = Path(path)
        records = _read_jsonl(source)
        return cls.from_detail_records(records, dictionary_hash=_sha256(source))

    def edge_index(self, start_id: int, end_id: int) -> int:
        self._validate_char_id(start_id)
        self._validate_char_id(end_id)
        return start_id * self.char_count + end_id

    def edge_count(self, start_id: int, end_id: int, counts: list[int] | tuple[int, ...] | None = None) -> int:
        values = self.initial_edge_counts if counts is None else counts
        return int(values[self.edge_index(start_id, end_id)])

    def bucket(self, start_id: int, end_id: int) -> tuple[int, ...]:
        index = self.edge_index(start_id, end_id)
        begin = self.bucket_offsets[index]
        end = self.bucket_offsets[index + 1]
        return self.bucket_word_ids[begin:end]

    def word_ids_for_start(self, start_id: int) -> tuple[int, ...]:
        self._validate_char_id(start_id)
        if self.char_count == 0:
            return ()
        first_edge = start_id * self.char_count
        after_last_edge = first_edge + self.char_count
        begin = self.bucket_offsets[first_edge]
        end = self.bucket_offsets[after_last_edge]
        return self.bucket_word_ids[begin:end]

    def available_end_ids(
        self,
        start_id: int,
        active_end_masks: list[int] | tuple[int, ...] | None = None,
    ) -> list[int]:
        self._validate_char_id(start_id)
        masks = self.initial_active_end_masks if active_end_masks is None else active_end_masks
        mask = int(masks[start_id])
        result: list[int] = []
        while mask:
            least_bit = mask & -mask
            result.append(least_bit.bit_length() - 1)
            mask ^= least_bit
        return result

    def to_word_graph(self) -> WordGraph:
        return WordGraph.from_words(list(self.word_readings))

    def to_edge_dictionary(self, word_count: int | None = None) -> EdgeDictionary:
        """Return the full edge dictionary or a stable ranked-prefix view."""

        if word_count is None:
            word_count = self.word_count
        if word_count < 0 or word_count > self.word_count:
            raise ValueError(
                f"word_count must be between 0 and {self.word_count}: {word_count}"
            )

        if word_count == self.word_count:
            edge_counts = self.initial_edge_counts
            active_end_masks = self.initial_active_end_masks
            dictionary_hash = self.dictionary_hash
        else:
            mutable_edge_counts = [0] * (self.char_count * self.char_count)
            for start_id, end_id in zip(
                self.word_start_ids[:word_count],
                self.word_end_ids[:word_count],
            ):
                mutable_edge_counts[start_id * self.char_count + end_id] += 1

            mutable_active_masks = [0] * self.char_count
            for start_id in range(self.char_count):
                row_offset = start_id * self.char_count
                mask = 0
                for end_id in range(self.char_count):
                    if mutable_edge_counts[row_offset + end_id] > 0:
                        mask |= 1 << end_id
                mutable_active_masks[start_id] = mask

            edge_counts = tuple(mutable_edge_counts)
            active_end_masks = tuple(mutable_active_masks)
            dictionary_hash = hashlib.sha256(
                f"{self.dictionary_hash}\0ranked-prefix\0{word_count}".encode("utf-8")
            ).hexdigest()

        return EdgeDictionary(
            dictionary_hash=dictionary_hash,
            normalization_version=self.normalization_version,
            char_to_id=dict(self.char_to_id),
            id_to_char=self.id_to_char,
            char_count=self.char_count,
            edge_instance_count=word_count,
            initial_edge_counts=edge_counts,
            initial_active_end_masks=active_end_masks,
        )

    def word_view_rows(self) -> list[dict[str, object]]:
        """Return a stable, human-readable row for every dictionary word."""

        rows: list[dict[str, object]] = []
        for word_id, reading in enumerate(self.word_readings):
            start_id = self.word_start_ids[word_id]
            end_id = self.word_end_ids[word_id]
            rows.append(
                {
                    "word_id": word_id,
                    "normalized_reading": reading,
                    "normalized_length": self.word_lengths[word_id],
                    "start_id": start_id,
                    "start_char": self.id_to_char[start_id],
                    "end_id": end_id,
                    "end_char": self.id_to_char[end_id],
                    "ends_with_n": self.id_to_char[end_id] == "ん",
                    "edge_word_count": self.edge_count(start_id, end_id),
                }
            )
        return rows

    def edge_view_rows(self) -> list[dict[str, object]]:
        """Return one stable row for every non-empty directed multigraph edge."""

        rows: list[dict[str, object]] = []
        for start_id in range(self.char_count):
            for end_id in range(self.char_count):
                word_ids = self.bucket(start_id, end_id)
                if not word_ids:
                    continue
                rows.append(
                    {
                        "edge_index": self.edge_index(start_id, end_id),
                        "start_id": start_id,
                        "start_char": self.id_to_char[start_id],
                        "end_id": end_id,
                        "end_char": self.id_to_char[end_id],
                        "word_count": len(word_ids),
                        "word_ids": json.dumps(list(word_ids), separators=(",", ":")),
                        "words": json.dumps(
                            [self.word_readings[word_id] for word_id in word_ids],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
        return rows

    def export_review_csvs(
        self,
        words_path: str | Path,
        edges_path: str | Path,
    ) -> tuple[Path, Path]:
        """Write deterministic CSV views for inspecting words and graph edges."""

        words_output = Path(words_path)
        edges_output = Path(edges_path)
        _write_csv(
            self.word_view_rows(),
            [
                "word_id",
                "normalized_reading",
                "normalized_length",
                "start_id",
                "start_char",
                "end_id",
                "end_char",
                "ends_with_n",
                "edge_word_count",
            ],
            words_output,
        )
        _write_csv(
            self.edge_view_rows(),
            [
                "edge_index",
                "start_id",
                "start_char",
                "end_id",
                "end_char",
                "word_count",
                "word_ids",
                "words",
            ],
            edges_output,
        )
        return words_output, edges_output

    def validate(self) -> None:
        expected_edge_size = self.char_count * self.char_count
        if len(self.initial_edge_counts) != expected_edge_size:
            raise ValueError("initial_edge_counts has the wrong size")
        if len(self.bucket_offsets) != expected_edge_size + 1:
            raise ValueError("bucket_offsets has the wrong size")
        if len(self.bucket_word_ids) != self.word_count:
            raise ValueError("not every word belongs to exactly one bucket")
        if sorted(self.bucket_word_ids) != list(range(self.word_count)):
            raise ValueError("bucket_word_ids must contain every word_id exactly once")
        if sum(self.initial_edge_counts) != self.word_count:
            raise ValueError("sum(initial_edge_counts) must equal word_count")
        if len(self.word_readings) != self.word_count or len(self.word_lengths) != self.word_count:
            raise ValueError("word arrays have inconsistent lengths")
        if len(self.word_start_ids) != self.word_count or len(self.word_end_ids) != self.word_count:
            raise ValueError("word character ID arrays have inconsistent lengths")
        if len(self.initial_active_end_masks) != self.char_count:
            raise ValueError("initial_active_end_masks has the wrong size")

        for word_id, reading in enumerate(self.word_readings):
            if self.word_to_id.get(reading) != word_id:
                raise ValueError(f"word_to_id mismatch for {reading!r}")
            if self.word_lengths[word_id] != len(reading):
                raise ValueError(f"word length mismatch for {reading!r}")
            if self.id_to_char[self.word_start_ids[word_id]] != normalize_game_char(reading[0]):
                raise ValueError(f"word start ID mismatch for {reading!r}")
            if self.id_to_char[self.word_end_ids[word_id]] != normalize_game_char(reading[-1]):
                raise ValueError(f"word end ID mismatch for {reading!r}")

        for start_id in range(self.char_count):
            expected_mask = 0
            for end_id in range(self.char_count):
                bucket_size = len(self.bucket(start_id, end_id))
                if bucket_size != self.edge_count(start_id, end_id):
                    raise ValueError("bucket size does not match edge count")
                if bucket_size:
                    expected_mask |= 1 << end_id
            if self.initial_active_end_masks[start_id] != expected_mask:
                raise ValueError("initial active end mask is inconsistent")

    def compare_word_graph(self, graph: WordGraph) -> dict[str, bool]:
        if tuple(graph.words) != self.word_readings:
            return {"word_order": False}
        old_edge_counts: dict[tuple[str, str], int] = {}
        for start_char, end_char in zip(graph.start_chars, graph.end_chars):
            key = (start_char, end_char)
            old_edge_counts[key] = old_edge_counts.get(key, 0) + 1
        new_edge_counts = {
            (self.id_to_char[start_id], self.id_to_char[end_id]): self.edge_count(start_id, end_id)
            for start_id in range(self.char_count)
            for end_id in range(self.char_count)
            if self.edge_count(start_id, end_id)
        }
        return {
            "word_order": True,
            "word_count": len(graph.words) == self.word_count,
            "edge_counts": old_edge_counts == new_edge_counts,
            "start_counts": graph.start_distribution()
            == {
                self.id_to_char[start_id]: sum(
                    self.edge_count(start_id, end_id) for end_id in range(self.char_count)
                )
                for start_id in range(self.char_count)
                if any(self.edge_count(start_id, end_id) for end_id in range(self.char_count))
            },
            "n_ending_count": graph.n_ending_word_count()
            == sum(
                self.edge_count(start_id, self.char_to_id["ん"])
                for start_id in range(self.char_count)
            )
            if "ん" in self.char_to_id
            else graph.n_ending_word_count() == 0,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "dictionary_hash": self.dictionary_hash,
            "normalization_version": self.normalization_version,
            "char_to_id": self.char_to_id,
            "id_to_char": list(self.id_to_char),
            "char_count": self.char_count,
            "word_count": self.word_count,
            "word_readings": list(self.word_readings),
            "word_to_id": self.word_to_id,
            "word_lengths": list(self.word_lengths),
            "word_start_ids": list(self.word_start_ids),
            "word_end_ids": list(self.word_end_ids),
            "initial_edge_counts": list(self.initial_edge_counts),
            "bucket_offsets": list(self.bucket_offsets),
            "bucket_word_ids": list(self.bucket_word_ids),
            "initial_active_end_masks": list(self.initial_active_end_masks),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RuntimeDictionary":
        runtime = cls(
            format_version=str(value["format_version"]),
            dictionary_hash=str(value["dictionary_hash"]),
            normalization_version=str(value["normalization_version"]),
            char_to_id={str(key): int(item) for key, item in dict(value["char_to_id"]).items()},
            id_to_char=tuple(str(item) for item in value["id_to_char"]),
            char_count=int(value["char_count"]),
            word_count=int(value["word_count"]),
            word_readings=tuple(str(item) for item in value["word_readings"]),
            word_to_id={str(key): int(item) for key, item in dict(value["word_to_id"]).items()},
            word_lengths=tuple(int(item) for item in value["word_lengths"]),
            word_start_ids=tuple(int(item) for item in value["word_start_ids"]),
            word_end_ids=tuple(int(item) for item in value["word_end_ids"]),
            initial_edge_counts=tuple(int(item) for item in value["initial_edge_counts"]),
            bucket_offsets=tuple(int(item) for item in value["bucket_offsets"]),
            bucket_word_ids=tuple(int(item) for item in value["bucket_word_ids"]),
            initial_active_end_masks=tuple(int(item) for item in value["initial_active_end_masks"]),
        )
        runtime.validate()
        return runtime

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeDictionary":
        with Path(path).open("r", encoding="utf-8") as json_file:
            value = json.load(json_file)
        if not isinstance(value, dict):
            raise ValueError("runtime dictionary JSON must be an object")
        return cls.from_dict(value)

    def save(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False
            ) as temporary:
                temporary_name = temporary.name
                json.dump(self.to_dict(), temporary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                temporary.write("\n")
            os.replace(temporary_name, output)
        except OSError:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
            raise
        return output

    def _validate_char_id(self, char_id: int) -> None:
        if char_id < 0 or char_id >= self.char_count:
            raise IndexError(f"character ID out of range: {char_id}")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"experiment details JSONL does not exist: {path}")
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            records.append(value)
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(rows: Iterable[dict[str, object]], fieldnames: list[str], path: Path) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(buffer.getvalue())
        os.replace(temporary_name, path)
    except OSError:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Experiment details JSONL")
    parser.add_argument("--output", required=True, help="Runtime dictionary JSON")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    try:
        runtime = RuntimeDictionary.from_details_jsonl(args.input)
        output = runtime.save(args.output)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    print(f"words={runtime.word_count}")
    print(f"chars={runtime.char_count}")
    print(f"edges={sum(1 for count in runtime.initial_edge_counts if count)}")
    print(f"output={output}")


if __name__ == "__main__":
    main()
