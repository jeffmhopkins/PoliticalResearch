"""Read an official sample-ballot PDF without the layout mode that splits columns.

`pdftotext -layout` pulls a bilingual ballot and its watermark into overlapping
columns. `-raw -nodiag` keeps the reading order. A stored quote is often only
the fragment that survived that overlap. The official question is the English
block that contains the fragment, from its first real opener through the
sentence end, before the Spanish text or the Yes/No line.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# A line that starts a Spanish block, a Yes/No choice, or the next contest.
_STOP_LINE = re.compile(
    r"^(?:"
    r"¿|Yes\b|No\s+-|Sí\b|N\.º\b|No\.\s+\d|Article\b|Artículo\b|"
    r"Fondo\b|Exención\b|Mayor\b|Renovación\b|Para\b|Propuesta\b|Esta\b|"
    r"Las\b|Juez\b|Tribunal\b|Vote Both\b|Official General\b|"
    r"County Charter\b|Enmiendas\b|Boleta\b|Condado\b"
    r")",
    re.IGNORECASE,
)
_OPENER = re.compile(
    r"(Shall\b|Proposing an amendment\b|This amendment\b|To restore\b)",
    re.IGNORECASE,
)


def extract_ballot_text(pdf: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-raw", "-nodiag", str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or "pdftotext failed").strip()
        raise RuntimeError(detail)
    return result.stdout or ""


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def english_blocks(raw: str) -> list[str]:
    """English runs on a bilingual ballot, split at Spanish text and Yes/No."""
    blocks: list[str] = []
    current: list[str] = []
    for line in (raw or "").splitlines():
        piece = _flat(line.replace("\f", " "))
        if not piece or _STOP_LINE.match(piece):
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        current.append(piece)
    if current:
        blocks.append(" ".join(current))
    return blocks


def _hints(fragments: list[str], title: str = "") -> list[str]:
    found: list[str] = []
    for raw in list(fragments) + [title]:
        text = _flat(raw)
        if len(text) >= 12:
            found.append(text)
        if ":" in text:
            tail = text.split(":", 1)[1].strip()
            if len(tail) >= 12:
                found.append(tail)
    return found


def official_english_question(raw: str, fragments: list[str], title: str = "") -> str:
    """The full English question that contains these stored fragments.

    Returns '' when the ballot text does not contain a complete question.
    A title alone is not a question.
    """
    hints = _hints(fragments, title)
    if not hints or not raw:
        return ""
    best = ""
    best_score = 0
    for block in english_blocks(raw):
        score = 0
        for hint in hints:
            if hint in block:
                score += len(hint)
        if score > best_score:
            best = block
            best_score = score
    if not best:
        return ""
    opener = _OPENER.search(best)
    if not opener:
        return ""
    question = best[opener.start() :].strip()
    if len(question) < 40 or question[-1] not in ".!?":
        return ""
    if not any(len(hint) >= 20 and hint in question for hint in hints):
        # The winning block was a title. A long hint has to land in the question.
        long = [hint for hint in hints if len(hint) >= 20 and hint in best]
        if not any(hint in question for hint in long):
            return ""
    return question
