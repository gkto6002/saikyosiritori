"""Build an information-preserving JSON Lines master dictionary from JMdict."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable

from jmdict_tags import (
    ARCHAIC_MISC_TAGS,
    OBSOLETE_MISC_TAGS,
    RARE_MISC_TAGS,
    canonicalize_tags,
    has_adjective_tag,
    has_noun_tag,
    has_verb_tag,
    priority_level,
    read_entity_tag_map,
)
from normalize import NORMALIZATION_VERSION, normalize_reading_with_reason


GENERATOR_VERSION = "1.0.0"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass(frozen=True)
class KanjiForm:
    spelling: str
    info_tags: tuple[str, ...]
    priority_tags: tuple[str, ...]


@dataclass(frozen=True)
class ReadingForm:
    reading: str
    no_kanji: bool
    restricted_spellings: tuple[str, ...]
    info_tags: tuple[str, ...]
    priority_tags: tuple[str, ...]


@dataclass(frozen=True)
class SenseData:
    number: int
    restricted_spellings: tuple[str, ...]
    restricted_readings: tuple[str, ...]
    pos_tags: tuple[str, ...]
    misc_tags: tuple[str, ...]
    field_tags: tuple[str, ...]
    dialect_tags: tuple[str, ...]
    glosses: tuple[dict[str, str], ...]
    sense_info: tuple[str, ...]


@dataclass(frozen=True)
class MasterBuildResult:
    metadata: dict[str, object]
    statistics: dict[str, object]


def _open_xml(path: str | Path) -> BinaryIO:
    source = Path(path)
    if source.suffix == ".gz":
        return gzip.open(source, "rb")
    return source.open("rb")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_named(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (child for child in element if _local_name(child.tag) == name)


def _texts(element: ET.Element, name: str) -> list[str]:
    return [child.text.strip() for child in _children_named(element, name) if child.text and child.text.strip()]


def _first_text(element: ET.Element, name: str) -> str | None:
    values = _texts(element, name)
    return values[0] if values else None


def _parse_kanji_forms(element: ET.Element, tag_map: dict[str, str]) -> list[KanjiForm]:
    forms: list[KanjiForm] = []
    for kanji_element in _children_named(element, "k_ele"):
        spelling = _first_text(kanji_element, "keb")
        if spelling is None:
            continue
        forms.append(
            KanjiForm(
                spelling=spelling,
                info_tags=canonicalize_tags(_texts(kanji_element, "ke_inf"), tag_map),
                priority_tags=tuple(sorted(set(_texts(kanji_element, "ke_pri")))),
            )
        )
    return forms


def _parse_reading_forms(element: ET.Element, tag_map: dict[str, str]) -> list[ReadingForm]:
    forms: list[ReadingForm] = []
    for reading_element in _children_named(element, "r_ele"):
        reading = _first_text(reading_element, "reb")
        if reading is None:
            continue
        forms.append(
            ReadingForm(
                reading=reading,
                no_kanji=any(True for _ in _children_named(reading_element, "re_nokanji")),
                restricted_spellings=tuple(sorted(set(_texts(reading_element, "re_restr")))),
                info_tags=canonicalize_tags(_texts(reading_element, "re_inf"), tag_map),
                priority_tags=tuple(sorted(set(_texts(reading_element, "re_pri")))),
            )
        )
    return forms


def _parse_senses(element: ET.Element, tag_map: dict[str, str]) -> list[SenseData]:
    senses: list[SenseData] = []
    inherited_pos_tags: tuple[str, ...] = ()
    for number, sense_element in enumerate(_children_named(element, "sense"), start=1):
        explicit_pos_tags = canonicalize_tags(_texts(sense_element, "pos"), tag_map)
        if explicit_pos_tags:
            inherited_pos_tags = explicit_pos_tags

        glosses: list[dict[str, str]] = []
        for gloss in _children_named(sense_element, "gloss"):
            text = "".join(gloss.itertext()).strip()
            if not text:
                continue
            glosses.append(
                {
                    "text": text,
                    "lang": gloss.attrib.get(XML_LANG, "eng"),
                    "type": gloss.attrib.get("g_type", ""),
                    "gender": gloss.attrib.get("g_gend", ""),
                }
            )

        senses.append(
            SenseData(
                number=number,
                restricted_spellings=tuple(sorted(set(_texts(sense_element, "stagk")))),
                restricted_readings=tuple(sorted(set(_texts(sense_element, "stagr")))),
                pos_tags=inherited_pos_tags,
                misc_tags=canonicalize_tags(_texts(sense_element, "misc"), tag_map),
                field_tags=canonicalize_tags(_texts(sense_element, "field"), tag_map),
                dialect_tags=canonicalize_tags(_texts(sense_element, "dial"), tag_map),
                glosses=tuple(glosses),
                sense_info=tuple(_texts(sense_element, "s_inf")),
            )
        )
    return senses


def _allowed_kanji_forms(reading: ReadingForm, kanji_forms: list[KanjiForm]) -> list[KanjiForm]:
    if reading.no_kanji:
        return []
    if reading.restricted_spellings:
        restrictions = set(reading.restricted_spellings)
        return [form for form in kanji_forms if form.spelling in restrictions]
    return list(kanji_forms)


def _applicable_spelling_names(reading: ReadingForm, sense: SenseData, allowed_forms: list[KanjiForm]) -> list[str] | None:
    if sense.restricted_readings and reading.reading not in sense.restricted_readings:
        return None
    allowed = {form.spelling for form in allowed_forms}
    if sense.restricted_spellings:
        applicable = allowed & set(sense.restricted_spellings)
        return sorted(applicable) if applicable else None
    return sorted(allowed)


def _new_bucket() -> dict[str, object]:
    return {
        "original_readings": set(),
        "original_reading_lengths": {},
        "spellings": set(),
        "entry_ids": set(),
        "priority_tags": set(),
        "reading_info_tags": set(),
        "kanji_info_tags": set(),
        "applicable_senses": {},
        "sources": {},
    }


def _stable_object_key(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def generate_master_records(input_path: str | Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Parse JMdict and return deterministic normalized-reading records and statistics."""

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"JMdict input file does not exist: {source}")

    tag_map = read_entity_tag_map(source)
    buckets: dict[str, dict[str, object]] = {}
    entry_count = 0
    kanji_spelling_count = 0
    reading_count = 0
    reading_candidate_count = 0
    normalization_success_count = 0
    failure_reasons: Counter[str] = Counter()

    with _open_xml(source) as xml_file:
        for _event, element in ET.iterparse(xml_file, events=("end",)):
            if _local_name(element.tag) != "entry":
                continue

            entry_count += 1
            entry_id_text = _first_text(element, "ent_seq")
            if entry_id_text is None or not entry_id_text.isdigit():
                raise ValueError(f"entry {entry_count} has an invalid ent_seq: {entry_id_text!r}")
            entry_id = int(entry_id_text)
            kanji_forms = _parse_kanji_forms(element, tag_map)
            reading_forms = _parse_reading_forms(element, tag_map)
            senses = _parse_senses(element, tag_map)
            kanji_spelling_count += len(kanji_forms)
            reading_count += len(reading_forms)

            for reading in reading_forms:
                reading_candidate_count += 1
                normalization = normalize_reading_with_reason(reading.reading)
                if not normalization.succeeded:
                    failure_reasons[normalization.failure_reason or "unknown"] += 1
                    continue

                normalization_success_count += 1
                normalized = normalization.normalized
                assert normalized is not None
                bucket = buckets.setdefault(normalized, _new_bucket())
                original_readings = bucket["original_readings"]
                original_reading_lengths = bucket["original_reading_lengths"]
                entry_ids = bucket["entry_ids"]
                reading_info_tags = bucket["reading_info_tags"]
                assert isinstance(original_readings, set)
                assert isinstance(original_reading_lengths, dict)
                assert isinstance(entry_ids, set)
                assert isinstance(reading_info_tags, set)
                original_readings.add(reading.reading)
                original_reading_lengths[reading.reading] = len(reading.reading)
                entry_ids.add(entry_id)
                reading_info_tags.update(reading.info_tags)

                allowed_forms = _allowed_kanji_forms(reading, kanji_forms)
                spellings = bucket["spellings"]
                priority_tags = bucket["priority_tags"]
                kanji_info_tags = bucket["kanji_info_tags"]
                assert isinstance(spellings, set)
                assert isinstance(priority_tags, set)
                assert isinstance(kanji_info_tags, set)
                spellings.update(form.spelling for form in allowed_forms)
                priority_tags.update(reading.priority_tags)
                for form in allowed_forms:
                    priority_tags.update(form.priority_tags)
                    kanji_info_tags.update(form.info_tags)

                source_record: dict[str, object] = {
                    "entry_id": entry_id,
                    "reading": reading.reading,
                    "no_kanji": reading.no_kanji,
                    "restricted_spellings": list(reading.restricted_spellings),
                    "applicable_spellings": sorted(form.spelling for form in allowed_forms),
                    "reading_info_tags": list(reading.info_tags),
                    "reading_priority_tags": list(reading.priority_tags),
                    "spellings": [
                        {
                            "spelling": form.spelling,
                            "kanji_info_tags": list(form.info_tags),
                            "priority_tags": list(form.priority_tags),
                        }
                        for form in sorted(allowed_forms, key=lambda item: item.spelling)
                    ],
                }
                sources = bucket["sources"]
                assert isinstance(sources, dict)
                sources[_stable_object_key(source_record)] = source_record

                applicable_senses = bucket["applicable_senses"]
                assert isinstance(applicable_senses, dict)
                for sense in senses:
                    applicable_spellings = _applicable_spelling_names(reading, sense, allowed_forms)
                    if applicable_spellings is None:
                        continue
                    sense_record: dict[str, object] = {
                        "entry_id": entry_id,
                        "reading": reading.reading,
                        "sense_number": sense.number,
                        "applicable_spellings": applicable_spellings,
                        "restricted_spellings": list(sense.restricted_spellings),
                        "restricted_readings": list(sense.restricted_readings),
                        "pos_tags": list(sense.pos_tags),
                        "misc_tags": list(sense.misc_tags),
                        "field_tags": list(sense.field_tags),
                        "dialect_tags": list(sense.dialect_tags),
                        "glosses": list(sense.glosses),
                        "sense_info": list(sense.sense_info),
                    }
                    applicable_senses[_stable_object_key(sense_record)] = sense_record

            element.clear()

    records = [_finalize_record(normalized, buckets[normalized]) for normalized in sorted(buckets)]
    statistics = _build_statistics(
        records=records,
        entry_count=entry_count,
        kanji_spelling_count=kanji_spelling_count,
        reading_count=reading_count,
        reading_candidate_count=reading_candidate_count,
        normalization_success_count=normalization_success_count,
        failure_reasons=failure_reasons,
    )
    return records, statistics


