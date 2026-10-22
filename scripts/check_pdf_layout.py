#!/usr/bin/env python3
"""Fail when a rendered PDF paints text outside the page, below the minimum size,
or in columns that are too narrow to read.

Table body type is 10.5pt. A short footnote marker may be smaller.
A comparison table holds at most MAX_CANDIDATES_PER_TABLE candidates.
Portrait tables hold at most MAX_PORTRAIT_COLUMNS columns. Landscape holds
at most MAX_LANDSCAPE_COLUMNS. Column starts closer than MIN_COLUMN_PT
(1.5 inches) fail the build.
"""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

MIN_TEXT_PT = 9.0
LETTER = (612.0, 792.0)
MIN_MARKER_PT = 5.0
OVERFLOW_PT = 1.0
MIN_COLUMN_PT = 108.0
# Word-box area over page area. A cover is exempt. A page that is only a
# running header and one stray line falls under this.
MIN_WORD_COVERAGE = 0.02
_LEAKED_WORD = {":::", "=", "count-many", "count-1"}
COLUMN_GAP_PT = 18.0
MAX_CANDIDATES_PER_TABLE = 3
MAX_PORTRAIT_COLUMNS = MAX_CANDIDATES_PER_TABLE + 1
MAX_LANDSCAPE_COLUMNS = 6
_PAGE_RE = re.compile(r"<page\b([^>]*)>")
_WORD_RE = re.compile(r"<word\b([^>]*)>(.*?)</word>", re.DOTALL)
_ATTR_RE = re.compile(r'([A-Za-z]+)="([0-9.]+)"')


def _attrs(blob: str) -> dict[str, float]:
    return {key: float(value) for key, value in _ATTR_RE.findall(blob)}


def _lines(words: list[tuple]) -> list[list[tuple]]:
    """Group (xMin, yMin, xMax, yMax, text) into visual lines.

    The tolerance is wide enough that a superscript marker stays on the
    line it cites. A marker row by itself is not a set of table columns.
    """
    lines: list[list[tuple]] = []
    for word in sorted(words, key=lambda item: ((item[1] + item[3]) / 2, item[0])):
        y_mid = (word[1] + word[3]) / 2
        if lines and abs(y_mid - ((lines[-1][0][1] + lines[-1][0][3]) / 2)) <= 5.5:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda item: item[0])
    return lines


def _cells(line: list[tuple]) -> list[list[tuple]]:
    cells = [[line[0]]]
    for word in line[1:]:
        gap = word[0] - cells[-1][-1][2]
        if gap >= COLUMN_GAP_PT:
            cells.append([word])
        else:
            cells[-1].append(word)
    return cells


def _content_words(words: list[tuple]) -> list[tuple]:
    """Drop leader dots so a table of contents is not read as a grid of columns."""
    return [word for word in words if any(char.isalnum() for char in word[4])]


def column_errors(words: list[tuple], *, page_index: int) -> list[str]:
    """Flag a line whose column pitch is under 1.5 inches, or a narrow one-word stack."""
    errors: list[str] = []
    lines = _lines(_content_words(words))
    for line in lines:
        if len(line) < 3:
            continue
        cells = _cells(line)
        if len(cells) < 3:
            continue
        starts = [cell[0][0] for cell in cells]
        slots = [starts[index + 1] - starts[index] for index in range(len(starts) - 1)]
        narrow = [slot for slot in slots if slot < MIN_COLUMN_PT]
        if narrow:
            errors.append(
                f"page {page_index}: table columns are {min(narrow):.0f}pt apart, "
                f"under the {MIN_COLUMN_PT:.0f}pt minimum"
            )
            break
    singles: list[tuple] = []
    for line in lines:
        letters = [word for word in line if any(char.isalpha() for char in word[4]) and len(word[4]) >= 4]
        if len(line) == 1 and letters:
            singles.append(line[0])
    clusters: list[list[tuple]] = []
    for word in singles:
        placed = False
        for cluster in clusters:
            left = min(item[0] for item in cluster)
            right = max(item[2] for item in cluster)
            if word[0] <= right + 4 and word[2] >= left - 4 and abs(word[1] - cluster[-1][1]) < 18:
                cluster.append(word)
                placed = True
                break
        if not placed:
            clusters.append([word])
    for cluster in clusters:
        if len(cluster) < 4:
            continue
        width = max(item[2] for item in cluster) - min(item[0] for item in cluster)
        if width < MIN_COLUMN_PT:
            sample = cluster[0][4]
            errors.append(
                f"page {page_index}: {sample[:40]!r} repeats in a {width:.0f}pt column, "
                f"under the {MIN_COLUMN_PT:.0f}pt minimum"
            )
    return errors


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
        size = tuple(sorted((width, height)))
        if abs(size[0] - LETTER[0]) > 1.5 or abs(size[1] - LETTER[1]) > 1.5:
            errors.append(
                f"page {index}: size {width:.1f}x{height:.1f} pt is not US Letter"
            )
        end = pages[index].start() if index < len(pages) else len(xml)
        chunk = xml[page.end() : end]
        words: list[tuple] = []
        for word in _WORD_RE.finditer(chunk):
            attrs = _attrs(word.group(1))
            text = re.sub(r"\s+", " ", word.group(2)).strip()
            if not text or "xMin" not in attrs or "xMax" not in attrs:
                continue
            x_min = attrs["xMin"]
            x_max = attrs["xMax"]
            y_min = attrs.get("yMin", 0)
            y_max = attrs.get("yMax", 0)
            words.append((x_min, y_min, x_max, y_max, text))
            if text in _LEAKED_WORD or text.startswith(":::"):
                errors.append(f"page {index}: leaked markup {text[:40]!r}")
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
        errors.extend(column_errors(words, page_index=index))
        if len(errors) >= 20:
            return errors
    return errors


