"""Citation, symmetry, readability, staleness, link, and edge-case checks."""

from __future__ import annotations

import difflib
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from lib.party import (
    MEASURE_SIDE_ROLES,
    NONPARTISAN_RACE,
    PARTY_SOURCE_KINDS,
    REGISTERED_PARTY_LABEL,
    is_nonpartisan_contest,
)
from lib.records import LEGAL_SWEEP_KEYS, alias_names
from lib.sentences import split_sentences
from lib.util import (
    RETRIEVED_RE,
    dump_json,
    iter_items,
    load_config,
    load_json,
    load_yaml,
    looks_like_street_address,
    norm_heading,
    repo_root,
    unsafe_fetch_target,
)

MARKER_RE = re.compile(r"\[\^(\d+)\]")
# Rendered guides replace [^n] with a small link into the sources addendum.
LINK_MARKER_RE = re.compile(r"\[(?:<sup>)?(\d+)(?:</sup>)?\]\(([^)\s]*)#source-\1\)")
WORK_RE = re.compile(r"^\[(\d+)\] ", re.MULTILINE)
FOOTNOTE_DEF_RE = re.compile(r"^\[\^\d+\]:")
# Hard cap for one contest in the reader edition. The full edition is not capped.
READER_CONTEST_WORD_BUDGET = 900
_NAV_LINK_RE = re.compile(
    r"^(?:\[Back to ballot\]\(#[A-Za-z0-9_-]+\)"
    r"|\[Sources, quotes, and the search log\]\([^)]+\)"
    r"|\[Further detail is in the full edition and the sources addendum\.\]\([^)]+\)"
    r"|\[[^\]]+\]\([^)]*#(?:profile|contest|addendum|source|cite)-[^)]+\))$"
)
_PERSON_PRONOUN_RE = re.compile(
    r"\b(?:he|she|they|his|her|their|him|hers|himself|herself|themselves)\b",
    re.IGNORECASE,
)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Kept for callers that still import the pattern. Splitting goes through split_sentences.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# A gap note may list places. It may not smuggle a second clause with ; : or a finite verb.
_GAP_CLAUSE_RE = re.compile(
    r"\b(?:was|were|is|are|been|being|has|have|had|shows|showed|took|paid|received|"
    r"convicted|guilty|sentenced|alleged|accused|indicted|arrested|admitted|pleaded|pled)\b",
    re.IGNORECASE,
)
# A bare year may date a source or place ("the 2026 ballot filing"). It may not
# introduce an event ("the 2019 arrest", "the 2019 plea", "conviction of 2019").
# The words are source and place names, not a list of allegation nouns.
_GAP_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_DATED_SOURCE_WORDS = {
    "agenda",
    "agendas",
    "archive",
    "archives",
    "ballot",
    "ballots",
    "book",
    "books",
    "borough",
    "budget",
    "budgets",
    "canvass",
    "certificate",
    "certificates",
    "charter",
    "charters",
    "city",
    "clerk",
    "clerks",
    "code",
    "codes",
    "commission",
    "committee",
    "congress",
    "council",
    "county",
    "court",
    "courts",
    "database",
    "databases",
    "directory",
    "directories",
    "district",
    "districts",
    "docket",
    "dockets",
    "election",
    "elections",
    "federal",
    "filing",
    "filings",
    "gazette",
    "general",
    "handbook",
    "handbooks",
    "house",
    "index",
    "indexes",
    "indices",
    "ledger",
    "legislature",
    "map",
    "maps",
    "minutes",
    "municipal",
    "note",
    "notes",
    "office",
    "offices",
    "ordinance",
    "ordinances",
    "page",
    "pages",
    "pamphlet",
    "pamphlets",
    "parish",
    "poll",
    "portal",
    "precinct",
    "precincts",
    "primary",
    "record",
    "records",
    "register",
    "registry",
    "report",
    "reports",
    "resolution",
    "resolutions",
    "return",
    "returns",
    "roll",
    "rolls",
    "roster",
    "rosters",
    "sample",
    "senate",
    "site",
    "statute",
    "statutes",
    "supervisor",
    "town",
    "township",
    "village",
    "website",
}
_GAP_MONTH_RE = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
_GAP_BARE_YEAR_RE = re.compile(r"\b(\d{4})\b(?!-\d{2}-\d{2})")
_GAP_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)*", re.IGNORECASE)
NEAR_COPY_RATIO = 0.85
_FOREIGN_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_FOREIGN_NAME_SKIP = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_FOREIGN_NAME_MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
# Organization and place words are not a second person. "John Smith" has none of these.
_FOREIGN_NAME_ORG_WORDS = {
    "agency",
    "association",
    "authority",
    "bank",
    "board",
    "bureau",
    "campaign",
    "center",
    "centre",
    "church",
    "city",
    "club",
    "college",
    "commission",
    "committee",
    "council",
    "county",
    "court",
    "department",
    "district",
    "foundation",
    "fund",
    "group",
    "guild",
    "hall",
    "hospital",
    "institute",
    "league",
    "office",
    "park",
    "parks",
    "party",
    "path",
    "river",
    "school",
    "service",
    "services",
    "society",
    "state",
    "temple",
    "union",
    "university",
    # Legal-entity words. A bare personal name has none of these.
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "llc",
    "llp",
    "ltd",
    "pac",
    "pc",
    "plc",
    "pllc",
}
_FIGURE_RE = re.compile(
    r"\b(?:dollars?|receipts?|disbursements?|\$|votes?\s+cast|vote\s+total|cash\s+on\s+hand)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
DISALLOWED_HOSTS = {
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "facebook.com",
    "www.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "reddit.com",
    "www.reddit.com",
}
GAP_SENTENCES = {
    "none.",
    "omitted.",
    "limited public record.",
    "no issue positions (judicial ethics rules).",
}
# Semicolons, colons, and finite verbs inside the parentheses are rejected in _gap_sentence.
# Hostname dots such as congress.gov stay allowed. A glued capital after a dot does not.
GAP_NOT_FOUND_RE = re.compile(r"^not found \(searched: (.+)\)\.$", re.IGNORECASE)
EXEMPT_HEADINGS = {
    "how to use this guide",
    "how to read this guide",
    "methodology",
    "changelog",
    "corrections",
    "glossary",
    "marker index",
    "sources and retrieval dates",
    "item changelog",
    "findings and disputes",
    "works cited",
    "disputed claims",
    "search log",
}
# The published "How we researched" heading is not exempt. An ordinary sentence
# there needs a marker. Only the lines the assembler actually writes are exempt:
# the version and count sentences, the two parallel-subagent sentences, a review
# line that starts with the status clause, an effort row whose label is a title,
# and the closed known-gap sentences. A title may contain a colon. A claim may not
# stand in for that title. policy/citations.md still treats this record as
# methodology, not as a claim about a candidate.
_RUN_RECORD_SENTENCE_RE = re.compile(
    r"^(?:"
    r"Version \S+ assembled on \d{4}-\d{2}-\d{2}"
    r"|Environment rating: (?:Full|Reduced|Minimal)"
    r"|Environment rating is not recorded in env\.md"
    r"|No environment rating file was found"
    # The citation checker strips markdown emphasis, including underscores,
    # before this match. The assembler writes suspected_injection.
    r"|Sources flagged suspected_?injection: \d+"
    r"|Parallel subagents: available"
    r"|Parallel subagents: not used; roles run one at a time in fresh contexts"
    r"|Findings recorded: \d+"
    r"|Accepted: \d+"
    r"|Disputed: \d+"
    r"|Disputed and unconfirmed claims are not used in summaries"
    r"|Blockers are removed rather than left disputed"
    r"|The reader edition keeps a short summary and comparison tables for each contest"
    r"|Works cited, quotes, and the search log are in the sources addendum"
    r"|Per-candidate prose is in the full edition"
    r"|The full edition adds the marker index and the changelog"
    r"|Reviews: \d+ of \d+ candidate profiles were checked by a separate reviewer"
    r"(?:; (?:the rest|\d+) were checked in the same session, which is less independent)?"
    r"|The review column is fact-check, sourcing, neutrality, and privacy, in that order"
    r")\.?$"
)
_REVIEW_STATUSES = r"researching|in-review|fixing|signed-off|capped-disputed"
_REVIEW_MODES = r"initial|refresh"
# Status comes first so a contest title may contain a colon. The words before
# "status" are not a free field.
_REVIEW_STATE_RE = re.compile(
    rf"^status (?:{_REVIEW_STATUSES}), round \d+, mode (?:{_REVIEW_MODES}) — (?P<label>.+)$"
)
_EFFORT_ROW_RE = re.compile(
    r"^\|\s*(?P<label>[^|]*)\|\s*\d*\s*\|\s*\d*\s*\|\s*\d*\s*\|$"
)
# The label is optional so a grouped run record can put the candidate in the heading.
_PROCESS_GAP_RE = re.compile(
    r"^(?:(?P<label>.+): )?(?:factcheck|sourcing|neutrality|privacy-legal) "
    r"signed off in the same context as the research\.?$"
)
_REMOVED_GAP_RE = re.compile(
    r"^(?:(?P<label>.+): )?Removed [A-Za-z0-9_.-]+ at the round cap\.?$"
)
_KNOWN_GAP_SENTENCES = {
    "None recorded in loop state.",
    "None recorded in loop state",
    "This is a process gap, not a fresh-context review.",
    "This is a process gap, not a fresh-context review",
}
# Exact reader sentences. Raw tool notes stay in the full-edition run record.
PLAIN_ACCESS_NOTES = (
    "Florida business records could not be retrieved automatically; ownership was not verified.",
    "Florida professional-license records could not be retrieved automatically; a license was not verified.",
    "Florida campaign-finance records could not be retrieved automatically.",
    "Florida lobbying records could not be retrieved automatically.",
    "A public records site could not be retrieved automatically.",
)
_ACCESS_FAILURE_RE = re.compile(
    r"blocked|unavailable|portal-down|cloudflare|captcha|recaptcha|could not|couldn.?t|failed|challenge|timed out|\b403\b|bot page",
    re.IGNORECASE,
)
_ACCESS_RULES = (
    (
        re.compile(r"sunbiz|officer search|division of corporations|business records|corporation search", re.IGNORECASE),
        PLAIN_ACCESS_NOTES[0],
    ),
    (
        re.compile(r"\bdfs\b|licensee search|professional[- ]license", re.IGNORECASE),
        PLAIN_ACCESS_NOTES[1],
    ),
    (re.compile(r"campaign[- ]finance", re.IGNORECASE), PLAIN_ACCESS_NOTES[2]),
    (re.compile(r"lobbyist", re.IGNORECASE), PLAIN_ACCESS_NOTES[3]),
    (re.compile(r"cloudflare|portal-down|captcha|recaptcha", re.IGNORECASE), PLAIN_ACCESS_NOTES[4]),
)
_ACCESS_ALLEGATION_RE = re.compile(
    r"\b(?:convicted|fraud|indict\w*|arrest\w*|bribe\w*|scandal|alleged|allegation)\b",
    re.IGNORECASE,
)
_READER_INTERNAL_PHRASES = (
    "fresh-context",
    "signed off in the same context",
    "process gap",
)
_REVIEW_STATUS_CELL = r"Separate|Same session|Not signed"
_REVIEW_ROW_RE = re.compile(
    rf"^\|\s*(?P<label>[^|]*)\|\s*(?:{_REVIEW_STATUS_CELL})(?:\s*/\s*(?:{_REVIEW_STATUS_CELL})){{3}}\s*\|$"
)


def _run_record_label_ok(label: str) -> bool:
    """A ballot title or item id. A sentence that states a fact is not a title."""
    text = re.sub(r"\s+", " ", label or "").strip()
    if not text:
        return False
    pieces = [part.strip() for part in split_sentences(text) if part.strip()]
    if len(pieces) != 1:
        return False
    if pieces[0].endswith((".", "!")):
        return False
    if _GAP_CLAUSE_RE.search(pieces[0]):
        return False
    return True


def plain_access_note(text: str) -> str | None:
    """Map a tool or portal failure onto one fixed reader sentence.

    A line that does not describe a failed retrieval stays untouched. The
    returned sentence is one of PLAIN_ACCESS_NOTES and names no vendor.
    """
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw or not _ACCESS_FAILURE_RE.search(raw):
        return None
    for pattern, note in _ACCESS_RULES:
        if pattern.search(raw):
            return note
    return None


def _is_plain_access_note(plain: str) -> bool:
    text = re.sub(r"\s+", " ", plain or "").strip().rstrip(".")
    return any(text == note.rstrip(".") for note in PLAIN_ACCESS_NOTES)


def _is_access_log_sentence(text: str) -> bool:
    """A portal-status line in the run record. An allegation still needs a citation."""
    if _ACCESS_ALLEGATION_RE.search(text or ""):
        return False
    return plain_access_note(text) is not None


def _is_known_gap_sentence(text: str) -> bool:
    if text in _KNOWN_GAP_SENTENCES:
        return True
    if _is_access_log_sentence(text):
        return True
    for pattern in (_PROCESS_GAP_RE, _REMOVED_GAP_RE):
        match = pattern.match(text)
        if not match:
            continue
        label = match.group("label")
        if label and not _run_record_label_ok(label):
            return False
        return True
    return False


def _is_run_record_sentence(plain: str, h1: str, h2: str, kind: str) -> bool:
    del kind
    if h1 != "how we researched":
        return False
    text = re.sub(r"\s+", " ", plain or "").strip()
    if h2 == "review state":
        match = _REVIEW_STATE_RE.match(text)
        return match is not None and _run_record_label_ok(match.group("label"))
    if h2 == "known gaps":
        return _is_known_gap_sentence(text)
    if h2 == "":
        return _RUN_RECORD_SENTENCE_RE.match(text) is not None
    return False


def _is_effort_row(row: str, h1: str, h2: str) -> bool:
    if h1 != "how we researched" or h2 != "effort":
        return False
    match = _EFFORT_ROW_RE.match(row.strip())
    return match is not None and _run_record_label_ok(match.group("label"))


def _is_review_row(row: str, h1: str, h2: str) -> bool:
    if h1 != "how we researched" or h2 != "reviews":
        return False
    match = _REVIEW_ROW_RE.match(row.strip())
    return match is not None and _run_record_label_ok(match.group("label"))


def reader_log_errors(text: str) -> list[str]:
    """The reader edition keeps no duplicated bullets and no internal review log."""
    errors = []
    lowered = (text or "").lower()
    for phrase in _READER_INTERNAL_PHRASES:
        if phrase in lowered:
            errors.append(f"final/guide.md: reader edition contains internal phrase {phrase!r}")
    counts: dict[str, int] = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        key = re.sub(r"\s+", " ", stripped)
        counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        if count > 1:
            errors.append(f"final/guide.md: duplicate bullet line ({count} times): {key[:160]}")
    return errors


CANDIDATE_CORE = [
    "identity",
    "party",
    "prior offices and public service",
    "occupational history",
    "education",
    "campaign funding",
    "outside spending",
    "attendance",
    "financial disclosure",
    "term limits",
    "record vs rhetoric",
    "promises versus record",
    "positions in own words",
    "questionnaire answers",
    "debates and forums",
    "endorsements",
    "fact checks",
    "legal issues",
    "ethics and elections orders",
    "strongest case",
]
# Same filing day and the same buckets for every candidate. A value may be a gap.
FINANCE_KEYS = (
    "report_date",
    "receipts",
    "cash_on_hand",
    "self_funding",
    "small_donors",
    "large_donors",
    "in_district",
    "pac_money",
    "party_money",
    "outside_spending",
)
# FEC itemization threshold. The guide uses this cut for every candidate.
SMALL_DONOR_THRESHOLD = 200
PROMISE_STATUS_LABELS = {
    "kept": "status is kept",
    "partially": "status is partially",
    "not": "status is not",
    "no_record": "status is no record",
}
SURVEY_NAMES = ("vote411", "ballotpedia", "votesmart")
FACT_CHECK_CAVEAT = "never checked is not the same as checked out clean"
MEASURE_CORE = [
    "official title",
    "measure type and qualification",
    "plain-language summary",
    "current law and proposed change",
    "what a yes vote does",
    "what a no vote does",
    "fiscal impact",
    "vote threshold",
    "funding by side",
    "arguments for",
    "arguments against",
    "official sponsor or committee",
    "organizations supporting",
    "organizations opposing",
    "top funders",
]
LEGISLATION_CORE = [
    "bill identity",
    "sponsors and cosponsors",
    "drafting and model legislation",
    "legislative history",
    "committee referrals and amendments",
    "companion bills",
    "status timeline",
    "plain summary",
    "current law and proposed change",
    "who is affected",
    "fiscal note",
    "staff analysis",
    "section-by-section changes",
    "effective date",
    "implementing agency",
    "roll-call votes",
    "party vote counts",
    "veto and override",
    "your legislators votes",
    "similar laws",
    "legal and constitutional challenges",
    "interest groups and lobbying",
    "hearing testimony",
    "sponsor contributions",
    "arguments for",
    "arguments against",
    "related litigation",
]
PRIMARY_ADDON = [
    "primary type",
    "intra-party comparison",
    "differences from the party platform",
    "party and official endorsements",
    "runoff or ranked-choice rules",
]
LOCAL_ADDON = [
    "what the office controls",
    "nonpartisan flag",
    "local data sources",
    "limited information",
]
RACE_OVERVIEW = [
    "contest",
    "comparison",
    "competitiveness",
    "candidate profiles",
    "write-in candidates",
    "withdrawn candidates",
    "uncontested",
]
PERSON_ITEM_TYPES = {"candidate", "primary", "local-office", "judicial-retention"}
ANCHOR_FIELDS = {
    "full_legal_name",
    "ballot_name",
    "name",
    "filing_ids",
    "filing_id",
    "city",
    "county",
    "office",
    "occupation",
    "district",
    "state",
    "campaign_site",
    "alias",
    "aliases",
}
# A blockquote is exempt only when the whole sentence is one of these banners.
# Comparison is after emphasis and punctuation are stripped, so a banner phrase
# followed by a fact does not match.
BANNER_SENTENCES = (
    "FICTIONAL EXAMPLE: the places, people, measures, and documents in this guide are invented, sources on fictional.example are placeholders and not real records, and this is not a voting guide.",
    "Not an official ballot and not voting instructions: confirm contests, deadlines, and polling places with the election office linked below.",
    "FICTIONAL EXAMPLE: this race is invented.",
    "FICTIONAL EXAMPLE: this measure is invented.",
    "FICTIONAL EXAMPLE: this bill is invented.",
    "FICTIONAL EXAMPLE: Avery Quinn is not a real person, and Cedar Hollow and Westland are not real places.",
    "FICTIONAL EXAMPLE: Blake Okonkwo is not a real person, and Cedar Hollow and Westland are not real places.",
    "FICTIONAL EXAMPLE: these publishers are invented.",
    "Not an official ballot. Not voting instructions.",
    "Not an official ballot.",
    "Not voting instructions.",
)
DISTINGUISHING_ANCHOR_FIELDS = {"full_legal_name", "ballot_name", "name", "filing_ids", "filing_id"}
WITHDRAWN_RE = re.compile(r"^Withdrawn on \d{4}-\d{2}-\d{2}\b")
JUDICIAL_CORE = [
    "retention question",
    "party",
    "court and term",
    "appointing authority",
    "performance evaluation",
    "notable rulings",
    "discipline record",
    "issue positions",
    "campaign funding",
    "outside spending",
    "attendance",
    "financial disclosure",
    "term limits",
    "fact checks",
    "ethics and elections orders",
]
SUMMARY_TYPES = {"race", "measure", "legislation", "judicial-retention"}


def _clean_anchor(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def sentence_count(text: str) -> int:
    return len(split_sentences(text or ""))


def host_of(url: str) -> str:
    match = re.match(r"https?://([^/?#]+)", url or "", re.IGNORECASE)
    return match.group(1).lower() if match else ""


def source_marker(claim: dict, source: dict) -> int | None:
    if source.get("marker") is not None:
        return int(source["marker"])
    if claim.get("marker") is not None:
        return int(claim["marker"])
    return None


def iter_claim_sources(doc: dict):
    for claim in doc.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for source in claim.get("sources") or []:
            if isinstance(source, dict):
                yield claim, source


def identity_anchor_matches(record: dict, attr: str) -> bool:
    key = str(attr or "").strip()
    if key == "name":
        return bool(str(record.get("ballot_name") or "").strip() or str(record.get("full_legal_name") or "").strip())
    if key in {"alias", "aliases"}:
        raw = record.get("aliases")
        if not isinstance(raw, list):
            return False
        return any(
            str((item.get("name") if isinstance(item, dict) else item) or "").strip()
            for item in raw
        )
    if key in {"filing_id", "filing_ids"}:
        ids = record.get("filing_ids")
        if ids is None:
            ids = record.get("filing_id")
        if isinstance(ids, str):
            return bool(ids.strip())
        return isinstance(ids, list) and any(str(item).strip() for item in ids)
    if key not in ANCHOR_FIELDS:
        return False
    return bool(str(record.get(key) or "").strip())


def anchors_match_one_record(attrs: list, records: list) -> bool:
    for record in records:
        if isinstance(record, dict) and all(identity_anchor_matches(record, attr) for attr in attrs):
            return True
    return False


def anchor_entries(record: dict) -> list[tuple[str, bool]]:
    """Anchor values from one identity record, flagged when the value can distinguish a person."""
    entries: list[tuple[str, bool]] = []
    for key in (
        "full_legal_name",
        "ballot_name",
        "name",
        "office",
        "district",
        "city",
        "county",
        "state",
        "occupation",
        "campaign_site",
    ):
        raw = str(record.get(key) or "").strip()
        if len(raw) >= 3:
            entries.append((raw, key in DISTINGUISHING_ANCHOR_FIELDS))
    filing_ids = record.get("filing_ids")
    if filing_ids is None:
        filing_ids = record.get("filing_id")
    if isinstance(filing_ids, str):
        filing_ids = [filing_ids]
    if isinstance(filing_ids, list):
        for item in filing_ids:
            text = str(item or "").strip()
            if len(text) >= 3:
                entries.append((text, True))
    for item in record.get("aliases") or []:
        if isinstance(item, dict):
            text = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
        else:
            text = re.sub(r"\s+", " ", str(item or "")).strip()
        if len(text) >= 3:
            # An alias is not a distinguishing anchor. It cannot, by itself, supply both anchors.
            entries.append((text, False))
    return entries


def _value_on_word_boundary(value: str, blob: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", blob, flags=re.IGNORECASE) is not None


def independent_anchor_values(record: dict, blob: str) -> list[tuple[str, bool]]:
    """Values from one record that appear as whole words, dropping a value nested in a longer match.

    A longer alias does not hide a distinguishing name or filing id contained in it.
    """
    found = [entry for entry in anchor_entries(record) if _value_on_word_boundary(entry[0], blob)]
    independent: list[tuple[str, bool]] = []
    for value, distinguishing in sorted(found, key=lambda item: len(item[0]), reverse=True):
        skip = False
        for chosen_value, chosen_distinguishing in independent:
            if value.lower() == chosen_value.lower():
                skip = True
                break
            if value.lower() in chosen_value.lower():
                if distinguishing and not chosen_distinguishing:
                    continue
                skip = True
                break
        if not skip:
            independent.append((value, distinguishing))
    return independent


def anchors_identify_person(record: dict, blob: str) -> bool:
    """Two anchors from one record, including a name or filing id that is not only an alias."""
    matched = independent_anchor_values(record, blob)
    alias_keys = {_clean_anchor(name) for name in alias_names(record)}
    non_alias = [entry for entry in matched if _clean_anchor(entry[0]) not in alias_keys]
    return len(matched) >= 2 and len(non_alias) >= 1 and any(distinguishing for _value, distinguishing in non_alias)


def _bind_trailing_markers(text: str) -> str:
    """Attach a marker that sits just after the period to the sentence it closes."""

    def _move(match: re.Match) -> str:
        return f" {match.group(2)}{match.group(1)}"

    return re.sub(r"([.!?])(\s*\[\^\d+\])", _move, text)


def _marker_lines(draft: str) -> list[str]:
    """Lines, with each markdown table cell on its own so a neighbor is not this sentence."""
    lines: list[str] = []
    cleaned = HTML_COMMENT_RE.sub("", draft or "")
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            for cell in stripped.strip("|").split("|"):
                cell = cell.strip()
                if cell and not re.fullmatch(r":?-{3,}:?", cell):
                    lines.append(cell)
            continue
        lines.append(line)
    return lines


def _marker_sentences(draft: str, markers: list[int]) -> list[str]:
    return [unit.text for unit in _cited_units(draft, markers)]


class _CitedUnit:
    """One marker sentence, with the context that may already name the person."""

    def __init__(self, text: str, kind: str, context: str, previous: str) -> None:
        self.text = text
        self.kind = kind
        self.context = context
        self.previous = previous


def _cited_units(draft: str, markers: list[int]) -> list[_CitedUnit]:
    """Prose sentences and table cells that carry one of these markers.

    A table cell is separate from the header. The header and the row label are
    context, not part of the cell sentence. Prose keeps the previous cited
    sentence in the same section so a pronoun can continue that name.
    """
    tokens = [f"[^{marker}]" for marker in markers]
    if not tokens:
        return []
    units: list[_CitedUnit] = []
    previous = ""
    lines = HTML_COMMENT_RE.sub("", draft or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#"):
            previous = ""
            index += 1
            continue
        if line.strip().startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rows: list[list[str]] = []
            for raw in table_lines:
                cells = [cell.strip() for cell in raw.strip("|").split("|")]
                compact = "".join(cells).replace(":", "").replace("-", "").replace(" ", "")
                if not compact:
                    continue
                rows.append(cells)
            if not rows:
                continue
            headers = rows[0]
            for cell in headers:
                for part in split_sentences(_bind_trailing_markers(cell)):
                    text = part.strip()
                    if text and any(token in text for token in tokens):
                        units.append(_CitedUnit(text, "cell", "", previous))
            for row in rows[1:]:
                row_label = row[0] if row else ""
                for cell_index, cell in enumerate(row):
                    header = headers[cell_index] if cell_index < len(headers) else ""
                    context = f"{header} {row_label}".strip()
                    for part in split_sentences(_bind_trailing_markers(cell)):
                        text = part.strip()
                        if text and any(token in text for token in tokens):
                            units.append(_CitedUnit(text, "cell", context, ""))
            continue
        for part in split_sentences(_bind_trailing_markers(line)):
            text = part.strip()
            if not text:
                continue
            if any(token in text for token in tokens):
                units.append(_CitedUnit(text, "prose", "", previous))
            if MARKER_RE.search(text) or LINK_MARKER_RE.search(text):
                previous = text
        index += 1
    return units


def _sentence_identifies(sentence: str, record: dict) -> bool:
    """The sentence itself names this record, not merely the section around it."""
    if anchors_identify_person(record, sentence):
        return True
    plain = MARKER_RE.sub("", sentence)
    for value, distinguishing in anchor_entries(record):
        if distinguishing and _value_on_word_boundary(value, plain):
            return True
    return False


def _foreign_name(sentence: str, record: dict) -> bool:
    """A person's name in the sentence that is not this identity record.

    A leading "The" or "On", a month, and an organization word are not a person.
    "John Smith" still is. The check runs even when the sentence also names this record.
    """
    anchors = {value.lower() for value, _distinguishing in anchor_entries(record)}
    plain = MARKER_RE.sub("", sentence)
    for match in _FOREIGN_NAME_RE.finditer(plain):
        words = match.group(0).split()
        if words and words[0].lower() in _FOREIGN_NAME_SKIP:
            words = words[1:]
        if len(words) < 2:
            continue
        lowered_words = [word.lower() for word in words]
        phrase = " ".join(lowered_words)
        # Only the full listed organization phrase is cleared. A shorter
        # person-name span, including one stored as an organizations entry, is not.
        if phrase in _registered_organizations(record):
            continue
        # A month or an organization word is not itself a person. The words
        # beside it still are: "the John Smith Committee" names John Smith
        # unless that full organization is listed on this identity record.
        person_words = [
            word
            for word in lowered_words
            if word not in _FOREIGN_NAME_MONTHS and word not in _FOREIGN_NAME_ORG_WORDS
        ]
        if len(person_words) < 2:
            continue
        lowered = " ".join(person_words)
        if any(lowered in anchor or anchor in lowered for anchor in anchors if len(anchor) >= 3):
            continue
        if any(phrase in anchor or anchor in phrase for anchor in anchors if len(anchor) >= 3):
            continue
        return True
    return False


def _name_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", (text or "").lower())


def organization_entry_is_personal_name(name: str) -> bool:
    """True when the entry has no organization word, so it is only a person's name."""
    tokens = _name_tokens(name)
    return not any(token in _FOREIGN_NAME_ORG_WORDS for token in tokens)


def organization_list_errors(identity: dict | None) -> list[str]:
    """Validation errors for organizations entries that are bare personal names."""
    if not isinstance(identity, dict):
        return []
    raw = identity.get("organizations")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return ["organizations: must be a list of organization names"]
    errors = []
    for index, item in enumerate(raw):
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if organization_entry_is_personal_name(text):
            shown = text or "(empty)"
            errors.append(
                f"organizations/{index}: {shown!r} is a personal name; an organization entry needs an "
                "organization word such as Committee, PAC, Inc, LLC, Party, Association, or Fund"
            )
    return errors


def _registered_organizations(record: dict) -> set[str]:
    """Full organization phrases on this record. A bare personal name is not included."""
    raw = record.get("organizations")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    names: set[str] = set()
    for item in raw:
        text = re.sub(r"\s+", " ", str(item or "")).strip().lower()
        if not text or organization_entry_is_personal_name(text):
            continue
        names.add(text)
        if text.startswith("the "):
            rest = text[4:].strip()
            if rest and not organization_entry_is_personal_name(rest):
                names.add(rest)
    return names


def identities_for_item(workspace, item, doc: dict) -> list[dict]:
    own = load_yaml(item / "identity.yaml")
    own_records = [own] if isinstance(own, dict) else []
    if doc.get("item_type") in PERSON_ITEM_TYPES:
        return own_records
    records = []
    for candidate in iter_items(workspace):
        identity = load_yaml(candidate / "identity.yaml")
        if isinstance(identity, dict):
            records.append(identity)
    return records


def semantic_claim_errors(doc: dict, label: str, identities: list | None = None, draft: str = "") -> list[str]:
    errors: list[str] = []
    seen_markers: dict[int, str] = {}
    for claim in doc.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        cid = str(claim.get("id", "?"))
        sources = claim.get("sources") or []
        if not sources:
            errors.append(f"{label}: {cid} has no sources")
            continue
        conf = claim.get("confidence")
        drives = bool(claim.get("drives_summary"))
        if conf in {"unconfirmed", "disputed", "identity-unconfirmed"} and drives:
            errors.append(f"{label}: {cid} is {conf} and cannot drive a summary")
        if claim.get("removed") and drives:
            errors.append(f"{label}: {cid} is removed and cannot drive a summary")
        if claim.get("removed") and not str(claim.get("removal_reason") or "").strip():
            errors.append(f"{label}: {cid} is removed without removal_reason")
        if doc.get("item_type") in PERSON_ITEM_TYPES and not claim.get("about_person"):
            errors.append(
                f"{label}: {cid} is a person-claim and must set about_person so it is checked against identity.yaml"
            )
        if claim.get("suspected_injection") is True:
            errors.append(
                f"{label}: {cid} suspected_injection belongs on the source; a claim-level flag cannot support the claim"
            )
            if conf == "verified":
                errors.append(f"{label}: {cid} cannot be verified from a claim-level suspected_injection flag")
            if drives:
                errors.append(f"{label}: {cid} has a claim-level suspected_injection flag and cannot drive a summary")
        if claim.get("about_person"):
            attrs = claim.get("identity_attributes") or []
            if not isinstance(attrs, list) or len(attrs) < 2:
                errors.append(f"{label}: {cid} is about a person but identity_attributes has fewer than 2 anchors")
            records = [record for record in (identities or []) if isinstance(record, dict)]
            if not records:
                errors.append(f"{label}: {cid} is about a person but no identity.yaml record was available to match")
            elif isinstance(attrs, list) and len(attrs) >= 2 and not anchors_match_one_record(attrs, records):
                errors.append(f"{label}: {cid} identity_attributes do not match one identity.yaml record")
            else:
                eligible = records
                if isinstance(attrs, list) and len(attrs) >= 2:
                    eligible = [record for record in records if anchors_match_one_record(attrs, [record])]
                claim_text = str(claim.get("text") or "")
                if not any(anchors_identify_person(record, claim_text) for record in eligible):
                    errors.append(
                        f"{label}: {cid} claim text does not contain two anchor values from one identity.yaml record, including a name or filing id"
                    )
                markers = []
                for source in sources:
                    if isinstance(source, dict):
                        marker = source_marker(claim, source)
                        if marker is not None:
                            markers.append(marker)
                units = _cited_units(draft, markers)
                if not units:
                    errors.append(
                        f"{label}: {cid} draft sentence carrying the marker does not contain two anchor values from one identity.yaml record, including a name or filing id"
                    )
                else:
                    # Prose names this record, or a pronoun continues the previous
                    # cited sentence in the same section. A table cell may rely on
                    # the header or row label that already names this record.
                    # Claim text above still needs two anchors. A second person's
                    # name in the sentence is still a separate claim.
                    for unit in units:
                        sentence = unit.text
                        identified = [record for record in eligible if _sentence_identifies(sentence, record)]
                        if not identified and unit.kind == "cell" and unit.context:
                            identified = [
                                record for record in eligible if _sentence_identifies(unit.context, record)
                            ]
                        if (
                            not identified
                            and unit.kind == "prose"
                            and unit.previous
                            and _PERSON_PRONOUN_RE.search(MARKER_RE.sub("", sentence))
                        ):
                            identified = [
                                record for record in eligible if _sentence_identifies(unit.previous, record)
                            ]
                        compared = identified or eligible
                        if any(_foreign_name(sentence, record) for record in compared):
                            errors.append(
                                f"{label}: {cid} draft sentence carrying the marker names a different person than identity.yaml"
                            )
                        if not identified:
                            errors.append(
                                f"{label}: {cid} draft sentence carrying the marker does not identify the person in identity.yaml"
                            )
        tiers = []
        publishers = []
        markers = []
        for source in sources:
            if not isinstance(source, dict):
                errors.append(f"{label}: {cid} has a source that is not a mapping")
                continue
            tiers.append(source.get("tier"))
            publishers.append(source.get("publisher"))
            marker = source_marker(claim, source)
            if marker is None:
                errors.append(f"{label}: {cid} source is missing a marker")
            else:
                markers.append(marker)
                previous = seen_markers.get(marker)
                if previous:
                    errors.append(f"{label}: marker {marker} is used by {previous} and {cid}")
                seen_markers[marker] = cid
            archive_url = source.get("archive_url")
            failed = source.get("archive_failed") is True and str(source.get("archive_failed_reason") or "").strip()
            if not archive_url and not failed:
                errors.append(f"{label}: {cid} needs archive_url or archive_failed plus a reason")
            retrieved = str(source.get("retrieved") or "")
            if not RETRIEVED_RE.match(retrieved):
                errors.append(f"{label}: {cid} retrieved must be 'YYYY-MM-DD HH:MM ET'")
            quote = str(source.get("quote") or "")
            if sentence_count(quote) > 2:
                errors.append(f"{label}: {cid} quote is longer than 2 sentences")
            url = str(source.get("url") or "")
            if not url.startswith(("https://", "http://")):
                errors.append(f"{label}: {cid} url must start with http:// or https://")
            host = host_of(url)
            if host in DISALLOWED_HOSTS or "chatgpt.com" in host:
                errors.append(f"{label}: {cid} uses disallowed host {host}")
        flagged = [source for source in sources if isinstance(source, dict) and source.get("suspected_injection") is True]
        dict_sources = [source for source in sources if isinstance(source, dict)]
        if dict_sources and len(flagged) == len(dict_sources):
            errors.append(f"{label}: {cid} suspected_injection source cannot be the only support")
            if conf == "verified":
                errors.append(f"{label}: {cid} cannot be verified when every source is suspected_injection")
            if drives:
                errors.append(f"{label}: {cid} is supported only by suspected_injection sources and cannot drive a summary")
        if sources and all(tier == "T4" for tier in tiers):
            if not claim.get("attribution_only"):
                errors.append(f"{label}: {cid} is supported only by T4 sources and is not marked attribution_only")
            if conf == "verified":
                errors.append(f"{label}: {cid} cannot be verified on T4 sources alone")
            if drives:
                errors.append(f"{label}: {cid} is T4-only and cannot drive a summary")
        if claim.get("polarity") == "negative" and conf == "verified":
            independent_publishers = {pub for pub, tier in zip(publishers, tiers) if tier in {"T1", "T2", "T3"} and pub}
            has_t1 = "T1" in tiers
            if not has_t1 and len(independent_publishers) < 2:
                errors.append(f"{label}: {cid} is a verified negative claim without a T1 source or two independent sources")
        if claim.get("polarity") == "negative" and conf == "single-source" and "T1" not in tiers:
            errors.append(f"{label}: {cid} negative single-source claim must be T1 or labeled unconfirmed")
        if conf == "identity-unconfirmed" and not claim.get("about_person"):
            errors.append(f"{label}: {cid} is identity-unconfirmed but not marked about_person")
    return errors


def strip_front_matter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def _heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
    if not match:
        return None
    # Pandoc header attributes ({#id .class}) are not part of the title.
    title = re.sub(r"\s*\{[^{}]*\}\s*$", "", match.group(2)).strip()
    return len(match.group(1)), norm_heading(title)


def factual_blocks(text: str) -> list[tuple[str, str, str]]:
    """Non-exempt blocks as (text, nearest h1, nearest h2)."""
    body = HTML_COMMENT_RE.sub("", strip_front_matter(text))
    kept: list[str] = []
    for raw in body.splitlines():
        if FOOTNOTE_DEF_RE.match(raw.strip()):
            continue
        kept.append(raw)
    blocks: list[tuple[str, str, str]] = []
    buf: list[str] = []
    stack: list[int] = []
    h1 = ""
    h2 = ""

    def flush(exempt: bool) -> None:
        nonlocal buf
        if buf and not exempt:
            block = "\n".join(buf).strip()
            if block:
                blocks.append((block, h1, h2))
        buf = []

    exempt = False
    for line in kept:
        heading = _heading(line)
        if heading:
            flush(exempt)
            level, title = heading
            if level == 1:
                h1, h2 = title, ""
            elif level == 2:
                h2 = title
            while stack and stack[-1] >= level:
                stack.pop()
            if title in EXEMPT_HEADINGS:
                stack.append(level)
            exempt = bool(stack)
            continue
        if line.strip() == "":
            flush(exempt)
            continue
        buf.append(line)
    flush(exempt)
    return blocks


def _sentences(block: str) -> list[str]:
    cleaned = MARKER_RE.sub("", block)
    cleaned = cleaned.replace("|", " ").replace(">", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    return [part.strip(" -*") for part in split_sentences(cleaned) if part.strip(" -*")]


def _gap_content_words(text: str) -> list[str]:
    return [word.lower() for word in _GAP_WORD_RE.findall(text) if word.lower() not in _GAP_FUNCTION_WORDS]


def _gap_items_name_an_event(inner: str) -> bool:
    """True when a searched item is an event rather than a source, place, or field label.

    A bare year is allowed only as the date on a source or place ("the 2026 ballot
    filing"). "the 2019 arrest", "the 2019 plea", and "conviction of 2019" are events.
    A month name is an event date. Field labels with no year stay allowed.
    """
    items = [part.strip(" .") for part in re.split(r",|\band\b", inner) if part.strip(" .")]
    for item in items:
        if _GAP_MONTH_RE.search(item):
            return True
        for match in _GAP_BARE_YEAR_RE.finditer(item):
            after = _gap_content_words(item[match.end() :])
            before = _gap_content_words(item[: match.start()])
            dated = after or before
            if not dated or any(word not in _DATED_SOURCE_WORDS for word in dated):
                return True
    return False


def _gap_sentence(sentence: str) -> bool:
    original = re.sub(r"\s+", " ", sentence).strip().strip("*").strip()
    text = original.lower()
    if text in GAP_SENTENCES:
        return True
    match = GAP_NOT_FOUND_RE.fullmatch(text)
    if not match:
        return False
    inner = match.group(1) if match.lastindex else ""
    if any(char in inner for char in ";:!"):
        return False
    if _GAP_CLAUSE_RE.search(inner):
        return False
    if _gap_items_name_an_event(inner):
        return False
    # A space after a dot is a second sentence. A capital glued to the dot is too.
    # A lowercase letter after the dot is a hostname, such as congress.gov.
    if re.search(r"\.\s", inner):
        return False
    inner_original = original[original.lower().find(inner) : original.lower().find(inner) + len(inner)] if inner else ""
    if re.search(r"\.[A-Z]", inner_original):
        return False
    return True


def _is_gap_text(text: str) -> bool:
    sentences = _sentences(text)
    if not sentences:
        return True
    return all(_gap_sentence(part) for part in sentences)


def _banner_key(sentence: str) -> str:
    text = re.sub(r"[*_>`]", "", sentence).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


BANNER_KEYS = {_banner_key(sentence) for sentence in BANNER_SENTENCES}


def _is_banner_sentence(sentence: str) -> bool:
    return _banner_key(sentence) in BANNER_KEYS


def unmarked_logistics_lines(ballot: dict | None) -> list[str]:
    """Office lines the guide may print without a marker. Values come from the ballot."""
    if not isinstance(ballot, dict):
        return []
    lines = []
    for entry in ballot.get("logistics") or []:
        if not isinstance(entry, dict) or entry.get("marker"):
            continue
        label = re.sub(r"\s+", " ", str(entry.get("label") or "Election office")).strip()
        url = str(entry.get("url") or "").strip()
        if label and url:
            lines.append(f"{label}: {url}")
    return lines


def precinct_restatement(ballot: dict | None) -> str:
    """The one precinct sentence generated from ballot.yaml. Empty when neither field is set."""
    if not isinstance(ballot, dict):
        return ""
    precinct = str(ballot.get("precinct") or "").strip()
    districts = [str(item).strip() for item in (ballot.get("districts") or []) if str(item).strip()]
    if not precinct and not districts:
        return ""
    bits = []
    if precinct:
        bits.append(f"Precinct {precinct}")
    if districts:
        bits.append("districts " + ", ".join(districts))
    return ", ".join(bits) + ", restates the confirmed ballot."


def _restatement_key(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().rstrip(".")


def official_restatement_sentences(ballot: dict | None) -> set[str]:
    """Exact uncited sentences the renderer may emit from this ballot. Nothing else."""
    found = {_restatement_key(line) for line in unmarked_logistics_lines(ballot)}
    precinct = precinct_restatement(ballot)
    if precinct:
        found.add(_restatement_key(precinct))
    return found


def prose_marker_errors(text: str, label: str, exempt: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    for block, h1, h2 in factual_blocks(text):
        if block.startswith("|"):
            rows = [line for line in block.splitlines() if line.strip().startswith("|")]
            seen_separator = False
            for index, row in enumerate(rows):
                compact = row.replace("|", "").replace(":", "").replace("-", "").replace(" ", "")
                if not compact:
                    seen_separator = True
                    continue
                if not seen_separator and index == 0:
                    continue
                if _is_gap_text(row) or _is_effort_row(row, h1, h2) or _is_review_row(row, h1, h2):
                    continue
                if not _has_citation_marker(row):
                    errors.append(f"{label}: table row has no citation marker: {row.strip()[:120]}")
            continue
        lines = block.splitlines()
        bullet_lines = [line for line in lines if line.strip().startswith(("- ", "* "))]
        if bullet_lines and len(bullet_lines) == len([line for line in lines if line.strip()]):
            for line in bullet_lines:
                errors.extend(
                    _sentence_marker_errors(
                        line.strip()[2:].strip(),
                        label,
                        "list item",
                        exempt=exempt,
                        h1=h1,
                        h2=h2,
                    )
                )
            continue
        errors.extend(
            _sentence_marker_errors(
                block,
                label,
                "sentence",
                banner_ok=block.lstrip().startswith(">"),
                exempt=exempt,
                h1=h1,
                h2=h2,
            )
        )
    return errors


def _has_citation_marker(text: str) -> bool:
    return MARKER_RE.search(text or "") is not None or LINK_MARKER_RE.search(text or "") is not None


def _mask_markers(text: str) -> str:
    masked = LINK_MARKER_RE.sub(" [M] ", text or "")
    return MARKER_RE.sub(" [M] ", masked)


def _is_navigation_sentence(plain: str, exempt: set[str] | None = None) -> bool:
    text = re.sub(r"\s+", " ", plain or "").strip().rstrip(".")
    if re.fullmatch(r":{3}(?:\s+[A-Za-z0-9_-]+)?", text):
        return True
    if _NAV_LINK_RE.match(text):
        return True
    # Only the exact office line or precinct sentence generated from ballot.yaml.
    # A similar allegation is still a sentence and still needs a marker.
    if exempt and text in exempt:
        return True
    return False


def _sentence_marker_errors(
    block: str,
    label: str,
    kind: str,
    banner_ok: bool = False,
    exempt: set[str] | None = None,
    h1: str = "",
    h2: str = "",
) -> list[str]:
    if _is_gap_text(block) and not _has_citation_marker(block):
        return []
    # Mask citation links before emphasis characters are removed. The link text
    # uses <sup>, and stripping ">" would hide the marker.
    protected = _mask_markers(_bind_trailing_markers(block))
    protected = re.sub(r"[*_>`]", "", protected)
    errors = []
    for part in split_sentences(protected.strip()):
        text = part.strip()
        if not text:
            continue
        plain = text.replace("[M]", "").strip()
        if not plain or _is_gap_text(plain):
            continue
        if _is_navigation_sentence(plain, exempt):
            continue
        if _is_plain_access_note(plain):
            continue
        if _is_run_record_sentence(plain, h1, h2, kind):
            continue
        if banner_ok and _is_banner_sentence(plain):
            continue
        if "[M]" not in text:
            errors.append(f"{label}: {kind} has no citation marker: {plain[:120]}")
    return errors


def marker_numbers(text: str) -> set[int]:
    body_lines = []
    for line in strip_front_matter(text).splitlines():
        if FOOTNOTE_DEF_RE.match(line.strip()):
            continue
        body_lines.append(line)
    blob = "\n".join(body_lines)
    found = {int(value) for value in MARKER_RE.findall(blob)}
    found.update(int(match.group(1)) for match in LINK_MARKER_RE.finditer(blob))
    return found


def works_cited_numbers(text: str) -> set[int]:
    return {int(value) for value in WORK_RE.findall(text)}


def claim_index(workspace) -> dict[int, tuple[str, dict, dict]]:
    index: dict[int, tuple[str, dict, dict]] = {}
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            marker = source_marker(claim, source)
            if marker is None or marker in index:
                continue
            index[marker] = (item.name, claim, source)
    return index


def marker_collision_errors(workspace) -> list[str]:
    owners: dict[int, list[str]] = {}
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            marker = source_marker(claim, source)
            if marker is None:
                continue
            ident = source.get("url") or source.get("title") or claim.get("id")
            owners.setdefault(marker, []).append(f"{item.name}/{claim.get('id')} ({ident})")
    errors = []
    for marker, rows in sorted(owners.items()):
        if len(rows) > 1:
            errors.append(f"marker {marker} is reused across sources: {'; '.join(rows)}")
    return errors


_HTML_ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
_HEADING_ANCHOR_RE = re.compile(r"\{#([A-Za-z0-9_-]+)")
_FRAGMENT_RE = re.compile(r"#([A-Za-z0-9_-]+)")


def anchor_ids(text: str) -> set[str]:
    """Whole anchor ids from HTML id attributes and markdown `{#id}`. `source-1` is not `source-10`."""
    found = set(_HTML_ID_RE.findall(text or ""))
    found.update(_HEADING_ANCHOR_RE.findall(text or ""))
    return found


def href_fragments(text: str) -> set[str]:
    """Whole URL fragments. `#cite-1` does not match `#cite-10`."""
    return set(_FRAGMENT_RE.findall(text or ""))


def assembled_guide_errors(
    text: str,
    index: dict[int, tuple[str, dict, dict]],
    addendum: str = "",
    *,
    reader: bool = False,
    ballot: dict | None = None,
) -> list[str]:
    """Check a rendered edition. Works cited may live in the sources addendum."""
    exempt = official_restatement_sentences(ballot)
    errors = prose_marker_errors(text, "final/guide.md", exempt)
    errors.extend(summary_errors(text, "final/guide.md", index))
    if reader:
        errors.extend(reader_contest_budget_errors(text))
        errors.extend(reader_log_errors(text))
    cited_text = addendum or text
    cited = works_cited_numbers(cited_text)
    addendum_anchors = anchor_ids(addendum) if addendum else set()
    body_anchors = anchor_ids(text)
    addendum_fragments = href_fragments(addendum) if addendum else set()
    for number in sorted(marker_numbers(text)):
        if number not in index:
            errors.append(f"final/guide.md: marker {number} does not resolve to a claim source")
        else:
            _item_name, claim, _source = index[number]
            if claim.get("removed"):
                errors.append(f"final/guide.md: marker {number} points at removed claim {claim.get('id')}")
            if claim.get("confidence") == "identity-unconfirmed":
                errors.append(f"final/guide.md: marker {number} is identity-unconfirmed and must not be published")
        if number not in cited:
            errors.append(f"final/guide.md: marker {number} has no works-cited entry")
        if addendum:
            if f"source-{number}" not in addendum_anchors:
                errors.append(f"final/guide.md: marker {number} does not link to an addendum entry")
            if f"cite-{number}" not in body_anchors:
                errors.append(f"final/guide.md: marker {number} has no back-link target")
            if f"cite-{number}" not in addendum_fragments:
                errors.append(f"final/guide.md: marker {number} addendum entry does not link back")
    for number in sorted(cited):
        if number not in index:
            errors.append(f"final/guide.md: works-cited [{number}] has no claim source")
    return errors


def reader_contest_budget_errors(text: str, budget: int | None = None) -> list[str]:
    """Each reader contest stays inside the word budget. The full edition does not."""
    limit = READER_CONTEST_WORD_BUDGET if budget is None else budget
    errors = []
    matches = list(re.finditer(r"(?m)^## .+\{#contest-([^}\s]+)", text or ""))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[start:end]
        later_heading = re.search(r"(?m)^# (?!#)", chunk)
        if later_heading:
            chunk = chunk[: later_heading.start()]
        words = reader_visible_word_count(chunk)
        if words > limit:
            errors.append(
                f"final/guide.md: contest {match.group(1)} is {words} words, over the {limit}-word reader budget"
            )
    return errors


def summary_errors(text: str, label: str, index: dict[int, tuple[str, dict, dict]]) -> list[str]:
    errors = []
    if "<!-- summary -->" not in text:
        return errors
    after = text.split("<!-- summary -->", 1)[1]
    paragraph_lines = []
    for line in after.splitlines():
        if line.strip() == "" and paragraph_lines:
            break
        if line.strip().startswith("#"):
            break
        if line.strip():
            paragraph_lines.append(line)
    paragraph = " ".join(paragraph_lines).strip()
    if not paragraph:
        errors.append(f"{label}: summary comment has no paragraph")
        return errors
    if _is_gap_text(paragraph):
        return errors
    numbers = marker_numbers(paragraph)
    if not numbers:
        errors.append(f"{label}: summary has no citation markers")
    for number in sorted(numbers):
        found = index.get(number)
        if not found:
            errors.append(f"{label}: summary marker {number} does not resolve")
            continue
        _item, claim, _source = found
        if claim.get("removed"):
            errors.append(f"{label}: summary marker {number} points at removed claim {claim.get('id')}")
        if claim.get("confidence") != "verified" or not claim.get("drives_summary"):
            errors.append(f"{label}: summary marker {number} is not a verified summary claim")
    return errors


def citation_errors(workspace, guide: bool = False) -> list[str]:
    errors: list[str] = []
    errors.extend(marker_collision_errors(workspace))
    index = claim_index(workspace)
    ballot = load_yaml(workspace / "ballot.yaml") if (workspace / "ballot.yaml").exists() else {}
    if not isinstance(ballot, dict):
        ballot = {}
    exempt = official_restatement_sentences(ballot)
    for item in iter_items(workspace):
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        text = draft_path.read_text(encoding="utf-8")
        label = f"items/{item.name}/draft.md"
        errors.extend(prose_marker_errors(text, label, exempt))
        doc = load_yaml(item / "claims.yaml") or {}
        item_type = doc.get("item_type") if isinstance(doc, dict) else None
        if item_type in SUMMARY_TYPES:
            if "<!-- summary -->" not in text:
                errors.append(f"{label}: missing <!-- summary --> paragraph")
            else:
                errors.extend(summary_errors(text, label, index))
        for number in marker_numbers(text):
            if number not in index:
                errors.append(f"{label}: marker {number} does not resolve to a claim source")
            else:
                _item_name, claim, _source = index[number]
                if claim.get("removed"):
                    errors.append(f"{label}: marker {number} points at removed claim {claim.get('id')}")
                if claim.get("confidence") == "identity-unconfirmed":
                    errors.append(f"{label}: marker {number} is identity-unconfirmed and must not be published")
    guide_path = workspace / "final" / "guide.md"
    if guide:
        if not guide_path.exists():
            errors.append("final/guide.md is missing")
        else:
            addendum_path = workspace / "final" / "guide-sources.md"
            addendum = addendum_path.read_text(encoding="utf-8") if addendum_path.exists() else ""
            if not addendum_path.exists():
                errors.append("final/guide-sources.md is missing")
            errors.extend(
                assembled_guide_errors(
                    guide_path.read_text(encoding="utf-8"),
                    index,
                    addendum,
                    reader=True,
                    ballot=ballot,
                )
            )
        full_path = workspace / "final" / "guide-full.md"
        if full_path.exists():
            full_addendum_path = workspace / "final" / "guide-full-sources.md"
            full_addendum = (
                full_addendum_path.read_text(encoding="utf-8") if full_addendum_path.exists() else ""
            )
            if not full_addendum_path.exists():
                errors.append("final/guide-full-sources.md is missing")
            errors.extend(
                assembled_guide_errors(
                    full_path.read_text(encoding="utf-8"),
                    index,
                    full_addendum,
                    reader=False,
                    ballot=ballot,
                )
            )
    return errors


def section_map(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in strip_front_matter(text).splitlines():
        heading = _heading(line)
        if heading and heading[0] == 2:
            current = heading[1]
            sections.setdefault(current, [])
            continue
        if current and heading and heading[0] < 2:
            current = None
            continue
        if current:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def reader_visible_word_count(text: str) -> int:
    """Words a reader sees. Link targets and HTML anchors are not printed."""
    visible = _HTML_TAG_RE.sub(" ", text or "")
    visible = _MD_LINK_RE.sub(r"\1", visible)
    return word_count(visible)


def _cited_word_count(text: str) -> int:
    """Words in sentences that carry a marker. Gap sentences do not count."""
    total = 0
    for line in HTML_COMMENT_RE.sub("", text or "").splitlines():
        if _heading(line) or FOOTNOTE_DEF_RE.match(line.strip()):
            continue
        for sentence in split_sentences(_bind_trailing_markers(line)):
            if "[^" not in sentence:
                continue
            plain = MARKER_RE.sub("", sentence)
            if _gap_sentence(plain):
                continue
            total += word_count(plain)
    return total


def core_for(item_type: str | None) -> list[str] | None:
    return {
        "candidate": CANDIDATE_CORE,
        "measure": MEASURE_CORE,
        "legislation": LEGISLATION_CORE,
        "judicial-retention": JUDICIAL_CORE,
    }.get(item_type or "")


def symmetry_errors(workspace) -> list[str]:
    errors: list[str] = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    config = load_config()
    ratio = float(config.get("effort_parity_ratio", 0.8))
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict):
            continue
        if contest.get("type") not in {"race", "primary", "local-office"}:
            item_id = contest.get("item_id") or contest.get("id")
            item_dir = workspace / "items" / str(item_id)
            doc = load_yaml(item_dir / "claims.yaml") or {}
            required = core_for(doc.get("item_type") or contest.get("type"))
            draft = item_dir / "draft.md"
            if required and draft.exists():
                have = set(section_map(draft.read_text(encoding="utf-8")))
                for name in required:
                    if name not in have:
                        errors.append(f"{item_id}: missing section '{name}'")
            continue
        candidates = [c for c in contest.get("candidates") or [] if isinstance(c, dict) and not c.get("write_in")]
        bodies = []
        efforts = []
        for candidate in candidates:
            item_id = candidate.get("item_id") or candidate.get("id")
            draft_path = workspace / "items" / str(item_id) / "draft.md"
            if not draft_path.exists():
                errors.append(f"{item_id}: missing draft.md")
                continue
            sections = section_map(draft_path.read_text(encoding="utf-8"))
            required = list(CANDIDATE_CORE)
            if contest.get("type") == "primary":
                required.extend(PRIMARY_ADDON)
            elif contest.get("type") == "local-office":
                required.extend(LOCAL_ADDON)
            for name in required:
                if name not in sections:
                    errors.append(f"{item_id}: missing section '{name}'")
            bodies.append((item_id, sections))
            effort_path = workspace / "items" / str(item_id) / "effort.json"
            effort = {}
            if effort_path.exists():
                import json

                effort = json.loads(effort_path.read_text(encoding="utf-8"))
            else:
                errors.append(f"{item_id}: missing effort.json")
            efforts.append((item_id, effort))
        for name in CANDIDATE_CORE:
            cited_rows = []
            for item_id, sections in bodies:
                body = sections.get(name, "")
                if _is_gap_text(body):
                    continue
                cited_rows.append((item_id, _cited_word_count(body)))
            positive = sorted(count for _item, count in cited_rows if count > 0)
            if len(positive) < 2:
                continue
            median = positive[len(positive) // 2] if len(positive) % 2 else (positive[len(positive) // 2 - 1] + positive[len(positive) // 2]) / 2
            if median <= 0:
                continue
            for item_id, count in cited_rows:
                if count <= 0:
                    continue
                if count / median < 0.5:
                    errors.append(
                        f"{contest.get('id')}: section '{name}' cited word count for {item_id} ({count}) "
                        f"is below half the median ({median:g})"
                    )
        scores = []
        section_rows: dict[str, list[tuple[str, int]]] = {}
        for item_id, effort in efforts:
            scores.append((item_id, int(effort.get("searches") or 0) + int(effort.get("fetches") or 0)))
            for name, counts in (effort.get("sections") or {}).items():
                if not isinstance(counts, dict):
                    continue
                total = int(counts.get("searches") or 0) + int(counts.get("fetches") or 0)
                section_rows.setdefault(norm_heading(str(name)), []).append((item_id, total))
        peak = max((score for _item, score in scores), default=0)
        if peak > 0:
            for item_id, score in scores:
                if score < ratio * peak:
                    errors.append(f"{item_id}: effort {score} is below {ratio:.0%} of the race max {peak}.")
        known_ids = {item_id for item_id, _score in scores}
        for name, rows in section_rows.items():
            present = {item_id for item_id, _score in rows}
            for item_id in known_ids - present:
                rows.append((item_id, 0))
            section_peak = max((score for _item, score in rows), default=0)
            if section_peak <= 0:
                continue
            for item_id, score in rows:
                if score < ratio * section_peak:
                    errors.append(
                        f"{item_id}: section '{name}' effort {score} is below {ratio:.0%} of {section_peak}."
                    )
        if contest.get("type") in {"race", "primary", "local-office"}:
            race_id = str(contest.get("item_id") or contest.get("id"))
            race_draft = workspace / "items" / race_id / "draft.md"
            if race_draft.exists():
                sections = section_map(race_draft.read_text(encoding="utf-8"))
                overview = list(RACE_OVERVIEW)
                if contest.get("type") == "primary":
                    overview.extend(PRIMARY_ADDON)
                elif contest.get("type") == "local-office":
                    overview.extend(LOCAL_ADDON)
                for name in overview:
                    if name not in sections:
                        errors.append(f"{contest.get('id')}: race draft is missing '{name}'")
    errors.extend(argument_length_errors(workspace))
    errors.extend(structured_symmetry_errors(workspace))
    return errors


def argument_length_errors(workspace) -> list[str]:
    errors: list[str] = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    seen: set[str] = set()
    targets: list[str] = []
    for contest in ballot.get("contests") or []:
        if isinstance(contest, dict) and contest.get("type") in {"measure", "legislation"}:
            targets.append(str(contest.get("item_id") or contest.get("id")))
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if isinstance(doc, dict) and doc.get("item_type") in {"measure", "legislation"}:
            targets.append(item.name)
    for item_id in targets:
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        draft = workspace / "items" / item_id / "draft.md"
        if not draft.exists():
            continue
        sections = section_map(draft.read_text(encoding="utf-8"))
        if "arguments for" not in sections and "arguments against" not in sections:
            continue
        for_body = sections.get("arguments for", "")
        against_body = sections.get("arguments against", "")
        # No organized opposition is a gap. Do not pad the empty side to match the other.
        if _is_gap_text(for_body) or _is_gap_text(against_body):
            continue
        for_words = word_count(for_body)
        against_words = word_count(against_body)
        peak = max(for_words, against_words)
        if peak and min(for_words, against_words) / peak < 0.8:
            errors.append(
                f"{item_id}: arguments for ({for_words} words) and against ({against_words} words) differ by more than 20%"
            )
    return errors


def _preamble(text: str) -> str:
    lines = []
    for line in strip_front_matter(text).splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines)


def _first_content_line(text: str) -> str:
    for line in _preamble(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ">", "<!--")):
            continue
        return stripped
    return ""


def _states_uncontested(body: str) -> bool:
    sentences = _sentences(body) or ([body] if body.strip() else [])
    for sentence in sentences:
        lowered = sentence.lower()
        if "uncontested" not in lowered:
            continue
        if re.search(r"\b(?:not|no|never|isn't|aren't|wasn't|weren't)\b", lowered):
            continue
        return True
    return False


def edge_errors(workspace) -> list[str]:
    errors: list[str] = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict):
            continue
        candidates = [c for c in contest.get("candidates") or [] if isinstance(c, dict)]
        active = [c for c in candidates if not c.get("withdrawn") and not c.get("write_in")]
        race_id = str(contest.get("item_id") or contest.get("id"))
        race_draft_path = workspace / "items" / race_id / "draft.md"
        race_text = race_draft_path.read_text(encoding="utf-8") if race_draft_path.exists() else ""
        sections = section_map(race_text) if race_text else {}
        if contest.get("type") in {"race", "primary", "local-office"} and len(active) == 1:
            if not _states_uncontested(sections.get("uncontested", "")):
                errors.append(f"{race_id}: uncontested race must say so in the Uncontested section")
        write_ins = [c for c in candidates if c.get("write_in")]
        if write_ins and "write-in candidates" not in sections:
            errors.append(f"{race_id}: write-in candidates need a Write-in candidates section")
        for candidate in candidates:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            draft_path = workspace / "items" / item_id / "draft.md"
            if not draft_path.exists():
                continue
            text = draft_path.read_text(encoding="utf-8")
            if candidate.get("withdrawn") and not WITHDRAWN_RE.match(_first_content_line(text)):
                errors.append(f"{item_id}: withdrawn candidate needs a 'withdrawn on DATE' banner")
            if candidate.get("limited_public_record") and "limited public record" not in _preamble(text).lower():
                errors.append(f"{item_id}: thin-record candidate needs a limited public record notice before the first section")
    return errors


def parse_retrieved(value: str) -> date:
    return date.fromisoformat(value[:10])


def staleness_findings(workspace, today: date, max_days: int | None = None) -> list[str]:
    if max_days is None:
        max_days = int(load_config().get("staleness_days", 7))
    findings = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    election_year = None
    election_date = (ballot.get("election") or {}).get("date") if isinstance(ballot.get("election"), dict) else None
    if isinstance(election_date, str) and len(election_date) >= 4:
        election_year = int(election_date[:4])
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            retrieved = str(source.get("retrieved") or "")
            if not RETRIEVED_RE.match(retrieved):
                continue
            age = (today - parse_retrieved(retrieved)).days
            if age > max_days:
                findings.append(
                    f"{claim.get('id')} marker {source_marker(claim, source)}: retrieved {retrieved} is {age} days before {today.isoformat()} (limit {max_days})"
                )
            published = str(source.get("published") or "")
            if election_year and re.match(r"^\d{4}-\d{2}-\d{2}$", published):
                if int(published[:4]) < election_year:
                    findings.append(
                        f"NOTE {claim.get('id')}: published {published} is before election year {election_year}; label the year in the guide"
                    )
    return findings


def stale_errors(workspace, today: date, max_days: int | None = None) -> list[str]:
    return [line for line in staleness_findings(workspace, today, max_days) if not line.startswith("NOTE ")]


def _year_is_on_claim(claim_text: str, draft: str, marker: int | None, year: str) -> bool:
    """The year must be a whole word in every draft sentence that carries this marker."""
    del claim_text
    if marker is None or not draft:
        return False
    token = f"[^{marker}]"
    # Letters count too, so 2018a and fy2018 are not the year 2018.
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(year)}(?![A-Za-z0-9])")
    found = False
    for line in HTML_COMMENT_RE.sub("", draft).splitlines():
        for sentence in split_sentences(_bind_trailing_markers(line)):
            if token not in sentence:
                continue
            found = True
            if pattern.search(sentence) is None:
                return False
    return found


def year_label_errors(workspace) -> list[str]:
    errors = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    election = ballot.get("election") if isinstance(ballot, dict) else None
    election_date = election.get("date") if isinstance(election, dict) else None
    if not isinstance(election_date, str) or len(election_date) < 4:
        return errors
    election_year = int(election_date[:4])
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        draft_path = item / "draft.md"
        draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            published = str(source.get("published") or "")
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", published):
                continue
            year = int(published[:4])
            if year >= election_year:
                continue
            label = str(year)
            marker = source_marker(claim, source)
            if _year_is_on_claim(str(claim.get("text") or ""), draft, marker, label):
                continue
            errors.append(
                f"{claim.get('id')}: published {published} is before election year {election_year}; label the year as a whole word in the draft sentence that carries the marker"
            )
    return errors


def _archive_fallback(source: dict) -> bool:
    if source.get("archive_url"):
        return True
    return source.get("archive_failed") is True and bool(str(source.get("archive_failed_reason") or "").strip())


def offline_link_errors(workspace) -> list[str]:
    errors = []
    checked = 0
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            checked += 1
            url = str(source.get("url") or "")
            reason = unsafe_fetch_target(url)
            if reason:
                errors.append(f"{claim.get('id')}: URL is not allowed ({reason})")
            if not _archive_fallback(source):
                errors.append(f"{claim.get('id')}: needs archive_url or archive_failed plus a reason")
    dump_json(workspace / "link-check.json", {"mode": "offline", "checked": checked, "errors": len(errors)})
    return errors


def environment_rating_sentence(workspace) -> str:
    for path in (workspace / "env.md", repo_root() / "output" / "env.md"):
        if not path.exists():
            continue
        match = re.search(r"Rating:\s*\**\s*(Full|Reduced|Minimal)\b", path.read_text(encoding="utf-8"))
        if match:
            return f"Environment rating: {match.group(1)}."
        return "Environment rating is not recorded in env.md."
    return "No environment rating file was found."


def _significant_numbers(text: str) -> set[str]:
    found: set[str] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(0).replace(",", "")
        if re.fullmatch(r"(?:19|20)\d{2}", raw):
            continue
        digits = raw.replace(".", "")
        if "." not in raw and len(digits) < 3:
            continue
        found.add(raw)
    return found


def _flat_text(text: str) -> str:
    cleaned = (text or "").replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _local_archive_text(workspace, source: dict) -> tuple[str | None, str | None]:
    """Text of a saved local copy, ignoring the filename.

    Returns (text, error). No local_copy is (None, None). A declared copy that
    cannot be read is an error so a quote cannot skip the verbatim check.
    """
    local = str(source.get("local_copy") or "").strip()
    if not local:
        return None, None
    path = Path(local)
    if not path.is_absolute():
        path = Path(workspace) / local
    if not path.is_file():
        return None, f"local copy not found: {local}"
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip"}:
        return None, f"local copy is not extractable text: {local}"
    if suffix == ".pdf":
        import subprocess

        try:
            result = subprocess.run(
                ["pdftotext", "-q", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"could not read local copy {local}: {exc}"
        if result.returncode != 0 and not result.stdout:
            detail = (result.stderr or "pdftotext failed").strip()
            return None, f"could not read local copy {local}: {detail[:200]}"
        return result.stdout, None
    if suffix in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", raw)
        raw = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", raw)
        raw = re.sub(r"(?is)<[^>]+>", " ", raw)
        return raw, None
    data = path.read_bytes()
    if b"\0" in data[:1024]:
        return None, f"local copy is not extractable text: {local}"
    return data.decode("utf-8", errors="replace"), None


def number_quote_errors(workspace) -> list[str]:
    """A figure in a draft sentence must appear in a quote or the archived page.

    The filename does not count. A number elsewhere on the saved page does.
    Two markers on one sentence may cover the figure with two quotes.
    """
    errors = []
    for item in iter_items(workspace):
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        quotes: dict[int, str] = {}
        archives: dict[int, str] = {}
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            marker = source_marker(claim, source)
            if marker is None:
                continue
            quotes[marker] = quotes.get(marker, "") + " " + str(source.get("quote") or "")
            page, _problem = _local_archive_text(workspace, source)
            if page:
                archives[marker] = archives.get(marker, "") + " " + page
        draft = draft_path.read_text(encoding="utf-8")
        for sentence in _marker_sentences(draft, list(quotes)):
            numbers = _significant_numbers(MARKER_RE.sub("", sentence))
            if not numbers:
                continue
            cited = [int(value) for value in MARKER_RE.findall(sentence)]
            quote_blob = " ".join(quotes.get(marker, "") for marker in cited)
            quote_numbers = _significant_numbers(quote_blob)
            missing = numbers - quote_numbers
            if not missing:
                continue
            page_blob = " ".join(archives.get(marker, "") for marker in cited)
            page_numbers = _significant_numbers(page_blob)
            still = sorted(missing - page_numbers)
            if still:
                errors.append(
                    f"items/{item.name}/draft.md: {still[0]} is in a cited sentence but not in the cited quote"
                )
    return errors


def _explicit_archive_failure(source: dict) -> bool:
    return source.get("archive_failed") is True and bool(str(source.get("archive_failed_reason") or "").strip())


def _unarchived_verified_figure_needs_second_source(claim: dict) -> bool:
    """The existing rule for a verified dollar or vote total whose filing was not archived."""
    if claim.get("confidence") != "verified":
        return False
    if not _FIGURE_RE.search(str(claim.get("text") or "")):
        return False
    sources = [source for source in (claim.get("sources") or []) if isinstance(source, dict)]
    if not sources:
        return False
    publishers = _independent_publishers(sources)
    has_t1 = "T1" in [source.get("tier") for source in sources]
    archived = any(source.get("archive_url") for source in sources)
    failed = all(source.get("archive_failed") is True and not source.get("archive_url") for source in sources)
    return bool(has_t1 and len(publishers) < 2 and failed and not archived)


def quote_verbatim_errors(workspace) -> list[str]:
    """A quote must be verbatim in a readable local copy.

    A source with no local copy is not skipped. It must be explicitly
    archive_failed. An unarchived verified dollar or vote total still needs a
    second independent source. Whitespace is collapsed. The filename is not the copy.
    """
    errors = []
    reported_figures: set[tuple[str, str]] = set()
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            quote = str(source.get("quote") or "").strip()
            if not quote:
                continue
            cid = str(claim.get("id"))
            if not str(source.get("local_copy") or "").strip():
                if not _explicit_archive_failure(source):
                    errors.append(f"{item.name}: {cid} quote has no readable local copy")
                elif _unarchived_verified_figure_needs_second_source(claim):
                    key = (item.name, cid)
                    if key not in reported_figures:
                        reported_figures.add(key)
                        errors.append(
                            f"{item.name}: {cid} quote was not archived and the verified figure needs a second independent source"
                        )
                continue
            page, problem = _local_archive_text(workspace, source)
            if problem:
                errors.append(f"{item.name}: {cid} {problem}")
                continue
            if page is None or _flat_text(quote) not in _flat_text(page):
                errors.append(f"{item.name}: {cid} quote is not verbatim in the archived local copy")
    return errors


def _independent_publishers(sources: list) -> set[str]:
    found = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("tier") not in {"T1", "T2", "T3"}:
            continue
        publisher = str(source.get("publisher") or "").strip().lower()
        if publisher:
            found.add(publisher)
    return found


def figure_source_errors(workspace) -> list[str]:
    """Dollar and vote totals need a T1 filing or two independent sources.

    A verified figure whose only source could not be archived needs a second
    independent source. A fiction: true practice ballot does not waive that.
    """
    errors = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("removed"):
                continue
            text = str(claim.get("text") or "")
            if not _FIGURE_RE.search(text):
                continue
            sources = [source for source in claim.get("sources") or [] if isinstance(source, dict)]
            if not sources:
                continue
            publishers = _independent_publishers(sources)
            tiers = [source.get("tier") for source in sources]
            has_t1 = "T1" in tiers
            archived = any(source.get("archive_url") for source in sources)
            failed = all(
                source.get("archive_failed") is True and not source.get("archive_url") for source in sources
            )
            if claim.get("confidence") == "verified" and not has_t1 and len(publishers) < 2:
                errors.append(
                    f"{item.name}: {claim.get('id')} is a verified dollar or vote claim without a T1 source or two independent sources"
                )
            if (
                claim.get("confidence") == "verified"
                and has_t1
                and len(publishers) < 2
                and failed
                and not archived
            ):
                errors.append(
                    f"{item.name}: {claim.get('id')} is a verified figure whose filing was not archived and needs a second independent source"
                )
    return errors


_HEAVY_RECORD_RE = re.compile(
    r"\b(?:division of elections|supervisor of elections|sample ballot|"
    r"paid qualifying fee|qualifying fee|qualified|qualifying)\b",
    re.IGNORECASE,
)
_OFFICIAL_RECORD_BOILERPLATE_RE = re.compile(
    r"\b(?:division of elections|supervisor of elections|sample ballot|"
    r"paid qualifying fee|qualifying fee|qualified|qualifying|nonpartisan|"
    r"ballot line|appears on the ballot|on the ballot)\b",
    re.IGNORECASE,
)


def _normalized_prose(text: str, names: list[str]) -> str:
    cleaned = MARKER_RE.sub("", text or "").lower()
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 3:
            cleaned = re.sub(rf"\b{re.escape(name.lower())}\b", "candidate", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _residual_prose(text: str) -> str:
    """Drop shared official-record boilerplate before a near-copy comparison.

    Narrative that does not use that boilerplate is compared as written, so a
    near-copy of a biography still fails. A filing-line skeleton loses the
    shared office words and the name placeholder, then the short remainder is
    not called a template. An identical paragraph is rejected before this step.
    """
    if not _HEAVY_RECORD_RE.search(text or ""):
        return text or ""
    cleaned = _OFFICIAL_RECORD_BOILERPLATE_RE.sub(" ", text or "")
    cleaned = re.sub(r"\bcandidate\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def templated_prose_errors(workspace) -> list[str]:
    """Name-swapped section text, including a near-copy, does not satisfy symmetry."""
    errors = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    if not isinstance(ballot, dict):
        return errors
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict) or contest.get("type") not in {"race", "primary", "local-office"}:
            continue
        candidates = [c for c in contest.get("candidates") or [] if isinstance(c, dict) and not c.get("write_in")]
        names = [str(c.get("name") or "") for c in candidates]
        by_section: dict[str, list[tuple[str, str]]] = {}
        for candidate in candidates:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            draft_path = workspace / "items" / item_id / "draft.md"
            if not draft_path.exists():
                continue
            sections = section_map(draft_path.read_text(encoding="utf-8"))
            for name in CANDIDATE_CORE:
                body = sections.get(name, "")
                if _is_gap_text(body) or _cited_word_count(body) < 12:
                    continue
                by_section.setdefault(name, []).append((item_id, _normalized_prose(body, names)))
        for name, bodies in by_section.items():
            for index, (item_id, text) in enumerate(bodies):
                for previous_id, previous_text in bodies[:index]:
                    if not text or not previous_text:
                        continue
                    if text == previous_text:
                        errors.append(
                            f"{contest.get('id')}: section '{name}' for {item_id} repeats the templated text used for {previous_id}"
                        )
                        continue
                    # Parallel filing lines share office boilerplate. Compare what
                    # is left, and skip a skeleton that is only that boilerplate.
                    # An identical paragraph already failed above.
                    left = _residual_prose(previous_text)
                    right = _residual_prose(text)
                    if word_count(left) < 12 or word_count(right) < 12:
                        continue
                    ratio = difflib.SequenceMatcher(None, left, right).ratio()
                    if ratio < NEAR_COPY_RATIO:
                        continue
                    errors.append(
                        f"{contest.get('id')}: section '{name}' for {item_id} is a near-copy of the templated text used for {previous_id}"
                    )
    return errors


_REPORT_DAY_RE = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})")
_REPORT_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_REPORT_LONG_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),\s+(20\d{2})\b",
    re.IGNORECASE,
)


def _parse_report_day(value: str):
    """The calendar day named in a report_date string, if the string has one."""
    match = _REPORT_DAY_RE.search(value or "")
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    long_match = _REPORT_LONG_RE.search(value or "")
    if not long_match:
        return None
    try:
        return date(int(long_match.group(3)), _REPORT_MONTHS[long_match.group(1).lower()], int(long_match.group(2)))
    except ValueError:
        return None


def heading_errors(workspace) -> list[str]:
    errors = []
    for item in iter_items(workspace):
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        text = draft_path.read_text(encoding="utf-8")
        if not re.search(r"^#\s+\S", text, re.M):
            errors.append(f"items/{item.name}/draft.md: missing a level-1 heading. Keep the scaffold's # title line.")
    return errors


def structured_symmetry_errors(workspace) -> list[str]:
    """Symmetry on profile.yaml fields. Rendered prose is not the only check."""
    errors = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    if not isinstance(ballot, dict):
        return errors
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict) or contest.get("type") not in {"race", "primary", "local-office"}:
            continue
        candidates = [c for c in contest.get("candidates") or [] if isinstance(c, dict) and not c.get("write_in")]
        profiles = []
        for candidate in candidates:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            path = workspace / "items" / item_id / "profile.yaml"
            if not path.exists():
                continue
            data = load_yaml(path)
            if isinstance(data, dict):
                profiles.append((item_id, data))
        if len(profiles) < 2:
            continue
        issue_sets = []
        for item_id, data in profiles:
            issues = data.get("issues") or {}
            if not isinstance(issues, dict):
                errors.append(f"{item_id}: profile.yaml issues must be a mapping of shared issue keys")
                continue
            issue_sets.append((item_id, set(issues)))
        if len(issue_sets) >= 2:
            union = set().union(*(keys for _item, keys in issue_sets))
            for item_id, keys in issue_sets:
                missing = sorted(union - keys)
                if missing:
                    errors.append(
                        f"{item_id}: profile.yaml is missing shared issue rows {', '.join(missing)}. "
                        "Every candidate gets the same issue rows."
                    )
        dates = []
        for item_id, data in profiles:
            money = data.get("money") or {}
            if isinstance(money, dict) and money.get("report_date"):
                raw_date = str(money.get("report_date"))
                dates.append((item_id, raw_date, _parse_report_day(raw_date)))
        parsed_days = {day for _item, _raw, day in dates if day is not None}
        raw_values = {raw for _item, raw, _day in dates}
        if len(parsed_days) > 1 or (not parsed_days and len(raw_values) > 1):
            shown = ", ".join(f"{item_id} {raw}" for item_id, raw, _day in dates)
            errors.append(f"{contest.get('id')}: money report_date differs across candidates ({shown})")
        elif parsed_days and any(day is None for _item, _raw, day in dates):
            shown = ", ".join(f"{item_id} {raw}" for item_id, raw, _day in dates)
            errors.append(f"{contest.get('id')}: money report_date differs across candidates ({shown})")
        gap_sets = []
        for item_id, data in profiles:
            gaps = data.get("gaps") or []
            if isinstance(gaps, list):
                gap_sets.append((item_id, {str(item) for item in gaps}))
        if len(gap_sets) >= 2:
            # A field found for someone must stay visible for everyone. Whole-race gaps are symmetric.
            found_somewhere = set()
            for _item, gaps in gap_sets:
                # gaps lists fields that were NOT found. A field absent from one list and present
                # in another means one candidate showed it. That is allowed only when every profile
                # lists the field as found-or-gap explicitly via the same keys in `fields`.
                pass
            field_maps = []
            for item_id, data in profiles:
                fields = data.get("fields")
                if isinstance(fields, dict):
                    field_maps.append((item_id, fields))
            if len(field_maps) >= 2:
                union_fields = set().union(*(set(fields) for _item, fields in field_maps))
                for item_id, fields in field_maps:
                    missing = sorted(union_fields - set(fields))
                    if missing:
                        errors.append(
                            f"{item_id}: profile.yaml fields omit {', '.join(missing)} that another candidate lists"
                        )
                for field in sorted(union_fields):
                    values = []
                    for item_id, fields in field_maps:
                        value = fields.get(field)
                        empty = value in (None, "", "Not found", "not found")
                        values.append(empty)
                    if all(values):
                        continue
                    if any(values) and not all(item_id for item_id, fields in field_maps if field in fields):
                        errors.append(f"{contest.get('id')}: field '{field}' is missing for a candidate")
        sweep_rows = []
        for item_id, data in profiles:
            sweep = data.get("legal_sweep")
            if isinstance(sweep, dict):
                sweep_rows.append((item_id, sweep))
        if sweep_rows:
            present = {item_id for item_id, _sweep in sweep_rows}
            for candidate in candidates:
                item_id = str(candidate.get("item_id") or candidate.get("id"))
                if item_id not in present:
                    errors.append(
                        f"{item_id}: legal_sweep is missing while another candidate in the race has one"
                    )
            key_sets = []
            for item_id, sweep in sweep_rows:
                keys = {key for key in sweep if key != "aliases_searched"}
                missing = [key for key in LEGAL_SWEEP_KEYS if key not in keys]
                if missing:
                    errors.append(f"{item_id}: legal_sweep is missing {', '.join(missing)}")
                key_sets.append((item_id, keys))
            if len(key_sets) >= 2:
                union_keys = set().union(*(keys for _item, keys in key_sets))
                for item_id, keys in key_sets:
                    absent = sorted(union_keys - keys)
                    if absent:
                        errors.append(
                            f"{item_id}: legal_sweep omits {', '.join(absent)} that another candidate lists"
                        )
            if len(sweep_rows) >= 2:
                for key in LEGAL_SWEEP_KEYS:
                    states = [(item_id, _sweep_search_state(sweep.get(key))) for item_id, sweep in sweep_rows]
                    checked = [item_id for item_id, state in states if state == "checked"]
                    unchecked = [item_id for item_id, state in states if state == "not_checked"]
                    if checked and unchecked:
                        for item_id in unchecked:
                            errors.append(
                                f"{item_id}: legal_sweep.{key} is not_checked while another candidate in the race was checked"
                            )
        party_rows = [(item_id, data.get("party")) for item_id, data in profiles if isinstance(data.get("party"), dict)]
        if party_rows:
            present = {item_id for item_id, _party in party_rows}
            for candidate in candidates:
                item_id = str(candidate.get("item_id") or candidate.get("id"))
                if item_id not in present:
                    errors.append(f"{item_id}: profile.yaml party is missing while another candidate in the race has one")
        endorsement_rows = [(item_id, data.get("endorsements")) for item_id, data in profiles if "endorsements" in data]
        if endorsement_rows:
            present = {item_id for item_id, _rows in endorsement_rows}
            for candidate in candidates:
                item_id = str(candidate.get("item_id") or candidate.get("id"))
                if item_id not in present:
                    errors.append(
                        f"{item_id}: profile.yaml endorsements is missing while another candidate in the race has a list"
                    )
    return errors


def _sweep_search_state(row) -> str:
    """Collapse a category status to whether that category was searched."""
    if not isinstance(row, dict):
        return "missing"
    status = str(row.get("status") or "")
    if status in {"checked_nothing_found", "record_found"}:
        return "checked"
    if status == "not_checked":
        return "not_checked"
    if status == "portal_unavailable":
        return "portal_unavailable"
    return status or "missing"


def _claim_section(claim: dict) -> str:
    return norm_heading(str(claim.get("section") or ""))


def _party_claims(doc: dict) -> list[dict]:
    found = []
    for claim in doc.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("removed"):
            continue
        if _claim_section(claim) == "party" or ".party." in str(claim.get("id") or ""):
            found.append(claim)
    return found


def _section_is_scaffold(body: str) -> bool:
    text = body or ""
    return "not started" in text.lower() and "[^" not in text


def party_record_errors(workspace) -> list[str]:
    """Every researched candidate states a cited party, including a nonpartisan race label."""
    errors = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    if not isinstance(ballot, dict):
        return errors
    contests = [contest for contest in ballot.get("contests") or [] if isinstance(contest, dict)]
    by_candidate: dict[str, dict] = {}
    for contest in contests:
        for candidate in contest.get("candidates") or []:
            if isinstance(candidate, dict) and not candidate.get("write_in"):
                item_id = str(candidate.get("item_id") or candidate.get("id") or "")
                if item_id:
                    by_candidate[item_id] = contest
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        item_type = str(doc.get("item_type") or "")
        contest = by_candidate.get(item.name)
        if item_type not in PERSON_ITEM_TYPES and contest is None:
            continue
        if item_type not in PERSON_ITEM_TYPES and (contest or {}).get("type") not in {
            "race",
            "primary",
            "local-office",
            "judicial-retention",
        }:
            continue
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        sections = section_map(draft_path.read_text(encoding="utf-8"))
        body = sections.get("party", "")
        if "party" not in sections:
            continue
        state = load_json(item / "loop-state.json") or {}
        signed = str(state.get("status") or "") in {"signed-off", "capped-disputed"}
        if _section_is_scaffold(body):
            if signed:
                errors.append(f"{item.name}: party is still the untouched scaffold on a signed-off item")
            continue
        profile = load_yaml(item / "profile.yaml") or {}
        party = profile.get("party") if isinstance(profile, dict) else None
        nonpartisan = bool(isinstance(party, dict) and party.get("race_nonpartisan")) or is_nonpartisan_contest(contest)
        if nonpartisan and NONPARTISAN_RACE not in body:
            errors.append(f"{item.name}: a nonpartisan race must say '{NONPARTISAN_RACE}' in the party section")
        if isinstance(party, dict):
            source_kind = str(party.get("source_kind") or "")
            if source_kind not in PARTY_SOURCE_KINDS:
                errors.append(f"{item.name}: party.source_kind must be ballot, elections office, filing, or voter registration")
            if party.get("race_nonpartisan") and source_kind not in {"ballot", "elections_office"}:
                errors.append(
                    f"{item.name}: the Nonpartisan race label is cited from the ballot or the elections office before a filing or registration"
                )
            display = str(party.get("display") or "")
            if nonpartisan and NONPARTISAN_RACE not in display:
                errors.append(f"{item.name}: party.display must include '{NONPARTISAN_RACE}'")
            registered = str(party.get("registered_party") or "").strip()
            if registered:
                if REGISTERED_PARTY_LABEL not in body or REGISTERED_PARTY_LABEL not in display:
                    errors.append(
                        f"{item.name}: a registered party on a nonpartisan race uses the label '{REGISTERED_PARTY_LABEL}'"
                    )
                if str(party.get("registered_source_kind") or "") not in PARTY_SOURCE_KINDS:
                    errors.append(f"{item.name}: registered party needs registered_source_kind")
            for change in party.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                when = str(change.get("date") or "")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
                    errors.append(f"{item.name}: a party change needs an ISO date")
                    continue
                if when not in body and when[:4] not in body:
                    errors.append(f"{item.name}: party change on {when} is not in the party section")
            if not (party.get("changes") or []) and "not found" not in body.lower() and "party change" not in body.lower():
                errors.append(
                    f"{item.name}: party changes in the last 10 years need a cited change or a not-found line"
                )
            if "[^" not in display and not _is_gap_text(body):
                errors.append(f"{item.name}: party.display needs the citation marker for the ballot label")
        claims = _party_claims(doc)
        if claims and not any(
            source.get("tier") == "T1"
            for claim in claims
            for source in (claim.get("sources") or [])
            if isinstance(source, dict)
        ):
            errors.append(f"{item.name}: party needs an official T1 source from the ballot, elections office, filing, or registration")
    return errors


def endorsement_record_errors(workspace) -> list[str]:
    """Endorsements name the endorser, type, date, and whether the words are the group's or the candidate's."""
    errors = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        draft_path = item / "draft.md"
        draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        sections = section_map(draft) if draft else {}
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("removed"):
                continue
            if _claim_section(claim) != "endorsements":
                continue
            record = claim.get("endorsement")
            if not isinstance(record, dict):
                errors.append(f"{item.name}: {claim.get('id')} is an endorsement without endorser, type, date, and source role")
                continue
            if str(record.get("endorser") or "").strip() and str(record.get("endorser")) not in str(claim.get("text") or ""):
                errors.append(f"{item.name}: {claim.get('id')} does not name the endorser in the claim text")
            when = str(record.get("date") or "")
            if when and when[:4] not in draft and when not in draft:
                errors.append(f"{item.name}: {claim.get('id')} endorsement date {when} is not in the draft")
        endorsements_body = sections.get("endorsements", "")
        if endorsements_body and _is_gap_text(endorsements_body):
            continue
        if doc.get("item_type") in PERSON_ITEM_TYPES and endorsements_body and not _section_is_scaffold(endorsements_body):
            if not any(
                isinstance(claim, dict) and _claim_section(claim) == "endorsements" and isinstance(claim.get("endorsement"), dict)
                for claim in doc.get("claims") or []
            ):
                errors.append(f"{item.name}: endorsements section has no structured endorsement record")
    return errors


def measure_side_errors(workspace) -> list[str]:
    """A measure lists the sponsor committee, both sides, and top funders, or an honest gap."""
    errors = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict) or doc.get("item_type") != "measure":
            continue
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        sections = section_map(draft_path.read_text(encoding="utf-8"))
        if _section_is_scaffold("\n".join(sections.values())):
            continue
        roles = set()
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("removed"):
                continue
            position = claim.get("ballot_position")
            if isinstance(position, dict) and position.get("role"):
                roles.add(str(position.get("role")))
        gaps = {
            "sponsor_committee": sections.get("official sponsor or committee", ""),
            "supporter": sections.get("organizations supporting", ""),
            "opponent": sections.get("organizations opposing", ""),
            "funder_for": sections.get("top funders", ""),
            "funder_against": sections.get("top funders", ""),
        }
        for role in MEASURE_SIDE_ROLES:
            if role in roles:
                continue
            body = gaps.get(role, "")
            if body and (_is_gap_text(body) or "not found" in body.lower()):
                continue
            errors.append(f"{item.name}: measure side '{role}' needs a cited organization or a not-found line")
    return errors


def legislation_depth_errors(workspace) -> list[str]:
    """A researched bill names sponsor party and district, or records the gap. It does not invent a model-bill origin."""
    errors = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict) or doc.get("item_type") != "legislation":
            continue
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        sections = section_map(draft_path.read_text(encoding="utf-8"))
        sponsors = sections.get("sponsors and cosponsors", "")
        if not sponsors or _section_is_scaffold(sponsors) or _is_gap_text(sponsors):
            continue
        if not re.search(r"\bdistrict\b", sponsors, re.IGNORECASE):
            errors.append(f"{item.name}: sponsors need a district or a not-found line")
        if not re.search(
            r"\b(?:democrat|republican|independent|libertarian|green|nonpartisan|no party affiliation|party)\b",
            sponsors,
            re.IGNORECASE,
        ):
            errors.append(f"{item.name}: sponsors need a party or a not-found line")
        model = sections.get("drafting and model legislation", "")
        if model and not _is_gap_text(model) and re.search(r"\b(?:ALEC|model bill)\b", model, re.IGNORECASE):
            if "[^" not in model:
                errors.append(f"{item.name}: a model-legislation origin needs a citation")
    return errors


