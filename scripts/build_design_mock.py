#!/usr/bin/env python3
"""Render the Docket design sample.

This does not call scripts/build.sh and does not change the default guide.
The sample is design/mock/sample.html plus design/mock/mock.css.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "design" / "mock" / "sample.html"
CSS = ROOT / "design" / "mock" / "mock.css"
LETTER = (612.0, 792.0)
TOLERANCE = 1.5

_PAGE_RE = re.compile(r"<page\b([^>]*)>")
_WORD_RE = re.compile(r"<word\b([^>]*)>(.*?)</word>", re.DOTALL)
_ATTR_RE = re.compile(r'([A-Za-z]+)="([0-9.]+)"')
_PRIVATE = ("chapman", "6070")


def _attrs(blob: str) -> dict[str, float]:
    return {key: float(value) for key, value in _ATTR_RE.findall(blob)}


def letter_errors(xml: str) -> list[str]:
    """Every page is US Letter, portrait or landscape."""
    errors = []
    pages = list(_PAGE_RE.finditer(xml or ""))
    if not pages:
        return ["PDF bbox output has no pages"]
    for index, page in enumerate(pages, start=1):
        box = _attrs(page.group(1))
        size = tuple(sorted((box.get("width", 0.0), box.get("height", 0.0))))
        if abs(size[0] - LETTER[0]) > TOLERANCE or abs(size[1] - LETTER[1]) > TOLERANCE:
            errors.append(
                f"page {index}: size {box.get('width', 0):.1f}x{box.get('height', 0):.1f} pt is not US Letter"
            )
    return errors


def blank_page_errors(xml: str) -> list[str]:
    """A page with only the running head and footer is blank."""
    errors = []
    pages = list(_PAGE_RE.finditer(xml or ""))
    for index, page in enumerate(pages, start=1):
        box = _attrs(page.group(1))
        height = box.get("height", 0.0)
        end = pages[index].start() if index < len(pages) else len(xml)
        words = []
        for word in _WORD_RE.finditer(xml[page.end() : end]):
            attrs = _attrs(word.group(1))
            text = re.sub(r"\s+", " ", word.group(2)).strip()
            y_min = attrs.get("yMin", 0.0)
            if not text or y_min < 48 or y_min > height - 40:
                continue
            if any(char.isalpha() for char in text):
                words.append(text)
        if not words:
            errors.append(f"page {index}: no body text")
    return errors


def privacy_errors(text: str) -> list[str]:
    lowered = (text or "").casefold()
    return [f"private token {token!r} appears in the sample" for token in _PRIVATE if token in lowered]


def render(html: Path, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["weasyprint", str(html), str(pdf)],
        check=True,
        cwd=html.parent,
    )


def bbox(pdf: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and not result.stdout:
        raise RuntimeError((result.stderr or "pdftotext -bbox failed").strip())
    return result.stdout


def page_count(pdf: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf)],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    if not match:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(match.group(1))


def check(pdf: Path, html_text: str) -> list[str]:
    errors = privacy_errors(html_text)
    errors.extend(privacy_errors(subprocess.run(
        ["pdftotext", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout))
    xml = bbox(pdf)
    errors.extend(letter_errors(xml))
    errors.extend(blank_page_errors(xml))
    count = page_count(pdf)
    if not 8 <= count <= 12:
        errors.append(f"design sample is {count} pages; expected 8 to 12")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dest = Path(args[0]) if args else Path("/opt/cursor/artifacts/design-mock.pdf")
    if not HTML.is_file() or not CSS.is_file():
        print("design sample template or CSS is missing", file=sys.stderr)
        return 2
    render(HTML, dest)
    errors = check(dest, HTML.read_text(encoding="utf-8"))
    count = page_count(dest)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"wrote {dest} ({count} pages) with errors", file=sys.stderr)
        return 1
    print(f"design sample OK {dest} ({count} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
