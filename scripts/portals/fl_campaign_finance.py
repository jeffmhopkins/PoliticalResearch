"""Florida campaign-finance disclosures from the Division of Elections.

dos.elections.myflorida.com publishes contributions. The adapter copies
contributor, candidate, date, and amount. It does not copy a street address.
"""

from __future__ import annotations

import re

from portals.base import PortalResult, classify_search_page
from portals.bill_parse import table_with_headers
from portals.fetch import PortalFetchError

DEFAULT_BASE = "https://dos.elections.myflorida.com"
CONTRIBUTIONS_PATH = "/campaign-finance/contributions/"
_MARKERS = ("contributor", "amount")
# The whole street span, not the suffix word. "12 Oak Street" leaves the name.
_STREET_ADDRESS = re.compile(
    r",?\s*\b(?:\d+[A-Za-z]?)\s+(?:[A-Za-z0-9.'#-]+\s+){0,8}"
    r"(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|lane|ln|court|ct|"
    r"circle|cir|place|pl|terrace|ter|parkway|pkwy|highway|hwy|way|trail|trl)\b\.?",
    re.IGNORECASE,
)
_PO_BOX = re.compile(r",?\s*\bP\.?\s*O\.?\s*Box\s+\d+\b", re.IGNORECASE)


def strip_street_address(value: str) -> str:
    """Drop a street address from a contributor cell. The person's name stays."""
    text = _STREET_ADDRESS.sub(" ", value or "")
    text = _PO_BOX.sub(" ", text)
    text = re.sub(r"\s+,", ",", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def contributions_url(base_url: str = DEFAULT_BASE) -> str:
    return f"{base_url.rstrip('/')}{CONTRIBUTIONS_PATH}"


def parse_contributions(page: str, url: str = "") -> dict:
    record = {"source": "Florida Division of Elections", "url": url, "contributions": [], "notes": []}
    rows = table_with_headers(page, ("contributor", "amount"))
    for row in rows:
        record["contributions"].append(
            {
                "contributor": strip_street_address(row.get("contributor") or ""),
                "candidate": row.get("candidate") or row.get("recipient") or "",
                "date": row.get("date") or "",
                "amount": row.get("amount") or "",
            }
        )
    if not record["contributions"]:
        record["notes"].append(
            "No contribution table. The Division of Elections contributions page is often a search form. "
            "A form is not a filing, and no contribution was invented."
        )
    return record


class FloridaCampaignFinance:
    key = "fl_campaign_finance"
    jurisdiction = "FL"
    label = "Florida campaign finance"

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")

    def fetch_contributions(self, fetcher) -> tuple[dict, PortalResult]:
        url = contributions_url(self.base_url)
        try:
            final_url, page = fetcher.fetch_html(url)
        except PortalFetchError as exc:
            empty = parse_contributions("", url)
            empty["notes"].append(str(exc))
            return empty, PortalResult(status="portal-down", executed=False, note=str(exc), citations=(url,))
        record = parse_contributions(page, final_url)
        status, executed, note = classify_search_page(page, len(record["contributions"]), _MARKERS)
        if record["notes"] and not record["contributions"] and status == "portal-down":
            note = record["notes"][0]
            status = "search-form-only"
            executed = False
        return record, PortalResult(status=status, executed=executed, note=note, citations=(final_url,))
