"""Reader and full editions of the guide.

The reader opens with the ballot, then one contest at a time, inside a word
budget. Comparison cells are short facts. Per-candidate prose stays in the full
edition. Works cited, quotes, search logs, and cell detail move to a sources
addendum. Markers in the body link to that addendum and back. A table row is
kept only when a cell carries a marker, or the row is replaced by one official
gap sentence.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from lib.docket_pages import bill_token, build_docket_contest, display_contest_title
from lib.party import endorsement_cell
from lib.quality import (
    HTML_COMMENT_RE,
    MARKER_RE,
    READER_CONTEST_WORD_BUDGET,
    claim_index,
    environment_rating_sentence,
    marker_numbers,
    plain_access_note,
    plain_reader_document,
    reader_visible_word_count,
    official_restatement_sentences,
    precinct_restatement,
    unmarked_logistics_lines,
    word_count,
    _is_navigation_sentence,
)
from lib.quality import _bind_trailing_markers, _gap_sentence, _heading, _is_gap_text
from lib.sentences import split_sentences
from lib.util import iter_items, load_json, load_yaml, slugify
from lib.workflow import format_work
from check_pdf_layout import MAX_CANDIDATES_PER_TABLE, MAX_LANDSCAPE_COLUMNS, MAX_PORTRAIT_COLUMNS

CELL_CHAR_CAP = 96
# Kept so older notes still point at the same caps the layout check enforces.
TRANSPOSE_CANDIDATES = MAX_CANDIDATES_PER_TABLE
LANDSCAPE_COLUMNS = MAX_LANDSCAPE_COLUMNS
FIELD_CHUNK = MAX_CANDIDATES_PER_TABLE

AUDIT_HEADINGS = {
    "sources and retrieval dates",
    "item changelog",
    "findings and disputes",
}
NONE_HEADINGS = {"write-in candidates", "withdrawn candidates"}
PROFILE_LINK_RE = re.compile(r"(?:\.\./|\bitems/)?([a-z0-9][a-z0-9-]*)/draft\.md")
BACK_LINK = "[Back to ballot](#your-ballot-at-a-glance)"
NOT_FOUND_CELL = "Not found"
CLAUSE = " (not found: see the search log)"
# "four-year term" is a term length, not a count of years in office.
_YEARS_IN_OFFICE_RE = re.compile(
    r"(?<![\w-])(?:\d+\s+years?\b(?!\s+term)|years?\s+in\s+(?:elected\s+)?office)\b",
    re.IGNORECASE,
)
_RECEIPTS_RE = re.compile(
    r"\breceipts\b|\bmonetary contributions\b|\bcontributions of\b",
    re.IGNORECASE,
)
_CASH_RE = re.compile(r"cash on hand", re.IGNORECASE)
_SELF_FUND_RE = re.compile(r"self-fund|self fund|loan", re.IGNORECASE)
_SMALL_DONOR_RE = re.compile(r"small donor|under \$200|\$200|\b200 dollars\b", re.IGNORECASE)
_LARGE_DONOR_RE = re.compile(r"large donor", re.IGNORECASE)
_DISTRICT_SHARE_RE = re.compile(r"in-district|in district", re.IGNORECASE)
_PAC_RE = re.compile(r"\bPAC\b|political action committee", re.IGNORECASE)
_PARTY_MONEY_RE = re.compile(r"party committee|party money", re.IGNORECASE)
_OUTSIDE_RE = re.compile(r"outside spending|independent expenditure", re.IGNORECASE)
_ATTENDANCE_RE = re.compile(
    r"\b\d+\s+of\s+\d+\b[\s\S]{0,160}?\bmedian\b|\bmedian\b[\s\S]{0,160}?\b\d+\s+of\s+\d+\b",
    re.IGNORECASE,
)
_ELIGIBLE_RE = re.compile(r"eligible through", re.IGNORECASE)
_PROMISE_RE = re.compile(r"status is", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"quarter|filed on|report date|as of", re.IGNORECASE)
_PARTY_RE = re.compile(r"incumbent|challenger|nonpartisan|party", re.IGNORECASE)
_PARTY_NAME = (
    r"No Party Affiliation|Working Families|Peace and Freedom|American Independent|"
    r"Republican|Democratic|Democrat|Libertarian|Green|Independent|Nonpartisan|"
    r"Constitution|Reform|Socialist|Forward|Whig|Conservative|NPA"
)
_PARTY_CHANGE_RE = re.compile(
    rf"party change|changed party|(?:from|to)\s+(?:the\s+)?(?:{_PARTY_NAME})(?:\s+Party)?\b",
    re.IGNORECASE,
)
_RHETORIC_LABEL_RE = re.compile(r"\b(?:MATCH|CONTRADICTION|NO RECORD)\b")
_TERM_LENGTH_RE = re.compile(r"\b(?:\d+-year\s+term|term\s+of\s+\d+)\b", re.IGNORECASE)
_SEATS_RE = re.compile(
    r"\b(?:number to elect|elects?\s+\d+|\d+\s+seats?\b|one seat|two seats)\b",
    re.IGNORECASE,
)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _yaml_quote(value: str) -> str:
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _display_date(value: str) -> str:
    """Long form of a stored ISO date. Any other string is returned unchanged."""
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (value or "").strip())
    if not match:
        return (value or "").strip()
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return value.strip()
    return f"{_MONTHS[month - 1]} {day}, {year}"


class _Row:
    """One comparison row. A patterned row takes the most specific unused sentence."""

    def __init__(
        self,
        label: str,
        section: str,
        pattern: re.Pattern | None = None,
        money_key: str | None = None,
        fallback_first: bool = False,
        omit_if_empty: bool = False,
        profile_path: tuple[str, ...] = (),
        keep_if_empty: bool = False,
    ):
        self.label = label
        self.section = section
        self.pattern = pattern
        self.money_key = money_key
        self.fallback_first = fallback_first
        self.omit_if_empty = omit_if_empty
        self.profile_path = profile_path
        self.keep_if_empty = keep_if_empty


_COMPARISON_GROUPS = [
    (
        "At a glance",
        [
            _Row("Party", "party", profile_path=("party", "display"), keep_if_empty=True),
            _Row("Party changes", "party", _PARTY_CHANGE_RE, profile_path=("party", "changes_display")),
            _Row("Current or most recent office", "prior offices and public service"),
            _Row("Years in elected office", "prior offices and public service", _YEARS_IN_OFFICE_RE),
        ],
    ),
    (
        "Money",
        [
            _Row("Receipts", "campaign funding", _RECEIPTS_RE, "receipts"),
            _Row("Cash on hand", "campaign funding", _CASH_RE, "cash_on_hand"),
            _Row("Self-funding or loans", "campaign funding", _SELF_FUND_RE, "self_funding"),
            _Row("Share from small donors", "campaign funding", _SMALL_DONOR_RE, "small_donors"),
            _Row("Large donors", "campaign funding", _LARGE_DONOR_RE, "large_donors"),
            _Row("In-district share", "campaign funding", _DISTRICT_SHARE_RE, "in_district"),
            _Row("PAC money", "campaign funding", _PAC_RE, "pac_money"),
            _Row("Party money", "campaign funding", _PARTY_MONEY_RE, "party_money"),
            _Row("Outside spending", "outside spending", _OUTSIDE_RE, "outside_spending"),
            _Row("Report date", "campaign funding", _REPORT_DATE_RE, "report_date"),
        ],
    ),
    (
        "Experience and background",
        [
            _Row("Prior offices", "prior offices and public service"),
            _Row("Occupation", "occupational history"),
            _Row("Education", "education"),
        ],
    ),
    (
        "Positions",
        [_Row("Positions in own words", "positions in own words")],
    ),
    (
        "Record",
        [
            _Row("Record", "record vs rhetoric"),
            _Row("Record vs. rhetoric", "record vs rhetoric", _RHETORIC_LABEL_RE, omit_if_empty=True),
            _Row("Endorsements", "endorsements"),
            _Row("Debates and forums", "debates and forums"),
            _Row("Legal issues", "legal issues"),
            _Row("Interest-group ratings", "interest-group ratings"),
        ],
    ),
    (
        "Service and record",
        [
            _Row("Attendance", "attendance", _ATTENDANCE_RE),
            _Row("Eligible through", "term limits", _ELIGIBLE_RE),
            _Row("Promises", "promises versus record", _PROMISE_RE),
            _Row("Questionnaire", "questionnaire answers"),
            _Row("Fact checks", "fact checks"),
            _Row("Disclosure", "financial disclosure"),
            _Row("Ethics orders", "ethics and elections orders"),
        ],
    ),
]
_MONEY_ROWS = [row for heading, rows in _COMPARISON_GROUPS if heading == "Money" for row in rows]

LEVEL_TITLES = {
    "federal": "Federal races",
    "state-executive": "State executive",
    "state-house": "State House",
    "county": "County",
    "judicial": "Judicial retentions",
    "amendment": "Amendments",
    "referendum": "Local referendums",
    "local": "Local offices",
    "other": "Other ballot items",
}
TYPE_TITLES = {
    "race": "Races",
    "primary": "Primaries",
    "local-office": "Local offices",
    "measure": "Measures",
    "judicial-retention": "Judicial retentions",
    "legislation": "Legislation",
}
GROUP_ORDER = [
    "Federal races",
    "State executive",
    "State House",
    "County",
    "Races",
    "Primaries",
    "Local offices",
    "Judicial retentions",
    "Amendments",
    "Measures",
    "Local referendums",
    "Legislation",
    "Other ballot items",
]
READER_PROFILE_ORDER = [
    "strongest case",
    "positions in own words",
    "record vs rhetoric",
    "legal issues",
    "identity",
    "prior offices and public service",
    "occupational history",
    "education",
    "campaign funding",
    "debates and forums",
    "endorsements",
    "interest-group ratings",
]
RACE_SKIP = AUDIT_HEADINGS | {
    "comparison",
    "candidate profiles",
    "competitiveness",
    "write-in candidates",
    "withdrawn candidates",
    "uncontested",
}


def build_editions(workspace: Path, today: str) -> tuple[str, str, str, str]:
    """Reader body, reader sources, full body, full sources."""
    model = _GuideModel(workspace, today)
    reader, reader_sources = model.render("reader")
    full, full_sources = model.render("full")
    return reader, reader_sources, full, full_sources


class _GuideModel:
    def __init__(self, workspace: Path, today: str) -> None:
        self.workspace = workspace
        self.today = today
        self.ballot = load_yaml(workspace / "ballot.yaml") or {}
        self.intake = load_yaml(workspace / "intake.yaml") or {}
        self.index = claim_index(workspace)
        self.titles = _titles(self.ballot, workspace)
        self.candidate_ids = _candidate_ids(self.ballot)
        self.search_log: list[tuple[str, str, str]] = []
        self._logged: set[tuple[str, str, str]] = set()
        self.details: list[tuple[str, str, str]] = []
        self.edition = "reader"
        self.addendum_name = "guide-sources.md"
        self.body_name = "guide.md"
        self.omitted_markers: set[int] = set()
        self.sources_only_markers: set[int] = set()
        self.bill_folds: dict[str, list[dict]] = {}
        self.folded_bill_ids: set[str] = set()

    def _jurisdiction_label(self) -> str:
        intake = self.intake if isinstance(self.intake, dict) else {}
        label = str(intake.get("jurisdiction_label") or "").strip()
        if label:
            return label
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        election = ballot.get("election") if isinstance(ballot.get("election"), dict) else {}
        jurisdiction = election.get("jurisdiction") if isinstance(election, dict) else {}
        if not isinstance(jurisdiction, dict):
            return ""
        parts = [str(jurisdiction.get(key) or "").strip() for key in ("city", "county", "state")]
        return ", ".join(part for part in parts if part)

    def _front_matter(self, title: str, edition: str, *, sources: bool) -> list[str]:
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        election = ballot.get("election") if isinstance(ballot.get("election"), dict) else {}
        fiction = bool(ballot.get("fiction"))
        title_name = str((election or {}).get("name") or ballot.get("election_id") or "Election")
        shown_date = _display_date(str((election or {}).get("date") or ""))
        lines = [
            "---",
            f"title: {_yaml_quote(title)}",
            f"version: {ballot.get('report_version') or 'v1.0'}",
            f"election_id: {ballot.get('election_id')}",
            f"build_date: {self.today}",
            f"edition: {edition}",
            f"fiction: {'true' if fiction else 'false'}",
            f"election_name: {_yaml_quote(title_name)}",
            f"election_date: {_yaml_quote(shown_date)}",
            f"jurisdiction: {_yaml_quote(self._jurisdiction_label())}",
            "sources_edition: true" if sources else "sources_edition: false",
            "---",
            "",
        ]
        return lines

    def render(self, edition: str) -> tuple[str, str]:
        self.search_log = []
        self._logged = set()
        self.details = []
        self.omitted_markers = set()
        self.sources_only_markers = set()
        self.edition = edition
        if edition == "full":
            self.addendum_name = "guide-full-sources.md"
            self.body_name = "guide-full.md"
        else:
            self.addendum_name = "guide-sources.md"
            self.body_name = "guide.md"
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        election = ballot.get("election") or {}
        fiction = bool(ballot.get("fiction"))
        title_name = election.get("name") or ballot.get("election_id") or "Election"
        title = f"Voter guide: {title_name}"
        if fiction:
            title = f"FICTIONAL voter guide: {title_name}"
        self.bill_folds, self.folded_bill_ids = self._pair_bills()
        parts = self._front_matter(title, edition, sources=False)
        parts.extend(self._contents())
        parts.extend(self._contests())
        if edition == "full":
            parts.extend(self._election_office())
        parts.extend(self._glossary())
        parts.extend(self._methodology(edition))
        parts.extend(self._disputed(edition))
        parts.extend(self._corrections())
        if edition == "full":
            parts.extend(self._changelog())
        body = "\n".join(parts).rstrip() + "\n"
        self.omitted_markers = set(getattr(self, "omitted_markers", set()))
        before_markers = marker_numbers(body)
        if edition == "reader":
            body = plain_reader_document(body)
        from lib.reader_substance import substance_document

        body = substance_document(body, self.index)
        self.sources_only_markers = set(self.omitted_markers)
        self.sources_only_markers |= before_markers - marker_numbers(body)
        self.sources_only_markers -= marker_numbers(body)
        used = marker_numbers(body) | self.sources_only_markers
        addendum = self._sources_addendum(used)
        body, addendum, mapping = _renumber_markers(
            body, addendum, extra=sorted(self.sources_only_markers)
        )
        body = _separate_adjacent_markers(body)
        body = _collapse_marker_runs(body)
        if edition == "full" and mapping:
            body = body.rstrip() + "\n\n" + "\n".join(self._marker_index_from_map(mapping)).rstrip() + "\n"
        linked = self._link_markers(body)
        text = re.sub(r"\n{3,}", "\n\n", linked).rstrip() + "\n"
        comment = _marker_map_comment(mapping)
        if comment:
            text += comment
        addendum_text = re.sub(r"\n{3,}", "\n\n", addendum).rstrip() + "\n"
        return text, addendum_text

    def _link_markers(self, text: str) -> str:
        """Link each marker to its global source, and restart the printed number per contest.

        Anchors and hrefs stay on the global id so the sources edition still
        matches. The number a reader sees starts again at 1 for each race or measure.
        """
        seen: set[str] = set()
        pattern = re.compile(r"\[\^(\d+)\](?:<!--fn-end:(\d+)-->)?")
        starts = [match.start() for match in re.finditer(r"\{#contest-", text)]
        back = re.search(r"\.back-matter", text)
        back_at = back.start() if back else len(text)
        local_of: dict[tuple[int, int], int] = {}
        counters: dict[int, int] = {}

        def section_index(pos: int) -> int:
            if pos >= back_at:
                return -1
            found = -1
            for index, start in enumerate(starts):
                if start <= pos:
                    found = index
                else:
                    break
            return found

        for match in pattern.finditer(text):
            section = section_index(match.start())
            if section < 0:
                continue
            start_n = int(match.group(1))
            end_n = int(match.group(2) or start_n)
            for value in range(start_n, end_n + 1):
                key = (section, value)
                if key in local_of:
                    continue
                counters[section] = counters.get(section, 0) + 1
                local_of[key] = counters[section]

        def repl(match: re.Match) -> str:
            number = match.group(1)
            end = match.group(2)
            start_n = int(number)
            end_n = int(end) if end else start_n
            section = section_index(match.start())

            def label_for(value: int) -> str:
                if section < 0:
                    return str(value)
                return str(local_of[(section, value)])

            anchors = []
            for value in range(start_n, end_n + 1):
                key = str(value)
                if key in seen:
                    continue
                seen.add(key)
                anchors.append(f'<a id="cite-{key}"></a>')
            label = label_for(start_n) if end_n == start_n else f"{label_for(start_n)}–{label_for(end_n)}"
            link = f"[<sup>{label}</sup>]({self.addendum_name}#source-{number})"
            return "".join(anchors) + link

        return pattern.sub(repl, text)

    def _show_cell(self, full: str, anchor: str, title: str, hint: str = "") -> str:
        """A complete short sentence, or an amount. Never an ellipsis or a detail link."""
        del anchor, title
        if not _cell_found(full):
            return NOT_FOUND_CELL
        return _short_fact(full, hint)

    def _show_prose(self, full: str) -> str:
        """A cited sentence in a card. Keep the marker on the sentence."""
        return self._rewrite(full or "").strip()

    def _detail_anchor(self, anchor: str, title: str, full: str) -> str:
        """One addendum heading per anchor. A second, different fact gets a new id."""
        for existing, _label, text in self.details:
            if existing == anchor and _sentence_key(text) == _sentence_key(full):
                return anchor
        if any(existing == anchor for existing, _label, _text in self.details):
            suffix = 2
            while any(existing == f"{anchor}-{suffix}" for existing, _label, _text in self.details):
                suffix += 1
            anchor = f"{anchor}-{suffix}"
        self.details.append((anchor, title, full))
        return anchor

    def _election_office(self) -> list[str]:
        logistics = self.workspace / "logistics.md"
        if logistics.exists():
            text = self._rewrite(logistics.read_text(encoding="utf-8")).strip()
            if text:
                return [text, ""]
        rows = []
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        for entry in ballot.get("logistics") or []:
            if not isinstance(entry, dict) or not entry.get("marker"):
                continue
            label = str(entry.get("label") or "Election office")
            url = str(entry.get("url") or "")
            marker = entry.get("marker")
            if url:
                rows.append(f"- {label}: {url}[^{marker}]")
        for line in unmarked_logistics_lines(ballot):
            rows.append(f"- {line}")
        if not rows:
            return [
                "# Official election office links",
                "",
                "Not found (searched: election office url on the confirmed ballot).",
                "",
            ]
        return ["# Official election office links", "", *rows, ""]

    def _precinct_line(self) -> list[str]:
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        precinct = str(ballot.get("precinct") or "").strip()
        cited = _sentence_mentioning(self.workspace, precinct) if precinct else None
        if precinct and cited:
            return [cited, ""]
        restatement = precinct_restatement(ballot)
        if restatement:
            return [restatement, ""]
        return ["Not found (searched: precinct code and district list on the confirmed ballot).", ""]

    def _at_a_glance(self) -> list[str]:
        """One scannable block per contest. No markers, no type words, no clipped sentences."""
        lines = [
            "# Your ballot at a glance {#your-ballot-at-a-glance .ballot-glance}",
            "",
        ]
        for contest in self._contests_raw():
            item_id = str(contest.get("item_id") or contest.get("id"))
            draft = self._draft(item_id)
            summary = _summary_paragraph(draft) or _first_cited(draft) or ""
            if "[^" not in summary:
                continue
            title = str(contest.get("title") or self.titles.get(item_id) or item_id)
            title, _subtitle = _title_pair(title)
            sentence = _one_sentence(summary)
            if not sentence:
                continue
            people = []
            if contest.get("type") in {"race", "primary", "local-office", "judicial-retention"}:
                for candidate in contest.get("candidates") or []:
                    if not isinstance(candidate, dict) or candidate.get("withdrawn"):
                        continue
                    name = str(candidate.get("name") or "").strip()
                    if not name:
                        continue
                    abbr = _party_abbr(self.workspace, candidate)
                    line = f"{name}, {abbr}" if abbr else name
                    if candidate.get("incumbent") is True:
                        line += " (incumbent)"
                    people.append(line)
            lines.append('<div class="glance-item">')
            lines.append("")
            href = f"#contest-{item_id}"
            lines.append(
                f'<h3 class="glance-contest"><a class="page-ref" href="{html.escape(href, quote=True)}">{html.escape(title)}</a></h3>'
            )
            lines.append("")
            if people:
                lines.append('<ul class="glance-people">')
                for person in people:
                    lines.append(f"<li>{html.escape(person)}</li>")
                lines.append("</ul>")
                lines.append("")
            lines.append(f'<p class="glance-summary">{html.escape(sentence)}</p>')
            lines.append("")
            lines.append("</div>")
            lines.append("")
        return lines

    def _how_to_read(self) -> list[str]:
        return [
            "# How to read this guide",
            "",
            "Start with the ballot at a glance, then read one contest at a time. "
            "Each race uses the same comparison rows for every candidate. "
            "Party is printed as text. This guide does not color a party. "
            "An endorsement names the group, its type, the date, and whether the words are the group's own statement or the candidate's site. "
            "Money rows use one as-of date for every candidate. Attendance includes the chamber median and does not rank members. "
            "A fact-check that was never checked is not a clean rating. "
            "A cell that says Not found was searched and not found. The places searched are in the sources addendum.",
            "",
            "A small number links to the sources addendum, where the works-cited line, the quote, and the search log live. "
            "Tier T1 is an official or primary source. T2 is an established nonpartisan reference. "
            "T3 is named journalism. T4 is an advocacy source and is quoted only as that group's view.",
            "",
            "One source means one record supports the sentence. "
            "An allegation stays labeled as an allegation, with the person's response or a not-found note. "
            "This guide does not rank candidates, score them, or recommend a vote. "
            "Claims marked disputed or unconfirmed are left out of summaries.",
            "",
        ]

    def _compare(self) -> list[str]:
        money = self._money_across()
        if money[:1] == ["::: landscape"]:
            # The landscape page break would otherwise leave this heading alone.
            lines = ["::: landscape", "", "# Compare across the ballot", ""]
            lines.extend(money[2:])
        else:
            lines = ["# Compare across the ballot", "", *money]
        lines.extend(self._issue_matrix())
        lines.extend(self._measures_across())
        lines.extend(self._judicial_across())
        lines.extend(self._incumbency_strip())
        lines.append(BACK_LINK)
        lines.append("")
        return lines

    def _money_across(self) -> list[str]:
        lines = [
            "## Money",
            "",
            "| Office | Candidate | Receipts | Cash on hand | Report date | Source tier |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        missing = []
        for contest in self._contests_raw():
            if contest.get("type") not in {"race", "primary", "local-office"}:
                continue
            office = str(contest.get("title") or "")
            for candidate in _people(contest):
                item_id = str(candidate.get("item_id") or candidate.get("id"))
                sections = _section_dict(self._draft(item_id))
                profile = load_yaml(self.workspace / "items" / item_id / "profile.yaml") or {}
                cells = _assign_cells(sections, profile if isinstance(profile, dict) else {}, _MONEY_ROWS)
                receipts = cells["Receipts"]
                cash = cells["Cash on hand"]
                report = cells["Report date"]
                if not _cell_found(receipts) and not _cell_found(cash):
                    missing.append(str(candidate.get("name") or item_id))
                    continue
                marker_source = next((cell for cell in (receipts, cash, report) if _cell_found(cell)), "")
                name = str(candidate.get("name") or item_id)
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(office),
                            _cell(name),
                            _cell(self._show_cell(receipts, f"detail-{item_id}-receipts", f"Receipts: {name}", "Receipts")),
                            _cell(self._show_cell(cash, f"detail-{item_id}-cash", f"Cash on hand: {name}", "Cash on hand")),
                            _cell(self._show_cell(report, f"detail-{item_id}-report-date", f"Report date: {name}", "Report date")),
                            _cell(_tier_cell(self.index, marker_source)),
                        ]
                    )
                    + " |"
                )
        lines.append("")
        if missing:
            lines.append(_gap_line("campaign receipts for " + ", ".join(missing)))
            lines.append("")
        if not any(line.startswith("| ") and _cell_has_marker(line) for line in lines):
            return [
                "## Money",
                "",
                _gap_line("campaign receipts and cash on hand"),
                "",
            ]
        return _with_landscape(lines, 6)

    def _issue_matrix(self) -> list[str]:
        lines = ["## Issues addressed in a candidate's own words", ""]
        races = [c for c in self._contests_raw() if c.get("type") in {"race", "primary", "local-office"}]
        issue_rows: dict[str, dict[str, str]] = {}
        offices: list[str] = []
        for contest in races:
            office = str(contest.get("title") or contest.get("id"))
            offices.append(office)
            found_for_issue: dict[str, list[str]] = {}
            for candidate in _people(contest):
                item_id = str(candidate.get("item_id") or candidate.get("id"))
                profile = load_yaml(self.workspace / "items" / item_id / "profile.yaml") or {}
                issues = profile.get("issues") if isinstance(profile, dict) else None
                if not isinstance(issues, dict):
                    continue
                sections = _section_dict(self._draft(item_id))
                assigned = _assign_cells(sections, profile if isinstance(profile, dict) else {}, [row for _heading, rows in _COMPARISON_GROUPS for row in rows])
                positions = assigned.get("Positions in own words", NOT_FOUND_CELL)
                for key, value in issues.items():
                    text = str(value or "").strip()
                    if not text or text.lower() in {"not found", "none"} or "[^" not in text:
                        found_for_issue.setdefault(str(key), [])
                        continue
                    if _sentence_key(text) == _sentence_key(positions):
                        continue
                    name = str(candidate.get("name") or item_id)
                    found_for_issue.setdefault(str(key), []).append(f"{name}: {_cell(self._show_cell(text, f'detail-{item_id}-{slugify(str(key))}', f'{key}: {name}', str(key)))}")
            for key, cells in found_for_issue.items():
                cited = [cell for cell in cells if "[^" in cell]
                if len(cited) < 2:
                    continue
                issue_rows.setdefault(key, {})[office] = " ".join(cited)
        if not issue_rows:
            lines.append(
                _gap_line("shared issue rows recorded for at least two candidates in profile.yaml")
            )
            lines.append("")
            return lines
        # One label column plus at most five offices, so a page never holds a
        # seven-column issue grid. Later offices repeat the issue label.
        for group in _chunks(offices, MAX_LANDSCAPE_COLUMNS - 1):
            header = ["Issue", *group]
            body = []
            for key in sorted(issue_rows):
                row = [key]
                for office in group:
                    row.append(issue_rows[key].get(office, NOT_FOUND_CELL))
                if not any("[^" in cell for cell in row[1:]):
                    continue
                body.append(row)
            if body:
                lines.extend(_emit_table(header, body))
        return lines

    def _measures_across(self) -> list[str]:
        measures = [c for c in self._contests_raw() if c.get("type") == "measure"]
        lines = ["## Measures side by side", ""]
        if not measures:
            lines.extend([_gap_line("measures on this ballot"), ""])
            return lines
        fields = [
            ("Type", "measure type and qualification"),
            ("Threshold", "vote threshold"),
            ("What a yes vote does", "what a yes vote does"),
            ("What a no vote does", "what a no vote does"),
            ("Fiscal impact", "fiscal impact"),
            ("Sunset or renewal", "sunset or renewal"),
            ("Funding by side", "funding by side"),
            ("Sponsor or committee", "official sponsor or committee"),
            ("Organizations supporting", "organizations supporting"),
            ("Organizations opposing", "organizations opposing"),
            ("Top funders", "top funders"),
        ]
        any_row = False
        for contest in measures:
            item_id = str(contest.get("item_id") or contest.get("id"))
            title = str(contest.get("title") or item_id)
            sections = _section_dict(self._draft(item_id))
            rows = []
            missing = []
            for header, key in fields:
                cell = _first_or_not_found(sections, key)
                if "[^" not in cell:
                    missing.append(header.lower())
                    continue
                rows.append(
                    [header, self._show_cell(cell, f"detail-{item_id}-{slugify(header)}", f"{header}: {item_id}", header)]
                )
            if not rows and not missing:
                continue
            any_row = True
            lines.extend([f"### {title}", ""])
            if rows:
                lines.extend(_emit_table(["Topic", "Fact"], rows))
            if missing:
                lines.extend([_gap_line(", ".join(missing)), ""])
        if not any_row:
            lines.extend([_gap_line("measures on this ballot"), ""])
        return lines

    def _judicial_across(self) -> list[str]:
        rows = [c for c in self._contests_raw() if c.get("type") == "judicial-retention" or c.get("level") == "judicial"]
        lines = ["## Judicial retentions side by side", ""]
        if not rows:
            lines.extend([_gap_line("judicial retention contests on this ballot"), ""])
            return lines
        columns = [
            ("Court", "court and term"),
            ("Appointed by", "appointing authority"),
            ("Prior retention", "prior retention"),
            ("Discipline", "discipline record"),
            ("Notable rulings", "notable rulings"),
            ("Performance evaluation", "performance evaluation"),
        ]
        built = []
        for contest in rows:
            item_id = str(contest.get("item_id") or contest.get("id"))
            sections = _section_dict(self._draft(item_id))
            built.append((str(contest.get("title") or item_id), [_first_or_not_found(sections, key) for _label, key in columns]))
        keep = []
        dropped = []
        for index, (label, _key) in enumerate(columns):
            if all(cells[index] == NOT_FOUND_CELL for _title, cells in built):
                dropped.append(label.lower())
            else:
                keep.append(index)
        # Repeat the judge column rather than adding a seventh field column.
        for chunk in _chunks(keep, MAX_LANDSCAPE_COLUMNS - 1):
            header = ["Judge", *[columns[index][0] for index in chunk]]
            body = []
            for title, cells in built:
                shown = [title]
                for index in chunk:
                    label = columns[index][0]
                    shown.append(
                        self._show_cell(cells[index], f"detail-{slugify(title)}-{slugify(label)}", f"{label}: {title}", label)
                    )
                if not any(_cell_has_marker(cell) or "[^" in cell for cell in shown):
                    continue
                body.append(shown)
            if body:
                lines.extend(_emit_table(header, body))
        if dropped:
            lines.append(_gap_line(", ".join(dropped) + " for every retention on this ballot"))
            lines.append("")
        return lines

    def _incumbency_strip(self) -> list[str]:
        lines = [
            "## Incumbency",
            "",
            "| Office | Incumbent | Candidates on the ballot |",
            "| --- | --- | --- |",
        ]
        any_row = False
        for contest in self._contests_raw():
            if contest.get("type") not in {"race", "primary", "local-office"}:
                continue
            item_id = str(contest.get("item_id") or contest.get("id"))
            draft = self._draft(item_id)
            people = _people(contest)
            incumbent = next((c for c in people if c.get("incumbent")), None)
            incumbent_cell = NOT_FOUND_CELL
            if incumbent:
                name = str(incumbent.get("name") or "")
                incumbent_cell = _matching_cited(draft, re.compile(re.escape(name), re.I)) or _matching_cited(
                    draft, re.compile(r"incumbent", re.I)
                ) or NOT_FOUND_CELL
            count_cell = _matching_cited(draft, re.compile(r"\btwo\b|\bthree\b|\bfour\b|\bcandidates\b|\brunning\b", re.I))
            if count_cell is None:
                count_cell = _first_cited(draft) or NOT_FOUND_CELL
            if "[^" not in incumbent_cell and "[^" not in count_cell:
                continue
            any_row = True
            office = str(contest.get("title") or item_id)
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(office),
                        _cell(self._show_cell(incumbent_cell, f"detail-{item_id}-incumbent", f"Incumbent: {office}", "Incumbent")),
                        _cell(self._show_cell(count_cell, f"detail-{item_id}-candidates", f"Candidates: {office}", "Candidates")),
                    ]
                )
                + " |"
            )
        lines.append("")
        if not any_row:
            return ["## Incumbency", "", _gap_line("incumbent marks on this ballot"), ""]
        return lines

    def _pair_bills(self) -> tuple[dict[str, list[dict]], set[str]]:
        """A bill that is the vehicle for a measure is not its own contest."""
        measures = []
        bills = []
        for contest in self._contests_raw():
            kind = str(contest.get("type") or "")
            if kind == "measure":
                measures.append(contest)
            elif kind == "legislation":
                bills.append(contest)
        folds: dict[str, list[dict]] = {}
        used: set[str] = set()
        for bill in bills:
            token = bill_token(str(bill.get("title") or ""))
            if not token:
                continue
            bill_id = str(bill.get("item_id") or bill.get("id") or "")
            for measure in measures:
                measure_id = str(measure.get("item_id") or measure.get("id") or "")
                draft = re.sub(r"\s+", "", self._draft(measure_id).lower())
                if token in draft:
                    folds.setdefault(measure_id, []).append(bill)
                    used.add(bill_id)
                    break
        return folds, used

    def _visible_contests(self) -> list[dict]:
        visible = []
        for contest in self._contests_raw():
            item_id = str(contest.get("item_id") or contest.get("id") or "")
            if item_id in self.folded_bill_ids:
                continue
            visible.append(contest)
        return visible

    def _contests(self) -> list[str]:
        lines: list[str] = []
        for contest in self._visible_contests():
            # The part name rides in the running header. It is not a heading of its own.
            lines.extend(self._docket_contest(contest, _group_name(contest)))
        return lines

    def _one_contest(self, contest: dict) -> list[str]:
        return self._docket_contest(contest, "")

    def _contents(self) -> list[str]:
        """Three columns: the contest, what it is, and the page it starts on."""
        lines = [
            '# What\'s on your ballot {#your-ballot-at-a-glance .ballot-glance}',
            "",
            '<table class="contents">',
            "<colgroup>",
            '<col class="contest">',
            '<col class="what">',
            '<col class="page">',
            "</colgroup>",
            "<thead>",
            '<tr><th scope="col">Contest</th><th scope="col">What it is</th>'
            '<th scope="col" class="page">Page</th></tr>',
            "</thead>",
            "<tbody>",
        ]
        for contest in self._visible_contests():
            item_id = str(contest.get("item_id") or contest.get("id"))
            title = str(contest.get("title") or self.titles.get(item_id) or item_id)
            short = display_contest_title(title)
            what = html.escape(self._contents_blurb(contest), quote=False)
            what = re.sub(r"\b(District)\s+(\d+)\b", r"\1&nbsp;\2", what)
            href = f"#contest-{item_id}"
            label = html.escape(short)
            label = re.sub(r"\b(District)\s+(\d+)\b", r"\1&nbsp;\2", label)
            lines.append(
                "<tr>"
                f'<th scope="row"><a href="{html.escape(href, quote=True)}">{label}</a></th>'
                f"<td>{what}</td>"
                f'<td class="page"><a class="page-ref" aria-label="page" href="{html.escape(href, quote=True)}"></a></td>'
                "</tr>"
            )
        lines.extend(["</tbody>", "</table>", ""])
        return lines

    def _contents_blurb(self, contest: dict) -> str:
        """One plain clause for the contents table. No markers and no process wording."""
        kind = str(contest.get("type") or "")
        title = str(contest.get("title") or "")
        if kind in {"race", "primary", "local-office"}:
            job = _office_job(title)
            count = _candidate_count_clause(contest)
            if job:
                return f"{job}."
            return "The office on this ballot."
        if kind == "judicial-retention" or contest.get("level") == "judicial":
            return _retention_blurb(title)
        effect = self._measure_effect(contest)
        if effect:
            return effect
        if kind == "legislation":
            return "A bill the legislature passed."
        return "A yes or no question."

    def _measure_effect(self, contest: dict) -> str:
        """What the measure would do, skipping a glossary definition of its name."""
        from lib.quality import plain_reader_sentence

        item_id = str(contest.get("item_id") or contest.get("id") or "")
        draft = self._draft(item_id)
        chunks = [_summary_paragraph(draft)]
        sections = _section_dict(draft)
        for name in ("plain-language summary", "plain summary", "what a yes vote does"):
            found = sections.get(name)
            if found:
                chunks.append(found[1])
        for chunk in chunks:
            for sentence in split_sentences(chunk or ""):
                cleaned = plain_reader_sentence(sentence)
                cleaned = re.sub(r"\s+", " ", MARKER_RE.sub("", cleaned)).strip()
                if not cleaned or cleaned == "No public record found.":
                    continue
                lowered = cleaned.lower()
                if any(token in lowered for token in ("sample ballot", "searched:", "single source", "not found")):
                    continue
                if _DEFINITION_BLURB_RE.search(cleaned):
                    continue
                if not _EFFECT_BLURB_RE.search(cleaned):
                    continue
                return cleaned
        return ""

    def _docket_contest(self, contest: dict, group: str) -> list[str]:
        return build_docket_contest(self, contest, group)

    def _contest_title_lines(self, contest: dict, title: str, item_id: str, sections) -> list[str]:
        """Sentence-case a long or all-caps title, and keep the official wording under it."""
        del contest, sections
        short, subtitle = _title_pair(title)
        lines = [f"## {short} {{#contest-{item_id} .contest-title}}", ""]
        if subtitle and subtitle != short:
            lines.extend([f'<p class="official-title">{html.escape(subtitle)}</p>', ""])
        return lines

    def _full_contest(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or self.titles.get(item_id) or item_id)
        draft = self._draft(item_id)
        sections = _section_pairs(draft)
        lines = self._contest_title_lines(contest, title, item_id, sections)
        lines.extend(self._contest_opener(contest))
        lines.extend(self._preamble(draft, item_id))
        kind = contest.get("type")
        if kind in {"race", "primary", "local-office"}:
            lines.extend(self._race_body(contest, sections))
            lines.extend(self._profiles(contest))
        elif kind == "measure":
            lines.extend(self._measure_body(item_id, title, sections))
        elif kind == "legislation":
            lines.extend(self._legislation_body(item_id, title, sections))
        else:
            lines.extend(self._generic_sections(item_id, title, sections, level=3))
        lines.extend([BACK_LINK, ""])
        return lines

    def _contest_opener(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        draft = self._draft(item_id)
        sections = _section_dict(draft)
        slots = _opener_slots(contest, sections, draft)
        lines = ["::: contest-open", ""]
        for label, sentence in slots:
            if sentence and "[^" in sentence:
                body = self._show_prose(sentence)
            else:
                body = _gap_line(label)
            lines.extend(["::: meta-item", "", f"#### {label}", "", body, "", ":::", ""])
        lines.extend([":::", ""])
        return lines

    def _candidate_index(self, contest: dict) -> list[str]:
        people = _people(contest)
        if not people:
            return []
        lines = ["::: candidate-index", ""]
        for candidate in people:
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            name = str(candidate.get("name") or self.titles.get(item_id) or item_id)
            lines.extend(self._nameplate(name, item_id, anchor=f"candidate-{item_id}"))
            lines.extend(self._access_note_lines(item_id))
        lines.extend([":::", ""])
        return lines

    def _nameplate(self, name: str, item_id: str, anchor: str) -> list[str]:
        party = _party_display(self.workspace, item_id) or _party_fallback(self.workspace, item_id)
        lines = [
            "::: nameplate",
            "",
            f"### {name} {{#{anchor} .candidate-name}}",
            "",
        ]
        if party:
            lines.extend([party, ""])
        else:
            lines.extend(
                [
                    "Not found (searched: ballot, elections office, candidate filing, and voter registration).",
                    "",
                ]
            )
        lines.extend([":::", ""])
        return lines

    def _reader_contest(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or self.titles.get(item_id) or item_id)
        draft = self._draft(item_id)
        sections = _section_pairs(draft)
        lines = self._contest_title_lines(contest, title, item_id, sections)
        for line in draft.splitlines():
            if line.startswith("## "):
                break
            if line.strip().startswith(">"):
                lines.append(line.rstrip())
        if lines[-1] != "":
            lines.append("")
        lines.extend(self._contest_opener(contest))
        if contest.get("type") in {"race", "primary", "local-office"}:
            lines.extend(self._candidate_index(contest))
        summary = _cap_summary(_summary_paragraph(draft))
        if summary:
            lines.extend(_boxed_summary(summary))
        lines.extend(
            [
                f"[Sources, quotes, and the search log]({self.addendum_name}#addendum-{item_id}).",
                "",
            ]
        )
        self._log_section_gaps(title, sections)
        kind = contest.get("type")
        if kind in {"race", "primary", "local-office"}:
            lines.extend(self._fixed_tables(contest))
            lines.extend(self._reader_profile_links(contest))
            self._log_profile_gaps(contest)
        elif kind == "measure":
            lines.extend(self._reader_measure(item_id, title, sections))
        elif kind == "legislation":
            lines.extend(self._reader_legislation(item_id, title, sections))
        else:
            lines.extend(self._reader_facts(item_id, title, sections))
        lines.extend([BACK_LINK, ""])
        return lines

    def _reader_profile_links(self, contest: dict) -> list[str]:
        lines = ["### Full edition", ""]
        any_link = False
        for candidate in _people(contest) + _other_people(contest):
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            if not item_id or not (self.workspace / "items" / item_id / "draft.md").exists():
                continue
            name = str(candidate.get("name") or self.titles.get(item_id) or item_id)
            lines.append(f"- [{name}](guide-full.md#profile-{item_id})")
            any_link = True
        if not any_link:
            return []
        lines.append("")
        return lines

    def _or_gap(self, sentence: str, anchor: str, title: str, hint: str) -> str:
        if sentence and "[^" in sentence:
            return self._show_prose(sentence)
        return _gap_line(hint)

    def _reader_measure(self, item_id: str, title: str, sections: list[tuple[str, str, str]]) -> list[str]:
        lines: list[str] = []
        rows = []
        by_name = {name: (raw, body) for raw, name, body in sections}
        shown_up_front = {
            "official title",
            "measure type and qualification",
            "vote threshold",
            "sunset or renewal",
            "plain-language summary",
            "what a yes vote does",
            "what a no vote does",
            "arguments for",
            "arguments against",
        }
        plain_body = by_name.get("plain-language summary", ("Plain-language summary", ""))[1]
        plain = _first_cited(plain_body) or ""
        lines.extend(
            [
                "::: summary-box",
                "",
                "#### In plain language",
                "",
                self._or_gap(plain, f"detail-{item_id}-plain-language", f"{title}: plain language", "plain-language summary"),
                "",
                ":::",
                "",
            ]
        )
        yes_body = by_name.get("what a yes vote does", ("What a yes vote does", ""))[1]
        no_body = by_name.get("what a no vote does", ("What a no vote does", ""))[1]
        lines.extend(
            _vote_pair(
                "A YES vote means",
                self._or_gap(_first_cited(yes_body) or "", f"detail-{item_id}-yes", f"{title}: yes", "what a yes vote does"),
                "A NO vote means",
                self._or_gap(_first_cited(no_body) or "", f"detail-{item_id}-no", f"{title}: no", "what a no vote does"),
            )
        )
        missing = []
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in shown_up_front:
                continue
            sentence = _first_cited(body)
            if not sentence:
                missing.append(body.strip() if _is_gap_text(body) and body.strip() else _gap_line(raw))
                continue
            rows.append((raw, self._show_cell(sentence, f"detail-{item_id}-{slugify(name)}", f"{title}: {raw}", raw)))
        if rows:
            lines.extend(_emit_table(["Topic", "Fact"], [[label, cell] for label, cell in rows]))
        for gap in missing:
            lines.extend([gap, ""])
        for_body = by_name.get("arguments for", ("Arguments for", ""))[1]
        against_body = by_name.get("arguments against", ("Arguments against", ""))[1]
        if for_body or against_body:
            for_text = _first_cited(for_body) or ""
            against_text = _first_cited(against_body) or ""
            lines.extend(
                _vote_pair(
                    "Arguments for",
                    self._or_gap(for_text, f"detail-{item_id}-arguments-for", f"{title}: arguments for", "arguments for"),
                    "Arguments against",
                    self._or_gap(against_text, f"detail-{item_id}-arguments-against", f"{title}: arguments against", "arguments against"),
                )
            )
        return lines

    def _reader_legislation(self, item_id: str, title: str, sections: list[tuple[str, str, str]]) -> list[str]:
        """Short bill table plus the two arguments side by side, in the speakers' cited words."""
        lines: list[str] = []
        by_name = {name: (raw, body) for raw, name, body in sections}
        summary = _first_cited(by_name.get("plain summary", ("Plain summary", ""))[1]) or ""
        lines.extend(
            [
                "::: summary-box",
                "",
                "#### In plain language",
                "",
                self._or_gap(summary, f"detail-{item_id}-plain-summary", f"{title}: plain summary", "plain summary"),
                "",
                ":::",
                "",
            ]
        )
        upfront = {"plain summary", "arguments for", "arguments against"}
        rows = []
        missing = []
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in upfront:
                continue
            sentence = _first_cited(body)
            if not sentence:
                missing.append(_named_gap(raw, body))
                continue
            rows.append((raw, self._show_cell(sentence, f"detail-{item_id}-{slugify(name)}", f"{title}: {raw}", raw)))
        if rows:
            lines.extend(_emit_table(["Topic", "Fact"], rows))
        for gap in missing:
            lines.extend([gap, ""])
        for_body = by_name.get("arguments for", ("Arguments for", ""))[1]
        against_body = by_name.get("arguments against", ("Arguments against", ""))[1]
        lines.extend(
            _vote_pair(
                "Supporters, in their words",
                self._or_gap(
                    _first_cited(for_body) or "",
                    f"detail-{item_id}-arguments-for",
                    f"{title}: arguments for",
                    "arguments for",
                ),
                "Opponents, in their words",
                self._or_gap(
                    _first_cited(against_body) or "",
                    f"detail-{item_id}-arguments-against",
                    f"{title}: arguments against",
                    "arguments against",
                ),
            )
        )
        return lines

    def _legislation_body(self, item_id: str, title: str, sections: list[tuple[str, str, str]]) -> list[str]:
        """Full bill text. Arguments sit side by side. A gap stays a gap."""
        lines: list[str] = []
        by_name = {name: (raw, body) for raw, name, body in sections}
        paired = {"arguments for", "arguments against"}
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in paired:
                rendered, gaps = prepare_section(self._rewrite(body))
                self._log_gaps(title, raw, gaps)
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                lines.extend([_gap_line(raw), ""])
                continue
            lines.extend([f"### {raw}", "", rendered, ""])
        for_body = by_name.get("arguments for", ("Arguments for", ""))[1]
        against_body = by_name.get("arguments against", ("Arguments against", ""))[1]
        for_rendered, _for_gaps = prepare_section(self._rewrite(for_body))
        against_rendered, _against_gaps = prepare_section(self._rewrite(against_body))
        lines.extend(
            _vote_pair(
                "Supporters, in their words",
                for_rendered or _gap_line("arguments for"),
                "Opponents, in their words",
                against_rendered or _gap_line("arguments against"),
            )
        )
        return lines

    def _reader_facts(self, item_id: str, title: str, sections: list[tuple[str, str, str]]) -> list[str]:
        rows = []
        collapsed = []
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS:
                continue
            sentence = _first_cited(body)
            if not sentence:
                rendered, _gaps = prepare_section(self._rewrite(body))
                if rendered is None:
                    collapsed.append(raw)
                continue
            rows.append((raw, self._show_cell(sentence, f"detail-{item_id}-{slugify(name)}", f"{title}: {raw}", raw)))
        lines: list[str] = []
        if rows:
            lines.extend(_emit_table(["", "Fact"], [[label, cell] for label, cell in rows]))
        if collapsed:
            lines.extend([_gap_line(", ".join(collapsed)), ""])
        return lines

    def _log_section_gaps(self, title: str, sections: list[tuple[str, str, str]]) -> None:
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS:
                continue
            _rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)

    def _log_profile_gaps(self, contest: dict) -> None:
        for candidate in _people(contest) + _other_people(contest):
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            if not item_id:
                continue
            name = str(candidate.get("name") or self.titles.get(item_id) or item_id)
            for raw, _norm, body in _section_pairs(self._draft(item_id)):
                _rendered, gaps = prepare_section(self._rewrite(body))
                self._log_gaps(name, raw, gaps)

    def _fit_contest_budget(self, lines: list[str]) -> list[str]:
        if reader_visible_word_count("\n".join(lines)) <= READER_CONTEST_WORD_BUDGET:
            return lines
        blocks: list[list[str]] = [[]]
        for line in lines:
            if line.strip() == "":
                if blocks[-1]:
                    blocks.append([])
                continue
            blocks[-1].append(line)
        blocks = [block for block in blocks if any(part.strip() for part in block)]

        def droppable(block: list[str]) -> bool:
            text = "\n".join(block).strip()
            if not text or text.startswith(("#", "|", ":", ">", "<", "Not found")):
                return False
            if _is_navigation_sentence(text, official_restatement_sentences(self.ballot if isinstance(self.ballot, dict) else None)):
                return False
            return reader_visible_word_count(text) > 40

        while reader_visible_word_count("\n".join(line for block in blocks for line in block)) > READER_CONTEST_WORD_BUDGET:
            index = next((i for i in range(len(blocks) - 1, -1, -1) if droppable(blocks[i])), None)
            if index is None:
                break
            del blocks[index]
        # Nameplates repeat the table headers. Experience and positions stay in
        # the full edition. Drop those reader blocks only when the contest is
        # still over the budget, and drop the same blocks for every candidate.
        if reader_visible_word_count("\n".join(line for block in blocks for line in block)) > READER_CONTEST_WORD_BUDGET:
            blocks = _drop_reader_overflow(blocks)
        out: list[str] = []
        for block in blocks:
            if out and out[-1] != "":
                out.append("")
            out.extend(block)
        if out and out[-1] != "":
            out.append("")
        return out

    def _preamble(self, draft: str, item_id: str) -> list[str]:
        lines: list[str] = []
        quotes: list[str] = []
        for line in draft.splitlines():
            if line.startswith("## "):
                break
            if line.startswith("# "):
                continue
            if line.strip().startswith(">"):
                quotes.append(line.rstrip())
        if quotes:
            lines.extend(quotes)
            lines.append("")
        summary = _summary_paragraph(draft)
        if summary:
            lines.extend(_boxed_summary(summary))
        return lines

    def _race_body(self, contest: dict, sections: list[tuple[str, str, str]]) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or item_id)
        lines: list[str] = []
        active = _people(contest)
        for raw, name, body in sections:
            if name in RACE_SKIP or name in AUDIT_HEADINGS:
                continue
            if name in NONE_HEADINGS and _is_placeholder_none(body):
                continue
            if name == "uncontested" and len(active) != 1:
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                lines.append(_gap_line(raw))
                lines.append("")
                continue
            lines.extend([f"### {raw}", "", rendered, ""])
        lines.extend(self._fixed_tables(contest))
        competitiveness = dict((name, body) for _raw, name, body in sections).get("competitiveness", "")
        rendered, gaps = prepare_section(self._rewrite(competitiveness))
        self._log_gaps(title, "Competitiveness", gaps)
        lines.append("### Competitiveness")
        lines.append("")
        if rendered is None:
            lines.append(_gap_line("competitiveness"))
        else:
            lines.append(rendered)
        lines.append("")
        for raw, name, body in sections:
            if name not in NONE_HEADINGS and name != "uncontested":
                continue
            if name in NONE_HEADINGS and _is_placeholder_none(body):
                continue
            if name == "uncontested" and len(active) != 1:
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                lines.extend([_gap_line(raw), ""])
            else:
                lines.extend([f"### {raw}", "", rendered, ""])
        return lines

    def _fixed_tables(self, contest: dict) -> list[str]:
        people = _people(contest)
        if len(people) < 1:
            return []
        bundles = []
        for candidate in people:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            sections = _section_dict(self._draft(item_id))
            profile = load_yaml(self.workspace / "items" / item_id / "profile.yaml") or {}
            bundles.append((candidate, sections, profile if isinstance(profile, dict) else {}))
        names = [str(candidate.get("name") or "") for candidate, _sections, _profile in bundles]
        all_rows = [row for _heading, rows in _COMPARISON_GROUPS for row in rows]
        assigned = [_assign_cells(sections, profile, all_rows) for _candidate, sections, profile in bundles]
        for cells_for, (candidate, _sections, _profile) in zip(assigned, bundles):
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            claims_doc = load_yaml(self.workspace / "items" / item_id / "claims.yaml") or {}
            claims = claims_doc.get("claims") if isinstance(claims_doc, dict) else []
            endorsements = endorsement_cell(claims if isinstance(claims, list) else [])
            if endorsements:
                cells_for["Endorsements"] = endorsements
        extra_issues = _shared_issue_keys(bundles)
        lines_out: list[str] = []
        for heading, specs in _COMPARISON_GROUPS:
            rows = []
            dropped = []
            for spec in specs:
                label = spec.label
                cells = [cells_for[label] for cells_for in assigned]
                if cells and all(cell == NOT_FOUND_CELL for cell in cells):
                    if spec.keep_if_empty:
                        rows.append((label, cells))
                        continue
                    if spec.omit_if_empty:
                        continue
                    dropped.append(label.lower())
                    continue
                rows.append((label, cells))
            if heading == "Positions":
                positions_cells = next((cells for label, cells in rows if label == "Positions in own words"), None)
                for key in extra_issues:
                    cells = []
                    cited = 0
                    for _candidate, _sections, profile in bundles:
                        text = str((profile.get("issues") or {}).get(key) or "").strip()
                        if text and "[^" in text and text.lower() not in {"not found", "none"}:
                            cells.append(text)
                            cited += 1
                        else:
                            cells.append(NOT_FOUND_CELL)
                    if cited < 2 or _duplicate_issue_row(cells, positions_cells):
                        continue
                    rows.append((key, cells))
            contest_id = str(contest.get("item_id") or contest.get("id"))
            shown_rows = []
            for label, cells in rows:
                short_cells = []
                for name, cell in zip(names, cells):
                    anchor = f"detail-{contest_id}-{slugify(label)}-{slugify(name)}"
                    short_cells.append(self._show_cell(cell, anchor, f"{label}: {name}", label))
                shown_rows.append((label, short_cells))
            # A group whose every cell is Not found is the same gap as an empty
            # section: one sentence, and no heading for a table that is not there.
            block: list[str] = []
            if shown_rows:
                block = [f"### {heading}", ""]
                for headers, body in comparison_tables(names, shown_rows):
                    block.extend(["::: comparison", ""])
                    block.extend(_emit_table(headers, body))
                    block.extend([":::", ""])
            if dropped:
                block.append(_gap_line(", ".join(dropped)))
                block.append("")
            if block:
                lines_out.extend(block)
        return lines_out

    def _profiles(self, contest: dict) -> list[str]:
        lines: list[str] = []
        ordered = _people(contest) + _other_people(contest)
        for candidate in ordered:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            if not item_id:
                continue
            draft_path = self.workspace / "items" / item_id / "draft.md"
            if not draft_path.exists():
                continue
            name = str(candidate.get("name") or self.titles.get(item_id) or item_id)
            draft = draft_path.read_text(encoding="utf-8")
            lines.extend(self._nameplate(name, item_id, anchor=f"profile-{item_id}"))
            lines.extend(self._access_note_lines(item_id))
            quotes = []
            for line in draft.splitlines():
                if line.startswith("## "):
                    break
                if line.startswith("#"):
                    continue
                if line.strip().startswith(">"):
                    quotes.append(line.rstrip())
            if quotes:
                lines.extend(quotes)
                lines.append("")
            sections = _section_pairs(draft)
            by_name = {norm: (raw, body) for raw, norm, body in sections}
            order = [name for name in READER_PROFILE_ORDER if name in by_name]
            order.extend(norm for norm in by_name if norm not in order and norm not in AUDIT_HEADINGS)
            collapsed: list[str] = []
            for norm in order:
                raw, body = by_name[norm]
                if norm in AUDIT_HEADINGS:
                    continue
                rendered, gaps = prepare_section(self._rewrite(body))
                self._log_gaps(name, raw, gaps)
                if rendered is None:
                    collapsed.append(raw)
                    continue
                lines.extend([f"#### {raw}", "", rendered, ""])
            if collapsed:
                lines.append(_gap_line(", ".join(collapsed)))
                lines.append("")
        return lines

    def _measure_body(self, item_id: str, title: str, sections: list[tuple[str, str, str]]) -> list[str]:
        lines: list[str] = []
        by_name = {name: (raw, body) for raw, name, body in sections}
        boxed = {
            "plain-language summary",
            "what a yes vote does",
            "what a no vote does",
            "arguments for",
            "arguments against",
        }
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in boxed:
                rendered, gaps = prepare_section(self._rewrite(body))
                self._log_gaps(title, raw, gaps)
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                lines.extend([_gap_line(raw), ""])
                continue
            lines.extend([f"### {raw}", "", rendered, ""])
        plain_body = by_name.get("plain-language summary", ("Plain-language summary", ""))[1]
        plain_rendered, _plain_gaps = prepare_section(self._rewrite(plain_body))
        lines.extend(
            [
                "::: summary-box",
                "",
                "#### In plain language",
                "",
                plain_rendered or _gap_line("plain-language summary"),
                "",
                ":::",
                "",
            ]
        )
        yes_body = by_name.get("what a yes vote does", ("What a yes vote does", ""))[1]
        no_body = by_name.get("what a no vote does", ("What a no vote does", ""))[1]
        yes_rendered, _yes_gaps = prepare_section(self._rewrite(yes_body))
        no_rendered, _no_gaps = prepare_section(self._rewrite(no_body))
        lines.extend(
            _vote_pair(
                "A YES vote means",
                yes_rendered or _gap_line("what a yes vote does"),
                "A NO vote means",
                no_rendered or _gap_line("what a no vote does"),
            )
        )
        for_body = by_name.get("arguments for", ("Arguments for", ""))[1]
        against_body = by_name.get("arguments against", ("Arguments against", ""))[1]
        if for_body or against_body:
            for_rendered, _for_gaps = prepare_section(self._rewrite(for_body))
            against_rendered, _against_gaps = prepare_section(self._rewrite(against_body))
            lines.extend(
                _vote_pair(
                    "Arguments for",
                    for_rendered or _gap_line("arguments for"),
                    "Arguments against",
                    against_rendered or _gap_line("arguments against"),
                )
            )
        return lines

    def _generic_sections(self, item_id: str, title: str, sections: list[tuple[str, str, str]], level: int) -> list[str]:
        lines: list[str] = []
        hashes = "#" * level
        collapsed = []
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS:
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                collapsed.append(raw)
                continue
            lines.extend([f"{hashes} {raw}", "", rendered, ""])
        if collapsed:
            lines.extend([_gap_line(", ".join(collapsed)), ""])
        return lines

    def _glossary(self) -> list[str]:
        lines = [
            "# Glossary {#glossary .back-matter}",
            "",
            "Levy",
            ": A levy is a tax or charge put on a ballot for voters to accept or reject.",
            "",
            "Nonpartisan race",
            ": A Nonpartisan race does not list a party on the ballot.",
            "",
            "Cash on hand",
            ": Cash on hand is the money a campaign reported still having at the end of a filing period.",
            "",
            "Allegation",
            ": An allegation is a claim someone has made that this guide has not confirmed.",
            "",
            "No public record found",
            ": No public record found means this guide did not locate a public record of that fact.",
            "",
        ]
        if self.edition == "reader":
            return lines
        lines.extend(
            [
                "Filing period",
                ": A filing period is the date range a finance report covers.",
                "",
                "Tier T1",
                ": Tier T1 is a primary or official source.",
                "",
                "Tier T2",
                ": Tier T2 is an established nonpartisan reference.",
                "",
                "Tier T3",
                ": Tier T3 is named journalism.",
                "",
                "Tier T4",
                ": Tier T4 is an advocacy source and is quoted only as that group's view.",
                "",
            ]
        )
        return lines

    def _methodology(self, edition: str) -> list[str]:
        """Plain words only. Review logs stay in the workspace, not in the guide."""
        if edition == "reader":
            return []
        when = self.today
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when or ""):
            when = _display_date(when)
        return [
            "# How we researched {#methodology .back-matter}",
            "",
            f"This guide was assembled on {when}.",
            "The facts come from official records, candidate filings, and named news reports.",
            "Where this guide did not find a public record, the page says so.",
            "The sources edition lists the citation for each fact.",
            "",
        ]

    def _candidate_item_ids(self) -> list[str]:
        seen: list[str] = []
        for contest in self._contests_raw():
            for candidate in contest.get("candidates") or []:
                if not isinstance(candidate, dict) or candidate.get("write_in"):
                    continue
                item_id = str(candidate.get("item_id") or candidate.get("id") or "")
                if item_id and item_id not in seen:
                    seen.append(item_id)
        return seen

    def _review_statuses(self, item_id: str) -> dict[str, str]:
        state = load_json(self.workspace / "items" / item_id / "loop-state.json") or {}
        signoffs = state.get("signoffs") if isinstance(state.get("signoffs"), dict) else {}
        gaps = [str(gap) for gap in (state.get("process_gaps") or [])]
        statuses = {}
        for reviewer in ("factcheck", "sourcing", "neutrality", "privacy-legal"):
            same = any(str(gap).lower().startswith(f"{reviewer} signed off") for gap in gaps)
            signed = bool((signoffs.get(reviewer) or {}).get("signed")) if isinstance(signoffs, dict) else False
            if same:
                statuses[reviewer] = "Same session"
            elif signed:
                statuses[reviewer] = "Separate"
            else:
                statuses[reviewer] = "Not signed"
        return statuses

    def _reader_reviews(self) -> list[str]:
        """One plain sentence, plus a status table. No process-log bullets."""
        rows = []
        separate = 0
        same_session = 0
        for item_id in self._candidate_item_ids():
            label = self.titles.get(item_id, item_id)
            statuses = self._review_statuses(item_id)
            if all(status == "Separate" for status in statuses.values()):
                separate += 1
            elif any(status == "Same session" for status in statuses.values()):
                same_session += 1
            rows.append((label, statuses))
        total = len(rows)
        if total == 0:
            return []
        if same_session and same_session == total - separate:
            sentence = (
                f"Reviews: {separate} of {total} candidate profiles were checked by a separate reviewer; "
                "the rest were checked in the same session, which is less independent."
            )
        elif same_session:
            sentence = (
                f"Reviews: {separate} of {total} candidate profiles were checked by a separate reviewer; "
                f"{same_session} were checked in the same session, which is less independent."
            )
        else:
            sentence = (
                f"Reviews: {separate} of {total} candidate profiles were checked by a separate reviewer."
            )
        lines = [
            sentence,
            "The review column is fact-check, sourcing, neutrality, and privacy, in that order.",
            "",
            "## Reviews",
            "",
            "| Candidate | Fact-check / sourcing / neutrality / privacy |",
            "| --- | --- |",
        ]
        for label, statuses in rows:
            joined = " / ".join(
                statuses[name] for name in ("factcheck", "sourcing", "neutrality", "privacy-legal")
            )
            lines.append(f"| {label} | {joined} |")
        lines.append("")
        return lines

    def _machine_label(self, owner: str) -> str:
        for item_id, title in self.titles.items():
            if owner in {item_id, title}:
                return item_id
        return owner

    def _grouped_known_gaps(self) -> list[str]:
        """Full-edition run record. Identical lines are kept once, under the candidate."""
        grouped: dict[str, list[str]] = {}
        order: list[str] = []

        def add(label: str, text: str) -> None:
            published = _published_known_gap(text)
            if not published:
                return
            if label not in grouped:
                order.append(label)
                grouped[label] = []
            if published not in grouped[label]:
                grouped[label].append(published)

        for item in iter_items(self.workspace):
            state = load_json(item / "loop-state.json") or {}
            for gap in list(state.get("gaps") or []) + list(state.get("process_gaps") or []):
                add(item.name, str(gap))
        for owner, _section, text in self.search_log:
            if plain_access_note(text):
                add(self._machine_label(owner), text)
        lines = ["", "## Known gaps", ""]
        if not order:
            lines.extend(["- None recorded in loop state.", ""])
            return lines
        for label in order:
            lines.extend([f"### {label}", ""])
            for gap in grouped[label]:
                lines.append(f"- {gap}")
            lines.append("")
        return lines

    def _access_notes(self, item_id: str) -> list[str]:
        notes: list[str] = []

        def take(text: str) -> None:
            note = plain_access_note(text)
            if note and note not in notes:
                notes.append(note)

        state = load_json(self.workspace / "items" / item_id / "loop-state.json") or {}
        for gap in list(state.get("gaps") or []) + list(state.get("process_gaps") or []):
            take(str(gap))
        draft = self._draft(item_id)
        for paragraph in re.split(r"\n\s*\n", draft):
            take(paragraph)
            for sentence in split_sentences(paragraph):
                take(sentence)
        return notes

    def _access_note_lines(self, item_id: str) -> list[str]:
        lines: list[str] = []
        for note in self._access_notes(item_id):
            lines.extend([note, ""])
        return lines

    def _disputed(self, edition: str) -> list[str]:
        lines = ["# Disputed claims {#disputed-claims .back-matter}", ""]
        any_row = False
        for item in iter_items(self.workspace):
            findings = load_yaml(item / "findings.yaml") or []
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict) or finding.get("status") != "disputed":
                    continue
                any_row = True
                claim_id = str(finding.get("claim_id") or "disputed claim")
                heading = claim_id if edition == "full" else self.titles.get(item.name, item.name)
                lines.extend(
                    [
                        f"## {heading}",
                        "",
                        f"Reviewer ({finding.get('reviewer')}, {finding.get('severity')}): {finding.get('issue')}",
                        "",
                    ]
                )
                response = finding.get("response") or {}
                if isinstance(response, dict) and response.get("rationale"):
                    lines.extend([f"Researcher position: {response.get('rationale')}", ""])
                if finding.get("coordinator_note"):
                    lines.extend([str(finding["coordinator_note"]), ""])
                lines.extend(["This disputed claim is not used in the summary.", ""])
        if not any_row:
            return []
        return lines

    def _corrections(self) -> list[str]:
        corrections = load_yaml(self.workspace / "corrections.yaml") or []
        if not corrections:
            return []
        lines = ["# Corrections {#corrections .back-matter}", ""]
        for entry in corrections:
            if not isinstance(entry, dict):
                continue
            lines.append(
                f"- {entry.get('version')} on {entry.get('date')}: {entry.get('claim_id')} — {entry.get('change')} Reason: {entry.get('reason')}"
            )
        lines.append("")
        return lines

    def _search_log(self) -> list[str]:
        lines = ["# Search log", ""]
        if not self.search_log:
            lines.extend(["No search paths were recorded.", ""])
            return lines
        current = None
        for owner, section, text in self.search_log:
            if owner != current:
                lines.extend([f"## {owner}", ""])
                current = owner
            lines.append(f"- {section}: {text}")
            lines.append("")
        return lines

    def _sources_addendum(self, used: set[int]) -> str:
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        election = ballot.get("election") or {}
        fiction = bool(ballot.get("fiction"))
        title_name = election.get("name") or ballot.get("election_id") or "Election"
        title = f"Sources: {title_name}"
        if fiction:
            title = f"FICTIONAL sources: {title_name}"
        parts = self._front_matter(title, f"{self.edition}-sources", sources=True)
        if fiction:
            parts.extend(
                [
                    "> **FICTIONAL EXAMPLE:** the places, people, measures, and documents in this guide are invented, "
                    "sources on fictional.example are placeholders and not real records, and this is not a voting guide.",
                    "",
                ]
            )
        parts.extend(
            [
                "> **Not an official ballot and not voting instructions:** confirm contests, deadlines, and polling places with the election office linked in the guide.",
                "",
                "# Works cited {#works-cited .back-matter .sources-title}",
                "",
                "Each marker in the guide links to an entry here. Each entry links back. "
                "Quotes are the archived words. The search log lists places that were checked.",
                "",
            ]
        )
        seen: set[int] = set()
        used_logs: set[int] = set()
        for contest in self._contests_raw():
            item_id = str(contest.get("item_id") or contest.get("id"))
            title_bit = str(contest.get("title") or item_id)
            item_ids = [item_id]
            owners = {title_bit}
            for candidate in contest.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                item_ids.append(str(candidate.get("item_id") or candidate.get("id")))
                if candidate.get("name"):
                    owners.add(str(candidate.get("name")))
            markers = []
            for number in sorted(used):
                if number in seen:
                    continue
                found = self.index.get(number)
                if not found or found[0] not in item_ids:
                    continue
                _item, claim, _source = found
                if claim.get("removed"):
                    continue
                markers.append(number)
            details = [row for row in self.details if row[0].startswith(f"detail-{item_id}-") or row[0].startswith(f"detail-{slugify(title_bit)}-")]
            logs = [(index, row) for index, row in enumerate(self.search_log) if row[0] in owners]
            if not markers and not details and not logs:
                continue
            parts.extend(
                [
                    f"## {title_bit} {{#addendum-{item_id} .source-group}}",
                    "",
                    f"[Back to {title_bit}]({self.body_name}#contest-{item_id})",
                    "",
                ]
            )
            for number in markers:
                seen.add(number)
                back = f"contest-{item_id}" if number in self.sources_only_markers else ""
                parts.extend(self._source_entry(number, back_anchor=back))
            if details:
                parts.extend(["### Cell detail", ""])
                for anchor, label, full in details:
                    parts.extend([f"#### {label} {{#{anchor}}}", "", full, ""])
            if logs:
                parts.extend(["### Search log", ""])
                for index, (owner, section, text) in logs:
                    used_logs.add(index)
                    parts.extend([f"- {owner} — {section}: {text}", ""])
        leftovers = [number for number in sorted(used) if number not in seen and number in self.index]
        if leftovers:
            parts.extend(["## Other sources {#addendum-other}", ""])
            for number in leftovers:
                _item, claim, _source = self.index[number]
                if claim.get("removed"):
                    continue
                seen.add(number)
                parts.extend(self._source_entry(number))
        remaining = [row for index, row in enumerate(self.search_log) if index not in used_logs]
        if remaining:
            parts.extend(["## Other search notes", ""])
            for owner, section, text in remaining:
                parts.extend([f"- {owner} — {section}: {text}", ""])
        return "\n".join(parts).rstrip() + "\n"

    def _source_entry(self, number: int, back_anchor: str = "") -> list[str]:
        _item, claim, source = self.index[number]
        lines = [
            f"### Source {number} {{#source-{number} .source-entry}}",
            "",
            format_work(number, source),
            "",
        ]
        quote = str(source.get("quote") or "").strip()
        if quote:
            lines.extend(["Quote:", "", f"> {quote}", ""])
        claim_text = str(claim.get("text") or "").strip()
        if claim_text:
            lines.extend([f"Claim {claim.get('id')}: {claim_text}", ""])
        target = back_anchor or f"cite-{number}"
        lines.extend([f"[Back to the guide]({self.body_name}#{target})", ""])
        return lines

    def _works_cited(self, used: set[int]) -> list[str]:
        lines = ["# Works cited", ""]
        seen: set[int] = set()
        for contest in self._contests_raw():
            item_ids = [str(contest.get("item_id") or contest.get("id"))]
            for candidate in contest.get("candidates") or []:
                if isinstance(candidate, dict):
                    item_ids.append(str(candidate.get("item_id") or candidate.get("id")))
            markers = []
            for number in sorted(used):
                if number in seen:
                    continue
                found = self.index.get(number)
                if not found or found[0] not in item_ids:
                    continue
                _item, claim, _source = found
                if claim.get("removed"):
                    continue
                markers.append(number)
            if not markers:
                continue
            lines.extend([f"## {contest.get('title') or item_ids[0]}", ""])
            for number in markers:
                seen.add(number)
                _item, _claim, source = self.index[number]
                lines.extend([format_work(number, source), ""])
        leftovers = [number for number in sorted(used) if number not in seen and number in self.index]
        if leftovers:
            lines.extend(["## Other sources", ""])
            for number in leftovers:
                _item, claim, source = self.index[number]
                if claim.get("removed"):
                    continue
                lines.extend([format_work(number, source), ""])
        return lines

    def _marker_index_from_map(self, mapping: dict[int, int]) -> list[str]:
        """Display numbers, in edition order, mapped back to the claim file id."""
        lines = ["# Marker index {#marker-index}", "", "| Marker | Claim ID |", "| --- | --- |"]
        for display, original in sorted(mapping.items()):
            found = self.index.get(original)
            if not found:
                continue
            _item, claim, _source = found
            if claim.get("removed"):
                continue
            lines.append(f"| {display} | {claim.get('id')} |")
        lines.append("")
        return lines

    def _changelog(self) -> list[str]:
        lines = ["# Changelog {#changelog}", ""]
        for item in iter_items(self.workspace):
            path = item / "CHANGELOG.md"
            if not path.exists():
                continue
            lines.extend([f"## {item.name}", ""])
            body = path.read_text(encoding="utf-8").strip()
            body = re.sub(r"^# Changelog\s*", "", body).strip()
            lines.extend([body, ""])
        return lines

    def _draft(self, item_id: str) -> str:
        path = self.workspace / "items" / item_id / "draft.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _rewrite(self, text: str) -> str:
        def repl(match: re.Match) -> str:
            item_id = match.group(1)
            title = self.titles.get(item_id, item_id)
            anchor = f"profile-{item_id}" if item_id in self.candidate_ids else f"contest-{item_id}"
            return f"[{title}](#{anchor})"

        return PROFILE_LINK_RE.sub(repl, text or "")

    def _contests_raw(self) -> list[dict]:
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        return [contest for contest in ballot.get("contests") or [] if isinstance(contest, dict)]

    def _log_gaps(self, owner: str, section: str, gaps: list[str]) -> None:
        for gap in gaps:
            cleaned = re.sub(r"\s+", " ", gap).strip()
            if not cleaned:
                continue
            if self.edition == "reader":
                note = plain_access_note(cleaned)
                if note:
                    cleaned = note
            key = (owner, section, cleaned)
            if key in self._logged:
                continue
            self._logged.add(key)
            self.search_log.append(key)


