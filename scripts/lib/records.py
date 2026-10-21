"""Deterministic record checks: identity, legal sweep, rhetoric labels, shifts.

Birth year is an internal identity input. These helpers never format it for a guide.
"""

from __future__ import annotations

import re

LEGAL_SWEEP_KEYS = (
    "criminal",
    "civil",
    "financial",
    "ethics_campaign_finance",
    "professional_discipline",
    "labor_consumer",
    "misuse_of_office",
    "prior_statements",
)

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "vi"}
_NAME_TOKEN = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*", re.UNICODE)
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_GAP = re.compile(r"^not found \(searched: (.+)\)\.$", re.IGNORECASE)
_BIRTH_PHRASE = re.compile(
    r"\b(?:date of birth|birth year|d\.?\s*o\.?\s*b\.?)\b"
    r"|\bborn\s+in\s+(?:1[89]\d\d|20\d\d)\b"
    r"|\bborn\s+on\b",
    re.IGNORECASE,
)
_SHIFT = re.compile(r"\b(?:shift(?:ed|s)?|changed position|position changed)\b", re.IGNORECASE)
_ALIGNMENT = re.compile(
    r"\b(?:alignment|aligned with|hypocrisy|hypocrite|revealed preference|"
    r"contradicts (?:the |their |his |her )?(?:message|messaging|rhetoric|campaign)|"
    r"signals (?:that|their))\b",
    re.IGNORECASE,
)
_ABSENCE_OVERCLAIM = re.compile(
    r"\b(?:no record exists|has no record|no (?:license|cases|case) exists|"
    r"never (?:had|has) a (?:record|case|license))\b",
    re.IGNORECASE,
)
_DISPOSITIONS_WITH_ACCUSATION = {"dismissal", "acquittal", "overturned_or_vacated", "dismissed"}
_DEGREE_ABBREV = re.compile(
    r"(?<!\w)(?:B\.S\.|B\.A\.|M\.S\.|M\.A\.|M\.B\.A\.|Ph\.D\.|J\.D\.|D\.B\.A\.|DBA|Ed\.D\.)(?!\w)"
)
_DEGREE_FIELD = re.compile(
    r"(?<!\w)(?:degree|bachelor(?:'s)?|master(?:'s)?|doctorate|B\.S\.|B\.A\.|M\.S\.|M\.A\.|M\.B\.A\.|Ph\.D\.|J\.D\.|DBA|D\.B\.A\.|Ed\.D\.)\s+in\s+([A-Za-z][A-Za-z &-]{2,40})",
    re.IGNORECASE,
)
_IDENTIFIER = re.compile(
    r"\b(?:license|licence|docket|case|MUR|NPI)\s*(?:number|no\.|#)?\s*[:#]?\s*([A-Z0-9-]*\d[A-Z0-9-]{2,})",
    re.IGNORECASE,
)
_SEARCH_FORM_URL = re.compile(
    r"CorporationSearch/ByName|(?:^|//)licenseesearch\.fldfs\.com/?$",
    re.IGNORECASE,
)
_DETAIL_URL = re.compile(r"SearchResultDetail|/Licensee/[^/?#]+", re.IGNORECASE)
_COURT_TEXT = re.compile(r"\bv\.\s|\bdocket\b|\bcase no\b", re.IGNORECASE)
_ENTITY_ATTRIBUTION = re.compile(
    r"\b(?:he|she|they|candidate)\b[^.]{0,80}\b(?:is licensed|holds (?:a |the )?license|license number)\b",
    re.IGNORECASE,
)
_ENTITY_WORD = re.compile(r"\b(?:LLC|L\.L\.C\.|Inc\.?|company|firm|corporation|entity)\b", re.IGNORECASE)
_RESPONSE = re.compile(
    r"response requested, not found|\bresponded\b|\bsaid\b|\bwrote\b|\bstatement\b",
    re.IGNORECASE,
)
_RHETORIC_LABELS = ("MATCH", "CONTRADICTION", "NO RECORD")
_RHETORIC_WORD = re.compile(r"\b(?:MATCH|CONTRADICTION|NO RECORD)\b")


