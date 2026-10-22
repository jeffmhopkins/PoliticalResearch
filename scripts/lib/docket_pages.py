"""Docket contest pages for the reader and the full edition.

The same page set is used for every race, measure, retention, and bill.
Numbers in money tables stay numbers. A missing statement stays a gap sentence.
Nothing here describes the layout.
"""

from __future__ import annotations

import html
import re

from lib.party import endorsement_cell, is_nonpartisan_contest
from lib.sentences import split_sentences
from lib.util import load_yaml

_RANGE_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4}),?\s+through\s+([A-Z][a-z]+ \d{1,2}, \d{4})"
)
_QUARTER_RE = re.compile(r"\bquarter\b", re.IGNORECASE)
_AMOUNT = r"(?:\$\s*\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s+dollars)"
_SPENT_RES = (
    re.compile(rf"({_AMOUNT})\s+spent\b", re.IGNORECASE),
    re.compile(rf"\bspent\s+({_AMOUNT})", re.IGNORECASE),
    re.compile(rf"\b(?:total\s+)?disbursements\s+of\s+({_AMOUNT})", re.IGNORECASE),
    re.compile(rf"({_AMOUNT})\s+in disbursements\b", re.IGNORECASE),
)
_VOTE_RE = re.compile(
    r"\bthe (House|Senate) passed\b[^.]*?\b(\d+)\s+yeas?\s+and\s+(\d+)\s+nays?\b",
    re.IGNORECASE,
)
_YES_RE = re.compile(r"\ba yes vote\b", re.IGNORECASE)
_NO_RE = re.compile(r"\ba no vote\b", re.IGNORECASE)
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
_PROFILE_HEADS = (
    ("Education", "education", "education"),
    ("Work", "occupational history", "work"),
    ("Time in elected office", "prior offices and public service", "time in elected office"),
    ("Recorded votes", "record vs rhetoric", "voting record"),
)
_BILL_DEEPER = (
    (
        "What is the history of this bill?",
        (
            "legislative history",
            "status timeline",
            "committee referrals and amendments",
            "companion bills",
            "section-by-section changes",
            "effective date",
            "current law and proposed change",
        ),
    ),
    (
        "Who sponsored it, and who drafted it?",
        ("sponsors and cosponsors", "drafting and model legislation", "implementing agency"),
    ),
    (
        "Who lobbied or testified?",
        ("interest groups and lobbying", "hearing testimony", "sponsor contributions"),
    ),
    (
        "How did the chambers vote?",
        ("roll-call votes", "party vote counts", "veto and override"),
    ),
    (
        "How did your legislators vote?",
        ("your legislators votes",),
    ),
)
_MEASURE_SUMMARY = {
    "official title",
    "plain-language summary",
    "what a yes vote does",
    "what a no vote does",
    "arguments for",
    "arguments against",
    "organizations supporting",
    "organizations opposing",
    "supporters and opponents",
    "fiscal impact",
}
_BILL_SUMMARY = {
    "bill identity",
    "plain summary",
    "arguments for",
    "arguments against",
    "fiscal note",
    "current law and proposed change",
}


def _lead(text: str, limit: int = 1) -> str:
    from lib.quality import _bind_trailing_markers

    parts = [part.strip() for part in split_sentences(_bind_trailing_markers(text or "")) if part.strip()]
    return " ".join(parts[:limit])


def _markers(text: str) -> str:
    from lib.quality import MARKER_RE

    return "".join(f"[^{number}]" for number in MARKER_RE.findall(text or ""))