def _split_access(paragraph: str) -> tuple[str, list[str]]:
    """Drop portal-failure sentences from reader text and return their raw wording."""
    raw_hits: list[str] = []
    kept: list[str] = []
    sentences = split_sentences(paragraph)
    if not sentences:
        note = plain_access_note(paragraph)
        if note:
            return "", [re.sub(r"\s+", " ", paragraph).strip()]
        return paragraph, []
    for sentence in sentences:
        if plain_access_note(sentence):
            raw_hits.append(re.sub(r"\s+", " ", sentence).strip())
        else:
            kept.append(sentence.strip())
    return " ".join(kept).strip(), raw_hits


def prepare_section(body: str) -> tuple[str | None, list[str]]:
    """Return reader text and the gap sentences moved to the search log.

    A section that is only a gap returns no reader text. A section with both
    cited sentences and a gap keeps the cited sentences and folds a short clause
    onto the last one.
    """
    text = (body or "").strip()
    if not text or text in {"See `CHANGELOG.md`.", "See `findings.yaml`.", "See `claims.yaml`."}:
        return None, []
    if _is_gap_text(text) and "[^" not in text:
        return None, [text]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    kept: list[str] = []
    gaps: list[str] = []
    for paragraph in paragraphs:
        visible, access = _split_access(paragraph)
        gaps.extend(access)
        if not visible:
            continue
        if _is_gap_text(visible) and "[^" not in visible:
            gaps.append(visible)
            continue
        kept.append(visible)
    if not kept:
        return None, gaps
    if gaps:
        kept[-1] = _attach_clause(kept[-1])
    return "\n\n".join(kept), gaps


