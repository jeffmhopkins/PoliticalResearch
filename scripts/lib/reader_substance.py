"""Turn cited research into facts a voter can use.

The reader states the fact first and leaves the source in the footnote.
A sentence whose meaning cannot be read from the cited record is left out
of the reader. The sources edition still carries the claim.
"""

from __future__ import annotations

import re

from lib.sentences import split_sentences
from lib.util import street_address_spans

_MARKER_RE = re.compile(r"\[\^(\d+)\]")
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
_MONTH_RE = "(?:" + "|".join(_MONTHS) + ")"
_RANGE_RE = re.compile(
    rf"({_MONTH_RE} \d{{1,2}}, \d{{4}}),?\s+through\s+({_MONTH_RE} \d{{1,2}}, \d{{4}})"
)
_SHORT_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2}|\d{4})\b")
_FILING_RE = re.compile(
    r"qualified on|filed on|file date|qualifying fee|status qualified|"
    r"primary (?:result|column)|made-ballot date|\bstatus Qualified\b|"
    r"\bas qualified\b|primary and general cells",
    re.IGNORECASE,
)
_VERIFY_RE = re.compile(
    r"unconfirmed|unverified|does not (?:print|show|state|include|name)|saved page|"
    r"is a statement of focus|it is not the|candidate connection survey|"
    r", and the reply is\.?|could not be retrieved|blocked by cloudflare",
    re.IGNORECASE,
)
_TAUTOLOGY_RE = re.compile(
    r"prepared by nonpartisan committee staff\.?$|will be submitted to the electors|"
    r"filed it with the Secretary of State\.?$|described on the ballot|printed on the ballot",
    re.IGNORECASE,
)
_DOC_ROW_RE = re.compile(
    r"document index|index (?:lists|for)|row dated|letter dated",
    re.IGNORECASE,
)
_ROUTINE_DOC_RE = re.compile(
    r"poll watcher|statement of candidate|matching funds|"
    r"financial disclosure (?:row|receipt)|candidate oath",
    re.IGNORECASE,
)
_FINE_RE = re.compile(
    r"fine (?:appeal |final |letter|payment)|fail to file|response to fine",
    re.IGNORECASE,
)
_ATTR_RE = re.compile(
    r"^(?:The |A |An )?(?:[\w\s\-'.]{0,80}?)(?:says|reports that|lists|identifies|shows|records that|prints)\b[:,]?\s*",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r",\s*(?:U\.S\. Senator(?: from Florida)?|Board of County Commissioners(?:, District \d+)?|"
    r"Commissioner of Agriculture|a Justice of the (?:Supreme Court|[\w\s]+Court of Appeal)|"
    r"of the Fifth District(?: Court of Appeal)?|Division of Elections)\b[^,.]*",
    re.IGNORECASE,
)
_BILL_RE = re.compile(
    r"\b(?:H\.?\s*R\.?\s*\d+|S\.?\s*B\.?\s*\d+|H\.?\s*C\.?\s*R\.?\s*\d+|"
    r"House bill \d+|Senate bill S?\s*\d+|House concurrent resolution \d+)\b",
    re.IGNORECASE,
)
_VOTE_WORD_RE = re.compile(r"\b(Yea|Nay|Yes|No|Aye)\b", re.IGNORECASE)
_WHICH_RE = re.compile(r"\b(?:which|that would)\b", re.IGNORECASE)
_OFFICE_WORD_RE = re.compile(
    r"\b(?:senator|representative|congress|judge|justice|attorney general|commissioner|"
    r"governor|mayor|council|sheriff|president of the|house|senate|court)\b",
    re.IGNORECASE,
)
_PROPER = {
    "brevard community college": "Brevard Community College",
    "eastern florida state college": "Eastern Florida State College",
    "bob graham center": "Bob Graham Center",
    "university of florida": "University of Florida",
    "university of central florida": "University of Central Florida",
    "florida atlantic university": "Florida Atlantic University",
    "stetson university": "Stetson University",
    "university of arkansas": "University of Arkansas",
    "emory university": "Emory University",
    "george mason university": "George Mason University",
    "indian river lagoon": "Indian River Lagoon",
    "hillsborough county": "Hillsborough County",
    "miami-dade county": "Miami-Dade County",
    "u.s. attorney's office": "U.S. Attorney's Office",
    "west orange high school": "West Orange High School",
    "titusville high school": "Titusville High School",
    "loyd contracting": "Loyd Contracting",
    "yale law school": "Yale Law School",
    "georgetown university law center": "Georgetown University Law Center",
    "florida state university": "Florida State University",
    "university of virginia": "University of Virginia",
    "oklahoma university": "Oklahoma University",
    "jones day": "Jones Day",
}
_JARGON = (
    ("tangible personal property", "tangible personal property (business equipment and other goods a tax can cover)"),
    ("ad valorem", "ad valorem (a property tax based on value)"),
    ("millage", "millage (a property-tax rate)"),
    ("cloture", "cloture (a vote to limit debate)"),
    ("Form 6", "Form 6 (the state's full financial disclosure)"),
    ("CS/", "CS/ (a committee substitute of) "),
    ("HJR", "HJR (a House joint resolution)"),
    ("NPA", "NPA (no party affiliation)"),
    ("LPF", "LPF (Libertarian Party of Florida)"),
    ("PAC", "PAC (a political action committee)"),
    ("surtax", "surtax (a tax added on top of another tax)"),
    ("retention", "retention (a vote on whether a judge stays in office)"),
)
_WHICH_NEEDLES = (
    ("further consolidated appropriations bill", "is a further consolidated appropriations bill"),
    ("making further consolidated appropriations", "makes further consolidated appropriations"),
    (
        "National Defense Authorization Act for Fiscal Year 2026",
        "is the National Defense Authorization Act for Fiscal Year 2026",
    ),
    (
        "Streamlining Procurement for Effective Execution and Delivery",
        "is the Streamlining Procurement for Effective Execution and Delivery and National Defense Authorization Act for Fiscal Year 2026",
    ),
    ("Health and Human Services conference report", "is the Health and Human Services conference report"),
    ("health and human services conference report", "is the Health and Human Services conference report"),
    ("hurricane-shutter sales-tax bill", "is a hurricane-shutter sales-tax bill"),
    (
        "directing removal of armed forces from hostilities with Iran",
        "directs removal of armed forces from hostilities with Iran",
    ),
    (
        "removal of armed forces from hostilities with Iran",
        "directs removal of armed forces from hostilities with Iran",
    ),
)
_GAP_CATEGORIES = (
    ("residence", "city and state of residence"),
    ("education", "education"),
    ("career", "career"),
    ("military", "military service"),
    ("office", "prior elected or appointed office"),
    ("campaign", "earlier campaigns"),
    ("license", "professional licenses"),
    ("community", "community or board roles"),
)
_NONE_LEGAL = (
    "No court cases, ethics findings, or campaign-finance penalties found in the records checked."
)
_LOAN_RE = re.compile(
    r"\bloans?\s+(?:of\s+|are\s+)?\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_BARE_MONEY_RE = re.compile(r"(?<!\$)\b(\d{1,3}(?:,\d{3})*\.\d{2})\b")
_SELF_REPORT_RE = re.compile(
    r"campaign site|candidate connection|wrote that|in a \d{4} survey",
    re.IGNORECASE,
)
_BACK_MATTER_RE = re.compile(
    r"^(?:# Glossary\b|# How we researched\b|# Changelog\b|# Corrections\b|# Disputed\b|"
    r"# Marker index\b|# Official election\b|# Works cited\b)|\{#[^}]*\}\s*\.back-matter|\.back-matter",
    re.IGNORECASE,
)


def markers_of(text: str) -> list[str]:
    return _MARKER_RE.findall(text or "")


def marker_suffix(text: str) -> str:
    return "".join(f"[^{number}]" for number in markers_of(text))


def plain_of(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKER_RE.sub("", text or "")).strip()


def street_spans(text: str) -> list[str]:
    """Street-address hits, skipping court names such as Supreme Court."""
    return street_address_spans(text)


def _whole_dollars(raw: str) -> str:
    try:
        value = int(round(float(raw.replace(",", "").replace("$", ""))))
    except ValueError:
        return ""
    return f"${value:,}"


def expand_short_dates(text: str) -> str:
    def repl(match: re.Match) -> str:
        month = int(match.group(1))
        day = int(match.group(2))
        year_text = match.group(3)
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return match.group(0)
        if len(year_text) == 2:
            year = 2000 + int(year_text) if int(year_text) < 70 else 1900 + int(year_text)
        else:
            year = int(year_text)
        return f"{_MONTHS[month - 1]} {day}, {year}"

    return _SHORT_DATE_RE.sub(repl, text or "")


def _fix_proper(text: str) -> str:
    cleaned = text
    for raw, shown in _PROPER.items():
        cleaned = re.sub(re.escape(raw), shown, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r", now ([^,]+),", r" (now \1),", cleaned)
    return cleaned


def _strip_titles(text: str) -> str:
    return _TITLE_RE.sub("", text)


def _attach(text: str, marks: str) -> str:
    body = re.sub(r"\s+", " ", text or "").strip(" ,;:")
    if not body:
        return ""
    if body[0].islower():
        body = body[0].upper() + body[1:]
    body = _BARE_MONEY_RE.sub(r"$\1", body)
    if body[-1] not in ".!?":
        body += "."
    if not marks:
        return body
    return body[:-1] + marks + body[-1]


def _strip_attribution(text: str, original: str) -> str:
    cleaned = text
    removed = False
    for _ in range(3):
        nxt = _ATTR_RE.sub("", cleaned).strip()
        if nxt == cleaned:
            break
        cleaned = nxt
        removed = True
    if removed:
        cleaned = re.sub(r"^(?:that|as)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:")
    if _SELF_REPORT_RE.search(original) and cleaned and "(self-reported)" not in cleaned.lower():
        cleaned = cleaned.rstrip(".") + " (self-reported)"
    return cleaned


def _repair_listed_fact(plain: str) -> str:
    """Turn a stripped 'lists X as Y' fragment into a sentence, or drop it."""
    text = plain.rstrip(".")
    sponsor = re.match(r"(?i)^(?:the\s+)?sponsor\s+as\s+(.+)$", text)
    if sponsor:
        who = sponsor.group(1).strip(" .")
        if re.search(r"(?i)florida\s+legislature\s*/\s*house", who):
            return "The Florida House is the sponsor"
        if "/" in who:
            return ""
        return f"The sponsor is {who}"
    job = re.match(
        r"(?i)^the occupation of\s+([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3}),?\s+as\s+"
        r"([A-Za-z][\w-]*)\s+and\s+(?:his|her|their)\s+city of residence\s+as\s+"
        r"([A-Z][\w.]+(?:\s+[A-Z][\w.]+){0,2})$",
        text,
    )
    if job:
        name, work, city = job.group(1), job.group(2), job.group(3)
        return f"{name} is a {work.lower()} and lives in {city}, Florida"
    officer = re.match(
        r"(?i)^(.+?),\s+document\s+\S+,\s+filed in\s+(\d{4}),\s+as\s+(\w+),\s+with\s+"
        r"([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3}),\s+on the officer line\b.*\bin\s+"
        r"([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,2})$",
        text,
    )
    if officer:
        company, year, status, person, city = officer.groups()
        return (
            f"{person} is an officer of {company.strip()}, filed in {year} and {status.lower()}, "
            f"in {city}, Florida"
        )
    if re.search(r"(?i)\bofficer line\b", text):
        return ""
    named = re.match(
        r"^([A-Z][\w.'\"-]+(?:\s+[A-Z][\w.'\"-]+){0,4})\s+as\s+(.+)$",
        text,
    )
    if named and not re.search(r"\b(?:served|worked|elected|known)\s+as\b", text, re.IGNORECASE):
        person, rest = named.group(1), named.group(2).strip()
        if re.search(r"(?i)\bqualified\b|cells blank", rest):
            return ""
        if not re.search(r"\b(?:19|20)\d{2}\b", rest):
            return ""
        return f"{person} served as {rest}"
    text = re.sub(r",\s+as\s+(a|an)\s+", r" is \1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\s+as\s+", "and ", text, flags=re.IGNORECASE)
    text = re.sub(r",\s+as\s+(?=voting\b)", " as ", text, flags=re.IGNORECASE)

    def _source_clause(match: re.Match) -> str:
        chunk = match.group(0)
        dated = re.search(r"(?i)dated\s+([A-Z][a-z]+ \d{1,2}, \d{4})", chunk)
        if dated and re.match(r"(?i)\s*(?:a|the)\s", chunk):
            return f"On {dated.group(1)}, "
        if re.search(r"(?i)\band\b", chunk):
            return ", and "
        return " "

    text = re.sub(
        r"(?i)(?:,\s*)?(?:and\s+)?(?:a|the)\s+[A-Za-z][\w\s,]{0,80}?\b"
        r"(?:biography|page|handbook|release|analysis)\s+"
        r"(?:dated\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4},\s+)?says\s+(?:that\s+)?",
        _source_clause,
        text,
    )
    text = re.sub(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}),\s+(?=(?:was|were|is|are|founded|served|resigned|occurred)\b)",
        r"\1 ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip(" ,;:")