def identity_names(record: dict | None) -> list[str]:
    """Ballot name, legal name, and every documented alias."""
    if not isinstance(record, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = re.sub(r"\s+", " ", value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            names.append(text)

    add(str(record.get("ballot_name") or ""))
    add(str(record.get("full_legal_name") or ""))
    add(str(record.get("name") or ""))
    for item in record.get("aliases") or []:
        if isinstance(item, dict):
            add(str(item.get("name") or ""))
        else:
            add(str(item or ""))
    return names


def alias_names(record: dict | None) -> list[str]:
    if not isinstance(record, dict):
        return []
    names = []
    for item in record.get("aliases") or []:
        if isinstance(item, dict):
            text = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
        else:
            text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text:
            names.append(text)
    return names


def surname(name: str) -> str:
    """Last name token, with a trailing generational suffix removed."""
    cleaned = (name or "").replace("’", "'").replace("`", "'")
    tokens = _NAME_TOKEN.findall(cleaned)
    while tokens and tokens[-1].casefold().rstrip(".") in _SUFFIXES:
        tokens.pop()
    return tokens[-1].casefold() if tokens else ""


def surnames_for(names: list[str]) -> set[str]:
    return {surname(name) for name in names if surname(name)}


def names_party(caption: str, surnames: set[str]) -> bool:
    """True when the caption names one of these surnames as a whole word."""
    lowered = (caption or "").lower()
    for token in surnames:
        if token and re.search(rf"(?<![\w'-]){re.escape(token)}(?![\w'-])", lowered):
            return True
    return False


def record_year(value: str | None) -> int | None:
    match = _YEAR.search(str(value or ""))
    if not match:
        return None
    return int(match.group(1))


def adult_year(birth_year: int | None) -> int | None:
    if birth_year is None:
        return None
    return int(birth_year) + 18


def is_court_claim(claim: dict) -> bool:
    if not isinstance(claim, dict) or claim.get("removed"):
        return False
    if claim.get("record_kind") == "court":
        return True
    if str(claim.get("court_caption") or "").strip():
        return True
    if claim.get("legal_category") in {"criminal", "civil"} and claim.get("legal_status"):
        return True
    return bool(_COURT_TEXT.search(str(claim.get("text") or "")))


def court_gate(
    caption: str,
    record_date: str | None,
    names: list[str],
    birth_year: int | None,
) -> list[str]:
    """Party gate, then era gate. A missing birth year leaves the era gate off."""
    errors = []
    if not str(caption or "").strip():
        return ["court record needs a caption so the party gate can run"]
    if not names_party(caption, surnames_for(names)):
        errors.append("court caption does not name the candidate or a documented alias as a party")
    cutoff = adult_year(birth_year)
    year = record_year(record_date)
    if cutoff is not None and year is None:
        errors.append("court record needs record_date so matters before adulthood can be dropped")
    elif cutoff is not None and year is not None and year < cutoff:
        errors.append(f"court record year {year} is before {cutoff}, the year the candidate turned 18")
    return errors


def rendered_birth_errors(text: str, birth_years: list[int] | None = None) -> list[str]:
    """Phrases that would publish a birth year or a date of birth."""
    errors = []
    if _BIRTH_PHRASE.search(text or ""):
        errors.append("birth year or date of birth is internal and must not be rendered")
    for year in birth_years or []:
        if re.search(rf"\bborn\b.{{0,40}}\b{year}\b|\b{year}\b.{{0,40}}\bborn\b", text or "", re.IGNORECASE):
            message = f"birth year {year} must not be rendered"
            if message not in errors:
                errors.append(message)
    return errors


def alias_gap_errors(draft: str, aliases: list[str], aliases_searched: list[str] | None = None) -> list[str]:
    """A Not found line has to show that every documented alias was searched."""
    if not aliases:
        return []
    searched = " ".join(aliases_searched or []).lower()
    errors = []
    for raw in (draft or "").splitlines():
        stripped = raw.strip()
        gap = _GAP.match(stripped)
        if gap:
            blob = gap.group(1).lower()
            missing = [name for name in aliases if name.lower() not in blob]
            if missing:
                errors.append(
                    "Not found line omits alias search for " + ", ".join(missing)
                )
            continue
        if "checked, nothing found" in stripped.lower():
            blob = stripped.lower() + " " + searched
            missing = [name for name in aliases if name.lower() not in blob]
            if missing:
                errors.append(
                    "checked, nothing found omits alias search for " + ", ".join(missing)
                )
    return errors


def legal_sweep_errors(sweep: dict | None, claims: list[dict], aliases: list[str]) -> list[str]:
    if not isinstance(sweep, dict):
        return []
    errors = []
    missing_keys = [key for key in LEGAL_SWEEP_KEYS if key not in sweep]
    if missing_keys:
        errors.append("legal_sweep is missing " + ", ".join(missing_keys))
    searched = [str(item) for item in (sweep.get("aliases_searched") or [])]
    searched_blob = " ".join(searched).lower()
    active = [claim for claim in claims if isinstance(claim, dict) and not claim.get("removed")]
    for key in LEGAL_SWEEP_KEYS:
        row = sweep.get(key)
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        note = str(row.get("note") or "")
        if status == "checked_nothing_found":
            for name in aliases:
                if name.lower() not in searched_blob and name.lower() not in note.lower():
                    errors.append(
                        f"legal_sweep.{key} is checked, nothing found, but {name} was not searched"
                    )
        elif status == "record_found":
            if not any(claim.get("legal_category") == key for claim in active):
                errors.append(
                    f"legal_sweep.{key} says a record was found but no claim uses that category"
                )
        elif status == "portal_unavailable":
            if not note.strip():
                errors.append(f"legal_sweep.{key} is portal_unavailable and needs a note")
            if _ABSENCE_OVERCLAIM.search(note):
                errors.append(f"legal_sweep.{key} portal outage is not a finding that no record exists")
        elif status == "not_checked":
            if re.search(r"checked, nothing found|no record exists", note, re.IGNORECASE):
                errors.append(f"legal_sweep.{key} is not_checked and cannot say the category was clear")
    return errors


def disposition_errors(claim: dict) -> list[str]:
    status = str(claim.get("legal_status") or "")
    text = str(claim.get("text") or "")
    errors = []
    if status in _DISPOSITIONS_WITH_ACCUSATION or status in {"dismissal", "acquittal", "overturned_or_vacated"}:
        accusation = str(claim.get("accusation") or "").strip()
        if not accusation:
            errors.append("a dismissal, acquittal, or reversal must include the accusation")
        elif accusation.lower() not in text.lower():
            errors.append("the claim text must state the accusation with the dismissal, acquittal, or reversal")
        word = {
            "dismissal": "dismiss",
            "dismissed": "dismiss",
            "acquittal": "acquit",
            "overturned_or_vacated": "overturn",
        }.get(status, "")
        if word and word not in text.lower():
            errors.append("the claim text must name the dismissal, acquittal, or reversal")
    if status == "settlement_without_admission":
        if not re.search(r"without admission|no admission|did not admit", text, re.IGNORECASE):
            errors.append("a settlement without admission must say there was no admission")
        if re.search(r"\b(?:admitted guilt|admitted liability|admitted wrongdoing)\b", text, re.IGNORECASE):
            errors.append("a settlement without admission is not an admission of guilt or liability")
    if status and not _RESPONSE.search(text):
        errors.append("a legal record needs the candidate's response or 'response requested, not found'")
    return errors


def rhetoric_errors(claim: dict) -> list[str]:
    label = claim.get("rhetoric_label")
    text = str(claim.get("text") or "")
    section = re.sub(r"\s+", " ", str(claim.get("section") or "").strip().lower())
    errors = []
    if section == "record vs rhetoric" and not label:
        errors.append("a record-vs-rhetoric claim needs a MATCH, CONTRADICTION, or NO RECORD label")
    if not label:
        return errors
    if label not in text:
        errors.append("the record-vs-rhetoric label must appear in the claim text")
    if label == "CONTRADICTION" and claim.get("rhetoric_basis") == "occupation":
        errors.append("occupation is not a contradiction")
    if label == "CONTRADICTION" and re.search(r"\b(?:occupation|profession)\b", text, re.IGNORECASE):
        if not re.search(r"\b(?:vote|voted|donation|donated|filed|said|wrote|statement)\b", text, re.IGNORECASE):
            errors.append("occupation is not a contradiction; use MATCH or NO RECORD")
    return errors


def rhetoric_draft_errors(draft: str, claims: list[dict]) -> list[str]:
    labels = {claim.get("rhetoric_label") for claim in claims if isinstance(claim, dict)}
    errors = []
    section = _section_body(draft, "record vs rhetoric")
    for label in _RHETORIC_LABELS:
        if re.search(rf"\b{re.escape(label)}\b", section) and label not in labels:
            errors.append(f"the draft uses {label} without a claim that carries that label")
    return errors


def shift_errors(claim: dict) -> list[str]:
    text = str(claim.get("text") or "")
    if not claim.get("shift") and not _SHIFT.search(text):
        return []
    start = str(claim.get("shift_from") or "")
    end = str(claim.get("shift_to") or "")
    errors = []
    if not _DATE.match(start) or not _DATE.match(end):
        errors.append("a shift needs both endpoints as shift_from and shift_to (YYYY-MM-DD)")
    sources = [source for source in (claim.get("sources") or []) if isinstance(source, dict)]
    if len(sources) < 2:
        errors.append("a shift needs a source for each endpoint")
    if _DATE.match(start) and start not in text:
        errors.append("the claim text has to state the earlier endpoint date")
    if _DATE.match(end) and end not in text:
        errors.append("the claim text has to state the later endpoint date")
    return errors


def profile_position_errors(profile: dict | None) -> list[str]:
    if not isinstance(profile, dict):
        return []
    grouped: dict[str, list[dict]] = {}
    for row in profile.get("positions") or []:
        if isinstance(row, dict):
            grouped.setdefault(str(row.get("issue") or "position"), []).append(row)
    errors = []
    for issue, rows in grouped.items():
        blob = " ".join(str(row.get("statement") or "") for row in rows)
        if not _SHIFT.search(blob):
            continue
        dates = [str(row.get("as_of") or "") for row in rows if _DATE.match(str(row.get("as_of") or ""))]
        if len(set(dates)) < 2:
            errors.append(f"position {issue} says shift but does not document both endpoints")
    return errors


def entity_license_errors(claim: dict) -> list[str]:
    text = str(claim.get("text") or "")
    holder = claim.get("license_holder")
    kind = claim.get("record_kind")
    entity_record = holder == "entity" or kind == "license_entity"
    if not entity_record and not (_ENTITY_WORD.search(text) and re.search(r"\blicen[sc]e\b", text, re.IGNORECASE)):
        return []
    if entity_record or holder == "entity":
        errors = []
        if _ENTITY_ATTRIBUTION.search(text):
            errors.append("a company license is the entity's record, not the person's")
        if entity_record and not _ENTITY_WORD.search(text):
            errors.append("an entity license claim has to name the entity")
        return errors
    if _ENTITY_ATTRIBUTION.search(text) and holder != "individual":
        return ["a company license is the entity's record, not the person's"]
    return []


def overspecific_errors(claim: dict) -> list[str]:
    """A degree, field, or identifier in the claim must be in a cited quote."""
    text = str(claim.get("text") or "")
    quotes = "\n".join(
        str(source.get("quote") or "")
        for source in (claim.get("sources") or [])
        if isinstance(source, dict)
    )
    quotes_lower = quotes.lower()
    errors = []
    for abbrev in _DEGREE_ABBREV.findall(text):
        if abbrev.lower() not in quotes_lower:
            errors.append(f"degree {abbrev} is not in the cited quote")
    for match in _DEGREE_FIELD.finditer(text):
        field = match.group(1).strip()
        if field.lower() not in quotes_lower:
            errors.append(f"degree field {field} is not in the cited quote")
    for match in _IDENTIFIER.finditer(text):
        ident = match.group(1)
        if ident.lower() not in quotes_lower:
            errors.append(f"identifier {ident} is not in the cited quote")
    return errors


def absence_overclaim_errors(text: str) -> list[str]:
    if _ABSENCE_OVERCLAIM.search(text or ""):
        return ["an empty search is not proof that no record exists; say what was checked"]
    return []


def url_is_search_form(url: str) -> bool:
    if _DETAIL_URL.search(url or ""):
        return False
    return bool(_SEARCH_FORM_URL.search(url or ""))


def search_form_source_errors(claim: dict) -> list[str]:
    text = str(claim.get("text") or "")
    if not re.search(r"\b(?:not found|nothing found|no record|checked, nothing found)\b", text, re.IGNORECASE):
        return []
    sources = [source for source in (claim.get("sources") or []) if isinstance(source, dict)]
    if sources and all(url_is_search_form(str(source.get("url") or "")) for source in sources):
        return ["a search form is not a completed search and cannot support an absence claim"]
    return []


def donation_alignment_errors(text: str) -> list[str]:
    if _ALIGNMENT.search(text or ""):
        return ["candidate donations are listed as recipient, amount, and date, without alignment commentary"]
    return []


def claim_record_errors(claim: dict, identity: dict) -> list[str]:
    if not isinstance(claim, dict) or claim.get("removed"):
        return []
    errors: list[str] = []
    birth = identity.get("birth_year") if isinstance(identity, dict) else None
    birth_year = birth if isinstance(birth, int) else None
    names = identity_names(identity)
    if is_court_claim(claim):
        errors.extend(
            court_gate(
                str(claim.get("court_caption") or ""),
                str(claim.get("record_date") or ""),
                names,
                birth_year,
            )
        )
    errors.extend(disposition_errors(claim))
    errors.extend(rhetoric_errors(claim))
    errors.extend(shift_errors(claim))
    errors.extend(entity_license_errors(claim))
    errors.extend(overspecific_errors(claim))
    errors.extend(absence_overclaim_errors(str(claim.get("text") or "")))
    errors.extend(search_form_source_errors(claim))
    if claim.get("record_kind") == "donation" or claim.get("section") == "donations made":
        errors.extend(donation_alignment_errors(str(claim.get("text") or "")))
    for message in rendered_birth_errors(_claim_blob(claim), [birth_year] if birth_year else []):
        errors.append(message)
    return errors


def item_record_errors(identity: dict, claims: list[dict], draft: str, profile: dict | None) -> list[str]:
    identity = identity if isinstance(identity, dict) else {}
    claims = [claim for claim in claims if isinstance(claim, dict)]
    profile = profile if isinstance(profile, dict) else {}
    errors: list[str] = []
    birth = identity.get("birth_year")
    years = [birth] if isinstance(birth, int) else []
    aliases = alias_names(identity)
    raw_sweep = profile.get("legal_sweep")
    sweep = raw_sweep if isinstance(raw_sweep, dict) else None
    searched = [str(item) for item in (raw_sweep.get("aliases_searched") or [])] if isinstance(raw_sweep, dict) else []
    for claim in claims:
        errors.extend(claim_record_errors(claim, identity))
    errors.extend(alias_gap_errors(draft, aliases, searched))
    errors.extend(legal_sweep_errors(sweep, claims, aliases))
    errors.extend(rhetoric_draft_errors(draft, claims))
    errors.extend(profile_position_errors(profile))
    errors.extend(rendered_birth_errors(draft, years))
    errors.extend(rendered_birth_errors("\n".join(_strings(profile)), years))
    errors.extend(absence_overclaim_errors(draft))
    money = profile.get("money") if isinstance(profile.get("money"), dict) else {}
    for row in (money.get("donations_made") or []) if isinstance(money, dict) else []:
        errors.extend(donation_alignment_errors("\n".join(_strings(row))))
    # Preserve order while dropping repeats from the birth-year scan.
    unique: list[str] = []
    for message in errors:
        if message not in unique:
            unique.append(message)
    return unique


def _claim_blob(claim: dict) -> str:
    parts = [str(claim.get("text") or ""), str(claim.get("notes") or ""), str(claim.get("accusation") or "")]
    for source in claim.get("sources") or []:
        if isinstance(source, dict):
            parts.append(str(source.get("quote") or ""))
    return "\n".join(parts)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _section_body(draft: str, heading: str) -> str:
    """Body under one level-2 heading, compared as a lowercase heading."""
    lines = (draft or "").splitlines()
    capture = False
    kept: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if capture:
                break
            title = line[3:].strip().lower()
            capture = title == heading
            continue
        if capture:
            kept.append(line)
    return "\n".join(kept)