def _attach_clause(paragraph: str) -> str:
    stripped = paragraph.rstrip()
    if stripped.endswith("."):
        return stripped[:-1] + CLAUSE + "."
    return stripped + CLAUSE + "."


def _named_gap(raw: str, body: str) -> str:
    """A missing bill section keeps its name so the reader can see which topic was empty."""
    text = (body or "").strip()
    if _is_gap_text(text) and raw.lower() in text.lower():
        return text
    if _is_gap_text(text):
        match = re.search(r"(?is)not found \(searched:\s*(.+)\)\s*\.?\s*$", text)
        if match:
            return _gap_line(f"{raw}, {match.group(1)}")
    return _gap_line(raw)


_OVERFLOW_READER_HEADINGS = {"Experience and background", "Positions"}


def _drop_reader_overflow(blocks: list[list[str]]) -> list[list[str]]:
    """Shorten one reader contest that is still over the word budget.

    The candidate index repeats names that are already the table headers.
    Experience and positions remain in the full edition. The same headings
    are removed for every candidate in the contest.
    """
    lines: list[str] = []
    for block in blocks:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(block)
    kept: list[str] = []
    depth = 0
    skip = False
    for line in lines:
        stripped = line.strip()
        if depth == 0 and stripped == "::: candidate-index":
            depth = 1
            continue
        if depth:
            if stripped.startswith(":::") and stripped != ":::":
                depth += 1
            elif stripped == ":::":
                depth -= 1
            continue
        if line.startswith("### "):
            title = re.sub(r"\s*\{#.*$", "", line[4:]).strip()
            skip = title in _OVERFLOW_READER_HEADINGS
            if skip:
                continue
        if skip:
            continue
        kept.append(line)
    blocks_out: list[list[str]] = [[]]
    for line in kept:
        if line.strip() == "":
            if blocks_out[-1]:
                blocks_out.append([])
            continue
        blocks_out[-1].append(line)
    return [block for block in blocks_out if any(part.strip() for part in block)]