def _finalize_record(normalized: str, bucket: dict[str, object]) -> dict[str, object]:
    applicable_senses_by_key = bucket["applicable_senses"]
    sources_by_key = bucket["sources"]
    assert isinstance(applicable_senses_by_key, dict)
    assert isinstance(sources_by_key, dict)
    applicable_senses = sorted(
        applicable_senses_by_key.values(),
        key=lambda sense: (
            int(sense["entry_id"]),
            str(sense["reading"]),
            int(sense["sense_number"]),
            tuple(sense["applicable_spellings"]),
        ),
    )
    sources = sorted(
        sources_by_key.values(),
        key=lambda source: (
            int(source["entry_id"]),
            str(source["reading"]),
            tuple(source["applicable_spellings"]),
        ),
    )

    pos_tags = sorted({tag for sense in applicable_senses for tag in sense["pos_tags"]})
    misc_tags = sorted({tag for sense in applicable_senses for tag in sense["misc_tags"]})
    field_tags = sorted({tag for sense in applicable_senses for tag in sense["field_tags"]})
    dialect_tags = sorted({tag for sense in applicable_senses for tag in sense["dialect_tags"]})
    priority_tags = sorted(bucket["priority_tags"])

    return {
        "normalized_reading": normalized,
        "normalized_length": len(normalized),
        "original_readings": sorted(bucket["original_readings"]),
        "original_reading_lengths": dict(sorted(bucket["original_reading_lengths"].items())),
        "spellings": sorted(bucket["spellings"]),
        "entry_ids": sorted(bucket["entry_ids"]),
        "priority_tags": priority_tags,
        "priority_level": priority_level(priority_tags),
        "pos_tags": pos_tags,
        "misc_tags": misc_tags,
        "field_tags": field_tags,
        "dialect_tags": dialect_tags,
        "reading_info_tags": sorted(bucket["reading_info_tags"]),
        "kanji_info_tags": sorted(bucket["kanji_info_tags"]),
        "start_char": normalized[0],
        "end_char": normalized[-1],
        "ends_with_n": normalized[-1] == "ん",
        "has_noun_sense": has_noun_tag(pos_tags),
        "has_verb_sense": has_verb_tag(pos_tags),
        "has_adjective_sense": has_adjective_tag(pos_tags),
        "has_archaic_sense": bool(set(misc_tags) & ARCHAIC_MISC_TAGS),
        "has_obsolete_sense": bool(set(misc_tags) & OBSOLETE_MISC_TAGS),
        "has_rare_sense": bool(set(misc_tags) & RARE_MISC_TAGS),
        "has_dialect_sense": bool(dialect_tags),
        "has_specialized_sense": bool(field_tags),
        "applicable_senses": applicable_senses,
        "sources": sources,
    }


