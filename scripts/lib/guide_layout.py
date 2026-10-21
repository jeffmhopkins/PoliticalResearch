"""Reader and full editions of the guide.

The reader opens with the ballot, then one contest at a time, inside a word
budget. Comparison cells are short facts. Per-candidate prose stays in the full
edition. Works cited, quotes, search logs, and cell detail move to a sources
addendum. Markers in the body link to that addendum and back. A table row is
kept only when a cell carries a marker, or the row is replaced by one official
gap sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.quality import (
    HTML_COMMENT_RE,
    MARKER_RE,
    READER_CONTEST_WORD_BUDGET,
    claim_index,
    environment_rating_sentence,
    marker_numbers,
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
_RECEIPTS_RE = re.compile(r"\breceipts\b", re.IGNORECASE)
_CASH_RE = re.compile(r"cash on hand", re.IGNORECASE)
_SELF_FUND_RE = re.compile(r"self-fund|self fund|loan", re.IGNORECASE)
_SMALL_DONOR_RE = re.compile(r"small donor|under \$200|\$200", re.IGNORECASE)
_OUTSIDE_RE = re.compile(r"outside spending|independent expenditure", re.IGNORECASE)
_REPORT_DATE_RE = re.compile(r"quarter|filed on|report date|as of", re.IGNORECASE)
_PARTY_RE = re.compile(r"incumbent|challenger|nonpartisan|party", re.IGNORECASE)
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

    def __init__(self, label: str, section: str, pattern: re.Pattern | None = None, money_key: str | None = None, fallback_first: bool = False, omit_if_empty: bool = False):
        self.label = label
        self.section = section
        self.pattern = pattern
        self.money_key = money_key
        self.fallback_first = fallback_first
        self.omit_if_empty = omit_if_empty


_COMPARISON_GROUPS = [
    (
        "At a glance",
        [
            _Row("Ballot status", "identity", _PARTY_RE, fallback_first=True),
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
            _Row("Outside spending", "campaign funding", _OUTSIDE_RE, "outside_spending"),
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
        self.details: list[tuple[str, str, str]] = []
        self.edition = "reader"
        self.addendum_name = "guide-sources.md"
        self.body_name = "guide.md"

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
        self.details = []
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
        parts = self._front_matter(title, edition, sources=False)
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
                "> **Not an official ballot and not voting instructions:** confirm contests, deadlines, and polling places with the election office linked below.",
                "",
            ]
        )
        date_bit = _display_date(str(election.get("date") or ""))
        heading = str(title_name)
        if date_bit:
            heading = f"{heading}, {date_bit}"
        parts.extend([f"# {heading} {{.guide-title}}", ""])
        parts.extend(self._election_office())
        parts.extend(self._precinct_line())
        parts.extend(self._at_a_glance())
        parts.extend(self._how_to_read())
        parts.extend(self._compare())
        parts.extend(self._contests())
        parts.extend(self._glossary())
        parts.extend(self._methodology(edition))
        parts.extend(self._disputed(edition))
        parts.extend(self._corrections())
        if edition == "full":
            used_for_index = marker_numbers("\n".join(parts))
            parts.extend(self._marker_index(used_for_index))
            parts.extend(self._changelog())
        body = "\n".join(parts).rstrip() + "\n"
        used = marker_numbers(body)
        addendum = self._sources_addendum(used)
        linked = self._link_markers(body)
        text = re.sub(r"\n{3,}", "\n\n", linked).rstrip() + "\n"
        addendum_text = re.sub(r"\n{3,}", "\n\n", addendum).rstrip() + "\n"
        return text, addendum_text

    def _link_markers(self, text: str) -> str:
        seen: set[str] = set()

        def repl(match: re.Match) -> str:
            number = match.group(1)
            link = f"[<sup>{number}</sup>]({self.addendum_name}#source-{number})"
            if number in seen:
                return link
            seen.add(number)
            return f'<a id="cite-{number}"></a>{link}'

        return MARKER_RE.sub(repl, text)

    def _show_cell(self, full: str, anchor: str, title: str, hint: str = "") -> str:
        if not _cell_found(full):
            return NOT_FOUND_CELL
        short = _short_fact(full, hint)
        if _sentence_key(short) != _sentence_key(full):
            anchor = self._detail_anchor(anchor, title, full)
            short = f"{short} [detail]({self.addendum_name}#{anchor})"
        return short

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
        lines = [
            "# Your ballot at a glance {#your-ballot-at-a-glance .ballot-glance}",
            "",
            "| Contest | Summary | Read |",
            "| --- | --- | --- |",
        ]
        for contest in self._contests_raw():
            item_id = str(contest.get("item_id") or contest.get("id"))
            draft = self._draft(item_id)
            summary = _summary_paragraph(draft) or _first_cited(draft) or ""
            if "[^" not in summary:
                continue
            title = str(contest.get("title") or self.titles.get(item_id) or item_id)
            bits = [f"**{_cell(title)}**", _cell(_contest_kind(contest)), _cell(_choices(contest))]
            if contest.get("type") in {"race", "primary", "local-office"}:
                incumbent = _incumbent_names(contest) or NOT_FOUND_CELL
                bits.append("Incumbent: " + _cell(incumbent))
            summary_cell = self._show_cell(summary, f"detail-{item_id}-summary", f"{title} summary")
            link = f"[{_cell(title)}](#contest-{item_id})"
            row = ["<br>".join(bits), _cell(summary_cell), link]
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        return lines

    def _how_to_read(self) -> list[str]:
        return [
            "# How to read this guide",
            "",
            "Start with the ballot table, then read one contest at a time. "
            "Each race uses the same comparison rows for every candidate. "
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
            BACK_LINK,
            "",
        ]

    def _compare(self) -> list[str]:
        lines = ["# Compare across the ballot", ""]
        lines.extend(self._money_across())
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

    def _contests(self) -> list[str]:
        grouped: dict[str, list] = {}
        for contest in self._contests_raw():
            grouped.setdefault(_group_name(contest), []).append(contest)
        lines: list[str] = []
        for name in GROUP_ORDER:
            contests = grouped.get(name) or []
            if not contests:
                continue
            lines.extend([f"# {name} {{.ballot-group}}", ""])
            for contest in contests:
                lines.extend(self._one_contest(contest))
        return lines

    def _one_contest(self, contest: dict) -> list[str]:
        if self.edition == "reader":
            return self._fit_contest_budget(self._reader_contest(contest))
        return self._full_contest(contest)

    def _full_contest(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or self.titles.get(item_id) or item_id)
        draft = self._draft(item_id)
        sections = _section_pairs(draft)
        lines = [f"## {title} {{#contest-{item_id} .contest-title}}", ""]
        lines.extend(self._contest_opener(contest))
        lines.extend(self._preamble(draft, item_id))
        kind = contest.get("type")
        if kind in {"race", "primary", "local-office"}:
            lines.extend(self._race_body(contest, sections))
            lines.extend(self._profiles(contest))
        elif kind == "measure":
            lines.extend(self._measure_body(item_id, title, sections))
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
            lines.extend([f"### {name} {{#candidate-{item_id} .candidate-name}}", ""])
        lines.extend([":::", ""])
        return lines

    def _reader_contest(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or self.titles.get(item_id) or item_id)
        draft = self._draft(item_id)
        sections = _section_pairs(draft)
        lines = [f"## {title} {{#contest-{item_id} .contest-title}}", ""]
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
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in shown_up_front:
                continue
            sentence = _first_cited(body)
            if not sentence:
                continue
            rows.append((raw, self._show_cell(sentence, f"detail-{item_id}-{slugify(name)}", f"{title}: {raw}", raw)))
        if rows:
            lines.extend(_emit_table(["Topic", "Fact"], [[label, cell] for label, cell in rows]))
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
        extra_issues = _shared_issue_keys(bundles)
        lines_out: list[str] = []
        for heading, specs in _COMPARISON_GROUPS:
            rows = []
            dropped = []
            for spec in specs:
                label = spec.label
                cells = [cells_for[label] for cells_for in assigned]
                if cells and all(cell == NOT_FOUND_CELL for cell in cells):
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
            block = [f"### {heading}", ""]
            for headers, body in comparison_tables(names, shown_rows):
                block.extend(["::: comparison", ""])
                block.extend(_emit_table(headers, body))
                block.extend([":::", ""])
            if dropped:
                block.append(_gap_line(", ".join(dropped)))
                block.append("")
            if len(block) > 2:
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
            lines.extend(
                [
                    "::: candidate-name",
                    "",
                    f"### {name} {{#profile-{item_id}}}",
                    "",
                    ":::",
                    "",
                ]
            )
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
        return [
            "# Glossary {#glossary .back-matter}",
            "",
            "Levy",
            ": A levy is a tax or charge put on a ballot for voters to accept or reject.",
            "",
            "Nonpartisan",
            ": The ballot does not list a party for that office.",
            "",
            "Cash on hand",
            ": Cash on hand is the money a campaign reported still having at the end of a filing period.",
            "",
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
            "Single source",
            ": A single source means the sentence rests on one record.",
            "",
            "Allegation",
            ": An allegation is a claim someone has made that this guide has not confirmed.",
            "",
            "Not found",
            ": Not found means the listed places were searched and the fact was not in them.",
            "",
        ]

    def _methodology(self, edition: str) -> list[str]:
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        intake = self.intake if isinstance(self.intake, dict) else {}
        counts = _finding_counts(self.workspace)
        env_line = environment_rating_sentence(self.workspace)
        flagged = 0
        for _item, claim, source in self.index.values():
            if source.get("suspected_injection") is True and not claim.get("removed"):
                flagged += 1
        subagents = "available" if intake.get("parallel_subagents") else "not used; roles run one at a time in fresh contexts"
        lines = [
            "# How we researched {#methodology .back-matter}",
            "",
            f"Version {ballot.get('report_version') or 'v1.0'} assembled on {self.today}. {env_line}",
            f"Sources flagged suspected_injection: {flagged}.",
            f"Parallel subagents: {subagents}.",
            f"Findings recorded: {counts['total']}. Accepted: {counts['accepted']}. Disputed: {counts['disputed']}.",
            "Disputed and unconfirmed claims are not used in summaries. Blockers are removed rather than left disputed.",
            "The reader edition keeps a short summary and comparison tables for each contest. "
            "Works cited, quotes, and the search log are in the sources addendum. "
            "Per-candidate prose is in the full edition. "
            "The full edition adds the marker index and the changelog.",
            "",
            "## Review state",
            "",
        ]
        for item in iter_items(self.workspace):
            state = load_json(item / "loop-state.json") or {}
            label = item.name if edition == "full" else self.titles.get(item.name, item.name)
            lines.append(
                f"- {label}: status {state.get('status')}, round {state.get('round')}, mode {state.get('mode')}"
            )
        lines.extend(["", "## Effort", ""])
        lines.append("| Item | Searches | Fetches | Minutes |")
        lines.append("| --- | --- | --- | --- |")
        for item in iter_items(self.workspace):
            effort = load_json(item / "effort.json") or {}
            label = item.name if edition == "full" else self.titles.get(item.name, item.name)
            lines.append(
                f"| {label} | {effort.get('searches', '')} | {effort.get('fetches', '')} | {effort.get('minutes', '')} |"
            )
        lines.extend(["", "## Known gaps", ""])
        gap_lines = []
        for item in iter_items(self.workspace):
            state = load_json(item / "loop-state.json") or {}
            label = item.name if edition == "full" else self.titles.get(item.name, item.name)
            for gap in state.get("gaps") or []:
                gap_lines.append(f"- {label}: {gap}")
            for gap in state.get("process_gaps") or []:
                gap_lines.append(f"- {label}: {gap}")
        lines.extend(gap_lines or ["- None recorded in loop state."])
        lines.append("")
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
            lines.extend(["No claims are disputed.", ""])
        return lines

    def _corrections(self) -> list[str]:
        corrections = load_yaml(self.workspace / "corrections.yaml") or []
        lines = ["# Corrections {#corrections .back-matter}", ""]
        if not corrections:
            lines.extend(["No corrections have been issued.", ""])
            return lines
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
                "# Works cited {.back-matter}",
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
                parts.extend(self._source_entry(number))
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

    def _source_entry(self, number: int) -> list[str]:
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
        lines.extend([f"[Back to the guide]({self.body_name}#cite-{number})", ""])
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

    def _marker_index(self, used: set[int]) -> list[str]:
        lines = ["# Marker index", "", "| Marker | Claim ID |", "| --- | --- |"]
        for number in sorted(used):
            found = self.index.get(number)
            if not found:
                continue
            _item, claim, _source = found
            if claim.get("removed"):
                continue
            lines.append(f"| {number} | {claim.get('id')} |")
        lines.append("")
        return lines

    def _changelog(self) -> list[str]:
        lines = ["# Changelog", ""]
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
            if cleaned:
                self.search_log.append((owner, section, cleaned))


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
        if _is_gap_text(paragraph) and "[^" not in paragraph:
            gaps.append(paragraph)
            continue
        kept.append(paragraph)
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


def _gap_line(subject: str) -> str:
    inner = re.sub(r"\s+", " ", subject).strip().strip(".")
    inner = inner.replace(";", ",").replace(":", ",")
    return f"Not found (searched: {inner})."


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


def _short_fact(sentence: str, hint: str = "") -> str:
    """A value or a brief phrase, with the citation markers kept on the end."""
    if not sentence or sentence == NOT_FOUND_CELL:
        return NOT_FOUND_CELL
    markers = "".join(f"[^{number}]" for number in MARKER_RE.findall(sentence))
    plain = re.sub(r"\s+", " ", MARKER_RE.sub("", sentence)).strip().rstrip(".")
    excerpt = _excerpt_for_hint(plain, hint)
    if len(excerpt) > CELL_CHAR_CAP:
        clipped = excerpt[: CELL_CHAR_CAP - 3].rsplit(" ", 1)[0].rstrip(",;:")
        excerpt = (clipped or excerpt[: CELL_CHAR_CAP - 3]) + "..."
    return f"{excerpt}{markers}" if excerpt else NOT_FOUND_CELL


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
    return plain


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


def _choices(contest: dict) -> str:
    if contest.get("type") in {"measure", "judicial-retention"}:
        return "Yes or No"
    parts = []
    for candidate in contest.get("candidates") or []:
        if not isinstance(candidate, dict) or candidate.get("withdrawn"):
            continue
        label = str(candidate.get("name") or "")
        extra = []
        if candidate.get("party"):
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