def _month_index(label: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", label.strip())
    if not match or match.group(1) not in _MONTHS:
        return None
    month = _MONTHS.index(match.group(1)) + 1
    return int(match.group(3)), month, int(match.group(2))


def coverage_months(text: str) -> str | None:
    """Inclusive months when the filing states a start and an end.

    A quarter is three months. A single as-of date is not a coverage length.
    """
    match = _RANGE_RE.search(text or "")
    if match:
        start = _month_index(match.group(1))
        end = _month_index(match.group(2))
        if start and end:
            months = (end[0] - start[0]) * 12 + (end[1] - start[1]) + 1
            if months > 0:
                return str(months)
    if _QUARTER_RE.search(text or ""):
        return "3"
    return None


def _spent_amount(text: str) -> str | None:
    from lib.guide_layout import _format_dollars

    plain = text or ""
    for pattern in _SPENT_RES:
        match = pattern.search(plain)
        if match:
            return _format_dollars(match.group(1))
    return None


def _numeric_cell(shown: str) -> bool:
    plain = re.sub(r"<[^>]+>", "", shown or "")
    plain = re.sub(r"\[\^[^\]]+\]", "", plain).strip()
    return bool(re.fullmatch(r"\$\d[\d,]*", plain))


def _cell_plain(shown: str) -> str:
    plain = re.sub(r"<[^>]+>", "", shown or "")
    plain = re.sub(r"\[\^[^\]]+\]", "", plain)
    return re.sub(r"\s+", " ", plain).strip()


def _clip_words(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" .")
    if len(cleaned) <= limit:
        return cleaned
    chosen: list[str] = []
    for word in cleaned.split():
        trial = " ".join(chosen + [word])
        if len(trial) > limit:
            break
        chosen.append(word)
    while chosen and chosen[-1].lower().strip(";,") in {
        "on",
        "of",
        "the",
        "a",
        "an",
        "and",
        "or",
        "in",
        "for",
        "to",
        "from",
    }:
        chosen.pop()
    clipped = " ".join(chosen).strip(" ;,")
    if ";" in clipped:
        head, tail = clipped.split(";", 1)
        if len(tail.split()) < 3:
            clipped = head.strip(" ;,")
    return clipped or cleaned[:limit].rsplit(" ", 1)[0]


def bill_token(title: str) -> str:
    """`HJR 5019` and `CS/HJR 1F` both become a token a measure draft can contain."""
    match = re.search(r"\b(HJR|SJR|HB|SB)\s*([0-9]+[A-Za-z]?)\b", title or "", re.IGNORECASE)
    if not match:
        return ""
    return (match.group(1) + match.group(2)).lower()


def display_contest_title(title: str) -> str:
    """A contents label that stays unique when several contests share a ballot heading."""
    text = re.sub(r"\s+", " ", title or "").strip()
    lowered = text.lower()
    judge = re.search(r"Shall (?:Justice|Judge) (.+?) of the", text)
    if judge:
        name = judge.group(1).strip()
        if "supreme court" in lowered:
            return f"Supreme Court: {name}"
        return f"District Court of Appeal: {name}"
    if "lagoon" in lowered:
        return "Brevard: Save Our Indian River Lagoon tax"
    if "millage" in lowered or "teacher pay" in lowered:
        return "Brevard: school millage"
    if "school" in lowered and ("half-cent" in lowered or "sales surtax" in lowered or "sales tax" in lowered):
        return "Brevard: school sales tax"
    amendment = re.match(r"No\.\s*(\d+)\b", text, re.IGNORECASE)
    if amendment and "amendment" in lowered:
        subject = text.split(":")[-1].strip()
        return f"Amendment {amendment.group(1)}: {_clip_words(subject, 52)}"
    from lib.guide_layout import _title_pair

    short, _subtitle = _title_pair(text)
    return short or text


def _append_back_link(lines: list[str]) -> None:
    """Put the back link inside a trailing tail so a short section is not left alone."""
    link = "[Back to ballot](#your-ballot-at-a-glance)"
    end = len(lines)
    while end > 0 and lines[end - 1] == "":
        end -= 1
    if end > 0 and lines[end - 1] == ":::":
        depth = 1
        for index in range(end - 2, -1, -1):
            stripped = lines[index].strip()
            if not stripped:
                continue
            if stripped == ":::":
                depth += 1
                continue
            if stripped.startswith(":::"):
                depth -= 1
                if depth == 0:
                    if stripped == "::: {.tail}":
                        lines.insert(end - 1, "")
                        lines.insert(end - 1, link)
                        return
                    break
    lines.extend([link, ""])


def _sheet(lines: list[str], opener: bool = False) -> list[str]:
    """Only a race or measure opening starts a new page."""
    if not opener:
        body = list(lines)
        if body and body[-1] != "":
            body.append("")
        return body
    body = ["::: {.sheet .opener}", ""]
    body.extend(lines)
    if body[-1] != "":
        body.append("")
    body.extend([":::", ""])
    return body


def _card_party(model, candidate: dict, contest: dict) -> str:
    if is_nonpartisan_contest(contest):
        return "Nonpartisan"
    from lib.guide_layout import _party_abbr

    abbr = _party_abbr(model.workspace, candidate)
    return abbr or "Nonpartisan"


def _pair(people_blocks: list[list[str]], count: int) -> list[str]:
    if count <= 1:
        klass = "{.pair .count-1}"
    elif count >= 3:
        klass = "{.pair .count-many}"
    else:
        klass = "{.pair}"
    lines = [f"::: {klass}", ""]
    for block in people_blocks:
        lines.extend(["::: card", ""])
        lines.extend(block)
        if lines[-1] != "":
            lines.append("")
        lines.extend([":::", ""])
    lines.extend([":::", ""])
    return lines


def _section_text(model, sections: dict, name: str) -> str:
    from lib.guide_layout import prepare_section

    found = sections.get(name)
    if not found:
        return ""
    rendered, _gaps = prepare_section(model._rewrite(found[1]))
    return rendered or ""


def _gap_or(model, text: str, subject: str) -> str:
    from lib.guide_layout import _gap_line

    if text and "[^" in text:
        return model._show_prose(text)
    return _gap_line(subject)


def _vote_sentence(draft: str, kind: str) -> str:
    pattern = _YES_RE if kind == "yes" else _NO_RE
    for sentence in split_sentences(draft or ""):
        if pattern.search(sentence) and "[^" in sentence:
            return sentence.strip()
    return ""


def build_docket_contest(model, contest: dict, group: str) -> list[str]:
    kind = str(contest.get("type") or "")
    if kind == "measure":
        return _measure(model, contest, group)
    if kind == "legislation":
        return _bill(model, contest, group)
    if kind == "judicial-retention" or contest.get("level") == "judicial":
        return _retention(model, contest, group)
    return _race(model, contest, group)


def _title_lines(model, contest: dict, item_id: str) -> list[str]:
    title = str(contest.get("title") or model.titles.get(item_id) or item_id)
    shown = display_contest_title(title)
    lines = [f"## {shown} {{#contest-{item_id} .contest-title}}", ""]
    if title and title.lower() != shown.lower():
        lines.extend([f'<p class="official-title">{html.escape(re.sub(r"\\s+", " ", title).strip())}</p>', ""])
    return lines


def _office_lines(model, contest: dict, draft: str, sections: dict) -> list[str]:
    from lib.guide_layout import _TERM_LENGTH_RE, _gap_line, _matching_cited

    lines = ["### What does this office do?", ""]
    duties = ""
    for name in ("what the office controls", "contest", "court and term", "retention question"):
        duties = _section_text(model, sections, name)
        if duties:
            break
    if not duties:
        cited = _lead(draft, 1)
        duties = cited if "[^" in cited else ""
    lines.append(duties or _gap_line("what this office does"))
    lines.append("")
    term = _matching_cited(draft, _TERM_LENGTH_RE) or ""
    if term:
        lines.extend([model._show_prose(term), ""])
    if not re.search(r"\bpay\b|\bsalary\b", draft or "", re.IGNORECASE):
        lines.extend(["Pay was not in the sources checked.", ""])
    return lines


def _people_cards(model, contest: dict, people: list[dict]) -> list[str]:
    blocks = []
    any_incumbent = any(person.get("incumbent") is True for person in people)
    for candidate in people:
        item_id = str(candidate.get("item_id") or candidate.get("id") or "")
        name = str(candidate.get("name") or model.titles.get(item_id) or item_id)
        party = _card_party(model, candidate, contest)
        if candidate.get("incumbent") is True:
            role = f"{party} · incumbent"
        elif any_incumbent:
            role = f"{party} · challenger"
        else:
            role = party
        draft = model._draft(item_id)
        from lib.guide_layout import _section_dict

        sections = _section_dict(draft)
        job = _section_text(model, sections, "occupational history") or _section_text(
            model, sections, "prior offices and public service"
        )
        job = _lead(job, 1) if job else ""
        block = [
            f"### {name} {{#candidate-{item_id} .candidate-name}}",
            "",
            f'<p class="official-title">{html.escape(role)}</p>',
            "",
            _gap_or(model, job, "current job"),
            "",
        ]
        blocks.append(block)
    lines = ["### Who is running?", ""]
    if is_nonpartisan_contest(contest):
        lines.extend(["Nonpartisan means the ballot does not list a party.", ""])
    elif any_incumbent:
        lines.extend(
            [
                "Incumbent means the person already holds this office. Challenger means the person is running against the incumbent.",
                "",
            ]
        )
    lines.extend(["Candidates appear in ballot order.", ""])
    lines.extend(_pair(blocks, len(people)))
    from lib.guide_layout import _other_people

    for candidate in _other_people(contest):
        name = str(candidate.get("name") or "")
        if not name:
            continue
        label = "Withdrawn" if candidate.get("withdrawn") else "Write-in"
        lines.extend([f'<p class="official-title">{html.escape(label)}: {html.escape(name)}</p>', ""])
    return lines


def _money_table(model, contest: dict, people: list[dict]) -> list[str]:
    from lib.guide_layout import (
        NOT_FOUND_CELL,
        _MONEY_ROWS,
        _assign_cells,
        _emit_table,
        _section_dict,
        comparison_tables,
    )

    bundles = []
    for candidate in people:
        item_id = str(candidate.get("item_id") or candidate.get("id") or "")
        sections = _section_dict(model._draft(item_id))
        profile = load_yaml(model.workspace / "items" / item_id / "profile.yaml") or {}
        bundles.append((candidate, sections, profile if isinstance(profile, dict) else {}))
    if not bundles:
        return []
    names = [str(candidate.get("name") or "") for candidate, _sections, _profile in bundles]
    assigned = [_assign_cells(sections, profile, _MONEY_ROWS) for _candidate, sections, profile in bundles]
    rows: list[tuple[str, list[str]]] = []
    month_cells = []
    outside_numeric = False
    outside_cells = []
    for cells, (_candidate, sections, _profile) in zip(assigned, bundles):
        receipts = cells.get("Receipts", "")
        funding = sections.get("campaign funding", ("", ""))[1]
        months = None
        mark = ""
        for sentence in split_sentences(funding or receipts):
            found = coverage_months(sentence)
            if found:
                months = found
                mark = _markers(sentence)
                break
        if not mark:
            mark = _markers(receipts)
        month_cells.append(f'<span class="num">{months}{mark}</span>' if months else NOT_FOUND_CELL)
        outside = model._show_cell(cells.get("Outside spending", ""), "x", "x", "Outside spending")
        outside_cells.append(outside if _numeric_cell(outside) else NOT_FOUND_CELL)
        if _numeric_cell(outside):
            outside_numeric = True
    rows.append(("Months in this report", month_cells))
    for label, hint in (
        ("Raised", "Receipts"),
        ("Cash on hand", "Cash on hand"),
    ):
        shown = []
        for cells, (candidate, _sections, _profile) in zip(assigned, bundles):
            name = str(candidate.get("name") or "")
            shown.append(model._show_cell(cells.get(label if label != "Raised" else "Receipts", ""), "x", name, hint))
        if any(_numeric_cell(cell) for cell in shown):
            rows.append((label, [cell if _numeric_cell(cell) else NOT_FOUND_CELL for cell in shown]))
    spent_cells = []
    any_spent = False
    for cells, (_candidate, sections, _profile) in zip(assigned, bundles):
        funding = sections.get("campaign funding", ("", ""))[1]
        amount = None
        mark = ""
        for sentence in split_sentences(funding or cells.get("Receipts", "")):
            found = _spent_amount(sentence)
            if found:
                amount = found
                mark = _markers(sentence)
                break
        if amount:
            any_spent = True
            spent_cells.append(f'<span class="num">{amount}{mark}</span>')
        else:
            spent_cells.append(NOT_FOUND_CELL)
    if any_spent:
        rows.append(("Spent", spent_cells))
    for label, hint in (
        ("Self-funding or loans", "Self-funding or loans"),
        ("Share from small donors", "Share from small donors"),
        ("Large donors", "Large donors"),
        ("PAC money", "PAC money"),
        ("Party money", "Party money"),
    ):
        shown = []
        keep = False
        for cells in assigned:
            cell = model._show_cell(cells.get(label, ""), "x", "x", hint)
            if _numeric_cell(cell):
                keep = True
                shown.append(cell)
            else:
                shown.append(NOT_FOUND_CELL)
        if keep:
            rows.append((label, shown))
    if outside_numeric:
        rows.append(("Outside spending", outside_cells))
    kept = []
    for label, cells in rows:
        if all(_cell_plain(cell).lower() in {"", "not found"} for cell in cells):
            continue
        kept.append((label, cells))
    if not kept:
        return ["No public record found for campaign funds.", ""]
    lines = ["### Who is paying for their campaign?", ""]
    if not outside_numeric:
        lines.extend(
            [
                "Outside spending was not in the finance summaries checked for any candidate in this race.",
                "",
            ]
        )
    lines.extend(["Amounts are rounded to the nearest dollar. Cash on hand is money the campaign still reported having.", ""])
    for headers, body in comparison_tables(names, kept):
        headers = ["Amount", *headers[1:]]
        lines.extend(["::: {.comparison .money}", ""])
        lines.extend(_emit_table(headers, body))
        lines.extend([":::", ""])
    return lines


def _support_lines(model, contest: dict, people: list[dict]) -> list[str]:
    from lib.guide_layout import _gap_line, _section_dict

    endorse_blocks = []
    legal_blocks = []
    unchecked = ("labor_consumer", "misuse_of_office")
    all_unchecked = bool(people)
    for candidate in people:
        item_id = str(candidate.get("item_id") or candidate.get("id") or "")
        name = str(candidate.get("name") or item_id)
        sections = _section_dict(model._draft(item_id))
        claims_doc = load_yaml(model.workspace / "items" / item_id / "claims.yaml") or {}
        claims = claims_doc.get("claims") if isinstance(claims_doc, dict) else []
        endorsed = endorsement_cell(claims if isinstance(claims, list) else [])
        if not endorsed:
            endorsed = _section_text(model, sections, "endorsements")
        endorsed = _lead(endorsed, 1)
        endorse_blocks.append(
            [
                f"### {name}",
                "",
                _gap_or(model, endorsed, "a dated endorsement"),
                "",
            ]
        )
        legal = _section_text(model, sections, "legal issues")
        legal = _lead(legal, 2)
        legal_blocks.append(
            [
                f"### {name}",
                "",
                _gap_or(model, legal, "legal or ethics issues"),
                "",
            ]
        )
        profile = load_yaml(model.workspace / "items" / item_id / "profile.yaml") or {}
        sweep = profile.get("legal_sweep") if isinstance(profile, dict) else None
        if not isinstance(sweep, dict):
            all_unchecked = False
            continue
        for key in unchecked:
            status = str((sweep.get(key) or {}).get("status") or "") if isinstance(sweep.get(key), dict) else ""
            if status != "not_checked":
                all_unchecked = False
    endorse_found = any("[^" in "\n".join(block) for block in endorse_blocks)
    legal_found = any("[^" in "\n".join(block) for block in legal_blocks)
    lines = ["### Who supports them?", ""]
    if endorse_found:
        lines.extend(_pair(endorse_blocks, len(people)))
    else:
        lines.extend(["No public record found for a dated endorsement.", ""])
    lines.extend(["### Any legal or ethics issues?", ""])
    if legal_found:
        lines.extend(_pair(legal_blocks, len(people)))
    elif all_unchecked:
        lines.extend(["No public record found for legal, labor, consumer, or misuse-of-office checks.", ""])
    else:
        lines.extend(["No public record found for legal or ethics issues.", ""])
    return lines


def _profile_fields(model, sections: dict, mapped: dict | None = None) -> list[str]:
    filled = []
    empty = []
    for heading, key, label in _PROFILE_HEADS:
        rendered = mapped[key] if mapped is not None else _section_text(model, sections, key)
        if rendered and "[^" in rendered:
            filled.append((heading, rendered))
        else:
            empty.append(label)
    lines: list[str] = []
    for heading, rendered in filled:
        lines.extend([f"### {heading}", "", rendered, ""])
    if empty:
        lines.extend([f"No public records found for: {', '.join(empty)}.", ""])
    return lines


def _profile_block(model, item_id: str, name: str, sections: dict, mapped: dict | None = None) -> list[str]:
    body = [f"## {name} {{#profile-{item_id} .profile-title}}", ""]
    body.extend(_profile_fields(model, sections, mapped))
    if model.edition != "reader":
        body.extend(model._access_note_lines(item_id))
    lines = ["::: {.profile}", ""]
    lines.extend(body)
    if lines[-1] != "":
        lines.append("")
    lines.extend([":::", ""])
    return lines


def _profiles(model, contest: dict, people: list[dict], group: str) -> list[str]:
    del group
    from lib.guide_layout import _other_people, _section_dict

    lines: list[str] = []
    ordered = list(people) + _other_people(contest)
    for candidate in ordered:
        item_id = str(candidate.get("item_id") or candidate.get("id") or "")
        if not item_id or not (model.workspace / "items" / item_id / "draft.md").exists():
            continue
        name = str(candidate.get("name") or model.titles.get(item_id) or item_id)
        sections = _section_dict(model._draft(item_id))
        lines.extend(_profile_block(model, item_id, name, sections))
    return lines


def _race(model, contest: dict, group: str) -> list[str]:
    from lib.guide_layout import _people, _section_dict, _section_pairs

    item_id = str(contest.get("item_id") or contest.get("id"))
    draft = model._draft(item_id)
    sections = _section_dict(draft)
    model._log_section_gaps(str(contest.get("title") or item_id), _section_pairs(draft))
    model._log_profile_gaps(contest)
    people = _people(contest)
    opening = _title_lines(model, contest, item_id)
    if group:
        opening = [f"# {group} {{.ballot-group}}", ""] + opening
    opening.extend(_office_lines(model, contest, draft, sections))
    opening.extend(_people_cards(model, contest, people))
    lines = _sheet(opening, opener=True)
    if len(people) != 1:
        lines.extend(_positions(model, contest, people))
    lines.extend(_money_table(model, contest, people))
    lines.extend(_support_lines(model, contest, people))
    lines.extend(_profiles(model, contest, people, group or "Race"))
    _append_back_link(lines)
    return lines


def _issue_already_said(cell: str, base: str) -> bool:
    from lib.guide_layout import NOT_FOUND_CELL, _sentence_key

    if not cell or cell == NOT_FOUND_CELL or "[^" not in str(cell):
        return True
    key = _sentence_key(cell).rstrip(".!?")
    base_key = _sentence_key(base or "").rstrip(".!?")
    if not key:
        return True
    if not base_key:
        return False
    return key in base_key or base_key in key


def _positions(model, contest: dict, people: list[dict]) -> list[str]:
    from lib.guide_layout import NOT_FOUND_CELL, _duplicate_issue_row, _section_dict

    lines = ["### Where do they stand?", ""]
    bundles = []
    for candidate in people:
        item_id = str(candidate.get("item_id") or candidate.get("id") or "")
        sections = _section_dict(model._draft(item_id))
        profile = load_yaml(model.workspace / "items" / item_id / "profile.yaml") or {}
        bundles.append((candidate, sections, profile if isinstance(profile, dict) else {}))
    position_cells = []
    for candidate, sections, _profile in bundles:
        text = _section_text(model, sections, "positions in own words")
        position_cells.append(text or NOT_FOUND_CELL)
    questions: list[tuple[str, list[str]]] = [("positions", position_cells)]
    keys: list[str] = []
    for _candidate, _sections, profile in bundles:
        issues = profile.get("issues") if isinstance(profile, dict) else None
        if isinstance(issues, dict):
            for key in issues:
                if key not in keys:
                    keys.append(str(key))
    for key in keys:
        cells = []
        for _candidate, _sections, profile in bundles:
            text = str((profile.get("issues") or {}).get(key) or "").strip()
            cells.append(text if text and "[^" in text else NOT_FOUND_CELL)
        fresh = [
            NOT_FOUND_CELL if _issue_already_said(cell, base) else cell
            for cell, base in zip(cells, position_cells)
        ]
        if all(cell == NOT_FOUND_CELL or "[^" not in str(cell) for cell in fresh):
            continue
        if _duplicate_issue_row(fresh, position_cells):
            continue
        questions.append((key, fresh))
    for label, cells in questions:
        topic = "positions" if label == "positions" else label.replace("_", " ")
        lines.extend([f"### What has each candidate said about {topic}?", ""])
        blocks = []
        for candidate, cell in zip(people, cells):
            name = str(candidate.get("name") or "")
            if cell and cell != NOT_FOUND_CELL and "[^" in cell:
                shown = model._show_prose(_lead(cell, 3))
            else:
                shown = f"No public statement found on {topic}."
            blocks.append([f"### {name}", "", shown, ""])
        lines.extend(_pair(blocks, len(people)))
    return lines


def _summary_box(model, contest, group, item_id, about, yes, no, support, oppose, cost, exact, marker: str) -> list[str]:
    from lib.guide_layout import _vote_pair

    lines = [f"<!-- {marker} -->", ""]
    lines.extend(_title_lines(model, contest, item_id))
    if group:
        lines = [f"# {group} {{.ballot-group}}", ""] + lines
    lines.extend(["### What is this about?", "", about or "No public record found.", ""])
    yes_body = yes if yes and "[^" in yes else (about if about and "[^" in about else "No public record found.")
    no_body = no if no and "[^" in no else "No public record found."
    lines.extend(_vote_pair("YES", yes_body, "NO", no_body))
    lines.extend(["### Who supports it, and who opposes it?", ""])
    support_body = support if support and "[^" in support else "No public record found."
    oppose_body = oppose if oppose and "[^" in oppose else "No public record found."
    if support_body == oppose_body == "No public record found.":
        lines.extend(["No public record found for supporters or opponents.", ""])
    else:
        lines.extend(
            _pair(
                [
                    ["#### Supports it", "", support_body, ""],
                    ["#### Opposes it", "", oppose_body, ""],
                ],
                2,
            )
        )
    lines.extend(["### What would it cost?", "", cost if cost and "[^" in cost else "No public record found.", ""])
    lines.extend(
        [
            "::: ballot-words",
            "",
            "#### Exact words on your ballot",
            "",
            exact or "No public record found.",
            "",
            ":::",
            "",
        ]
    )
    return lines


def _measure(model, contest: dict, group: str) -> list[str]:
    from lib.guide_layout import _section_dict, _section_pairs, prepare_section

    item_id = str(contest.get("item_id") or contest.get("id"))
    title = str(contest.get("title") or item_id)
    draft = model._draft(item_id)
    sections = _section_dict(draft)
    model._log_section_gaps(title, _section_pairs(draft))
    about = _lead(_section_text(model, sections, "plain-language summary"), 4)
    yes = _lead(_section_text(model, sections, "what a yes vote does"), 2) or _vote_sentence(draft, "yes")
    no = _lead(_section_text(model, sections, "what a no vote does"), 2) or _vote_sentence(draft, "no")
    support = _lead(
        _section_text(model, sections, "organizations supporting")
        or _section_text(model, sections, "arguments for"),
        2,
    )
    oppose = _lead(
        _section_text(model, sections, "organizations opposing")
        or _section_text(model, sections, "arguments against"),
        2,
    )
    cost = _lead(_section_text(model, sections, "fiscal impact"), 1)
    exact = _section_text(model, sections, "official title")
    lines = _sheet(
        _summary_box(model, contest, group, item_id, about, yes, no, support, oppose, cost, exact, "docket-measure"),
        opener=True,
    )
    for raw, name, body in _section_pairs(draft):
        if name in _MEASURE_SUMMARY or name in {"sources and retrieval dates", "item changelog", "findings and disputes"}:
            rendered, gaps = prepare_section(model._rewrite(body))
            model._log_gaps(title, raw, gaps)
            continue
        rendered, gaps = prepare_section(model._rewrite(body))
        model._log_gaps(title, raw, gaps)
        if not rendered:
            continue
        lines.extend([f"### {raw}", "", rendered, ""])
    for bill in model.bill_folds.get(item_id, []):
        lines.extend(_bill_deeper(model, bill))
    _append_back_link(lines)
    return lines


def _bill_deeper(model, contest: dict) -> list[str]:
    """History and votes that belong inside a measure, with empty groups left out."""
    from lib.guide_layout import _emit_table, _section_dict, _section_pairs, prepare_section
    from lib.quality import MARKER_RE

    item_id = str(contest.get("item_id") or contest.get("id"))
    title = str(contest.get("title") or item_id)
    draft = model._draft(item_id)
    sections = _section_dict(draft)
    model._log_section_gaps(title, _section_pairs(draft))
    lines: list[str] = []
    used = set(_BILL_SUMMARY)
    for heading, names in _BILL_DEEPER:
        block = [f"### {heading}", ""]
        any_part = False
        for name in names:
            used.add(name)
            found = sections.get(name)
            raw = found[0] if found else name
            rendered = _section_text(model, sections, name)
            if not rendered:
                continue
            any_part = True
            if name == "roll-call votes":
                table_rows = []
                for sentence in split_sentences(rendered):
                    match = _VOTE_RE.search(MARKER_RE.sub("", sentence))
                    if not match:
                        continue
                    mark = _markers(sentence)
                    table_rows.append([match.group(1).title(), f"{match.group(2)}{mark}", match.group(3)])
                block.extend([f"#### {raw}", ""])
                if table_rows:
                    block.extend(_emit_table(["Chamber", "Yes", "No"], table_rows))
                else:
                    block.extend([rendered, ""])
                continue
            block.extend([f"#### {raw}", "", rendered, ""])
        if any_part:
            lines.extend(block)
    extra: list[tuple[str, str]] = []
    for raw, name, body in _section_pairs(draft):
        if name in used or name in {
            "sources and retrieval dates",
            "item changelog",
            "findings and disputes",
            "related litigation",
        }:
            continue
        rendered, gaps = prepare_section(model._rewrite(body))
        model._log_gaps(title, raw, gaps)
        if rendered:
            extra.append((raw, rendered))
    if extra:
        lines.extend(["::: {.tail}", ""])
        for raw, rendered in extra:
            lines.extend([f"### {raw}", "", rendered, ""])
        lines.extend([":::", ""])
    litigation = _section_text(model, sections, "related litigation")
    # Keep a gap with the summary side of the section, not alone at the end.
    note = ["### Related litigation", "", litigation or "No public record found.", ""]
    return note + lines


def _bill(model, contest: dict, group: str) -> list[str]:
    from lib.guide_layout import _section_dict, _section_pairs

    item_id = str(contest.get("item_id") or contest.get("id"))
    title = str(contest.get("title") or item_id)
    draft = model._draft(item_id)
    sections = _section_dict(draft)
    model._log_section_gaps(title, _section_pairs(draft))
    about = _lead(_section_text(model, sections, "plain summary"), 4)
    yes = _vote_sentence(draft, "yes") or _lead(_section_text(model, sections, "arguments for"), 2) or about
    no = _vote_sentence(draft, "no") or _lead(_section_text(model, sections, "arguments against"), 2)
    support = _lead(_section_text(model, sections, "arguments for"), 2)
    oppose = _lead(_section_text(model, sections, "arguments against"), 2)
    cost = _lead(_section_text(model, sections, "fiscal note"), 1)
    exact = _section_text(model, sections, "bill identity")
    lines = _sheet(
        _summary_box(model, contest, group, item_id, about, yes, no, support, oppose, cost, exact, "docket-bill"),
        opener=True,
    )
    lines.extend(_bill_deeper(model, contest))
    _append_back_link(lines)
    return lines


def _retention(model, contest: dict, group: str) -> list[str]:
    from lib.guide_layout import _section_dict, _section_pairs

    item_id = str(contest.get("item_id") or contest.get("id"))
    draft = model._draft(item_id)
    sections = _section_dict(draft)
    model._log_section_gaps(str(contest.get("title") or item_id), _section_pairs(draft))
    question = _section_text(model, sections, "retention question") or _section_text(model, sections, "court and term")
    about = _lead(question, 3)
    yes = _vote_sentence(draft, "yes") or about
    no = _vote_sentence(draft, "no")
    lines = _summary_box(
        model,
        contest,
        group,
        item_id,
        about,
        yes,
        no,
        _lead(_section_text(model, sections, "endorsements"), 1),
        "",
        _lead(_section_text(model, sections, "fiscal impact"), 1),
        _lead(question, 1),
        "docket-measure",
    )
    mapped = {
        "education": _section_text(model, sections, "education"),
        "occupational history": _section_text(model, sections, "appointing authority"),
        "prior offices and public service": _section_text(model, sections, "court and term"),
        "record vs rhetoric": _section_text(model, sections, "notable rulings"),
    }
    name = display_contest_title(str(contest.get("title") or model.titles.get(item_id) or item_id))
    lines.extend([f"## {name} {{#profile-{item_id} .profile-title}}", ""])
    lines.extend(_profile_fields(model, sections, mapped))
    if model.edition != "reader":
        lines.extend(model._access_note_lines(item_id))
    lines = _sheet(lines, opener=True)
    _append_back_link(lines)
    return lines
