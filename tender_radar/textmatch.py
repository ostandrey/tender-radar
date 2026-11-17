"""Keyword matching that understands Ukrainian word endings.

Every term becomes one regular expression:

* Ukrainian words lose their ending, so "розробка" also finds "розробки",
  "розробку", "розробкою". The last syllable tolerates the і/о alternation
  (простір -> простору).
* English words may carry a short suffix (website -> websites).
* Upper-case abbreviations up to six letters (CRM, API, КСЗІ) match exactly,
  case-sensitively, as whole words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_APOSTROPHES = re.compile("['’ʼ`´‘′]")
_CYRILLIC = re.compile(r"[а-яіїєґ]", re.I)
_UA_VOWELS = "аеєиіїоуюя"
_WORD_SPLIT = re.compile(r"[\s\-–—]+")
_JOIN = r"[\s\-–—]+"

# Longest endings first, so the longest one is stripped.
_UA_ENDINGS = sorted(
    {
        "ості", "ість", "ення", "ання", "іння", "ями", "ами", "ові", "ого", "ому", "ими",
        "ній", "ий", "ій", "ої", "ою", "ах", "ях", "ам", "ям", "ів", "ії", "ія", "ію",
        "ей", "ом", "ем", "а", "я", "і", "и", "у", "ю", "о", "е", "ь", "й",
    },
    key=len,
    reverse=True,
)


def normalize(text: str) -> str:
    """Unify apostrophes and non-breaking spaces."""
    return _APOSTROPHES.sub("'", text or "").replace(" ", " ")


def ua_stem(word: str) -> str:
    """Strip one inflection ending, keeping at least four letters."""
    w = word.lower()
    for ending in _UA_ENDINGS:
        if w.endswith(ending) and len(w) - len(ending) >= 4:
            return w[: -len(ending)]
    return w


def _ua_word_pattern(word: str) -> str:
    stem = ua_stem(word)
    m = re.search(rf"[іо]([^{_UA_VOWELS}']+)$", stem)  # і/о alternation in the last syllable
    stem_re = re.escape(stem[: m.start()]) + "[іо]" + re.escape(m.group(1)) if m else re.escape(stem)
    suffix = 4 if len(stem) <= 4 else 6
    return stem_re + rf"\w{{0,{suffix}}}"


def _en_word_pattern(word: str) -> str:
    w = word.lower()
    suffix = 2 if len(w) <= 4 else 4
    return re.escape(w) + rf"\w{{0,{suffix}}}"


def is_abbreviation(term: str) -> bool:
    letters = re.sub(r"\W", "", term)
    return bool(letters) and " " not in term and letters.isupper() and len(letters) <= 6


def compile_term(term: str) -> re.Pattern[str]:
    """Compile one keyword or phrase into a regex."""
    term = normalize(term).strip()
    if is_abbreviation(term):
        return re.compile(rf"(?<![\w']){re.escape(term)}(?!\w)")
    words = [w for w in _WORD_SPLIT.split(term) if w]
    parts = [_ua_word_pattern(w) if _CYRILLIC.search(w) else _en_word_pattern(w) for w in words]
    return re.compile(rf"(?<![\w']){_JOIN.join(parts)}(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class MatchResult:
    """Which groups and which terms were found in a text."""

    groups: list[str]
    terms: list[str]


class KeywordMatcher:
    """Finds keyword hits per group (category) in a text."""

    def __init__(self, groups: dict[str, tuple[str, ...]]) -> None:
        self._groups = {
            name: [(term, compile_term(term)) for term in terms] for name, terms in groups.items()
        }

    def match(self, text: str) -> MatchResult:
        text = normalize(text)
        found_groups: list[str] = []
        found_terms: list[str] = []
        for name, compiled in self._groups.items():
            hits = [term for term, pattern in compiled if pattern.search(text)]
            if hits:
                found_groups.append(name)
                found_terms.extend(hits)
        return MatchResult(found_groups, found_terms)