def _form6(plain: str) -> str | None:
    """Label a financial-disclosure figure. Return None when this is not one."""
    if not re.search(r"form 6|net worth|net-worth", plain, re.IGNORECASE):
        return None
    if re.search(r"\borganization line as N/A\b|\borganization is printed N/A\b", plain, re.IGNORECASE):
        return ""
    date = ""
    found_date = re.search(rf"({_MONTH_RE} \d{{1,2}}, \d{{4}})", plain)
    if found_date:
        date = found_date.group(1)
    sentences = []
    beside = re.search(
        r"([\d,]+\.\d{2})\s+next to\s+([A-Za-z0-9][^.]{1,60}?)"
        r"(?=\s+and\b|\s+dated\b|[.]|$)",
        plain,
        re.IGNORECASE,
    )
    if beside:
        amount = _whole_dollars(beside.group(1))
        label = beside.group(2).strip(" ,.")
        if amount:
            when = f" (as of {date}, state financial disclosure)" if date else " (state financial disclosure)"
            sentences.append(f"Listed next to {label}: {amount}{when}")
    net = re.search(r"net-?worth(?: line)?(?: of| shows)?\s*([\d,]+\.\d{2})", plain, re.IGNORECASE)
    if not net:
        net = re.search(r"shows\s+([\d,]+\.\d{2})", plain, re.IGNORECASE)
    if net:
        amount = _whole_dollars(net.group(1))
        if amount:
            when = f" (as of {date}, state financial disclosure)" if date else " (state financial disclosure)"
            sentences.append(f"Net worth reported: {amount}{when}")
    if not sentences:
        return None
    return ". ".join(sentences)