class _TableLayout(HTMLParser):
    """Count columns on built guide tables. Comparison tables cap the candidates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self._divs: list[set[str]] = []
        self._in_table = False
        self._first_row = False
        self._cells = 0
        self._columns = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        if tag in {"div", "section"}:
            self._divs.append(classes)
        elif tag == "table":
            self._in_table = True
            self._first_row = True
            self._cells = 0
            self._columns = 0
        elif tag == "tr" and self._in_table:
            self._cells = 0
        elif tag in {"td", "th"} and self._in_table and self._first_row:
            self._cells += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "section"} and self._divs:
            self._divs.pop()
        elif tag == "tr" and self._in_table and self._first_row:
            self._columns = self._cells
            self._first_row = False
        elif tag == "table" and self._in_table:
            self._check_table()
            self._in_table = False

    def _check_table(self) -> None:
        classes: set[str] = set()
        for item in self._divs:
            classes |= item
        columns = self._columns
        if columns <= 0:
            return
        if "comparison" in classes:
            candidates = max(columns - 1, 0)
            if candidates > MAX_CANDIDATES_PER_TABLE:
                self.errors.append(
                    f"comparison table has {candidates} candidates; "
                    f"the maximum is {MAX_CANDIDATES_PER_TABLE}"
                )
        limit = MAX_LANDSCAPE_COLUMNS if "landscape" in classes else MAX_PORTRAIT_COLUMNS
        if columns > limit:
            where = "landscape" if "landscape" in classes else "portrait"
            self.errors.append(f"{where} table has {columns} columns; the maximum is {limit}")


def html_layout_errors(html: str) -> list[str]:
    parser = _TableLayout()
    parser.feed(html or "")
    return parser.errors


def sparse_page_errors(xml: str, *, min_coverage: float = MIN_WORD_COVERAGE) -> list[str]:
    """Flag pages whose words cover almost none of the sheet. Page 1 is the cover."""
    errors: list[str] = []
    pages = list(_PAGE_RE.finditer(xml or ""))
    for index, page in enumerate(pages, start=1):
        if index == 1:
            continue
        box = _attrs(page.group(1))
        width = box.get("width", 0)
        height = box.get("height", 0)
        page_area = width * height
        if page_area <= 0:
            continue
        end = pages[index].start() if index < len(pages) else len(xml)
        chunk = xml[page.end() : end]
        word_area = 0.0
        for word in _WORD_RE.finditer(chunk):
            attrs = _attrs(word.group(1))
            if "xMin" not in attrs or "xMax" not in attrs:
                continue
            word_area += max(0.0, attrs["xMax"] - attrs["xMin"]) * max(0.0, attrs.get("yMax", 0) - attrs.get("yMin", 0))
        coverage = word_area / page_area
        if coverage < min_coverage:
            errors.append(f"page {index}: text coverage {coverage:.3f} is below {min_coverage:.3f}")
            if len(errors) >= 20:
                break
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
    errors = errors_from_bbox(result.stdout, min_text_pt=min_text_pt)
    errors.extend(sparse_page_errors(result.stdout))
    html_path = pdf.with_suffix(".html")
    if html_path.is_file():
        errors.extend(html_layout_errors(html_path.read_text(encoding="utf-8")))
    return errors


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