def rendered_party_errors(workspace) -> list[str]:
    """The reader guide shows party and endorsements as text, with no party color class."""
    guide_path = workspace / "final" / "guide.md"
    if not guide_path.exists():
        return []
    text = guide_path.read_text(encoding="utf-8")
    errors = []
    if re.search(r"party-(?:democrat|republican)|color:\s*#(?:ff0000|0000ff|0000ee)\b", text, re.IGNORECASE):
        errors.append("final/guide.md: party is colored or classed by party")
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    contests = [contest for contest in (ballot.get("contests") or []) if isinstance(contest, dict)] if isinstance(ballot, dict) else []
    if any(is_nonpartisan_contest(contest) for contest in contests) and NONPARTISAN_RACE not in text:
        errors.append("final/guide.md: missing the Nonpartisan race label")
    if any(contest.get("type") in {"race", "primary", "local-office"} for contest in contests):
        if not re.search(r"^\|\s*Party\s*\|", text, re.MULTILINE):
            errors.append("final/guide.md: comparison tables are missing the Party row")
        if not re.search(r"^\|\s*Endorsements\s*\|", text, re.MULTILINE):
            errors.append("final/guide.md: comparison tables are missing the Endorsements row")
    if any(contest.get("type") == "legislation" for contest in contests):
        if "Related litigation" not in text and "related litigation" not in text.lower():
            errors.append("final/guide.md: legislation is missing related litigation")
    return errors


