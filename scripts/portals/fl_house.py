"""Florida House bill pages on myfloridahouse.gov.

www.myfloridahouse.gov often returns a session picker. That page is not the
bill. flhouse.gov is the member list, not a bill docket. Party and district
stay empty when the page does not print them.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from portals.base import PortalResult
from portals.bill_parse import bill_chamber, bill_number, is_session_picker, plain, table_with_headers
from portals.fetch import PortalFetchError

DEFAULT_BASE = "https://www.myfloridahouse.gov"
_SPONSOR = re.compile(
    r"\b(?:Rep\.|Representative)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)*)"
    r"(?:\s+\(([DRINPA]{1,3})-(\d+)\))?",
)
_PARTY = {
    "D": "Democratic",
    "R": "Republican",
    "I": "Independent",
    "NPA": "No Party Affiliation",
}


def search_url(session: str, bill: str, base_url: str = DEFAULT_BASE) -> str:
    """BillType follows the requested chamber. An SB lookup must not ask for HB."""
    query = urlencode(
        {"SessionId": session, "BillNumber": bill_number(bill), "BillType": bill_chamber(bill)}
    )
    return f"{base_url.rstrip('/')}/Sections/Bills/billsdetail.aspx?{query}"


def parse_house_bill(page: str, url: str = "") -> dict:
    record = {
        "source": "myfloridahouse.gov",
        "url": url,
        "title": "",
        "sponsors": [],
        "actions": [],
        "companions": [],
        "notes": [],
    }
    if is_session_picker(page) or "flhouse.gov" in (url or "") and "billsdetail" not in (url or "").lower():
        record["notes"].append(
            "Florida House returned a session picker or the member-list host, not the bill."
        )
        return record
    text = plain(page)
    title = re.search(r"\b(HB\s*\d+\s*:\s+[^.]{3,180})", text)
    if title:
        record["title"] = title.group(1).strip()
    seen = set()
    for match in _SPONSOR.finditer(text):
        name = match.group(1)
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        record["sponsors"].append(
            {
                "name": name,
                "party": _PARTY.get(match.group(2) or "", None),
                "district": match.group(3),
                "role": "primary" if not record["sponsors"] else "cosponsor",
            }
        )
    for row in table_with_headers(page, ("date", "action")):
        record["actions"].append({"date": row.get("date") or "", "action": row.get("action") or ""})
    if not record["title"] and not record["actions"] and not record["sponsors"]:
        record["notes"].append("The Florida House page had no bill title, sponsor line, or history table.")
    return record


class FloridaHouseBills:
    key = "fl_house"
    jurisdiction = "FL"
    label = "Florida House bill page"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")

    def fetch_bill(self, fetcher, session: str, bill: str) -> tuple[dict, PortalResult]:
        url = search_url(session, bill, self.base_url)
        try:
            final_url, page = fetcher.fetch_html(url)
        except PortalFetchError as exc:
            empty = parse_house_bill("", url)
            empty["notes"].append(str(exc))
            return empty, PortalResult(status="portal-down", executed=False, note=str(exc), citations=(url,))
        record = parse_house_bill(page, final_url)
        if record["notes"] and not record["sponsors"] and not record["actions"]:
            return record, PortalResult(
                status="search-form-only",
                executed=False,
                note=record["notes"][0],
                citations=(final_url,),
            )
        return record, PortalResult(status="hits", executed=True, note="", citations=(final_url,))