def _gap_line(subject: str) -> str:
    inner = re.sub(r"\s+", " ", subject).strip().strip(".")
    inner = inner.replace(";", ",").replace(":", ",")
    # "J." and "Dr." are initials, not a second sentence inside the gap.
    inner = re.sub(r"\.(?=\s)", "", inner)
    return f"Not found (searched: {inner})."


def _published_known_gap(gap: str) -> str:
    """Drop free-text finding issues from the run record.

    The loop keeps the issue. The guide line is the closed removal sentence,
    so an allegation in the issue is not an uncited run-record bullet.
    """
    text = re.sub(r"\s+", " ", str(gap or "")).strip()
    removed = re.fullmatch(r"Removed ([A-Za-z0-9_.-]+): .+", text)
    if removed:
        return f"Removed {removed.group(1)} at the round cap."
    from lib.quality import _is_known_gap_sentence

    def allowed(part: str) -> bool:
        return _is_known_gap_sentence(part) or _is_gap_text(part)

    if allowed(text) or (split_sentences(text) and all(allowed(part) for part in split_sentences(text))):
        return text
    note = plain_access_note(text)
    if note:
        return note
    # A free-text research note is not a citation. Keep it in loop state only.
    return ""


def _cell_has_marker(text: str) -> bool:
    return "[^" in (text or "") or "#source-" in (text or "")


