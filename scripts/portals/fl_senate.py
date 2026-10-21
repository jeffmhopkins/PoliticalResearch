"""Florida Senate bill pages on flsenate.gov.

The adapter reads the page it was given. A missing sponsor, party, or vote
stays empty. It does not invent them.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from portals.base import PortalResult
from portals.bill_parse import is_session_picker, links_matching, plain, table_with_headers
from portals.fetch import PortalFetchError

DEFAULT_BASE = "https://www.flsenate.gov"
_SPONSOR = re.compile(
    r"\b(?:Senator|Representative)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)*)"
    r"(?:\s+\(([DRINPA]{1,3})-(\d+)\))?",
)
_PARTY = {
    "D": "Democratic",
    "R": "Republican",
    "I": "Independent",
    "NPA": "No Party Affiliation",
}


def bill_url(session: str, bill: str, base_url: str = DEFAULT_BASE) -> str:
    number = re.sub(r"\s+", "", bill or "")
    number = re.sub(r"^(?:SB|HB|CS/SB|CS/HB)", "", number, flags=re.IGNORECASE)
    return f"{base_url.rstrip('/')}/Session/Bill/{quote(str(session))}/{quote(number)}"


def parse_senate_bill(page: str, url: str = "") -> dict:
    """Structured fields present on the page. Absent fields are empty lists or null."""
    record = {
        "source": "flsenate.gov",
        "url": url,
        "title": "",
        "sponsors": [],
        "actions": [],
        "companions": [],
        "notes": [],
    }
    if is_session_picker(page):
        record["notes"].append("Florida Senate returned a session picker, not a bill.")
        return record
    text = plain(page)
    title = re.search(r"\b((?:SB|HB|CS/SB|CS/HB)\s*\d+\s*:\s+[^.]{3,180})", text)
    if title:
        record["title"] = title.group(1).strip()
    seen = set()
    for match in _SPONSOR.finditer(text):
        name, party, district = match.group(1), match.group(2), match.group(3)
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        record["sponsors"].append(
            {
                "name": name,
                "party": _PARTY.get(party or "", None),
                "district": district,
                "role": "primary" if not record["sponsors"] else "cosponsor",
            }
        )
    for row in table_with_headers(page, ("date", "action")):
        record["actions"].append(
            {
                "date": row.get("date") or "",
                "action": row.get("action") or "",
                "chamber": row.get("chamber") or "",
            }
        )
    for href in links_matching(page, r"/Session/Bill/"):
        if href.rstrip("/") != (url or "").rstrip("/"):
            record["companions"].append(href)
    if not record["title"] and not record["actions"] and not record["sponsors"]:
        record["notes"].append("The Florida Senate page had no bill title, sponsor line, or history table.")
    return record


class FloridaSenateBills:
    key = "fl_senate"
    jurisdiction = "FL"
    label = "Florida Senate bill page"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")

    def fetch_bill(self, fetcher, session: str, bill: str) -> tuple[dict, PortalResult]:
        url = bill_url(session, bill, self.base_url)
        try:
            final_url, page = fetcher.fetch_html(url)
        except PortalFetchError as exc:
            return (
                parse_senate_bill("", url),
                PortalResult(status="portal-down", executed=False, note=str(exc), citations=(url,)),
            )
        record = parse_senate_bill(page, final_url)
        if record["notes"] and not record["actions"] and not record["sponsors"]:
            return record, PortalResult(status="search-form-only", executed=False, note=record["notes"][0], citations=(final_url,))
        return record, PortalResult(status="hits", executed=True, note="", citations=(final_url,))