def _child_count_line(plain: str) -> str:
    count = re.search(
        r"\b(one|two|three|four|five|six|seven|eight|\d+)\s+(?:minor\s+)?children\b",
        plain,
        re.IGNORECASE,
    )
    if count:
        word = count.group(1).lower()
        if word in {"2", "two"}:
            return "Two children, both minors"
        if word in {"1", "one"}:
            return "One child, a minor"
        return f"{word[:1].upper()}{word[1:]} children, all minors"
    if re.search(r"\b(?:son|daughter|child)\b", plain, re.IGNORECASE):
        return "One child, a minor"
    return ""


def _family_or_none(plain: str) -> str | None:
    """None when the sentence is not about family. '' when a child detail must be dropped.

    Minor children are a count only. A named adult child stays only when the
    sentence says the candidate made that public and the fact is relevant.
    """
    if re.search(r"working with children|students with|families,", plain, re.IGNORECASE):
        return None
    if not re.search(r"\b(?:son|daughter|children|child|wife|husband|spouse)\b", plain, re.IGNORECASE):
        return None
    about_child = re.search(r"\b(?:son|daughter|children|child)\b", plain, re.IGNORECASE)
    if not about_child:
        return None
    private = re.search(
        r"\b(?:age|years old|year-old|elementary|high school|middle school|preschool|grade)\b",
        plain,
        re.IGNORECASE,
    )
    minor = re.search(r"\bminors?\b", plain, re.IGNORECASE)
    adult = re.search(r"\badult\b", plain, re.IGNORECASE)
    if minor or private:
        return _child_count_line(plain)
    if adult and not private:
        named = re.search(
            r"\b(?:son|daughter)\s+[A-Z][a-z]+|\b[A-Z][a-z]+\s*,\s*(?:his|her|their)\s+(?:son|daughter)\b",
            plain,
        )
        made_public = re.search(
            r"\b(?:said|stated|wrote|told|announced|campaign site|biography|interview|publicly)\b",
            plain,
            re.IGNORECASE,
        )
        relevant = re.search(
            r"\b(?:campaign|office|business|board|company|firm|election)\b",
            plain,
            re.IGNORECASE,
        )
        if named and not (made_public and relevant):
            return ""
        return plain
    named = re.search(
        r"\b(?:son|daughter)\s+[A-Z][a-z]+|\b[A-Z][a-z]+\s*,\s*(?:his|her|their)\s+(?:son|daughter)\b",
        plain,
    )
    if named:
        return ""
    return _child_count_line(plain) or None


