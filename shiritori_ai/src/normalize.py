"""Reading normalization for finite-dictionary Japanese shiritori."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable


NORMALIZATION_VERSION = "legacy_v1"


@dataclass(frozen=True)
class NormalizationResult:
    """Result of normalizing a reading, including a machine-readable failure reason."""

    normalized: str | None
    failure_reason: str | None

    @property
    def succeeded(self) -> bool:
        return self.normalized is not None


SMALL_KANA_MAP = {
    "ぁ": "あ",
    "ぃ": "い",
    "ぅ": "う",
    "ぇ": "え",
    "ぉ": "お",
    "ゃ": "や",
    "ゅ": "ゆ",
    "ょ": "よ",
    "っ": "つ",
    "ゎ": "わ",
    "ゕ": "か",
    "ゖ": "け",
}


EQUIVALENT_KANA_MAP = {
    "ゐ": "い",
    "ゑ": "え",
    "ぢ": "じ",
    "づ": "ず",
    "ゔ": "ぶ",
}


VOWEL_BY_CHAR: dict[str, str] = {}


def _register_vowel(chars: str, vowel: str) -> None:
    for char in chars:
        VOWEL_BY_CHAR[char] = vowel


_register_vowel("あかがさざただなはばぱまやらわ", "あ")
_register_vowel("いきぎしじちぢにひびぴみりゐ", "い")
_register_vowel("うくぐすずつづぬふぶぷむゆるゔ", "う")
_register_vowel("えけげせぜてでねへべぺめれゑ", "え")
_register_vowel("おこごそぞとどのほぼぽもよろを", "お")


def katakana_to_hiragana_char(char: str) -> str:
    """Convert a full-width katakana character to hiragana when possible."""

    code = ord(char)
    if 0x30A1 <= code <= 0x30F6:
        return chr(code - 0x60)
    return char


def normalize_equivalent_kana_char(char: str) -> str:
    """Canonicalize kana variants that should be treated as the same reading."""

    return EQUIVALENT_KANA_MAP.get(char, char)


def is_hiragana_text(text: str) -> bool:
    """Return True when text consists only of ordinary hiragana code points."""

    return bool(text) and all("\u3041" <= char <= "\u3096" for char in text)


def normalize_reading_with_reason(reading: str) -> NormalizationResult:
    """Normalize one reading and retain a reason when normalization fails."""

    text = unicodedata.normalize("NFKC", reading.strip())
    if not text:
        return NormalizationResult(None, "empty")

    normalized: list[str] = []
    for raw_char in text:
        char = katakana_to_hiragana_char(raw_char)
        char = SMALL_KANA_MAP.get(char, char)
        char = normalize_equivalent_kana_char(char)

        if char == "ー":
            if not normalized:
                return NormalizationResult(None, "unresolvable_long_vowel")
            vowel = VOWEL_BY_CHAR.get(normalized[-1])
            if vowel is None:
                return NormalizationResult(None, "unresolvable_long_vowel")
            normalized.append(vowel)
            continue

        normalized.append(char)

    result = "".join(normalized)
    if len(result) < 2:
        return NormalizationResult(None, "too_short")
    if not is_hiragana_text(result):
        return NormalizationResult(None, "contains_non_hiragana")
    return NormalizationResult(result, None)


def normalize_reading(reading: str) -> str | None:
    """Normalize one reading while preserving the original optional-string API.

    Returns None when the reading contains unsupported characters, an
    unresolvable long vowel mark, or fewer than two kana after normalization.
    """

    return normalize_reading_with_reason(reading).normalized


def normalize_readings(readings: Iterable[str]) -> list[str]:
    """Normalize readings, removing duplicates while preserving first order."""

    seen: set[str] = set()
    normalized_readings: list[str] = []
    for reading in readings:
        normalized = normalize_reading(reading)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        normalized_readings.append(normalized)
    return normalized_readings
