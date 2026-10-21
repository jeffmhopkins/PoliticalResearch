"""Shared HTML table parsing for legislative adapters. No network calls."""

from __future__ import annotations

import html
import re

_ROW = re.compile(r"<tr\b[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_HREF = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)

_SESSION_PICKER = (
    "select a session",
    "select session",
    "session picker",
    "choose a session",
    "please select a session",
)


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", html.unescape(fragment or ""))).strip()


def is_session_picker(page: str) -> bool:
    lowered = plain(page).lower()
    return any(token in lowered for token in _SESSION_PICKER)


def html_tables(page: str) -> list[list[list[str]]]:
    """Each table is a list of rows, and each row is a list of cell strings."""
    tables = []
    for block in re.findall(r"<table\b[^>]*>.*?</table>", page or "", flags=re.IGNORECASE | re.DOTALL):
        rows = []
        for row in _ROW.findall(block):
            cells = [plain(cell) for cell in _CELL.findall(row)]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def table_with_headers(page: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    """Rows from the first table whose header contains every required label."""
    wanted = tuple(label.lower() for label in required)
    for table in html_tables(page):
        header = [cell.lower() for cell in table[0]]
        if not all(any(label in cell for cell in header) for label in wanted):
            continue
        indexes = []
        for label in wanted:
            indexes.append(next(index for index, cell in enumerate(header) if label in cell))
        found = []
        for row in table[1:]:
            record = {}
            for label, index in zip(wanted, indexes):
                record[label] = row[index] if index < len(row) else ""
            if any(record.values()):
                found.append(record)
        return found
    return []


def links_matching(page: str, pattern: str) -> list[str]:
    return [html.unescape(match) for match in _HREF.findall(page or "") if re.search(pattern, match, re.IGNORECASE)]