def _city_state(city: str, state: str) -> str:
    city = re.sub(r"\s+", " ", city or "").strip(" ,.")
    if not city:
        return ""
    if (state or "").upper() in {"FL", "FLORIDA"} or state == "Florida":
        return f"Lives in {city}, Florida"
    if state:
        return f"Lives in {city}, {state}"
    return f"Lives in {city}"


def _residence_clause(plain: str) -> str | None:
    """City and state only. A street number never survives into the reader."""
    lives_at = re.search(
        r"\b(?:lives|resides)\s+at\b.+?,\s*([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,2}),\s*(Florida|FL)\b",
        plain,
    )
    if lives_at:
        return _city_state(lives_at.group(1), lives_at.group(2))
    lives = re.search(
        r"\b(?:lives in|resident of|resides in)\s+([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,2})"
        r"(?:,\s*(Florida|FL))?",
        plain,
    )
    if lives:
        return _city_state(lives.group(1), lives.group(2) or "")
    filing = re.search(r"\bfiling city is ([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,2})", plain)
    if filing:
        state = "Florida" if re.search(r"\bFlorida\b|Division of Elections", plain) else ""
        shown = _city_state(filing.group(1), state)
        if shown.startswith("Lives in "):
            return "Filing city: " + shown[len("Lives in ") :]
        return shown
    if street_spans(plain):
        return ""
    return None


def _grounded_which(plain: str, blob: str) -> str:
    found = re.search(r"\bwhich\s+((?:is|makes|directs|would|requires|creates|limits)[^.]{8,160})", plain, re.IGNORECASE)
    if found:
        return found.group(1).strip().rstrip(" ,")
    haystack = f"{plain} {blob}"
    lowered = haystack.lower()
    for needle, clause in _WHICH_NEEDLES:
        if needle.lower() in lowered:
            return clause
    return ""


def _claim_blob(sentence: str, index) -> str:
    if not index:
        return ""
    parts = []
    for number in markers_of(sentence):
        found = index.get(int(number))
        if not found:
            continue
        _item, claim, source = found
        parts.append(str(claim.get("text") or ""))
        parts.append(str(source.get("quote") or ""))
        parts.append(str(source.get("title") or ""))
    return " ".join(parts)


def _insert_which(sentence: str, clause: str) -> str:
    if _WHICH_RE.search(plain_of(sentence)):
        return sentence
    match = re.search(r"(\s*(?:\[\^\d+\])+)([.!?])?\s*$", sentence)
    if match:
        head = sentence[: match.start()].rstrip(" ,;.")
        return f"{head}, which {clause}{match.group(1)}{match.group(2) or '.'}"
    if sentence.endswith((".", "!", "?")):
        return sentence[:-1] + f", which {clause}{sentence[-1]}"
    return sentence + f", which {clause}."


def loan_sentence(text: str) -> str | None:
    """The loans figure stated in a finance sentence, with that sentence's marker."""
    for sentence in split_sentences(text or ""):
        match = _LOAN_RE.search(sentence)
        if not match:
            continue
        amount = _whole_dollars(match.group(1))
        marks = marker_suffix(sentence)
        if amount and marks:
            return f"Loans are {amount}{marks}."
    return None


def period_sentence(name: str, text: str) -> str:
    """A cited start and end, or a cited start, for one finance report."""
    dated = expand_short_dates(text or "")
    for sentence in split_sentences(dated):
        match = _RANGE_RE.search(sentence)
        marks = marker_suffix(sentence)
        if match and marks:
            return f"{name}'s report covers {match.group(1)} through {match.group(2)}{marks}."
        one = re.search(rf"({_MONTH_RE} \d{{1,2}}, \d{{4}})", sentence)
        if one and marks and re.search(r"\b(?:period|through|from|start|cover)\b", sentence, re.IGNORECASE):
            return f"{name}'s report includes {one.group(1)}{marks}."
    return ""