def _signed_item(item: Path) -> bool:
    state = load_json(item / "loop-state.json") or {}
    return str(state.get("status") or "") in {"signed-off", "capped-disputed"}


def _require_real_section(errors: list[str], item_name: str, sections: dict, name: str, signed: bool) -> str:
    """Return the section body. A signed-off item cannot leave the heading as a scaffold."""
    body = sections.get(name, "")
    if not signed:
        return body
    if name not in sections or _section_is_scaffold(body):
        errors.append(f"{item_name}: '{name}' needs a cited fact or a not-found line before sign-off")
        return ""
    return body


def depth_record_errors(workspace) -> list[str]:
    """Signed-off candidates and bills carry the depth fields, or an honest gap.

    Finance uses one as-of date and the same buckets. Attendance is a count plus
    the chamber median, not a rank. A fact-check that was never opened is not a
    clean bill of health. Ethics lines are final orders. Term limits name the
    eligible-through year. Bills cite a staff analysis or say it was not found.
    Legislator votes follow district labels and never a street address.
    """
    errors: list[str] = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    if not isinstance(ballot, dict):
        ballot = {}
    districts = [str(item).strip() for item in (ballot.get("districts") or []) if str(item).strip()]
    for district in districts:
        if looks_like_street_address(district):
            errors.append("ballot.yaml districts contain a street address. Store the district label only.")
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        signed = _signed_item(item)
        if not signed:
            continue
        sections = section_map(draft_path.read_text(encoding="utf-8"))
        item_type = str(doc.get("item_type") or "")
        if item_type in PERSON_ITEM_TYPES:
            errors.extend(_candidate_depth_errors(item.name, item, doc, sections, item_type))
        if item_type == "legislation":
            errors.extend(_legislation_depth_fields(item.name, doc, sections, districts))
    return errors


