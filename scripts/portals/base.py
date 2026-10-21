"""Shared portal result. status separates a real empty search from an outage or a form."""

from __future__ import annotations

from dataclasses import dataclass

SEARCH_FORM_NOTE = (
    "That page is an interactive search form, not results. "
    "The query was not executed, so this is not evidence the record is absent."
)
_CHALLENGE = (
    "cf-browser-verification",
    "cf-challenge",
    "just a moment",
    "g-recaptcha",
    "hcaptcha",
)


@dataclass(frozen=True)
class PortalRow:
    title: str
    subtitle: str = ""
    detail_url: str = ""
    identifiers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PortalResult:
    """One portal attempt.

    status is hits, searched-none, portal-down, or search-form-only.
    counts_as_searched_empty is true only when the query ran and returned no rows.
    """

    status: str
    executed: bool
    rows: tuple[PortalRow, ...] = ()
    note: str = ""
    citations: tuple[str, ...] = ()

    def counts_as_searched_empty(self) -> bool:
        return self.status == "searched-none" and self.executed


def classify_portal_html(html: str, detail_marker: str) -> str:
    """Return rows, empty, form, challenge, or unreadable."""
    lowered = (html or "").lower()
    if detail_marker.lower() in lowered:
        return "rows"
    if any(token in lowered for token in _CHALLENGE):
        return "challenge"
    if "<table" in lowered:
        return "empty"
    if "<form" in lowered:
        return "form"
    return "unreadable"
