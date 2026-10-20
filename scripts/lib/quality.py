"""Citation, symmetry, readability, staleness, link, and edge-case checks."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

from lib.util import RETRIEVED_RE, iter_items, load_config, load_yaml, norm_heading

MARKER_RE = re.compile(r"\[\^(\d+)\]")
WORK_RE = re.compile(r"^\[(\d+)\] ", re.MULTILINE)
FOOTNOTE_DEF_RE = re.compile(r"^\[\^\d+\]:")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
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
GAP_PREFIXES = (
    "not found",
    "no issue positions",
    "limited public record",
    "omitted because",
    "omitted.",
    "none.",
    "none",
)
EXEMPT_HEADINGS = {
    "how to use this guide",
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
}
CANDIDATE_CORE = [
    "identity",
    "prior offices and public service",
    "occupational history",
    "education",
    "campaign funding",
    "record vs rhetoric",
    "positions in own words",
    "debates and forums",
    "endorsements",
    "legal issues",
    "strongest case",
]
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
    "supporters and opponents",
]
LEGISLATION_CORE = [
    "bill identity",
    "sponsors and cosponsors",
    "status timeline",
    "plain summary",
    "current law and proposed change",
    "fiscal note",
    "roll-call votes",
]
JUDICIAL_CORE = [
    "retention question",
    "court and term",
    "appointing authority",
    "performance evaluation",
    "notable rulings",
    "discipline record",
    "issue positions",
]
SUMMARY_TYPES = {"race", "measure", "legislation", "judicial-retention"}


def sentence_count(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0
    parts = [part for part in SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
    return len(parts)


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


def semantic_claim_errors(doc: dict, label: str) -> list[str]:
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
        if claim.get("about_person"):
            attrs = claim.get("identity_attributes") or []
            if not isinstance(attrs, list) or len(attrs) < 2:
                errors.append(f"{label}: {cid} is about a person but identity_attributes has fewer than 2 anchors")
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
                if previous and previous != cid:
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
    return len(match.group(1)), norm_heading(match.group(2))


def factual_blocks(text: str) -> list[str]:
    body = strip_front_matter(text)
    kept: list[str] = []
    for raw in body.splitlines():
        if FOOTNOTE_DEF_RE.match(raw.strip()):
            continue
        kept.append(raw)
    blocks: list[str] = []
    buf: list[str] = []
    stack: list[int] = []

    def flush(exempt: bool) -> None:
        nonlocal buf
        if buf and not exempt:
            block = "\n".join(buf).strip()
            if block:
                blocks.append(block)
        buf = []

    exempt = False
    for line in kept:
        heading = _heading(line)
        if heading:
            flush(exempt)
            level, title = heading
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
    return [part.strip(" -*") for part in SENTENCE_SPLIT_RE.split(cleaned) if part.strip(" -*")]


def _is_gap_text(text: str) -> bool:
    sentences = _sentences(text)
    if not sentences:
        return True
    return all(part.lower().startswith(GAP_PREFIXES) for part in sentences)


def prose_marker_errors(text: str, label: str) -> list[str]:
    errors: list[str] = []
    for block in factual_blocks(text):
        if block.startswith(">"):
            continue
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
                if _is_gap_text(row):
                    continue
                if "[^" not in row:
                    errors.append(f"{label}: table row has no citation marker: {row.strip()[:120]}")
            continue
        lines = block.splitlines()
        bullet_lines = [line for line in lines if line.strip().startswith(("- ", "* "))]
        if bullet_lines and len(bullet_lines) == len([line for line in lines if line.strip()]):
            for line in bullet_lines:
                errors.extend(_sentence_marker_errors(line.strip()[2:].strip(), label, "list item"))
            continue
        errors.extend(_sentence_marker_errors(block, label, "sentence"))
    return errors


def _sentence_marker_errors(block: str, label: str, kind: str) -> list[str]:
    if _is_gap_text(block) and "[^" not in block:
        return []
    protected = MARKER_RE.sub(" [M] ", block)
    errors = []
    for part in SENTENCE_SPLIT_RE.split(protected.strip()):
        text = part.strip()
        if not text:
            continue
        plain = text.replace("[M]", "").strip()
        if not plain or _is_gap_text(plain):
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
    return {int(value) for value in MARKER_RE.findall("\n".join(body_lines))}


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
            if marker is None:
                continue
            index[marker] = (item.name, claim, source)
    return index


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
    index = claim_index(workspace)
    for item in iter_items(workspace):
        draft_path = item / "draft.md"
        if not draft_path.exists():
            continue
        text = draft_path.read_text(encoding="utf-8")
        label = f"items/{item.name}/draft.md"
        errors.extend(prose_marker_errors(text, label))
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
    guide_path = workspace / "final" / "guide.md"
    if guide or guide_path.exists():
        if not guide_path.exists():
            errors.append("final/guide.md is missing")
        else:
            text = guide_path.read_text(encoding="utf-8")
            errors.extend(prose_marker_errors(text, "final/guide.md"))
            errors.extend(summary_errors(text, "final/guide.md", index))
            cited = works_cited_numbers(text)
            for number in sorted(marker_numbers(text)):
                if number not in index:
                    errors.append(f"final/guide.md: marker {number} does not resolve to a claim source")
                if number not in cited:
                    errors.append(f"final/guide.md: marker {number} has no works-cited entry")
            for number in sorted(cited):
                if number not in index:
                    errors.append(f"final/guide.md: works-cited [{number}] has no claim source")
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
            for name in CANDIDATE_CORE:
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
        for index, (left_id, left_sections) in enumerate(bodies):
            for right_id, right_sections in bodies[index + 1 :]:
                for name in CANDIDATE_CORE:
                    left = left_sections.get(name, "")
                    right = right_sections.get(name, "")
                    if _is_gap_text(left) or _is_gap_text(right):
                        continue
                    left_words = word_count(left)
                    right_words = word_count(right)
                    peak = max(left_words, right_words)
                    if peak == 0:
                        continue
                    if min(left_words, right_words) / peak < 0.5:
                        errors.append(
                            f"{contest.get('id')}: section '{name}' word count for {left_id} ({left_words}) "
                            f"and {right_id} ({right_words}) is below half the longer one"
                        )
        scores = []
        for item_id, effort in efforts:
            scores.append((item_id, int(effort.get("searches") or 0) + int(effort.get("fetches") or 0), effort))
        peak = max((score for _item, score, _effort in scores), default=0)
        if peak > 0:
            for item_id, score, effort in scores:
                if score < ratio * peak and not str(effort.get("explanation") or "").strip():
                    errors.append(
                        f"{item_id}: effort {score} is below {ratio:.0%} of the race max {peak}. "
                        "Close the gap or record explanation in effort.json."
                    )
        if contest.get("type") == "race":
            race_draft = workspace / "items" / str(contest.get("item_id") or contest.get("id")) / "draft.md"
            if race_draft.exists():
                sections = section_map(race_draft.read_text(encoding="utf-8"))
                if "write-in candidates" not in sections:
                    errors.append(f"{contest.get('id')}: race draft is missing 'Write-in candidates'")
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict) or contest.get("type") != "measure":
            continue
        item_id = str(contest.get("item_id") or contest.get("id"))
        draft = workspace / "items" / item_id / "draft.md"
        if not draft.exists():
            continue
        sections = section_map(draft.read_text(encoding="utf-8"))
        for_words = word_count(sections.get("arguments for", ""))
        against_words = word_count(sections.get("arguments against", ""))
        peak = max(for_words, against_words)
        if peak and min(for_words, against_words) / peak < 0.8:
            errors.append(
                f"{item_id}: arguments for ({for_words} words) and against ({against_words} words) differ by more than 20%"
            )
    return errors


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
        if contest.get("type") in {"race", "primary", "local-office"} and len(active) == 1:
            if "uncontested" not in race_text.lower():
                errors.append(f"{race_id}: uncontested race must say so in the draft")
        write_ins = [c for c in candidates if c.get("write_in")]
        if write_ins:
            if "write-in" not in race_text.lower():
                errors.append(f"{race_id}: write-in candidates need a Write-in section")
        for candidate in candidates:
            item_id = str(candidate.get("item_id") or candidate.get("id"))
            draft_path = workspace / "items" / item_id / "draft.md"
            if not draft_path.exists():
                continue
            text = draft_path.read_text(encoding="utf-8").lower()
            if candidate.get("withdrawn") and "withdrawn on" not in text:
                errors.append(f"{item_id}: withdrawn candidate needs a 'withdrawn on DATE' banner")
            if candidate.get("limited_public_record") and "limited public record" not in text:
                errors.append(f"{item_id}: thin-record candidate needs a limited public record notice")
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
            errors.append(f"{path.name}: summary grade {grade:.1f} is above {limit:.0f}")
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
