"""Florida legislative lobbyist registration.

The legislative index is the Senate lobbyist session page. The executive-branch
registry is floridalobbyist.gov. A search form is not a completed search, and
a missing position is not a guess about support or opposition.
"""

from __future__ import annotations

from urllib.parse import quote

from portals.base import PortalResult, classify_search_page
from portals.bill_parse import bill_token, is_session_picker, table_with_headers
from portals.fetch import PortalFetchError

SENATE_BASE = "https://www.flsenate.gov"
EXECUTIVE_BASE = "https://www.floridalobbyist.gov"
_MARKERS = ("lobbyist", "principal")


def senate_lobbyist_url(session: str, base_url: str = SENATE_BASE) -> str:
    return f"{base_url.rstrip('/')}/Session/Lobbyist/{quote(str(session))}"


def _column(row: dict, *names: str) -> str:
    for name in names:
        for key, value in row.items():
            if name in key:
                return value
    return ""


def lobbyists_for_bill(rows: list[dict], bill: str) -> list[dict]:
    """Keep the registration that names this bill. Other bills in the index stay out."""
    target = bill_token(bill)
    if not target:
        return []
    return [row for row in rows if bill_token(str(row.get("bill") or "")) == target]


def parse_lobbyist_page(page: str, url: str = "") -> dict:
    record = {"source": "Florida lobbyist registration", "url": url, "lobbyists": [], "notes": []}
    if is_session_picker(page):
        record["notes"].append("The lobbyist page is a session picker, not a registration result.")
        return record
    rows = table_with_headers(page, ("lobbyist", "principal"))
    for row in rows:
        record["lobbyists"].append(
            {
                "lobbyist": _column(row, "lobbyist"),
                "principal": _column(row, "principal"),
                "bill": _column(row, "bill"),
                "position": _column(row, "position", "stance"),
            }
        )
    if not record["lobbyists"]:
        record["notes"].append(
            "No lobbyist result table. Legislative registrations are listed at the Senate lobbyist index. "
            "Executive-branch registrations are at floridalobbyist.gov. A search form is not a result."
        )
    return record


class FloridaLobbyistRegistration:
    key = "fl_lobbyists"
    jurisdiction = "FL"
    label = "Florida lobbyist registration"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or SENATE_BASE).rstrip("/")

    def fetch_session(self, fetcher, session: str) -> tuple[dict, PortalResult]:
        url = senate_lobbyist_url(session, self.base_url)
        try:
            final_url, page = fetcher.fetch_html(url)
        except PortalFetchError as exc:
            empty = parse_lobbyist_page("", url)
            empty["notes"].append(str(exc))
            return empty, PortalResult(status="portal-down", executed=False, note=str(exc), citations=(url,))
        record = parse_lobbyist_page(page, final_url)
        status, executed, note = classify_search_page(page, len(record["lobbyists"]), _MARKERS)
        if record["notes"] and not record["lobbyists"] and status == "portal-down":
            note = record["notes"][0]
            status = "search-form-only"
            executed = False
        return record, PortalResult(status=status, executed=executed, note=note, citations=(final_url,))