def _candidate_depth_errors(item_name: str, item: Path, doc: dict, sections: dict, item_type: str) -> list[str]:
    errors: list[str] = []
    funding = _require_real_section(errors, item_name, sections, "campaign funding", True)
    if funding and not _is_gap_text(funding):
        needed = (
            ("small donor", "small donors at or under 200 dollars"),
            ("large donor", "large donors"),
            ("in-district", "in-district share"),
            ("self-fund", "self-funding or loans"),
            ("pac", "PAC money"),
            ("party", "party committee money"),
        )
        lowered = funding.lower()
        for needle, label in needed:
            if needle == "self-fund":
                if "self-fund" not in lowered and "loan" not in lowered:
                    errors.append(f"{item_name}: campaign funding is missing {label}")
                continue
            if needle == "party":
                if "party committee" not in lowered and "party money" not in lowered:
                    errors.append(f"{item_name}: campaign funding is missing {label}")
                continue
            if needle not in lowered:
                errors.append(f"{item_name}: campaign funding is missing {label}")
    profile = load_yaml(item / "profile.yaml") or {}
    money = profile.get("money") if isinstance(profile, dict) else None
    if not isinstance(money, dict):
        errors.append(f"{item_name}: profile.yaml money needs the shared finance breakdown")
    else:
        for key in FINANCE_KEYS:
            if not str(money.get(key) or "").strip():
                errors.append(f"{item_name}: profile.yaml money.{key} is empty")
    outside = _require_real_section(errors, item_name, sections, "outside spending", True)
    if outside and not _is_gap_text(outside):
        if "independent expenditure" not in outside.lower() and "outside spending" not in outside.lower():
            errors.append(f"{item_name}: outside spending must name independent expenditures or a not-found line")
        if re.search(r"\baffiliated\b", outside, re.IGNORECASE) and "filing" not in outside.lower():
            errors.append(f"{item_name}: an affiliated committee has to come from a filing")
    attendance = _require_real_section(errors, item_name, sections, "attendance", True)
    if attendance and not _is_gap_text(attendance):
        if "median" not in attendance.lower():
            errors.append(f"{item_name}: attendance needs the chamber median beside the member's count")
        if re.search(r"\brank(?:ed|ing|s)?\b", attendance, re.IGNORECASE):
            errors.append(f"{item_name}: attendance does not rank members")
    disclosure = _require_real_section(errors, item_name, sections, "financial disclosure", True)
    if disclosure and not _is_gap_text(disclosure):
        if re.search(r"\b(?:conflict|unethical|corrupt|improper)\b", disclosure, re.IGNORECASE):
            errors.append(f"{item_name}: a disclosure overlap is stated without a verdict")
    _require_real_section(errors, item_name, sections, "fact checks", True)
    fact_body = sections.get("fact checks", "")
    if fact_body and not _section_is_scaffold(fact_body) and FACT_CHECK_CAVEAT not in fact_body.lower():
        errors.append(
            f"{item_name}: fact checks must say that never checked is not the same as checked out clean"
        )
    ethics = _require_real_section(errors, item_name, sections, "ethics and elections orders", True)
    if ethics and "final order" not in ethics.lower():
        errors.append(f"{item_name}: ethics and elections lines are final orders, or a not-found line that says so")
    limits = _require_real_section(errors, item_name, sections, "term limits", True)
    if limits and not _is_gap_text(limits) and not re.search(r"eligible through\s+\d{4}", limits, re.IGNORECASE):
        errors.append(f"{item_name}: term limits need an eligible-through year or a not-found line")
    if item_type == "judicial-retention":
        return errors
    promises = _require_real_section(errors, item_name, sections, "promises versus record", True)
    if promises and not _is_gap_text(promises):
        if "first platform item" not in promises.lower():
            errors.append(f"{item_name}: promises use the first platform item, the same rule for every candidate")
        found_status = False
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("removed"):
                continue
            if norm_heading(str(claim.get("section") or "")) != "promises versus record":
                continue
            status = str(claim.get("promise_status") or "")
            label = PROMISE_STATUS_LABELS.get(status, "")
            if not label:
                errors.append(f"{item_name}: {claim.get('id')} needs promise_status kept, partially, not, or no_record")
                continue
            found_status = True
            if label not in promises.lower():
                errors.append(f"{item_name}: {claim.get('id')} status '{label}' is not in the promises section")
        if not found_status:
            errors.append(f"{item_name}: promises versus record needs a promise_status claim or a not-found line")
    survey = _require_real_section(errors, item_name, sections, "questionnaire answers", True)
    if survey and not _is_gap_text(survey):
        lowered = survey.lower().replace(" ", "")
        for name in SURVEY_NAMES:
            if name not in lowered and name not in survey.lower():
                errors.append(f"{item_name}: questionnaire answers must cover {name}")
        if "did not respond" not in survey.lower() and "answered" not in survey.lower():
            errors.append(f"{item_name}: a missing survey answer is 'did not respond'")
        if re.search(r"sent a questionnaire|emailed the candidate|we asked them", survey, re.IGNORECASE):
            errors.append(f"{item_name}: do not send a questionnaire; use Vote411, Ballotpedia, and VoteSmart")
    elif survey and _is_gap_text(survey):
        blob = survey.lower().replace(" ", "")
        for name in SURVEY_NAMES:
            if name not in blob:
                errors.append(f"{item_name}: questionnaire gap must name {name}")
    return errors


