"""Florida Sunbiz entity-name search. Cites the detail page, not the search form."""

from __future__ import annotations

import html
import re
from urllib.parse import urlencode, urljoin

from portals.base import SEARCH_FORM_NOTE, PortalResult, PortalRow, classify_portal_html
from portals.fetch import PortalFetchError

DEFAULT_BASE = "https://search.sunbiz.org"
_ROW = re.compile(r"<tr\b[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href=["']([^"']*SearchResultDetail[^"']*)["']""", re.IGNORECASE)
_CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", html.unescape(fragment or ""))).strip()


def parse_sunbiz_rows(page: str, final_url: str, limit: int) -> list[PortalRow]:
    rows: list[PortalRow] = []
    for block in _ROW.findall(page or ""):
        if "searchresultdetail" not in block.lower():
            continue
        href = _HREF.search(block)
        if not href:
            continue
        cells = [_text(cell) for cell in _CELL.findall(block)]
        title = cells[0] if cells else ""
        if not title:
            continue
        document = cells[1] if len(cells) > 1 else ""
        status = cells[2] if len(cells) > 2 else ""
        subtitle = " · ".join(part for part in (status, document) if part)
        detail = urljoin(final_url, html.unescape(href.group(1)))
        if "SearchResultDetail" not in detail:
            continue
        identifiers = (("document_number", document),) if document else ()
        rows.append(PortalRow(title=title, subtitle=subtitle, detail_url=detail, identifiers=identifiers))
        if len(rows) >= limit:
            break
    return rows


class SunbizPortal:
    key = "fl_business"
    jurisdiction = "FL"
    kind = "business"
    label = "Florida Sunbiz corporation search"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")

    def search(self, fetcher, name: str, *, limit: int = 10) -> PortalResult:
        query = re.sub(r"\s+", " ", name or "").strip()
        if not self.base_url:
            return PortalResult(status="portal-down", executed=False, note="not configured")
        if not query:
            return PortalResult(status="searched-none", executed=False, note="Sunbiz search needs a name. The search was not submitted.")
        compact = re.sub(r"[^A-Za-z0-9]", "", query).upper()
        url = (
            f"{self.base_url}/Inquiry/CorporationSearch/SearchResults?"
            + urlencode(
                {
                    "inquiryType": "EntityName",
                    "searchNameOrder": compact,
                    "searchTerm": query,
                }
            )
        )
        if "CorporationSearch/ByName" in url:
            return PortalResult(status="search-form-only", executed=False, note=SEARCH_FORM_NOTE)
        try:
            final_url, page = fetcher.fetch_html(url)
        except PortalFetchError:
            return PortalResult(
                status="portal-down",
                executed=False,
                note="Sunbiz search is unavailable right now",
            )
        if "CorporationSearch/ByName" in (final_url or ""):
            return PortalResult(status="search-form-only", executed=False, note=SEARCH_FORM_NOTE)
        kind = classify_portal_html(page, "searchresultdetail")
        if kind == "challenge":
            return PortalResult(status="portal-down", executed=False, note="Sunbiz returned a challenge page, not results")
        if kind == "form":
            return PortalResult(status="search-form-only", executed=False, note=SEARCH_FORM_NOTE)
        if kind == "unreadable":
            return PortalResult(status="portal-down", executed=False, note="Sunbiz response was not a results page")
        rows = parse_sunbiz_rows(page, final_url, limit)
        if not rows:
            return PortalResult(
                status="searched-none",
                executed=True,
                note="searched, no match under this name",
            )
        return PortalResult(
            status="hits",
            executed=True,
            rows=tuple(rows),
            citations=tuple(row.detail_url for row in rows),
        )
