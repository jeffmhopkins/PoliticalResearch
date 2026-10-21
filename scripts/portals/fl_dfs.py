"""Florida DFS licensee search. The detail URL is /Licensee/{id}, not the search form."""

from __future__ import annotations

import html
import re
from urllib.parse import urlencode, urljoin

from portals.base import SEARCH_FORM_NOTE, PortalResult, PortalRow, classify_portal_html
from portals.fetch import PortalFetchError

DEFAULT_BASE = "https://licenseesearch.fldfs.com"
_INPUT = re.compile(r"<input\b([^>]*)>", re.IGNORECASE)
_ATTR = re.compile(r"""\b([A-Za-z_:][\w:.-]*)\s*=\s*(['"])(.*?)\2""", re.IGNORECASE | re.DOTALL)
_OPEN_ROW = re.compile(r"<tr\b[^>]*data-licensee-id\s*=\s*['\"][^'\"]+['\"][^>]*>", re.IGNORECASE)


def _attrs(fragment: str) -> dict[str, str]:
    found = {}
    for match in _ATTR.finditer(fragment or ""):
        found[match.group(1).lower()] = html.unescape(match.group(3))
    return found


def form_fields(page: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in _INPUT.finditer(page or ""):
        attrs = _attrs(match.group(1))
        name = attrs.get("name")
        if not name:
            continue
        fields[name] = attrs.get("value", "")
    return fields


def split_name(name: str) -> tuple[str, str]:
    """DFS uses the first token and the last token. One token is the last name."""
    tokens = [token for token in (name or "").split() if token]
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return "", tokens[0]
    return tokens[0], tokens[-1]


def build_dfs_body(page: str, first: str, last: str) -> str:
    fields = form_fields(page)
    fields["IndividualLNameFilter"] = last
    fields["IndividualFNameFilter"] = first
    fields["LicenseeSearchInfo.PagingInfo.SortBy"] = "Name"
    fields["LicenseeSearchInfo.PagingInfo.SortDesc"] = "False"
    fields["LicenseeSearchInfo.PagingInfo.CurrentPage"] = "1"
    return urlencode(fields)


def parse_dfs_rows(page: str, final_url: str, limit: int) -> list[PortalRow]:
    rows: list[PortalRow] = []
    for match in _OPEN_ROW.finditer(page or ""):
        attrs = _attrs(match.group(0))
        licensee_id = attrs.get("data-licensee-id", "").strip()
        licensee_name = attrs.get("data-licensee-name", "").strip()
        license_num = attrs.get("data-license-num", "").strip()
        if not licensee_id or not licensee_name:
            continue
        detail = urljoin(final_url, f"/Licensee/{licensee_id}")
        if "/Licensee/" not in detail:
            continue
        subtitle = f"License {license_num}" if license_num else ""
        identifiers = (("license_number", license_num),) if license_num else ()
        rows.append(
            PortalRow(
                title=licensee_name,
                subtitle=subtitle,
                detail_url=detail,
                identifiers=identifiers,
            )
        )
        if len(rows) >= limit:
            break
    return rows


class DfsPortal:
    key = "fl_license"
    jurisdiction = "FL"
    kind = "license"
    label = "Florida DFS licensee search"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")

    def search(self, fetcher, name: str, *, limit: int = 10) -> PortalResult:
        if not self.base_url:
            return PortalResult(status="portal-down", executed=False, note="not configured")
        first, last = split_name(name)
        if len(last) < 3:
            return PortalResult(
                status="searched-none",
                executed=False,
                note="DFS needs a last name of at least 3 characters. The search was not submitted.",
            )
        root = self.base_url + "/"
        try:
            final_url, page = fetcher.submit_form(root, root, lambda html: build_dfs_body(html, first, last))
        except PortalFetchError:
            return PortalResult(
                status="portal-down",
                executed=False,
                note="DFS licensee search is unavailable now",
            )
        kind = classify_portal_html(page, "data-licensee-id")
        if kind == "challenge":
            return PortalResult(status="portal-down", executed=False, note="DFS returned a challenge page, not results")
        if kind == "form":
            return PortalResult(status="search-form-only", executed=False, note=SEARCH_FORM_NOTE)
        if kind == "unreadable":
            return PortalResult(status="portal-down", executed=False, note="DFS response was not a results page")
        rows = parse_dfs_rows(page, final_url, limit)
        if not rows:
            return PortalResult(status="searched-none", executed=True, note="searched, no match under this name")
        return PortalResult(
            status="hits",
            executed=True,
            rows=tuple(rows),
            citations=tuple(row.detail_url for row in rows),
        )
