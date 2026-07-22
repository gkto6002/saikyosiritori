"""Central tag and classification rules used by the JMdict master dictionary."""

from __future__ import annotations

import gzip
import html
import re
from pathlib import Path
from typing import Iterable


PRIORITY_LEVEL_LABELS = {
    1: "low",
    2: "medium",
    3: "high",
}

HIGH_PRIORITY_TAGS = {"news1", "ichi1", "spec1", "gai1"}
MEDIUM_PRIORITY_TAGS = {"news2", "ichi2", "spec2", "gai2"}

NOUN_POS_TAGS = {
    "n",
    "n-adv",
    "n-pref",
    "n-suf",
    "n-t",
    "num",
    "pn",
}

ARCHAIC_MISC_TAGS = {"arch"}
OBSOLETE_MISC_TAGS = {"obs"}
RARE_MISC_TAGS = {"rare"}

IRREGULAR_KANJI_INFO_TAGS = {"ateji", "iK", "ik", "io", "oK", "rK"}

_ENTITY_PATTERN = re.compile(r'<!ENTITY\s+([^\s]+)\s+"([^"]*)">')


def read_entity_tag_map(path: str | Path) -> dict[str, str]:
    """Return expanded JMdict entity descriptions mapped back to short codes."""

    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    description_to_code: dict[str, str] = {}
    with opener(source, "rt", encoding="utf-8") as xml_file:
        for line in xml_file:
            if "<JMdict" in line and "<!ELEMENT JMdict" not in line:
                break
            match = _ENTITY_PATTERN.search(line)
            if match:
                code, description = match.groups()
                description_to_code.setdefault(html.unescape(description), code)
    return description_to_code


def canonicalize_tag(value: str | None, description_to_code: dict[str, str]) -> str | None:
    """Convert an expanded entity description to its stable JMdict short code."""

    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return description_to_code.get(cleaned, cleaned)


def canonicalize_tags(
    values: Iterable[str | None],
    description_to_code: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                canonical
                for value in values
                if (canonical := canonicalize_tag(value, description_to_code)) is not None
            }
        )
    )


def priority_level(tags: Iterable[str]) -> int:
    """Classify priority tags as 3=high, 2=medium, or 1=low."""

    cleaned = set(tags)
    if cleaned & HIGH_PRIORITY_TAGS or any(_nf_in_range(tag, 1, 5) for tag in cleaned):
        return 3
    if cleaned & MEDIUM_PRIORITY_TAGS or any(_nf_in_range(tag, 6, 10) for tag in cleaned):
        return 2
    return 1


def _nf_in_range(tag: str, minimum: int, maximum: int) -> bool:
    return len(tag) == 4 and tag.startswith("nf") and tag[2:].isdigit() and minimum <= int(tag[2:]) <= maximum


def has_noun_tag(tags: Iterable[str]) -> bool:
    return bool(set(tags) & NOUN_POS_TAGS)


def has_verb_tag(tags: Iterable[str]) -> bool:
    return any(tag.startswith("v") for tag in tags)


def has_adjective_tag(tags: Iterable[str]) -> bool:
    return any(tag.startswith("adj-") for tag in tags)


def has_irregular_kanji_info(tags: Iterable[str]) -> bool:
    return bool(set(tags) & IRREGULAR_KANJI_INFO_TAGS)