def _boxed_summary(summary: str) -> list[str]:
    return ["::: summary-box", "", "<!-- summary -->", summary, "", ":::", ""]


def _vote_pair(left_label: str, left_body: str, right_label: str, right_body: str) -> list[str]:
    return [
        "::: vote-pair",
        "",
        "::: vote-box",
        "",
        f"#### {left_label}",
        "",
        left_body,
        "",
        ":::",
        "",
        "::: vote-box",
        "",
        f"#### {right_label}",
        "",
        right_body,
        "",
        ":::",
        "",
        ":::",
        "",
    ]


def _opener_slots(contest: dict, sections: dict, draft: str) -> list[tuple[str, str]]:
    kind = str(contest.get("type") or "")

    def sentence(name: str) -> str:
        found = sections.get(name)
        if not found:
            return ""
        return _first_cited(found[1]) or ""

    if kind == "measure":
        return [
            ("Measure", sentence("official title")),
            ("Type", sentence("measure type and qualification")),
            ("Threshold", sentence("vote threshold")),
            ("Sunset", sentence("sunset or renewal")),
        ]
    office = sentence("contest") or sentence("court and term") or sentence("what the office controls")
    duties = sentence("what the office controls")
    if duties and office and _sentence_key(duties) == _sentence_key(office):
        duties = ""
    term = _matching_cited(draft, _TERM_LENGTH_RE) or ""
    if term and office and _sentence_key(term) == _sentence_key(office):
        term = ""
    seats = _matching_cited(draft, _SEATS_RE) or ""
    return [
        ("Office", office),
        ("What it does", duties),
        ("Term", term),
        ("Number to elect", seats),
    ]