def fact_sentence(sentence: str, slot: str = "general", *, index=None) -> str:
    """The voter-facing sentence, or '' when the record does not support one."""
    raw = re.sub(r"\s+", " ", (sentence or "")).strip()
    if not raw:
        return ""
    marks = marker_suffix(raw)
    plain = plain_of(raw)
    if not plain:
        return ""
    if re.match(r"(?i)^no public (?:record|statement)", plain) or re.match(
        r"(?i)^limited public record\.?$", plain
    ):
        return raw if raw[-1:] in ".!?" else raw + "."
    if re.match(r"(?i)^not found \(searched:", plain):
        return ""
    formed = _form6(plain)
    if formed is not None:
        if not formed:
            return ""
        return " ".join(_attach(part, marks) for part in formed.split(". ") if part.strip())
    family = _family_or_none(plain)
    if family is not None:
        if not family:
            return ""
        return _attach(family, marks)
    if slot == "background":
        residence = _residence_clause(plain)
        if residence == "":
            return ""
        if residence:
            return _attach(residence, marks)
    plain = expand_short_dates(plain)
    plain = _fix_proper(_strip_titles(plain))
    plain = re.sub(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}),\s+(?!(?:and|or|who|which|that|a|the)\b)",
        r"\1 ",
        plain,
    )
    plain = re.sub(
        r"\b(?:where\s+)?the (?:biography|handbook|campaign site|page)\s+(?:says|said)\s+",
        "",
        plain,
        flags=re.IGNORECASE,
    )
    plain = re.sub(r"(?i)^(?:a |in a )?single source[:,]?\s*", "", plain)
    plain = re.sub(
        r"(?i),?\s*(?:and\s+)?(?:this|that|these|those|both)\s+(?:[\w'-]+\s+){0,6}(?:is|are)\s+a\s+single source\b",
        "",
        plain,
    )
    plain = re.sub(r"(?i),?\s*and the record label is match\b", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip(" ,;:")
    if _FILING_RE.search(plain) and slot in {"office", "card", "background", "votes", "position", "general"}:
        return ""
    if _VERIFY_RE.search(plain):
        return ""
    if _TAUTOLOGY_RE.search(plain):
        plain = _TAUTOLOGY_RE.sub("", plain)
        plain = re.sub(r"\s+,", ",", plain)
        plain = re.sub(r"\s{2,}", " ", plain).strip(" ,;.")
        if len(plain.split()) < 4:
            return ""
    if _DOC_ROW_RE.search(plain) or _ROUTINE_DOC_RE.search(plain):
        return ""
    if street_spans(plain):
        return ""
    plain = _strip_attribution(plain, raw)
    plain = _repair_listed_fact(plain)
    if not plain:
        return ""
    if re.search(r"(?i)\b(?:and|or|but)\s*$", plain):
        return ""
    if slot == "position" and re.search(
        r"not accepting contributions|no party affiliation|national leaders|did not respond|status qualified",
        plain,
        re.IGNORECASE,
    ):
        return ""
    if slot == "votes":
        if not _VOTE_WORD_RE.search(plain) or not _BILL_RE.search(plain):
            return ""
        clause = _grounded_which(plain, _claim_blob(raw, index))
        if not clause and not _WHICH_RE.search(plain):
            return ""
        rebuilt = _attach(plain, marks)
        if clause and not _WHICH_RE.search(plain_of(rebuilt)):
            rebuilt = _insert_which(rebuilt, clause)
        return rebuilt
    if slot == "office" and _FILING_RE.search(plain):
        return ""
    return _attach(plain, marks)


def legal_sentence(text: str) -> str:
    """One outcome sentence, or the none-found line when the index rows are not findings."""
    cited = []
    fine = False
    bar_clear = False
    marks = ""
    for sentence in split_sentences(text or ""):
        plain = plain_of(sentence)
        if not plain or re.match(r"(?i)^not found \(searched:", plain):
            continue
        if re.search(r"discipline history of none|no discipline|member in good standing", plain, re.IGNORECASE):
            bar_clear = True
            marks = marks or marker_suffix(sentence)
            continue
        if _ROUTINE_DOC_RE.search(plain) and not _FINE_RE.search(plain):
            continue
        if _FINE_RE.search(plain):
            fine = True
            marks = marks or marker_suffix(sentence)
            continue
        cleaned = fact_sentence(sentence, "legal")
        if cleaned and cleaned != "Limited public record.":
            cited.append(cleaned)
    parts = []
    if bar_clear and marks:
        parts.append(f"The Florida Bar lists no discipline in the past 10 years{marks}.")
    if fine and marks:
        parts.append(
            f"Fine or fail-to-file letters are on the state campaign-finance index{marks}. "
            f"Those letters were not read, so the amount and the outcome are not stated here{marks}."
        )
    parts.extend(cited)
    if not parts:
        return _NONE_LEGAL
    return " ".join(parts)


def _category(plain: str) -> str:
    if re.search(r"\b(?:lives in|filing city:)\b", plain, re.IGNORECASE):
        return "residence"
    if re.search(r"\b(?:bachelor|master|degree|graduat|university|college|law school|high school)\b", plain, re.IGNORECASE):
        return "education"
    if re.search(r"\b(?:army|navy|marine|air force|coast guard|military|veteran)\b", plain, re.IGNORECASE):
        return "military"
    if re.search(r"\b(?:license|admitted to the bar|bar admission|board certified)\b", plain, re.IGNORECASE):
        return "license"
    if re.search(r"\b(?:nonprofit|foundation|volunteer|board of directors|board member)\b", plain, re.IGNORECASE):
        return "community"
    if re.search(r"\b(?:defeated|lost the|won the|ran for|candidate for|primary election)\b", plain, re.IGNORECASE):
        return "campaign"
    if _OFFICE_WORD_RE.search(plain) and re.search(r"\b(?:19|20)\d{2}\b", plain):
        return "office"
    if re.search(r"\b(?:elected|appointed)\b", plain, re.IGNORECASE):
        return "office"
    return "career"


def _year(sentence: str) -> int:
    match = re.search(r"\b((?:19|20)\d{2})\b", plain_of(sentence))
    return int(match.group(1)) if match else 9999


def _norm(sentence: str) -> str:
    return re.sub(r"\s+", " ", plain_of(sentence).lower()).strip(" .")


def background_lines(sections: dict, *, limited: bool = False) -> list[str]:
    """A short narrative, a dated timeline, and one gap line for what is missing."""
    if limited:
        return ["### Background", "", "Limited public record.", ""]
    found: dict[str, list[str]] = {key: [] for key, _label in _GAP_CATEGORIES}
    ordered: list[str] = []
    seen: set[str] = set()

    def take(sentence: str, slot: str = "background") -> None:
        cleaned = fact_sentence(sentence, slot)
        if not cleaned or cleaned == "Limited public record.":
            return
        key = _norm(cleaned)
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(cleaned)
        found[_category(plain_of(cleaned))].append(cleaned)

    background = sections.get("background") or ""
    if background and "[^" in background and "not found (searched" not in background.lower():
        for sentence in split_sentences(background):
            take(sentence)
    else:
        for name in ("education", "occupational history", "prior offices and public service"):
            for sentence in split_sentences(sections.get(name) or ""):
                take(sentence)
        for sentence in split_sentences(sections.get("record vs rhetoric") or ""):
            plain = plain_of(sentence)
            if _VOTE_WORD_RE.search(plain) and _BILL_RE.search(plain):
                continue
            if _OFFICE_WORD_RE.search(plain) and re.search(r"\b(?:19|20)\d{2}\b", plain):
                take(sentence, "general")
    for sentence in split_sentences(sections.get("identity") or ""):
        residence = _residence_clause(plain_of(sentence))
        if residence:
            take(sentence)

    if any(found["residence"]):
        pass
    undated = [sentence for sentence in ordered if _year(sentence) == 9999]
    dated = [sentence for sentence in ordered if _year(sentence) != 9999]
    narrative = (undated + dated)[:2]
    used = {_norm(sentence) for sentence in narrative}
    timeline = [sentence for sentence in sorted(dated, key=_year) if _norm(sentence) not in used]
    lines = ["### Background", ""]
    if narrative:
        lines.extend([" ".join(narrative), ""])
    elif not timeline:
        missing = ", ".join(label for _key, label in _GAP_CATEGORIES)
        lines.extend([f"No public record found for {missing}.", ""])
        return lines
    if timeline:
        lines.extend(["| When | What happened |", "| --- | --- |"])
        for sentence in timeline:
            year = _year(sentence)
            when = str(year) if year != 9999 else "Undated"
            event = sentence.replace("|", "/")
            lines.append(f"| {when} | {event} |")
        lines.append("")
    else:
        lines.extend(["No public record found for other dated events.", ""])
    missing = [label for key, label in _GAP_CATEGORIES if not found.get(key)]
    if missing:
        lines.extend([f"No public record found for {', '.join(missing)}.", ""])
    return lines


def vote_lines(text: str, index=None) -> list[str]:
    kept = []
    seen: set[str] = set()
    for sentence in split_sentences(text or ""):
        cleaned = fact_sentence(sentence, "votes", index=index)
        key = _norm(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            kept.append(cleaned)
    return kept


def _expand_jargon(line: str, seen: set[str]) -> str:
    parts = re.split(r"(<[^>]+>)", line)
    for term, phrase in _JARGON:
        if term in seen:
            continue
        definition = phrase[len(term) :].strip()
        replaced = False
        for index, part in enumerate(parts):
            if part.startswith("<") or term not in part:
                continue
            if definition and definition in part:
                seen.add(term)
                replaced = True
                break
            pattern = re.compile(rf"\b{re.escape(term)}\b") if term[-1].isalnum() else re.compile(re.escape(term))
            if not pattern.search(part):
                continue
            parts[index] = pattern.sub(phrase, part, count=1)
            seen.add(term)
            replaced = True
            break
        if replaced:
            continue
    return "".join(parts)


def substance_document(text: str, index=None) -> str:
    """Clean contest prose. Back matter, including the research log, stays as written."""
    lines = (text or "").splitlines()
    out: list[str] = []
    start = 0
    if lines and lines[0].strip() == "---":
        for index_line in range(1, len(lines)):
            if lines[index_line].strip() == "---":
                start = index_line + 1
                break
    out.extend(lines[:start])
    seen_jargon: set[str] = set()
    seen_sentences: set[str] = set()
    in_measure = False
    stopped = False
    for line in lines[start:]:
        if stopped:
            out.append(line)
            continue
        stripped = line.strip()
        if _BACK_MATTER_RE.search(stripped):
            stopped = True
            out.append(line)
            continue
        if re.search(r"\{#contest-", stripped):
            seen_jargon = set()
            seen_sentences = set()
            in_measure = "amendment" in stripped.lower() or "measure" in stripped.lower()
        copy = (
            not stripped
            or stripped.startswith(("#", "|", ">", ":", "{", "<!--", ":::", "---", "[", "<"))
        )
        if copy:
            if stripped.startswith(("<", "|")):
                out.append(_expand_jargon(expand_short_dates(line), seen_jargon))
            else:
                out.append(line)
            continue
        prefix = ""
        prose = stripped
        if stripped.startswith("- "):
            prefix = "- "
            prose = stripped[2:].strip()
        kept = []
        for sentence in split_sentences(prose):
            cleaned = fact_sentence(sentence, "general", index=index)
            if not cleaned:
                continue
            key = _norm(cleaned)
            if in_measure and key in seen_sentences:
                continue
            if key:
                seen_sentences.add(key)
            kept.append(cleaned)
        if not kept:
            continue
        rewritten = _expand_jargon(expand_short_dates(prefix + " ".join(kept)), seen_jargon)
        out.append(rewritten)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip() + "\n"


def _contest_chunks(text: str) -> list[tuple[str, str]]:
    body = text or ""
    stop = re.search(r"(?m)^# (?:Glossary|How we researched|Changelog|Corrections|Disputed|Marker index)\b", body)
    if stop:
        body = body[: stop.start()]
    matches = list(re.finditer(r"(?m)^## .+\{#contest-([^}\s]+)", body))
    chunks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunks.append((match.group(1), body[match.start() : end]))
    return chunks


def _heading_bodies(chunk: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^(#{2,4}) .+$", chunk))
    bodies = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(chunk)
        heading = match.group(0).strip()
        bodies.append((heading, chunk[match.end() : end]))
    return bodies


def _is_gap_line(text: str) -> bool:
    plain = plain_of(text).lower().rstrip(".")
    return plain.startswith("no public record") or plain.startswith("no public statement") or plain in {
        "not found",
        "limited public record",
    }


def substance_errors(text: str, ballot: dict | None = None) -> list[str]:
    """The reader gates. A guide with no contest pages is not a printed edition."""
    if "{#contest-" not in (text or ""):
        return []
    errors: list[str] = []
    names = []
    limited: set[str] = set()
    for contest in (ballot or {}).get("contests") or []:
        if not isinstance(contest, dict):
            continue
        for candidate in contest.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            name = str(candidate.get("name") or "").strip()
            if name:
                names.append(name)
            if candidate.get("limited_public_record") and item_id:
                limited.add(item_id)
    scan = text
    stop = re.search(r"(?m)^# (?:Glossary|How we researched)\b", scan)
    if stop:
        scan = scan[: stop.start()]
    for span in street_spans(scan):
        errors.append(f"final/guide.md: street address in the guide: {span[:80]}")
        break
    lowered = scan.casefold()
    for token in ("chapman", "6070"):
        if token in lowered:
            errors.append(f"final/guide.md: private token {token!r} appears in the guide")
    if re.search(r"document index|index (?:lists|for)|row dated|letter dated|\b\d{2}/\d{2}/\d{2}\b", scan, re.IGNORECASE):
        errors.append("final/guide.md: reader still has a document-index row or a numeric date")
    if re.search(
        r"qualified on|filed on|file date|qualifying fee|status qualified|primary (?:result|column)|made-ballot date",
        scan,
        re.IGNORECASE,
    ):
        errors.append("final/guide.md: reader still has filing or qualifying trivia")
    if re.search(
        r"unconfirmed|unverified|does not (?:print|show|state|include)|saved page|"
        r"is a statement of focus|it is not the|candidate connection survey",
        scan,
        re.IGNORECASE,
    ):
        errors.append("final/guide.md: reader still has a research note")
    if re.search(
        r"prepared by nonpartisan committee staff|will be submitted to the electors|"
        r"filed it with the Secretary of State(?!\s+[A-Za-z])|described on the ballot|printed on the ballot",
        scan,
        re.IGNORECASE,
    ):
        errors.append("final/guide.md: reader still has a tautology")
    if re.search(r"said about own words|, and the reply is\.", scan, re.IGNORECASE):
        errors.append("final/guide.md: reader still has a broken template")
    if _BARE_MONEY_RE.search(_MARKER_RE.sub("", scan)):
        errors.append("final/guide.md: reader has a bare dollar figure with no $ sign")
    for name in names:
        pattern = re.compile(
            rf"{re.escape(name)},\s*(?:U\.S\. Senator|Board of County|Commissioner of|a Justice of|"
            rf"of the Fifth District|Division of Elections)",
            re.IGNORECASE,
        )
        if pattern.search(scan):
            errors.append(f"final/guide.md: {name} is given a title that is not the candidate's office")
    for contest_id, chunk in _contest_chunks(text):
        bodies = _heading_bodies(chunk)
        gap_run = 0
        attr_count = 0
        for heading, body in bodies:
            heading_l = heading.lower()
            prose = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith(("|", ":", ":::", "<!--", "<"))]
            for line in prose:
                for sentence in split_sentences(line):
                    if re.match(
                        r"^(?:The |A |An )?(?:[\w\s\-'.]{0,60})(?:says|reports that|lists|identifies|shows|records that|prints)\b",
                        plain_of(sentence),
                        re.IGNORECASE,
                    ):
                        attr_count += 1
            if "what does this office do" in heading_l:
                for name in names:
                    if name and name in body:
                        errors.append(f"final/guide.md: office section names {name}")
                        break
            if heading_l.startswith("### recorded votes") or heading_l.startswith("## recorded votes"):
                for line in prose:
                    plain = plain_of(line)
                    if _is_gap_line(plain):
                        continue
                    if not (_VOTE_WORD_RE.search(plain) and _BILL_RE.search(plain) and _WHICH_RE.search(plain)):
                        errors.append("final/guide.md: recorded votes entry does not say the vote and what the bill did")
                        break
            if "time in elected office" in heading_l:
                plain = plain_of(" ".join(prose))
                if plain and not _is_gap_line(plain):
                    if not (_OFFICE_WORD_RE.search(plain) and re.search(r"\b(?:19|20)\d{2}\b", plain)):
                        errors.append("final/guide.md: time in office is not an office and a year")
            only_gap = bool(prose) and all(_is_gap_line(line) for line in prose)
            section_heading = bool(
                re.search(
                    r"what |who |any |background|recorded|education|time in|on the bench|"
                    r"appointed|notable|where do|ballot|support",
                    heading_l,
                )
            )
            if section_heading:
                gap_run = gap_run + 1 if only_gap else 0
            else:
                gap_run = 0
            if gap_run >= 3:
                errors.append(f"final/guide.md: {contest_id} has three gap-only headings in a row")
                gap_run = 0
            if "who is paying" in heading_l or "months in this report" in body.lower():
                if re.search(r"\|\s*\d{1,3}\s*(?:\[\^|\|)", body) and not re.search(
                    rf"{_MONTH_RE}\s+\d{{1,2}},\s+\d{{4}}", body
                ):
                    errors.append(f"final/guide.md: {contest_id} money table has no report dates")
                raised = _row_amounts(body, "Raised")
                loans = _row_amounts(body, "Self-funding")
                for left, right in zip(raised, loans):
                    if left and right and left == right and left != "$0":
                        errors.append(f"final/guide.md: {contest_id} self-funding equals total raised")
                        break
        if attr_count > 1:
            errors.append(f"final/guide.md: {contest_id} has more than one attribution lead")
        prose_for_jargon = "\n".join(
            line for line in chunk.splitlines() if line.strip() and not line.strip().startswith("#")
        )
        for term, phrase in _JARGON:
            definition = phrase[len(term) :].strip()
            token = re.compile(rf"\b{re.escape(term)}\b" if term[-1].isalnum() else re.escape(term))
            match = token.search(prose_for_jargon)
            if not match:
                continue
            earlier = prose_for_jargon[: match.start()]
            ahead = prose_for_jargon[match.start() : match.end() + len(definition) + 8]
            if definition not in earlier and definition not in ahead:
                errors.append(f"final/guide.md: {contest_id} uses {term} before defining it")
        if "amendment" in contest_id or "measure" in contest_id or "lagoon" in contest_id or "school" in contest_id:
            norms = []
            for _heading, body in bodies:
                for line in body.splitlines():
                    stripped_line = line.strip()
                    if not stripped_line or stripped_line.startswith(("|", ":", ":::", "<", "<!--", "[", "{")):
                        continue
                    for sentence in split_sentences(line):
                        key = _norm(sentence)
                        if not key or key in {":::", "::: vote-box", "::: card"}:
                            continue
                        norms.append(key)
            if len(norms) != len(set(norms)):
                errors.append(f"final/guide.md: {contest_id} repeats a sentence")
    for match in re.finditer(r"\{#profile-([^}\s]+)", text):
        item_id = match.group(1)
        if item_id in limited or item_id.startswith("retention-"):
            continue
        end = text.find("\n## ", match.end())
        chunk = text[match.start() : end if end != -1 else match.start() + 2500]
        if "### Background" not in chunk:
            errors.append(f"final/guide.md: {item_id} is missing a Background section")
            continue
        after = chunk.split("### Background", 1)[1]
        prose = [
            line.strip()
            for line in after.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not prose:
            errors.append(f"final/guide.md: {item_id} Background section is empty")
    return errors


def _row_amounts(chunk: str, label: str) -> list[str]:
    amounts = []
    for line in chunk.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not cells[0].lower().startswith(label.lower()):
            continue
        for cell in cells[1:]:
            plain = re.sub(r"<[^>]+>", "", cell)
            plain = _MARKER_RE.sub("", plain)
            plain = re.sub(r"\[[^\]]*\]\([^)]*\)", "", plain)
            plain = re.sub(r"\s+", "", plain)
            amounts.append(plain if plain.startswith("$") else "")
    return amounts


def draft_street_errors(workspace) -> list[str]:
    """Candidate drafts may not carry a home address."""
    from lib.util import iter_items

    errors = []
    for item in iter_items(workspace):
        if not item.name.startswith("cand-"):
            continue
        draft = item / "draft.md"
        if not draft.exists():
            continue
        text = draft.read_text(encoding="utf-8")
        spans = street_spans(text)
        if spans:
            errors.append(f"items/{item.name}/draft.md: street address in a candidate section: {spans[0][:80]}")
        lowered = text.casefold()
        for token in ("chapman", "6070"):
            if token in lowered:
                errors.append(f"items/{item.name}/draft.md: private token {token!r}")
    return errors
