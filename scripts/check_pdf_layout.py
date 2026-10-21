#!/usr/bin/env python3
"""Fail when a rendered PDF paints text outside the page or below the minimum size.

Table text is 9pt in the stylesheet. A short footnote marker may be smaller.
A dollar amount or other long token may not shrink to fit a column.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MIN_TEXT_PT = 7.5
MIN_MARKER_PT = 5.0
OVERFLOW_PT = 1.0
_PAGE_RE = re.compile(r'<page\b([^>]*)>')
_WORD_RE = re.compile(r'<word\b([^>]*)>(.*?)</word>', re.DOTALL)
_ATTR_RE = re.compile(r'([A-Za-z]+)="([0-9.]+)"')


def _attrs(blob: str) -> dict[str, float]:
    return {key: float(value) for key, value in _ATTR_RE.findall(blob)}


def errors_from_bbox(xml: str, *, min_text_pt: float = MIN_TEXT_PT) -> list[str]:
    """Read poppler `pdftotext -bbox` output. Coordinates are PDF points."""
    errors: list[str] = []
    pages = list(_PAGE_RE.finditer(xml or ""))
    if not pages:
        return ["PDF bbox output has no pages"]
    for index, page in enumerate(pages, start=1):
        box = _attrs(page.group(1))
        width = box.get("width", 0)
        height = box.get("height", 0)
        end = pages[index].start() if index < len(pages) else len(xml)
        chunk = xml[page.end() : end]
        for word in _WORD_RE.finditer(chunk):
            attrs = _attrs(word.group(1))
            text = re.sub(r"\s+", " ", word.group(2)).strip()
            if not text or "xMin" not in attrs or "xMax" not in attrs:
                continue
            x_min = attrs["xMin"]
            x_max = attrs["xMax"]
            y_min = attrs.get("yMin", 0)
            y_max = attrs.get("yMax", 0)
            if x_min < -OVERFLOW_PT or y_min < -OVERFLOW_PT or x_max > width + OVERFLOW_PT or y_max > height + OVERFLOW_PT:
                errors.append(
                    f"page {index}: {text[:40]!r} extends outside the page "
                    f"(x {x_min:.1f}-{x_max:.1f}, y {y_min:.1f}-{y_max:.1f}, page {width:.1f}x{height:.1f})"
                )
            text_height = y_max - y_min
            letters = any(char.isalpha() for char in text)
            digits = text.replace(",", "").replace(".", "").isdigit()
            too_small = False
            if letters and len(text) >= 4 and text_height < min_text_pt:
                too_small = True
            elif digits and len(text) >= 4 and text_height < min_text_pt:
                too_small = True
            elif digits and len(text) <= 3 and text_height < MIN_MARKER_PT:
                too_small = True
            if too_small:
                errors.append(f"page {index}: {text[:40]!r} is {text_height:.1f}pt, below the minimum")
            if len(errors) >= 20:
                return errors
    return errors


def layout_errors(pdf: Path, *, min_text_pt: float = MIN_TEXT_PT) -> list[str]:
    if not pdf.is_file():
        return [f"PDF not found: {pdf}"]
    try:
        result = subprocess.run(
            ["pdftotext", "-bbox", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"pdftotext -bbox failed: {exc}"]
    if result.returncode != 0 and not result.stdout:
        detail = (result.stderr or "pdftotext failed").strip()
        return [f"pdftotext -bbox failed: {detail[:300]}"]
    return errors_from_bbox(result.stdout, min_text_pt=min_text_pt)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: scripts/check_pdf_layout.py FILE.pdf", file=sys.stderr)
        return 2
    errors = layout_errors(Path(args[0]))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PDF layout OK {args[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