def _with_landscape(lines: list[str], columns: int) -> list[str]:
    """Five or six columns use a landscape page. Their heading stays on that page."""
    if columns <= MAX_PORTRAIT_COLUMNS:
        return lines
    out: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].startswith("|"):
            heading: list[str] = []
            while out and out[-1].strip() == "":
                heading.insert(0, out.pop())
            if out and out[-1].lstrip().startswith("#"):
                heading.insert(0, out.pop())
            out.extend(["::: landscape", ""])
            out.extend(heading)
            while index < len(lines) and (lines[index].startswith("|") or lines[index].strip() == ""):
                if lines[index].strip() == "" and index + 1 < len(lines) and not lines[index + 1].startswith("|"):
                    break
                out.append(lines[index])
                index += 1
            if out and out[-1] != "":
                out.append("")
            out.extend([":::", ""])
            continue
        out.append(lines[index])
        index += 1
    return out


def _chunks(items: list, size: int) -> list[list]:
    """Split a list into groups of `size`. An empty list stays empty."""
    width = max(int(size), 1)
    if not items:
        return []
    return [list(items[start : start + width]) for start in range(0, len(items), width)]


def comparison_tables(names: list[str], labeled_rows: list[tuple[str, list[str]]]) -> list[tuple[list[str], list[list[str]]]]:
    """Same rows for every candidate. At most three candidates share a table.

    Further candidates continue, in ballot order, on the next table. The row
    labels are repeated. Candidates are not sorted and are not turned into rows.
    """
    if not labeled_rows or not names:
        return []
    tables = []
    width = MAX_CANDIDATES_PER_TABLE
    for start in range(0, len(names), width):
        group = list(names[start : start + width])
        headers = ["Topic", *group]
        body = []
        for label, cells in labeled_rows:
            sliced = list(cells[start : start + width])
            if len(sliced) < len(group):
                sliced.extend([NOT_FOUND_CELL] * (len(group) - len(sliced)))
            body.append([label, *sliced])
        tables.append((headers, body))
    return tables


