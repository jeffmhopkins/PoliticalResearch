"""Shared portal result. status separates a real empty search from an outage or a form."""

from __future__ import annotations

import re
from dataclasses import dataclass

SEARCH_FORM_NOTE = (
    "That page is an interactive search form, not results. "
    "The query was not executed, so this is not evidence the record is absent."
)
CHALLENGE_NOTE = "The portal returned a challenge page, not results."
UNREADABLE_NOTE = "The response was not a recognized results page with an explicit no-results line."
_CHALLENGE = (
    "cf-browser-verification",
    "cf-challenge",
    "just a moment",
    "g-recaptcha",
    "hcaptcha",
    "recaptcha",
    "captcha",
    "/cdn-cgi/challenge",
    "attention required",
    "verify you are human",
    "are you a robot",
    "bot detection",
    "checking your browser",
)
_NO_RESULTS = (
    "no records found",
    "no record found",
    "no results found",
    "no result found",
    "no matching records",
    "no matches found",
    "no matches were found",
    "your search returned no",
    "0 records found",
    "no data found",
    "no licensees found",
    "no corporations found",
    "no entities found",
    "search returned no results",
)
_FORM = re.compile(r"<form\b", re.IGNORECASE)


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


def _flat(html: str) -> str:
    return re.sub(r"\s+", " ", html or "").lower()


def is_challenge_page(html: str) -> bool:
    lowered = _flat(html)
    return any(token in lowered for token in _CHALLENGE)


def has_search_form(html: str) -> bool:
    return bool(_FORM.search(html or ""))


def has_explicit_no_results(html: str) -> bool:
    lowered = _flat(html)
    return any(token in lowered for token in _NO_RESULTS)


def is_recognized_results_page(html: str, results_markers: tuple[str, ...]) -> bool:
    lowered = _flat(html)
    return any(marker in lowered for marker in results_markers)


def classify_search_page(html: str, row_count: int, results_markers: tuple[str, ...]) -> tuple[str, bool, str]:
    """Return status, executed, and a note.

    Real detail rows are hits even when the page also mentions a captcha or
    includes a search form. A recognized results page that states nothing was
    found is ``searched-none`` even if the search form is still on the page.
    A challenge, captcha, or bot page is not executed only when it has no
    result rows. A search form with neither rows nor an explicit no-results
    line was not executed.
    """
    if row_count:
        return "hits", True, ""
    if is_recognized_results_page(html, results_markers) and has_explicit_no_results(html):
        return "searched-none", True, "searched, no match under this name"
    if is_challenge_page(html):
        return "portal-down", False, CHALLENGE_NOTE
    if has_search_form(html):
        return "search-form-only", False, SEARCH_FORM_NOTE
    return "portal-down", False, UNREADABLE_NOTE
