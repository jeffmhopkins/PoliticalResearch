"""Sentence boundaries for citation, quote, and identity checks.

Abbreviations, initials, degrees, and hostname dots stay inside the sentence.
A period glued to the next capital still splits, so two clauses cannot share one marker.
"""

from __future__ import annotations

import re

# Titles and degrees whose final period is not a sentence boundary.
_ABBREV_TOKENS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "jr",
    "sr",
    "st",
    "mt",
    "gen",
    "sen",
    "rep",
    "gov",
    "lt",
    "sgt",
    "prof",
    "vs",
    "no",
    "u.s",
    "u.k",
    "j.d",
    "ph.d",
    "m.d",
    "b.a",
    "m.a",
    "b.s",
    "m.s",
    "ll.m",
    "ed.d",
    "d.d.s",
    "a.m",
    "p.m",
    "inc",
    "ltd",
    "fig",
    "al",
    "etc",
    "cf",
    "e.g",
    "i.e",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}


def _token_at_end(prefix: str) -> str:
    stripped = prefix.rstrip().rstrip("\"'`*_")
    parts = re.split(r"[\s(]", stripped)
    token = parts[-1] if parts else ""
    return token.lower().rstrip(".")


def _prefix_blocks_split(prefix: str) -> bool:
    """True when the period belongs to an initial, a title, or a degree."""
    stripped = prefix.rstrip()
    if re.search(r"(?:^|[\s(])[A-Z]$", stripped):
        return True
    token = _token_at_end(stripped)
    if token in _ABBREV_TOKENS:
        return True
    # "U.S" is stored without the trailing dot; "u.s" matches. "ph.d" too.
    # "H.R." and "S.B." are initialisms, not sentence breaks.
    compact = re.sub(r"[^a-z.]", "", token)
    if compact in _ABBREV_TOKENS:
        return True
    return re.fullmatch(r"[a-z](?:\.[a-z])+", compact) is not None


def split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Does not split after a single capital initial or a short title or degree
    (`Dr.`, `U.S.`, `J.D.`, `No.`). Does not split a hostname dot (`congress.gov`).
    Does split when punctuation is glued to the next capital (`Hollow.John`).
    """
    raw = text or ""
    if not raw.strip():
        return []
    parts: list[str] = []
    start = 0
    index = 0
    length = len(raw)
    while index < length:
        char = raw[index]
        if char not in ".!?":
            index += 1
            continue
        prefix = raw[start:index]
        rest = raw[index + 1 :]
        if char == "." and _prefix_blocks_split(prefix):
            index += 1
            continue
        # Hostname dot: letter/digit, dot, lowercase letter, and no whitespace.
        if char == "." and index > 0 and rest[:1].islower() and raw[index - 1].isalnum():
            index += 1
            continue
        # Need either whitespace or a glued capital before this is a boundary.
        if rest[:1].isspace() or (rest[:1].isupper() and char == "."):
            # Consume the following whitespace so it does not start the next sentence.
            end = index + 1
            while end < length and raw[end].isspace():
                end += 1
            chunk = raw[start:index + 1].strip()
            if chunk:
                parts.append(chunk)
            start = end
            index = end
            continue
        index += 1
    tail = raw[start:].strip()
    if tail:
        parts.append(tail)
    return parts