def _emit_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    lines = ["| " + " | ".join(" " if not str(header).strip() else _cell(header) for header in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    width = len(headers)
    for row in rows:
        padded = list(row) + [""] * (width - len(row))
        lines.append("| " + " | ".join(_cell(cell) for cell in padded[:width]) + " |")
    lines.append("")
    return _with_landscape(lines, width)


def _duplicate_issue_row(cells: list[str], positions: list[str] | None) -> bool:
    if not positions or len(cells) != len(positions):
        return False
    cited = [(left, right) for left, right in zip(cells, positions) if left != NOT_FOUND_CELL]
    if not cited:
        return False
    return all(_sentence_key(left) == _sentence_key(right) for left, right in cited)


def _cap_summary(summary: str, sentences: int = 2, words: int = 60) -> str:
    text = (summary or "").strip()
    if not text:
        return ""
    kept = []
    for sentence in split_sentences(_bind_trailing_markers(text)):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        kept.append(cleaned)
        if len(kept) >= sentences or word_count(" ".join(kept)) >= words:
            break
    return " ".join(kept)


def _is_money_hint(hint: str) -> bool:
    lowered = (hint or "").lower()
    keys = (
        "receipt",
        "cash",
        "self-fund",
        "self fund",
        "small donor",
        "large donor",
        "in-district",
        "in district",
        "pac money",
        "party money",
        "outside spending",
    )
    return any(key in lowered for key in keys)


_DOLLAR_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)|(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s+dollars\b",
    re.IGNORECASE,
)


def _format_dollars(plain: str) -> str | None:
    """The amount only. Cents drop once the sum reaches 100. Missing amounts stay missing."""
    text = (plain or "").strip()
    bare = re.fullmatch(r"\$?\s*([\d,]+(?:\.\d+)?)", text)
    match = None if bare else _DOLLAR_RE.search(text)
    if bare:
        raw = bare.group(1).replace(",", "")
    elif match:
        raw = (match.group(1) or match.group(2)).replace(",", "")
    else:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if abs(value) >= 100:
        return f"${int(value):,}"
    if value.is_integer():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _short_fact(sentence: str, hint: str = "") -> str:
    """A complete sentence or an amount, with the citation markers kept on the end.

    Money cells are the amount only. A money sentence with no amount is Not found.
    Nothing is cut off with an ellipsis.
    """
    if not sentence or sentence == NOT_FOUND_CELL:
        return NOT_FOUND_CELL
    markers = "".join(f"[^{number}]" for number in MARKER_RE.findall(sentence))
    plain = re.sub(r"\s+", " ", MARKER_RE.sub("", sentence)).strip()
    if _is_money_hint(hint):
        amount = _format_dollars(plain)
        if not amount:
            return NOT_FOUND_CELL
        return f'<span class="num">{amount}{markers}</span>'
    bare = plain.rstrip(".")
    excerpt = _excerpt_for_hint(bare, hint)
    if not excerpt:
        return NOT_FOUND_CELL
    if excerpt != bare or "report" in (hint or "").lower():
        body = excerpt
    elif plain[-1:] in ".!?":
        body = plain
    else:
        body = f"{plain}."
    return f"{body}{markers}"


def _renumber_markers(
    body: str, addendum: str, extra: list[int] | None = None
) -> tuple[str, str, dict[int, int]]:
    """Replace claim-file marker ids with 1, 2, 3… in the order the body first uses them.

    The returned map is display number to original number. Tokens are swapped in
    one pass so marker 10 is never rewritten as marker 1.
    """
    order: list[int] = []
    seen: set[int] = set()
    for match in MARKER_RE.finditer(body):
        number = int(match.group(1))
        if number not in seen:
            seen.add(number)
            order.append(number)
    for number in extra or []:
        if number not in seen:
            seen.add(number)
            order.append(number)
    if not order:
        return body, addendum, {}
    original_to_display = {original: index for index, original in enumerate(order, start=1)}

    def protect(text: str) -> str:
        def marker_repl(match: re.Match) -> str:
            number = int(match.group(1))
            if number not in original_to_display:
                return match.group(0)
            return f"[^@@M{number}@@]"

        text = MARKER_RE.sub(marker_repl, text)
        for original in order:
            token = f"@@M{original}@@"
            text = re.sub(rf"#source-{original}(?!\d)", f"#source-{token}", text)
            text = re.sub(rf"#cite-{original}(?!\d)", f"#cite-{token}", text)
            text = re.sub(rf"(### Source ){original}(?!\d)", rf"\g<1>{token}", text)
            text = re.sub(rf"(?m)^\[{original}\] ", f"[{token}] ", text)

        def finish(match: re.Match) -> str:
            return str(original_to_display[int(match.group(1))])

        return re.sub(r"@@M(\d+)@@", finish, text)

    display_to_original = {display: original for original, display in original_to_display.items()}
    return protect(body), protect(addendum), display_to_original


def _collapse_marker_runs(text: str) -> str:
    """Turn [^12], [^13], [^14] into one marker that displays as 12–14."""
    pattern = re.compile(r"\[\^\d+\](?:\s*,\s*\[\^\d+\])+")

    def repl(match: re.Match) -> str:
        numbers = [int(value) for value in re.findall(r"\d+", match.group(0))]
        pieces = []
        start = previous = numbers[0]

        def flush(left: int, right: int) -> None:
            if left == right:
                pieces.append(f"[^{left}]")
            else:
                pieces.append(f"[^{left}]<!--fn-end:{right}-->")

        for number in numbers[1:]:
            if number == previous + 1:
                previous = number
                continue
            flush(start, previous)
            start = previous = number
        flush(start, previous)
        return ", ".join(pieces)

    return pattern.sub(repl, text)


def _separate_adjacent_markers(text: str) -> str:
    """Keep neighboring markers from printing as one digit string.

    The same marker twice in a row is one source, so it stays one marker.
    Different neighbors are separated with a comma.
    """
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"(\[\^(\d+)\])\[\^\2\]", r"\1", text)
    return re.sub(r"(\[\^\d+\])(?=\[\^\d+\])", r"\1, ", text)


def _marker_map_comment(mapping: dict[int, int]) -> str:
    if not mapping:
        return ""
    pairs = " ".join(f"{display}={original}" for display, original in sorted(mapping.items()))
    return f"<!-- marker-map: {pairs} -->\n"


_PARTY_ABBR = (
    (re.compile(r"no party|n\.?p\.?a\.?\b|unaffiliated|non-?partisan", re.IGNORECASE), "NPA"),
    (re.compile(r"working families|\bwfp\b", re.IGNORECASE), "WFP"),
    (re.compile(r"republican|\bgop\b|\brep\b", re.IGNORECASE), "REP"),
    (re.compile(r"democrat|\bdem\b", re.IGNORECASE), "DEM"),
    (re.compile(r"libertarian|\blpf\b", re.IGNORECASE), "LPF"),
    (re.compile(r"\bgreen\b|\bgre\b", re.IGNORECASE), "GRE"),
    (re.compile(r"constitution", re.IGNORECASE), "CON"),
    (re.compile(r"independent|\bind\b", re.IGNORECASE), "IND"),
)


def _abbreviate_party(label: str) -> str:
    text = (label or "").strip()
    if re.fullmatch(r"[A-Z]{2,5}", text):
        return text
    for pattern, abbr in _PARTY_ABBR:
        if pattern.search(text):
            return abbr
    return ""


def _party_abbr(workspace: Path, candidate: dict) -> str:
    """A short plain-text party label. Registered party wins over the ballot's nonpartisan line."""
    labels: list[str] = []
    item_id = str(candidate.get("item_id") or candidate.get("id") or "")
    party: dict = {}
    if item_id:
        profile = load_yaml(workspace / "items" / item_id / "profile.yaml") or {}
        found = profile.get("party") if isinstance(profile, dict) else None
        if isinstance(found, dict):
            party = found
            registered = str(party.get("registered_party") or "").strip()
            if registered:
                labels.append(registered)
    ballot_party = str(candidate.get("party") or "").strip()
    if ballot_party:
        labels.append(ballot_party)
    ballot_label = str(party.get("ballot_label") or "").strip()
    if ballot_label:
        labels.append(ballot_label)
    for label in labels:
        abbr = _abbreviate_party(label)
        if abbr:
            return abbr
    return ""


def _one_sentence(text: str) -> str:
    """The first complete sentence, with citation markers removed."""
    cleaned = re.sub(r"\s+", " ", MARKER_RE.sub("", text or "")).strip()
    cleaned = re.sub(r"\s+([.!?])", r"\1", cleaned)
    if not cleaned:
        return ""
    first = split_sentences(cleaned)[0].strip()
    if first and first[-1] not in ".!?":
        first += "."
    return first


def _is_shouting(title: str) -> bool:
    letters = [char for char in title if char.isalpha()]
    if len(letters) < 8:
        return False
    upper = sum(1 for char in letters if char.isupper())
    return upper / len(letters) > 0.7


def _sentence_case(title: str) -> str:
    text = re.sub(r"\s+", " ", title or "").strip()
    if not text or not _is_shouting(text):
        return text
    lowered = text.lower()
    return lowered[0].upper() + lowered[1:]


_TRAILING_TITLE_WORDS = frozenset(
    {"of", "the", "to", "a", "an", "and", "or", "for", "in", "on", "without", "by", "from"}
)


def _short_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    for sep in (":", "—", "–"):
        if sep in cleaned:
            head = cleaned.split(sep, 1)[0].strip()
            if 3 <= len(head) <= 56:
                return _sentence_case(head)
    if "," in cleaned and (len(cleaned) > 72 or _is_shouting(cleaned)):
        head = cleaned.split(",", 1)[0].strip()
        if 3 <= len(head) <= 42:
            return _sentence_case(head)
    words = cleaned.split()
    if len(words) > 6 or len(cleaned) > 72 or _is_shouting(cleaned):
        chosen: list[str] = []
        for word in words[:10]:
            chosen.append(word)
            if len(" ".join(chosen)) >= 42 and word.lower().strip(",:;") not in _TRAILING_TITLE_WORDS:
                break
        while chosen and chosen[-1].lower().strip(",:;") in _TRAILING_TITLE_WORDS:
            chosen.pop()
        if not chosen:
            chosen = words[:4]
        return _sentence_case(" ".join(chosen))
    return _sentence_case(cleaned)


def _title_pair(title: str, official: str = "") -> tuple[str, str]:
    """A short sentence-case title, plus the full ballot title when that title is long or all caps."""
    del official
    full = re.sub(r"\s+", " ", title or "").strip()
    if not full:
        return "", ""
    if not (_is_shouting(full) or len(full) > 72):
        return full, ""
    short = _short_title(full)
    subtitle = "" if short.lower() == full.lower() else full
    return short, subtitle


def _excerpt_for_hint(plain: str, hint: str) -> str:
    lowered = (hint or "").lower()
    if "receipt" in lowered:
        match = re.search(r"\d[\d,]*(?:\.\d+)?\s+dollars in receipts", plain, re.IGNORECASE)
        if match:
            return match.group(0)
    if "cash" in lowered:
        match = re.search(r"\d[\d,]*(?:\.\d+)?\s+dollars in cash on hand", plain, re.IGNORECASE)
        if match:
            return match.group(0)
    if "report date" in lowered:
        match = re.search(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
            r"|20\d{2}-\d{2}-\d{2}"
            r"|quarter that ended [^.]{0,48}",
            plain,
            re.IGNORECASE,
        )
        if match:
            return match.group(0).strip()
    if "attendance" in lowered:
        excerpt = _attendance_excerpt(plain)
        if excerpt:
            return excerpt
    return plain


def _attendance_excerpt(plain: str) -> str | None:
    """The count and the chamber median. A shorter absence sentence is not this fact."""
    counts = list(re.finditer(r"\d+\s+of\s+\d+", plain or "", re.IGNORECASE))
    median = re.search(r"\bmedian\b", plain or "", re.IGNORECASE)
    if not counts or not median:
        return None
    start = min(median.start(), min(match.start() for match in counts))
    end = max(median.end(), max(match.end() for match in counts))
    return plain[start:end].strip(" ,;")


def _cell(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = cleaned.replace("|", "\\|")
    return cleaned or NOT_FOUND_CELL


def _titles(ballot: dict, workspace: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    if not isinstance(ballot, dict):
        ballot = {}
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict):
            continue
        item_id = str(contest.get("item_id") or contest.get("id") or "")
        if item_id:
            titles[item_id] = str(contest.get("title") or item_id)
        for candidate in contest.get("candidates") or []:
            if isinstance(candidate, dict):
                cid = str(candidate.get("item_id") or candidate.get("id") or "")
                if cid:
                    titles[cid] = str(candidate.get("name") or cid)
    for item in iter_items(workspace):
        if item.name in titles:
            continue
        draft = item / "draft.md"
        if not draft.exists():
            titles[item.name] = item.name
            continue
        for line in draft.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                titles[item.name] = line[2:].strip()
                break
        else:
            titles[item.name] = item.name
    return titles


def _candidate_ids(ballot: dict) -> set[str]:
    found = set()
    if not isinstance(ballot, dict):
        return found
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict):
            continue
        for candidate in contest.get("candidates") or []:
            if isinstance(candidate, dict):
                found.add(str(candidate.get("item_id") or candidate.get("id")))
    return found


def _people(contest: dict) -> list[dict]:
    rows = []
    for candidate in contest.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("write_in") or candidate.get("withdrawn"):
            continue
        rows.append(candidate)
    return rows


def _other_people(contest: dict) -> list[dict]:
    rows = []
    for candidate in contest.get("candidates") or []:
        if isinstance(candidate, dict) and (candidate.get("write_in") or candidate.get("withdrawn")):
            rows.append(candidate)
    return rows


_DEFINITION_BLURB_RE = re.compile(
    r"(?i)^(?:ad valorem|a mill|a sales surtax|a homestead exemption|one-half percent|one half percent)\b"
    r"|^the budget stabilization fund is\b"
    r"|is the name on the ballot"
    r"|\bmeans one\b"
    r"|\bis a tax added\b"
    r"|\bis the property-tax rate\b"
    r"|\bis the state's reserve\b"
    r"|\bis the part of a home\b"
)
_EFFECT_BLURB_RE = re.compile(
    r"\b(?:would|renews?|asks|raises?|exempts?|limits?|slows?|creates?|extends?|cuts?|replaces?|requires?)\b",
    re.IGNORECASE,
)