def _build_statistics(
    records: list[dict[str, object]],
    entry_count: int,
    kanji_spelling_count: int,
    reading_count: int,
    reading_candidate_count: int,
    normalization_success_count: int,
    failure_reasons: Counter[str],
) -> dict[str, object]:
    lengths = [int(record["normalized_length"]) for record in records]
    priority_counts = Counter(str(record["priority_level"]) for record in records)
    pos_counts = Counter(tag for record in records for tag in record["pos_tags"])
    start_counts = Counter(str(record["start_char"]) for record in records)
    end_counts = Counter(str(record["end_char"]) for record in records)
    length_counts = Counter(str(length) for length in lengths)
    normalization_failure_count = sum(failure_reasons.values())

    return {
        "entry_count": entry_count,
        "kanji_spelling_count": kanji_spelling_count,
        "reading_count": reading_count,
        "reading_candidate_count": reading_candidate_count,
        "normalization_success_count": normalization_success_count,
        "normalization_failure_count": normalization_failure_count,
        "normalization_failure_reasons": dict(sorted(failure_reasons.items())),
        "pre_merge_candidate_count": normalization_success_count,
        "post_merge_word_count": len(records),
        "duplicate_merge_count": normalization_success_count - len(records),
        "priority_level_word_counts": dict(sorted(priority_counts.items())),
        "pos_tag_word_counts": dict(sorted(pos_counts.items())),
        "noun_candidate_count": sum(bool(record["has_noun_sense"]) for record in records),
        "archaic_word_count": sum(bool(record["has_archaic_sense"]) for record in records),
        "obsolete_word_count": sum(bool(record["has_obsolete_sense"]) for record in records),
        "rare_word_count": sum(bool(record["has_rare_sense"]) for record in records),
        "dialect_word_count": sum(bool(record["has_dialect_sense"]) for record in records),
        "specialized_word_count": sum(bool(record["has_specialized_sense"]) for record in records),
        "n_ending_word_count": sum(bool(record["ends_with_n"]) for record in records),
        "start_char_word_counts": dict(sorted(start_counts.items())),
        "end_char_word_counts": dict(sorted(end_counts.items())),
        "normalized_length_word_counts": dict(sorted(length_counts.items(), key=lambda item: int(item[0]))),
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


def _write_json_atomic(data: object, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False) as temporary:
            temporary_name = temporary.name
            json.dump(data, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_name, output)
    except OSError:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _write_jsonl_atomic(records: list[dict[str, object]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False) as temporary:
            temporary_name = temporary.name
            for record in records:
                temporary.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                temporary.write("\n")
        os.replace(temporary_name, output)
    except OSError:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def default_sidecar_paths(output_path: str | Path) -> tuple[Path, Path]:
    output = Path(output_path)
    stem = output.name.removesuffix(".jsonl")
    return output.with_name(f"{stem}.metadata.json"), output.with_name(f"{stem}.stats.json")


def build_master_dictionary(
    input_path: str | Path,
    output_path: str | Path,
    metadata_path: str | Path | None = None,
    statistics_path: str | Path | None = None,
) -> MasterBuildResult:
    """Generate the JSONL master dictionary and its metadata/statistics sidecars."""

    output = Path(output_path)
    default_metadata, default_statistics = default_sidecar_paths(output)
    metadata_output = Path(metadata_path) if metadata_path is not None else default_metadata
    statistics_output = Path(statistics_path) if statistics_path is not None else default_statistics
    records, statistics = generate_master_records(input_path)
    _write_jsonl_atomic(records, output)

    metadata: dict[str, object] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file_name": Path(input_path).name,
        "input_sha256": _sha256(input_path),
        "master_dictionary_sha256": _sha256(output),
        "normalization_version": NORMALIZATION_VERSION,
        "generator_version": GENERATOR_VERSION,
        "entry_count": statistics["entry_count"],
        "reading_candidate_count": statistics["reading_candidate_count"],
        "normalization_success_count": statistics["normalization_success_count"],
        "normalization_failure_count": statistics["normalization_failure_count"],
        "pre_merge_candidate_count": statistics["pre_merge_candidate_count"],
        "post_merge_word_count": statistics["post_merge_word_count"],
        "output_file_name": output.name,
        "metadata_file_name": metadata_output.name,
        "statistics_file_name": statistics_output.name,
    }
    _write_json_atomic(statistics, statistics_output)
    _write_json_atomic(metadata, metadata_output)
    return MasterBuildResult(metadata=metadata, statistics=statistics)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JMdict XML or .gz input path")
    parser.add_argument("--output", required=True, help="Master dictionary JSONL output path")
    parser.add_argument("--metadata-output", help="Metadata JSON output path")
    parser.add_argument("--statistics-output", help="Statistics JSON output path")
    return parser.parse_args(argv)


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = build_master_dictionary(
            input_path=args.input,
            output_path=args.output,
            metadata_path=args.metadata_output,
            statistics_path=args.statistics_output,
        )
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ET.ParseError as error:
        print(f"error: JMdict XML is malformed: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"error: failed to build master dictionary: {error}", file=sys.stderr)
        return 2

    print(f"records={result.statistics['post_merge_word_count']}")
    print(f"output={args.output}")
    metadata_output, statistics_output = default_sidecar_paths(args.output)
    print(f"metadata={args.metadata_output or metadata_output}")
    print(f"statistics={args.statistics_output or statistics_output}")
    return 0


def main() -> None:
    raise SystemExit(run_cli(parse_args()))


if __name__ == "__main__":
    main()