def _legislation_depth_fields(item_name: str, doc: dict, sections: dict, districts: list[str]) -> list[str]:
    errors: list[str] = []
    for name in (
        "section-by-section changes",
        "effective date",
        "implementing agency",
        "party vote counts",
        "veto and override",
        "your legislators votes",
        "similar laws",
        "legal and constitutional challenges",
        "staff analysis",
    ):
        _require_real_section(errors, item_name, sections, name, True)
    staff_sources = False
    for claim in doc.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for source in claim.get("sources") or []:
            if not isinstance(source, dict):
                continue
            blob = f"{source.get('doc_type') or ''} {source.get('title') or ''}".lower()
            if "staff analysis" in blob:
                staff_sources = True
    staff_body = sections.get("staff analysis", "")
    if not staff_sources and not (_is_gap_text(staff_body) or "not found" in staff_body.lower()):
        errors.append(f"{item_name}: a bill needs a House or Senate staff analysis source, or a not-found line")
    changes = sections.get("section-by-section changes", "")
    if changes and not _is_gap_text(changes) and not _section_is_scaffold(changes):
        if "section" not in changes.lower():
            errors.append(f"{item_name}: section-by-section changes need the statute section or a not-found line")
    party_votes = sections.get("party vote counts", "")
    if party_votes and not _is_gap_text(party_votes) and not _section_is_scaffold(party_votes):
        if re.search(r"\b(?:in red|in blue|party color)\b", party_votes, re.IGNORECASE):
            errors.append(f"{item_name}: party vote counts are plain numbers, not colors")
        if not re.search(r"\b(?:yes|no)\b", party_votes, re.IGNORECASE):
            errors.append(f"{item_name}: party vote counts need the yes and no totals")
    votes = sections.get("your legislators votes", "")
    if votes and looks_like_street_address(votes):
        errors.append(f"{item_name}: legislator votes are looked up by district, not by street address")
    if votes and not _is_gap_text(votes) and not _section_is_scaffold(votes):
        if not districts:
            errors.append(f"{item_name}: legislator votes need district labels on the ballot, not an address")
        for district in districts:
            if district not in votes:
                errors.append(f"{item_name}: legislator votes are missing district '{district}'")
    similar = sections.get("similar laws", "")
    if similar and not _is_gap_text(similar) and not _section_is_scaffold(similar):
        lowered = similar.lower()
        if "ncsl" not in lowered and "oppaga" not in lowered:
            errors.append(f"{item_name}: similar laws cite NCSL or OPPAGA, or a not-found line")
        if len(re.findall(r"\[\^\d+\]", similar)) < 2:
            errors.append(f"{item_name}: a similar-law outcome needs two independent sources")
    legal = sections.get("legal and constitutional challenges", "")
    if legal and not _is_gap_text(legal) and re.search(r"\b(?:likely|probably)\b", legal, re.IGNORECASE):
        errors.append(f"{item_name}: legal challenges cite a filed case or opinion, not a prediction")
    return errors


