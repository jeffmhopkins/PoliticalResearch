"""Party labels and endorsement records.

The words stay neutral. Nothing here assigns a color, a rank, or a vote.
"""

from __future__ import annotations

NONPARTISAN_RACE = "Nonpartisan race"
REGISTERED_PARTY_LABEL = "registered party (race is nonpartisan)"
PARTY_SOURCE_KINDS = ("ballot", "elections_office", "filing", "voter_registration")
# The race label uses the first source that actually states it.
PARTY_SOURCE_ORDER = PARTY_SOURCE_KINDS

ENDORSER_TYPES = (
    "party",
    "union",
    "business_trade",
    "advocacy",
    "newspaper",
    "elected_official",
)
ENDORSER_TYPE_LABELS = {
    "party": "party",
    "union": "union",
    "business_trade": "business or trade group",
    "advocacy": "advocacy group",
    "newspaper": "newspaper",
    "elected_official": "elected official",
}
SOURCE_ROLES = ("endorser_statement", "candidate_site")
SOURCE_ROLE_LABELS = {
    "endorser_statement": "endorser's own statement",
    "candidate_site": "candidate's site",
}
MEASURE_SIDE_ROLES = (
    "sponsor_committee",
    "supporter",
    "opponent",
    "funder_for",
    "funder_against",
)
_NONPARTISAN_PARTIES = {"nonpartisan", "non-partisan", "np"}


def is_nonpartisan_contest(contest: dict | None) -> bool:
    """True when the ballot office is officially nonpartisan.

    An empty party string is not treated as nonpartisan. Judicial retention
    and a contest flagged nonpartisan are. A race is nonpartisan when every
    listed candidate's ballot party is the nonpartisan value.
    """
    if not isinstance(contest, dict):
        return False
    if contest.get("nonpartisan") is True:
        return True
    if contest.get("type") == "judicial-retention" or contest.get("level") == "judicial":
        return True
    parties = []
    for candidate in contest.get("candidates") or []:
        if not isinstance(candidate, dict) or candidate.get("write_in"):
            continue
        parties.append(str(candidate.get("party") or "").strip().lower())
    if not parties:
        return False
    return all(value in _NONPARTISAN_PARTIES for value in parties)


def endorsement_cell(claims: list | None) -> str:
    """One comparison cell: endorser, type, date, and which page the words came from."""
    parts = []
    for claim in claims or []:
        if not isinstance(claim, dict) or claim.get("removed"):
            continue
        record = claim.get("endorsement")
        if not isinstance(record, dict):
            continue
        marker = claim.get("marker")
        if marker is None:
            sources = claim.get("sources") or []
            if sources and isinstance(sources[0], dict):
                marker = sources[0].get("marker")
        if marker is None:
            continue
        name = str(record.get("endorser") or "").strip()
        label = ENDORSER_TYPE_LABELS.get(str(record.get("endorser_type") or ""), "")
        role = SOURCE_ROLE_LABELS.get(str(record.get("source_role") or ""), "")
        when = str(record.get("date") or "").strip()
        if not (name and label and role and when):
            continue
        parts.append(f"{name} ({label}), {when}, {role}[^{marker}]")
    return "; ".join(parts)