def _office_job(title: str) -> str:
    """The office's job in one short clause, taken from the office name."""
    text = re.sub(r"\s+", " ", title or "").strip()
    lowered = text.lower()
    district = ""
    found = re.search(r"district\s+(\d+)", lowered)
    if found:
        district = found.group(1)
    if "senator" in lowered and "state senator" not in lowered:
        return "Represents Florida in the U.S. Senate"
    if "representative in congress" in lowered or "u.s. house" in lowered or "us house" in lowered:
        where = f"District {district}" if district else "this district"
        return f"Represents {where} in the U.S. House"
    if "governor" in lowered:
        return "Heads the state government"
    if "attorney general" in lowered:
        return "Serves as the state's chief legal officer"
    if "chief financial officer" in lowered:
        return "Keeps the state's funds and settles its accounts"
    if "agriculture" in lowered:
        return "Serves on the Florida Cabinet"
    if "state representative" in lowered:
        where = f"District {district}" if district else "this district"
        return f"Represents {where} in the Florida House"
    if "county commissioner" in lowered or "board of county commissioners" in lowered:
        where = f"District {district}" if district else "a county district"
        return f"Serves on the county commission for {where}"
    if "mayor" in lowered:
        place = re.sub(r"(?i)^mayor of\s+", "", text).strip()
        if place and place.lower() != "mayor":
            return f"Heads the government of {place}"
        return "Heads the city government"
    return ""


def _candidate_count_clause(contest: dict) -> str:
    count = len(_people(contest))
    noun = "candidate" if count == 1 else "candidates"
    clause = f"{count} {noun}"
    write_ins = [row for row in _other_people(contest) if row.get("write_in") and not row.get("withdrawn")]
    if len(write_ins) == 1:
        clause += ", plus write-in"
    elif write_ins:
        clause += ", plus write-ins"
    return clause


def _retention_blurb(title: str) -> str:
    judge = re.search(r"Shall (Justice|Judge) (.+?) of the (.+?) be", title or "")
    if not judge:
        return "Voters decide whether this judge stays in office."
    role = judge.group(1)
    name = re.sub(r"\s+", " ", judge.group(2)).strip()
    court = re.sub(r"\s+", " ", judge.group(3)).strip()
    return f"Voters decide whether {role} {name} stays on the {court}."


def _group_name(contest: dict) -> str:
    level = contest.get("level")
    if isinstance(level, str) and level in LEVEL_TITLES:
        return LEVEL_TITLES[level]
    return TYPE_TITLES.get(str(contest.get("type") or ""), "Other ballot items")


def _contest_kind(contest: dict) -> str:
    level = contest.get("level")
    if level == "amendment":
        return "amendment"
    if level == "referendum":
        return "referendum"
    kind = str(contest.get("type") or "contest")
    if kind == "judicial-retention":
        return "retention"
    if kind == "race":
        party = [str(c.get("party") or "") for c in _people(contest) if isinstance(c, dict)]
        if party and all(value.lower() == "nonpartisan" for value in party):
            return "nonpartisan race"
        return "race"
    return kind


def _choices(contest: dict, hide_party: bool = False) -> str:
    if contest.get("type") in {"measure", "judicial-retention"}:
        return "Yes or No"
    parts = []
    for candidate in contest.get("candidates") or []:
        if not isinstance(candidate, dict) or candidate.get("withdrawn"):
            continue
        label = str(candidate.get("name") or "")
        extra = []
        if candidate.get("party") and not hide_party:
            extra.append(str(candidate.get("party")))
        if candidate.get("incumbent"):
            extra.append("incumbent")
        if candidate.get("write_in"):
            extra.append("write-in")
        if extra:
            label = f"{label} ({', '.join(extra)})"
        parts.append(label)
    return ", ".join(part for part in parts if part) or NOT_FOUND_CELL


def _incumbent_names(contest: dict) -> str:
    names = [str(c.get("name")) for c in _people(contest) if c.get("incumbent") and c.get("name")]
    return ", ".join(names)


def _summary_paragraph(draft: str) -> str:
    if "<!-- summary -->" not in draft:
        return ""
    after = draft.split("<!-- summary -->", 1)[1]
    lines = []
    for line in after.splitlines():
        if line.strip() == "" and lines:
            break
        if line.strip().startswith("#"):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith(("<!--", ">")):
            lines.append(stripped)
    return " ".join(lines)


def _section_pairs(draft: str) -> list[tuple[str, str, str]]:
    sections: list[tuple[str, str, str]] = []
    current_raw = None
    current_norm = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal current_raw, current_norm, buf
        if current_raw and current_norm:
            sections.append((current_raw, current_norm, "\n".join(buf).strip()))
        buf = []

    for line in draft.splitlines():
        heading = _heading(line) if line.startswith("#") else None
        if heading and heading[0] == 2:
            flush()
            current_raw = re.sub(r"^##\s+", "", line).strip()
            current_raw = re.sub(r"\s*\{[^{}]*\}\s*$", "", current_raw).strip()
            current_norm = heading[1]
            continue
        if current_raw is not None:
            buf.append(line)
    flush()
    return sections


def _section_dict(draft: str) -> dict[str, tuple[str, str]]:
    return {name: (raw, body) for raw, name, body in _section_pairs(draft)}


def _cited_sentences(body: str) -> list[str]:
    found = []
    text = HTML_COMMENT_RE.sub("", body or "")
    for paragraph in re.split(r"\n\s*\n", text):
        lines = paragraph.splitlines()
        table = [line for line in lines if line.strip()]
        if table and all(line.strip().startswith("|") for line in table):
            for line in table:
                compact = line.replace("|", "").replace(":", "").replace("-", "").replace(" ", "")
                if not compact:
                    continue
                for cell in line.strip().strip("|").split("|"):
                    cleaned = re.sub(r"\s+", " ", cell).strip()
                    if "[^" not in cleaned or _gap_sentence(MARKER_RE.sub("", cleaned)):
                        continue
                    found.append(cleaned)
            continue
        flat = _bind_trailing_markers(paragraph.replace("\n", " "))
        for sentence in split_sentences(flat):
            cleaned = sentence.strip()
            if "[^" not in cleaned:
                continue
            if _gap_sentence(MARKER_RE.sub("", cleaned)):
                continue
            found.append(re.sub(r"\s+", " ", cleaned))
    return found


def _first_cited(body: str) -> str | None:
    sentences = _cited_sentences(body)
    return sentences[0] if sentences else None


def _party_display(workspace: Path, item_id: str) -> str:
    """Cited party line from profile.yaml. Empty when the researcher has not written one."""
    if not item_id:
        return ""
    profile = load_yaml(workspace / "items" / item_id / "profile.yaml") or {}
    party = profile.get("party") if isinstance(profile, dict) else None
    if not isinstance(party, dict):
        return ""
    display = re.sub(r"\s+", " ", str(party.get("display") or "")).strip()
    if "[^" in display:
        return display
    return ""


def _party_fallback(workspace: Path, item_id: str) -> str:
    """First cited sentence in the party section when no structured display exists."""
    draft = workspace / "items" / item_id / "draft.md"
    if not item_id or not draft.exists():
        return ""
    body = _section_dict(draft.read_text(encoding="utf-8")).get("party")
    if not body:
        return ""
    return _first_cited(body[1]) or ""


def _dig(data: dict, path: tuple[str, ...]) -> str:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return re.sub(r"\s+", " ", str(current or "")).strip()


def _cell_found(cell: str) -> bool:
    return bool(cell) and cell != NOT_FOUND_CELL


def _sentence_key(sentence: str) -> str:
    plain = MARKER_RE.sub("", sentence or "")
    return re.sub(r"\s+", " ", plain).strip().lower()


def _structured_cell(profile: dict, row: _Row) -> str | None:
    """A cited profile.yaml value beats a prose sentence for this row."""
    if not isinstance(profile, dict):
        return None
    candidates = []
    money = profile.get("money") if isinstance(profile.get("money"), dict) else {}
    if row.money_key and str(money.get(row.money_key) or "").strip():
        candidates.append(str(money.get(row.money_key)))
    fields = profile.get("fields") if isinstance(profile.get("fields"), dict) else {}
    if str(fields.get(row.label) or "").strip():
        candidates.append(str(fields.get(row.label)))
    if row.profile_path:
        dug = _dig(profile, row.profile_path)
        if dug:
            candidates.append(dug)
    for text in candidates:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if "[^" in cleaned:
            return cleaned
    return None


def _row_options(row: _Row, sections: dict, used: set[str], *, ignore_pattern: bool = False) -> list[str]:
    found = sections.get(row.section)
    body = found[1] if found else ""
    options = []
    for sentence in _cited_sentences(body):
        key = _sentence_key(sentence)
        if not key or key in used:
            continue
        if row.pattern is not None and not ignore_pattern and not row.pattern.search(MARKER_RE.sub("", sentence)):
            continue
        options.append(sentence)
    return options


def _attendance_value(body: str) -> tuple[str, list[str]] | None:
    """The member's count and the chamber median, even when they are two sentences."""
    sentences = _cited_sentences(body)
    if not sentences:
        return None

    def plain(sentence: str) -> str:
        return MARKER_RE.sub("", sentence)

    def has_count(sentence: str) -> bool:
        return re.search(r"\b\d+\s+of\s+\d+\b", plain(sentence)) is not None

    def has_median(sentence: str) -> bool:
        return re.search(r"\bmedian\b", plain(sentence), re.IGNORECASE) is not None

    def has_member(sentence: str) -> bool:
        return re.search(r"\b(?:attended|missed)\b", plain(sentence), re.IGNORECASE) is not None

    both = [sentence for sentence in sentences if has_count(sentence) and has_median(sentence) and has_member(sentence)]
    if not both:
        both = [
            sentence
            for sentence in sentences
            if has_median(sentence) and len(re.findall(r"\b\d+\s+of\s+\d+\b", plain(sentence))) >= 2
        ]
    if both:
        chosen = both[0]
        return chosen, [_sentence_key(chosen)]
    members = [sentence for sentence in sentences if has_count(sentence) and not has_median(sentence)]
    medians = [sentence for sentence in sentences if has_median(sentence)]
    if members and medians:
        text = f"{members[0].strip()} {medians[0].strip()}"
        return text, [_sentence_key(members[0]), _sentence_key(medians[0])]
    return None


def _assign_cells(sections: dict, profile: dict, rows: list[_Row]) -> dict[str, str]:
    """Give each row its own fact.

    A cited structured field wins. Otherwise the row gets the unused cited
    sentence that matches the fewest other row patterns, then the shortest.
    The same sentence is not placed in two rows. Patterned rows are filled
    first, in list order, so a shared receipts-and-cash sentence stays on
    Receipts and Cash on hand becomes Not found.
    """
    used: set[str] = set()
    assigned: dict[str, str] = {}

    def take(label: str, sentence: str) -> None:
        assigned[label] = sentence
        key = _sentence_key(sentence)
        if key:
            used.add(key)

    for row in rows:
        structured = _structured_cell(profile, row)
        if structured and _sentence_key(structured) not in used:
            take(row.label, structured)

    patterned = [row for row in rows if row.pattern is not None and row.label not in assigned]
    plain = [row for row in rows if row.pattern is None and row.label not in assigned]

    def specificity(sentence: str) -> tuple[int, int]:
        plain_text = MARKER_RE.sub("", sentence)
        overlap = sum(1 for other in rows if other.pattern is not None and other.pattern.search(plain_text))
        return (overlap, len(sentence))

    for row in patterned:
        if row.label == "Attendance" and row.label not in assigned:
            found = sections.get(row.section)
            body = found[1] if found else ""
            combined = _attendance_value(body)
            if combined:
                text, keys = combined
                if not any(key in used for key in keys):
                    take(row.label, text)
                    used.update(key for key in keys if key)
                    continue
        options = _row_options(row, sections, used)
        if not options and row.fallback_first:
            options = _row_options(row, sections, used, ignore_pattern=True)
        if not options:
            assigned[row.label] = NOT_FOUND_CELL
            continue
        # Fewest other row patterns, then the shortest sentence.
        take(row.label, min(options, key=specificity))
    for row in plain:
        options = _row_options(row, sections, used)
        if not options:
            assigned[row.label] = NOT_FOUND_CELL
            continue
        # Document order: the first unused cited sentence in the section.
        take(row.label, options[0])
    for row in rows:
        assigned.setdefault(row.label, NOT_FOUND_CELL)
    return assigned


def _matching_cited(body: str, pattern: re.Pattern) -> str | None:
    for sentence in _cited_sentences(body):
        if pattern.search(MARKER_RE.sub("", sentence)):
            return sentence
    return None


def _first_or_not_found(sections: dict, name: str) -> str:
    found = sections.get(name)
    if not found:
        return NOT_FOUND_CELL
    sentence = _first_cited(found[1])
    return sentence or NOT_FOUND_CELL


def _shared_issue_keys(bundles: list) -> list[str]:
    counts: dict[str, int] = {}
    for _candidate, _sections, profile in bundles:
        issues = profile.get("issues") if isinstance(profile, dict) else None
        if not isinstance(issues, dict):
            continue
        for key, value in issues.items():
            text = str(value or "")
            if "[^" in text and text.lower().strip() not in {"not found", "none"}:
                counts[str(key)] = counts.get(str(key), 0) + 1
    return sorted(key for key, count in counts.items() if count >= 2)


def _is_placeholder_none(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return True
    if not _is_gap_text(text):
        return False
    for sentence in split_sentences(text):
        lowered = sentence.strip().lower().rstrip(".")
        if lowered not in {"none", "omitted"}:
            return False
    return True


def _sentence_mentioning(workspace: Path, needle: str) -> str | None:
    if not needle:
        return None
    for item in iter_items(workspace):
        draft = item / "draft.md"
        if not draft.exists():
            continue
        for sentence in _cited_sentences(draft.read_text(encoding="utf-8")):
            if needle in sentence:
                return sentence
    return None


def _tier_cell(index: dict, sentence: str) -> str:
    numbers = [int(value) for value in MARKER_RE.findall(sentence or "")]
    if not numbers:
        return NOT_FOUND_CELL
    found = index.get(numbers[0])
    if not found:
        return NOT_FOUND_CELL
    _item, _claim, source = found
    tier = source.get("tier")
    if not tier:
        return NOT_FOUND_CELL
    return f"{tier}[^{numbers[0]}]"


def _finding_counts(workspace: Path) -> dict[str, int]:
    counts = {"total": 0, "disputed": 0, "accepted": 0}
    for item in iter_items(workspace):
        findings = load_yaml(item / "findings.yaml") or []
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            counts["total"] += 1
            if finding.get("status") == "disputed":
                counts["disputed"] += 1
            if finding.get("status") == "accepted":
                counts["accepted"] += 1
    return counts