def content_gate_errors(workspace, today: date, *, include_guide: bool = True) -> list[str]:
    errors: list[str] = []
    errors.extend(citation_errors(workspace, guide=include_guide))
    errors.extend(symmetry_errors(workspace))
    errors.extend(edge_errors(workspace))
    errors.extend(readability_errors(workspace))
    errors.extend(stale_errors(workspace, today))
    errors.extend(year_label_errors(workspace))
    errors.extend(offline_link_errors(workspace))
    errors.extend(number_quote_errors(workspace))
    errors.extend(quote_verbatim_errors(workspace))
    errors.extend(figure_source_errors(workspace))
    errors.extend(templated_prose_errors(workspace))
    errors.extend(heading_errors(workspace))
    errors.extend(party_record_errors(workspace))
    errors.extend(endorsement_record_errors(workspace))
    errors.extend(measure_side_errors(workspace))
    errors.extend(legislation_depth_errors(workspace))
    errors.extend(depth_record_errors(workspace))
    if include_guide:
        errors.extend(rendered_party_errors(workspace))
    return errors


def wayback_api_url(url: str) -> str:
    return "https://archive.org/wayback/available?url=" + quote(url, safe="")


def classify_link(status: int | None, has_archive: bool) -> str:
    if status is None:
        return "unchecked" if not has_archive else "unchecked-with-archive"
    if 200 <= status < 400:
        return "live"
    if has_archive:
        return "dead-with-archive"
    return "dead"


