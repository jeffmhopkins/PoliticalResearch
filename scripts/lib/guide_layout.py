"""Reader and full editions of the guide.

The reader opens with the ballot, then one contest at a time. The full edition
adds the marker index and the changelog. Both editions cite every factual
sentence. A table row is kept only when a cell carries a marker, or the row is
replaced by one official gap sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.quality import (
    HTML_COMMENT_RE,
    MARKER_RE,
    claim_index,
    environment_rating_sentence,
    marker_numbers,
)
from lib.quality import _bind_trailing_markers, _gap_sentence, _heading, _is_gap_text
from lib.sentences import split_sentences
from lib.util import iter_items, load_json, load_yaml
from lib.workflow import footnote_line, format_work

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


class _Row:
    """One comparison row. A patterned row takes the most specific unused sentence."""

    def __init__(self, label: str, section: str, pattern: re.Pattern | None = None, money_key: str | None = None, fallback_first: bool = False):
        self.label = label
        self.section = section
        self.pattern = pattern
        self.money_key = money_key
        self.fallback_first = fallback_first


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


def build_editions(workspace: Path, today: str) -> tuple[str, str]:
    model = _GuideModel(workspace, today)
    return model.render("reader"), model.render("full")


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

    def render(self, edition: str) -> str:
        self.search_log = []
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        election = ballot.get("election") or {}
        fiction = bool(ballot.get("fiction"))
        title_name = election.get("name") or ballot.get("election_id") or "Election"
        title = f"Voter guide: {title_name}"
        if fiction:
            title = f"FICTIONAL voter guide: {title_name}"
        parts = [
            "---",
            f'title: "{title}"',
            f"version: {ballot.get('report_version') or 'v1.0'}",
            f"election_id: {ballot.get('election_id')}",
            f"build_date: {self.today}",
            f"edition: {edition}",
            f"fiction: {'true' if fiction else 'false'}",
            "---",
            "",
        ]
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
        date_bit = election.get("date")
        heading = str(title_name)
        if date_bit:
            heading = f"{heading}, {date_bit}"
        parts.extend([f"# {heading}", ""])
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
        parts.extend(self._search_log())
        body = "\n".join(parts).rstrip() + "\n"
        used = marker_numbers(body)
        tail = self._works_cited(used)
        if edition == "full":
            tail.extend(self._marker_index(used))
            tail.extend(self._changelog())
        tail.append("<!-- Pandoc footnote definitions. The reader-facing list is Works cited. -->")
        tail.append("")
        for number in sorted(used):
            found = self.index.get(number)
            if not found:
                continue
            _item, claim, source = found
            if claim.get("removed"):
                continue
            tail.append(footnote_line(number, source))
            tail.append("")
        text = body.rstrip() + "\n\n" + "\n".join(tail).rstrip() + "\n"
        return re.sub(r"\n{3,}", "\n\n", text)

    def _election_office(self) -> list[str]:
        logistics = self.workspace / "logistics.md"
        if logistics.exists():
            text = self._rewrite(logistics.read_text(encoding="utf-8")).strip()
            if text:
                return [text, ""]
        rows = []
        ballot = self.ballot if isinstance(self.ballot, dict) else {}
        for entry in ballot.get("logistics") or []:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "Election office")
            url = str(entry.get("url") or "")
            marker = entry.get("marker")
            if url and marker:
                rows.append(f"- {label}: {url}[^{marker}]")
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
        districts = ballot.get("districts") if isinstance(ballot.get("districts"), list) else []
        cited = _sentence_mentioning(self.workspace, precinct) if precinct else None
        if precinct and cited:
            lines = [cited, ""]
        else:
            lines = ["Not found (searched: precinct code and district list on the confirmed ballot).", ""]
        if districts and not cited:
            # District names stay in ballot.yaml until a sourced sentence carries them.
            pass
        return lines

    def _at_a_glance(self) -> list[str]:
        lines = [
            "# Your ballot at a glance {#your-ballot-at-a-glance}",
            "",
            "| Item | Type | Choices | Incumbent | Summary | Link |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for contest in self._contests_raw():
            item_id = str(contest.get("item_id") or contest.get("id"))
            draft = self._draft(item_id)
            summary = _summary_paragraph(draft) or _first_cited(draft) or ""
            if "[^" not in summary:
                continue
            title = str(contest.get("title") or self.titles.get(item_id) or item_id)
            kind = _contest_kind(contest)
            incumbent = _incumbent_names(contest) or NOT_FOUND_CELL
            link = f"[{_cell(title)}](#contest-{item_id})"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(title),
                        _cell(kind),
                        _cell(_choices(contest)),
                        _cell(incumbent),
                        _cell(summary),
                        link,
                    ]
                )
                + " |"
            )
        lines.append("")
        return lines

    def _how_to_read(self) -> list[str]:
        return [
            "# How to read this guide",
            "",
            "Start with the ballot table, then read one contest at a time. "
            "Each race uses the same comparison rows for every candidate. "
            "A cell that says Not found was searched and not found. The places searched are in the search log.",
            "",
            "A bracketed number points at a source in Works cited. "
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
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(office),
                            _cell(str(candidate.get("name") or item_id)),
                            _cell(receipts),
                            _cell(cash),
                            _cell(report),
                            _cell(_tier_cell(self.index, marker_source)),
                        ]
                    )
                    + " |"
                )
        lines.append("")
        if missing:
            lines.append(_gap_line("campaign receipts for " + ", ".join(missing)))
            lines.append("")
        if not any(line.startswith("| ") and "[^" in line for line in lines):
            return [
                "## Money",
                "",
                _gap_line("campaign receipts and cash on hand"),
                "",
            ]
        return lines

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
                for key, value in issues.items():
                    text = str(value or "").strip()
                    if not text or text.lower() in {"not found", "none"} or "[^" not in text:
                        found_for_issue.setdefault(str(key), [])
                        continue
                    name = str(candidate.get("name") or item_id)
                    found_for_issue.setdefault(str(key), []).append(f"{name}: {_cell(text)}")
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
        header = ["Issue", *offices]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for key in sorted(issue_rows):
            row = [key]
            for office in offices:
                row.append(issue_rows[key].get(office, NOT_FOUND_CELL))
            if all(cell == NOT_FOUND_CELL for cell in row[1:]):
                continue
            lines.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
        lines.append("")
        return lines

    def _measures_across(self) -> list[str]:
        measures = [c for c in self._contests_raw() if c.get("type") == "measure"]
        lines = ["## Measures side by side", ""]
        if not measures:
            lines.extend([_gap_line("measures on this ballot"), ""])
            return lines
        headers = [
            "Measure",
            "Type",
            "Threshold",
            "What a yes vote does",
            "What a no vote does",
            "Fiscal impact",
            "Sunset or renewal",
            "Funding by side",
        ]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for contest in measures:
            item_id = str(contest.get("item_id") or contest.get("id"))
            sections = _section_dict(self._draft(item_id))
            cells = [
                str(contest.get("title") or item_id),
                _first_or_not_found(sections, "measure type and qualification"),
                _first_or_not_found(sections, "vote threshold"),
                _first_or_not_found(sections, "what a yes vote does"),
                _first_or_not_found(sections, "what a no vote does"),
                _first_or_not_found(sections, "fiscal impact"),
                _first_or_not_found(sections, "sunset or renewal"),
                _first_or_not_found(sections, "funding by side"),
            ]
            if not any("[^" in cell for cell in cells):
                continue
            lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
        lines.append("")
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
        header = ["Judge", *[columns[index][0] for index in keep]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for title, cells in built:
            shown = [title, *[cells[index] for index in keep]]
            if not any("[^" in cell for cell in shown):
                continue
            lines.append("| " + " | ".join(_cell(cell) for cell in shown) + " |")
        lines.append("")
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
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(contest.get("title") or item_id)),
                        _cell(incumbent_cell),
                        _cell(count_cell),
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
            lines.extend([f"# {name}", ""])
            for contest in contests:
                lines.extend(self._one_contest(contest))
        return lines

    def _one_contest(self, contest: dict) -> list[str]:
        item_id = str(contest.get("item_id") or contest.get("id"))
        title = str(contest.get("title") or self.titles.get(item_id) or item_id)
        draft = self._draft(item_id)
        sections = _section_pairs(draft)
        lines = [f"## {title} {{#contest-{item_id} .contest-title}}", ""]
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
            lines.extend(["<!-- summary -->", summary, ""])
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
                    dropped.append(label.lower())
                    continue
                rows.append((label, cells))
            if heading == "Positions":
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
                    if cited < 2:
                        continue
                    rows.append((key, cells))
            block = [f"### {heading}", ""]
            if rows:
                block.append("| | " + " | ".join(_cell(name) for name in names) + " |")
                block.append("| " + " | ".join("---" for _ in range(len(names) + 1)) + " |")
                for label, cells in rows:
                    block.append("| " + " | ".join([_cell(label), *[_cell(cell) for cell in cells]]) + " |")
                block.append("")
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
            lines.extend([f"### {name} {{#profile-{item_id}}}", ""])
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
        for raw, name, body in sections:
            if name in AUDIT_HEADINGS or name in {"arguments for", "arguments against"}:
                continue
            rendered, gaps = prepare_section(self._rewrite(body))
            self._log_gaps(title, raw, gaps)
            if rendered is None:
                lines.extend([_gap_line(raw), ""])
                continue
            lines.extend([f"### {raw}", "", rendered, ""])
        for_body = by_name.get("arguments for", ("Arguments for", ""))[1]
        against_body = by_name.get("arguments against", ("Arguments against", ""))[1]
        if for_body or against_body:
            self._log_gaps(title, "Arguments for", prepare_section(for_body)[1])
            self._log_gaps(title, "Arguments against", prepare_section(against_body)[1])
            for_text = " ".join(_cited_sentences(for_body)) or NOT_FOUND_CELL
            against_text = " ".join(_cited_sentences(against_body)) or NOT_FOUND_CELL
            lines.extend(
                [
                    "### Arguments side by side",
                    "",
                    "| Arguments for | Arguments against |",
                    "| --- | --- |",
                    f"| {_cell(for_text)} | {_cell(against_text)} |",
                    "",
                ]
            )
            if for_text == NOT_FOUND_CELL or against_text == NOT_FOUND_CELL:
                missing = []
                if for_text == NOT_FOUND_CELL:
                    missing.append("arguments for")
                if against_text == NOT_FOUND_CELL:
                    missing.append("arguments against")
                lines.extend([_gap_line(", ".join(missing)), ""])
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
            "# Glossary",
            "",
            "A levy is a tax or charge put on a ballot for voters to accept or reject. "
            "Nonpartisan means the ballot does not list a party for that office. "
            "Cash on hand is the money a campaign reported still having at the end of a filing period. "
            "A filing period is the date range a finance report covers. "
            "Tier T1 is a primary or official source. T2 is an established nonpartisan reference. "
            "T3 is named journalism. T4 is an advocacy source and is quoted only as that group's view. "
            "A single source means the sentence rests on one record. "
            "An allegation is a claim someone has made that this guide has not confirmed. "
            "Not found means the listed places were searched and the fact was not in them.",
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
            "# Methodology",
            "",
            f"Version {ballot.get('report_version') or 'v1.0'} assembled on {self.today}. {env_line}",
            f"Sources flagged suspected_injection: {flagged}.",
            f"Parallel subagents: {subagents}.",
            f"Findings recorded: {counts['total']}. Accepted: {counts['accepted']}. Disputed: {counts['disputed']}.",
            "Disputed and unconfirmed claims are not used in summaries. Blockers are removed rather than left disputed.",
            "The reader edition drops empty template sections and moves search paths to the search log. "
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
        lines = ["# Disputed claims", ""]
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
        lines = ["# Corrections", ""]
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
