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


def bill_code(bill: str) -> str:
    """Chamber prefix plus number, such as HB18 or CS/SB18. A bare number stays numeric."""
    compact = re.sub(r"\s+", "", bill or "").upper()
    match = re.search(r"((?:CS/)?(?:HB|SB)\d+[A-Z]?)", compact)
    if match:
        return match.group(1)
    return re.sub(r"\D", "", compact)


def bill_chamber(bill: str) -> str:
    """HB or SB from the bill id. Empty when the text does not name a chamber."""
    code = bill_code(bill)
    if re.search(r"HB\d", code):
        return "HB"
    if re.search(r"SB\d", code):
        return "SB"
    return ""


def bill_number(bill: str) -> str:
    match = re.search(r"(\d+[A-Z]?)$", bill_code(bill))
    return match.group(1) if match else ""


def title_chamber(title: str) -> str:
    """HB or SB printed on a bill title. Empty when the title does not name one."""
    match = re.search(r"\b(HB|SB)\s*\d", title or "", re.IGNORECASE)
    return match.group(1).upper() if match else ""


def bill_token(value: str) -> str:
    """Comparable id: HB18 and 'HB 18' are the same token. The other chamber is not."""
    compact = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    match = re.search(r"((?:HB|SB)\d+)", compact)
    return match.group(1) if match else ""


def table_with_headers(page: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    """Rows from the first table whose header contains every required label.

    Every column is kept. A caller that asks for contributor and amount still
    receives date, candidate, bill, and position when those headers are present.
    """
    wanted = tuple(label.lower() for label in required)
    for table in html_tables(page):
        header = [cell.lower() for cell in table[0]]
        if not all(any(label in cell for cell in header) for label in wanted):
            continue
        found = []
        for row in table[1:]:
            record: dict[str, str] = {}
            for index, cell in enumerate(header):
                value = row[index] if index < len(row) else ""
                key = re.sub(r"\s+", " ", cell).strip()
                if key:
                    record[key] = value
                for label in wanted:
                    if label in cell:
                        record.setdefault(label, value)
            if any(record.values()):
                found.append(record)
        return found
    return []


def links_matching(page: str, pattern: str) -> list[str]:
    return [html.unescape(match) for match in _HREF.findall(page or "") if re.search(pattern, match, re.IGNORECASE)]