def flesch_kincaid_grade(text: str) -> float | None:
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return None
    sentences = _sentences(text) or [text]
    syllables = sum(_syllables(word) for word in words)
    words_per_sentence = len(words) / max(len(sentences), 1)
    syllables_per_word = syllables / len(words)
    return 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59


def _syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 0
    groups = re.findall(r"[aeiouy]+", cleaned)
    count = len(groups)
    if cleaned.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def summary_text(text: str) -> str:
    if "<!-- summary -->" not in text:
        return ""
    after = text.split("<!-- summary -->", 1)[1]
    lines = []
    for line in after.splitlines():
        if line.strip() == "" and lines:
            break
        if line.strip().startswith("#"):
            break
        if line.strip() and not line.strip().startswith("<!--"):
            lines.append(line)
    return MARKER_RE.sub("", " ".join(lines))


def readability_errors(workspace) -> list[str]:
    limit = float(load_config().get("summary_grade_level_max", 9))
    errors = []
    paths = [item / "draft.md" for item in iter_items(workspace)]
    guide = workspace / "final" / "guide.md"
    if guide.exists():
        paths.append(guide)
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "<!-- summary -->" not in text:
            continue
        grade = flesch_kincaid_grade(summary_text(text))
        if grade is not None and grade > limit:
            try:
                label = path.relative_to(workspace).as_posix()
            except ValueError:
                label = path.name
            errors.append(f"{label}: summary grade {grade:.1f} is above {limit:.0f}")
    return errors


def html_a11y_errors(html: str) -> list[str]:
    errors = []
    if not re.search(r"<html[^>]*\blang=", html, re.IGNORECASE):
        errors.append("HTML is missing a lang attribute")
    if not re.search(r"<h1[\s>]", html, re.IGNORECASE):
        errors.append("HTML is missing an h1")
    if "Not an official ballot" not in html:
        errors.append("HTML is missing the not-an-official-ballot banner")
    if "<main" not in html.lower():
        errors.append("HTML is missing a main element")
    if 'href="#content"' not in html and "href='#content'" not in html:
        errors.append("HTML is missing a skip link")
    for image in re.findall(r"<img\b[^>]*>", html, re.IGNORECASE):
        if not re.search(r"\balt=", image, re.IGNORECASE):
            errors.append(f"Image missing alt text: {image[:80]}")
    return errors


def blinded_swap(text: str, replacements: list[tuple[str, str]]) -> str:
    output = text
    for real, alias in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        if real:
            output = output.replace(real, alias)
    kept = []
    for line in output.splitlines():
        if re.search(r"requester (view|lean|preference|party|values)", line, re.IGNORECASE):
            continue
        kept.append(line)
    return "\n".join(kept).strip() + "\n"
