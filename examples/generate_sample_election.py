#!/usr/bin/env python3
"""Write the fictional Cedar Hollow fixture. People, places, and documents are invented."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.util import dump_json, dump_yaml
from lib.workflow import assemble_guide, write_status

DEST = ROOT / "examples" / "sample-election"
CLOCK = "2026-10-20 12:00 ET"
RETRIEVED = "2026-10-20 09:30 ET"


def source(marker, publisher, title, doc_type, published, quote, url, locator, tier="T1", confidence="verified"):
    return {
        "marker": marker,
        "url": url,
        "archive_url": None,
        "archive_failed": True,
        "archive_failed_reason": "Fictional example; no live document exists.",
        "publisher": publisher,
        "title": title,
        "doc_type": doc_type,
        "published": published,
        "retrieved": RETRIEVED,
        "tier": tier,
        "locator": locator,
        "quote": quote,
        "confidence": confidence,
    }


def claim(cid, section, text, sources, **extra):
    data = {
        "id": cid,
        "section": section,
        "text": text,
        "marker": sources[0]["marker"],
        "sources": sources,
        "confidence": extra.pop("confidence", "verified"),
        "drives_summary": extra.pop("drives_summary", True),
        "polarity": extra.pop("polarity", "neutral"),
        "about_person": extra.pop("about_person", False),
    }
    data.update(extra)
    if data["about_person"] and "identity_attributes" not in data:
        data["identity_attributes"] = ["ballot_name", "office"]
    return data


def signoffs(clock, round_number, signed=True):
    return {
        name: {"signed": signed, "at": clock if signed else None, "round": round_number if signed else None}
        for name in ("factcheck", "sourcing", "neutrality", "privacy-legal")
    }


def loop_state(item_id, status, round_number, signed, gaps=None):
    return {
        "item_id": item_id,
        "round": round_number,
        "max_rounds": 3,
        "mode": "initial",
        "status": status,
        "open_counts": {"blocker": 0, "major": 0, "minor": 0},
        "signoffs": signoffs(CLOCK, round_number, signed),
        "gaps": gaps or [],
        "removed_claims": [],
        "updated_at": CLOCK,
    }


def effort(item_id, searches, fetches, minutes):
    sections = {
        "identity": {"searches": 2, "fetches": 1},
        "prior offices and public service": {"searches": 1, "fetches": 1},
        "occupational history": {"searches": 1, "fetches": 1},
        "education": {"searches": 1, "fetches": 1},
        "campaign funding": {"searches": 2, "fetches": 1},
        "record vs rhetoric": {"searches": 1, "fetches": 1},
        "positions in own words": {"searches": 1, "fetches": 1},
        "debates and forums": {"searches": 1, "fetches": 1},
        "endorsements": {"searches": 1, "fetches": 1},
        "legal issues": {"searches": 1, "fetches": 1},
        "strongest case": {"searches": 0, "fetches": 0},
    }
    return {
        "item_id": item_id,
        "searches": searches,
        "fetches": fetches,
        "minutes": minutes,
        "sections": sections,
        "explanation": "",
    }


def write_item(item_id, claims_doc, draft, state, effort_doc, findings, changelog, identity=None):
    item = DEST / "items" / item_id
    item.mkdir(parents=True, exist_ok=True)
    (item / "sources").mkdir(exist_ok=True)
    dump_yaml(item / "claims.yaml", claims_doc)
    (item / "draft.md").write_text(draft.strip() + "\n", encoding="utf-8")
    dump_json(item / "loop-state.json", state)
    dump_json(item / "effort.json", effort_doc)
    dump_yaml(item / "findings.yaml", findings)
    (item / "CHANGELOG.md").write_text(changelog.strip() + "\n", encoding="utf-8")
    if identity:
        dump_yaml(item / "identity.yaml", identity)


def quinn_claims():
    office = "Oak County Elections (fictional)"
    ballot = source(
        1,
        office,
        "Sample ballot, Cedar Hollow, November 3, 2026",
        "Official sample ballot",
        "2026-09-15",
        "Avery Quinn, Mayor, Nonpartisan, Incumbent.",
        "https://fictional.example/oak-county/2026/sample-ballot",
        "Mayor contest, first name",
    )
    council = source(
        2,
        "Cedar Hollow Clerk (fictional)",
        "City council election certificate, 2018",
        "Election certificate",
        "2018-11-20",
        "Avery Quinn was elected to a four-year council term.",
        "https://fictional.example/cedar-hollow/certificates/2018-council",
        "Certificate body",
    )
    job = source(
        3,
        "Westland Schools (fictional)",
        "Staff directory extract, 2018",
        "Employer directory",
        "2018-06-01",
        "Avery Quinn, classroom teacher, 2004 through 2018.",
        "https://fictional.example/westland-schools/staff-2018",
        "Teacher table",
    )
    school = source(
        4,
        "State University of Westland (fictional)",
        "Registrar confirmation letter",
        "Education record",
        "2004-05-20",
        "Avery Quinn received a bachelor of arts degree in 2004.",
        "https://fictional.example/suw/registrar/quinn-2004",
        "Degree line",
    )
    filing = source(
        5,
        "Westland campaign finance office (fictional)",
        "Quinn for Cedar committee, quarter ending September 30, 2026",
        "Campaign filing",
        "2026-10-15",
        "Receipts 48200, disbursements 31000, cash on hand 17200, debt 0.",
        "https://fictional.example/westland-finance/quinn-2026-q3",
        "Summary page, lines 1 through 4",
    )
    vote = source(
        6,
        "Cedar Hollow Clerk (fictional)",
        "Council minutes, June 4, 2024",
        "Meeting minutes",
        "2024-06-04",
        "Mayor Quinn voted yes on the parks budget.",
        "https://fictional.example/cedar-hollow/minutes/2024-06-04",
        "Vote table, parks budget",
    )
    questions = source(
        7,
        "Cedar Hollow League of Voters (fictional)",
        "Mayoral questionnaire 2026",
        "Questionnaire",
        "2026-09-01",
        "I will ask the council to keep the levy at the amount printed on the ballot.",
        "https://fictional.example/ch-league/questionnaire-2026",
        "Quinn answer, parks question",
    )
    debate = source(
        8,
        "Cedar Hollow Library (fictional)",
        "Mayor forum recording, September 20, 2026",
        "Forum recording",
        "2026-09-20",
        "The parks budget I voted for is the one in the 2024 minutes.",
        "https://fictional.example/library/forum-2026-09-20",
        "Timestamp 00:14:10",
    )
    endorse = source(
        9,
        "Cedar Hollow Firefighters Association (fictional)",
        "Endorsement notice",
        "Organization statement",
        "2026-09-02",
        "The association endorses Avery Quinn for mayor.",
        "https://fictional.example/ch-firefighters/endorsement-2026",
        "Opening sentence",
        tier="T4",
        confidence="single-source",
    )
    claims = [
        claim("cand-quinn.identity.001", "identity", "Avery Quinn is on the Cedar Hollow mayoral ballot as the nonpartisan incumbent.", [ballot], about_person=True),
        claim("cand-quinn.prior-offices.001", "prior-offices", "Avery Quinn was elected to the Cedar Hollow council for a term that began in 2018.", [council], about_person=True, identity_attributes=["ballot_name", "city"]),
        claim("cand-quinn.occupation.001", "occupation", "Avery Quinn worked as a classroom teacher from 2004 through 2018.", [job], about_person=True, identity_attributes=["ballot_name", "occupation"]),
        claim("cand-quinn.education.001", "education", "Avery Quinn received a bachelor of arts degree from the State University of Westland in 2004.", [school], about_person=True),
        claim(
            "cand-quinn.funding.001",
            "funding",
            "The Quinn committee reported 48200 dollars in receipts and 17200 dollars in cash on hand for the quarter that ended September 30, 2026.",
            [filing],
            as_of="2026-09-30",
            filing_period="2026-07-01 through 2026-09-30",
        ),
        claim("cand-quinn.record.001", "record", "Mayor Quinn voted yes on the city parks budget on June 4, 2024.", [vote], about_person=True),
        claim("cand-quinn.positions.001", "positions", "Quinn wrote that the levy should stay at the amount printed on the ballot.", [questions], about_person=True),
        claim("cand-quinn.debates.001", "debates", "At a September 20, 2026 forum, Quinn pointed to the 2024 parks vote.", [debate], about_person=True),
        claim(
            "cand-quinn.endorsements.001",
            "endorsements",
            "The Cedar Hollow Firefighters Association says it endorses Avery Quinn.",
            [endorse],
            confidence="single-source",
            drives_summary=False,
            attribution_only=True,
            about_person=True,
        ),
    ]
    return {"item_id": "cand-quinn", "item_type": "candidate", "claims": claims}


def okonkwo_claims():
    office = "Oak County Elections (fictional)"
    ballot = source(
        10,
        office,
        "Sample ballot, Cedar Hollow, November 3, 2026",
        "Official sample ballot",
        "2026-09-15",
        "Blake Okonkwo, Mayor, Nonpartisan.",
        "https://fictional.example/oak-county/2026/sample-ballot",
        "Mayor contest, second name",
    )
    job = source(
        11,
        "Cedar Hollow Personnel (fictional)",
        "Parks planner appointment notice",
        "Personnel notice",
        "2016-03-01",
        "The parks director appointed Blake Okonkwo as a planner.",
        "https://fictional.example/cedar-hollow/personnel/okonkwo-2016",
        "Appointment paragraph",
    )
    school = source(
        12,
        "Westland State College (fictional)",
        "Registrar confirmation letter",
        "Education record",
        "2015-05-18",
        "Blake Okonkwo received a master of public administration degree in 2015.",
        "https://fictional.example/wsc/registrar/okonkwo-2015",
        "Degree line",
    )
    project = source(
        13,
        "Cedar Hollow Parks (fictional)",
        "River path project closeout, 2025",
        "Department report",
        "2025-12-01",
        "Planner Okonkwo managed the river path repair project.",
        "https://fictional.example/cedar-hollow/parks/river-path-2025",
        "Project lead line",
    )
    filing = source(
        14,
        "Westland campaign finance office (fictional)",
        "Okonkwo for Cedar committee, quarter ending September 30, 2026",
        "Campaign filing",
        "2026-10-15",
        "Receipts 30100, disbursements 18400, cash on hand 11700, debt 0.",
        "https://fictional.example/westland-finance/okonkwo-2026-q3",
        "Summary page, lines 1 through 4",
    )
    donor = source(
        19,
        "Westland campaign finance office (fictional)",
        "Okonkwo for Cedar itemized receipts, quarter ending September 30, 2026",
        "Campaign filing",
        "2026-10-15",
        "The largest receipt is 2500 dollars from Friends of the River Path.",
        "https://fictional.example/westland-finance/okonkwo-2026-q3-items",
        "Receipt schedule, first row",
    )
    questions = source(
        15,
        "Cedar Hollow League of Voters (fictional)",
        "Mayoral questionnaire 2026",
        "Questionnaire",
        "2026-09-01",
        "I will publish the parks repair list before I ask for a levy change.",
        "https://fictional.example/ch-league/questionnaire-2026",
        "Okonkwo answer, parks question",
    )
    debate = source(
        16,
        "Cedar Hollow Library (fictional)",
        "Mayor forum recording, September 20, 2026",
        "Forum recording",
        "2026-09-20",
        "I managed the river path repair and I will publish the project list.",
        "https://fictional.example/library/forum-2026-09-20",
        "Timestamp 00:28:40",
    )
    endorse = source(
        17,
        "Friends of the River Path (fictional)",
        "Endorsement notice",
        "Organization statement",
        "2026-09-05",
        "Friends of the River Path endorses Blake Okonkwo for mayor.",
        "https://fictional.example/river-path-friends/endorsement-2026",
        "Opening sentence",
        tier="T4",
        confidence="single-source",
    )
    mailer = source(
        18,
        "Quinn for Cedar committee (fictional)",
        "Campaign mailer, October 2026",
        "Campaign mailer",
        "2026-10-01",
        "Okonkwo's donors are mostly real-estate developers.",
        "https://fictional.example/quinn-mailer/2026-10",
        "Front panel",
        tier="T4",
        confidence="single-source",
    )
    disputed = claim(
        "cand-okonkwo.funding.002",
        "funding",
        "A Quinn campaign mailer said Okonkwo's donors are mostly real-estate developers.",
        [mailer, donor],
        confidence="disputed",
        drives_summary=False,
        attribution_only=True,
        about_person=True,
        identity_attributes=["ballot_name", "city"],
        polarity="negative",
        notes="Disputed. The itemized filing lists Friends of the River Path as the largest receipt.",
    )
    disputed.pop("marker", None)
    claims = [
        claim("cand-okonkwo.identity.001", "identity", "Blake Okonkwo is on the Cedar Hollow mayoral ballot as a nonpartisan challenger.", [ballot], about_person=True),
        claim("cand-okonkwo.occupation.001", "occupation", "The city appointed Blake Okonkwo as a parks planner in 2016.", [job], about_person=True, identity_attributes=["ballot_name", "occupation"]),
        claim("cand-okonkwo.education.001", "education", "Blake Okonkwo received a master of public administration degree from Westland State College in 2015.", [school], about_person=True),
        claim("cand-okonkwo.record.001", "record", "A 2025 parks report names Blake Okonkwo as the lead on the river path repair.", [project], about_person=True),
        claim(
            "cand-okonkwo.funding.001",
            "funding",
            "The Okonkwo committee reported 30100 dollars in receipts and 11700 dollars in cash on hand for the quarter that ended September 30, 2026.",
            [filing],
            as_of="2026-09-30",
            filing_period="2026-07-01 through 2026-09-30",
        ),
        disputed,
        claim("cand-okonkwo.positions.001", "positions", "Okonkwo wrote that any levy change should follow a published repair list.", [questions], about_person=True),
        claim("cand-okonkwo.debates.001", "debates", "At a September 20, 2026 forum, Okonkwo described managing the river path repair.", [debate], about_person=True),
        claim(
            "cand-okonkwo.endorsements.001",
            "endorsements",
            "Friends of the River Path says it endorses Blake Okonkwo.",
            [endorse],
            confidence="single-source",
            drives_summary=False,
            attribution_only=True,
            about_person=True,
        ),
    ]
    return {"item_id": "cand-okonkwo", "item_type": "candidate", "claims": claims}


def race_claims():
    ballot = source(
        32,
        "Oak County Elections (fictional)",
        "Sample ballot, Cedar Hollow, November 3, 2026",
        "Official sample ballot",
        "2026-09-15",
        "Mayor of Cedar Hollow, Avery Quinn and Blake Okonkwo.",
        "https://fictional.example/oak-county/2026/sample-ballot",
        "Mayor contest header",
    )
    quinn = source(
        33,
        "Oak County Elections (fictional)",
        "Sample ballot, Cedar Hollow, November 3, 2026",
        "Official sample ballot",
        "2026-09-15",
        "Avery Quinn, incumbent.",
        "https://fictional.example/oak-county/2026/sample-ballot",
        "Mayor contest, incumbent mark",
    )
    planner = source(
        34,
        "Cedar Hollow Personnel (fictional)",
        "Parks planner appointment notice",
        "Personnel notice",
        "2016-03-01",
        "Blake Okonkwo, parks planner.",
        "https://fictional.example/cedar-hollow/personnel/okonkwo-2016",
        "Job title line",
    )
    both = source(
        35,
        "Westland campaign finance office (fictional)",
        "2026 mayoral filings index",
        "Filing index",
        "2026-10-15",
        "Both mayoral committees filed a report for the quarter ending September 30, 2026.",
        "https://fictional.example/westland-finance/2026-mayor-index",
        "Mayor row",
    )
    office = source(
        40,
        "Oak County Elections (fictional)",
        "Elections office home page",
        "Official office page",
        "2026-10-01",
        "Official election information is published at this office.",
        "https://fictional.example/oak-county/elections",
        "Page header",
    )
    claims = [
        claim("race-mayor.contest.001", "contest", "Two candidates are listed for mayor of Cedar Hollow.", [ballot]),
        claim("race-mayor.contest.002", "contest", "Avery Quinn is marked incumbent on the sample ballot.", [quinn], about_person=True, identity_attributes=["ballot_name", "office"]),
        claim("race-mayor.contest.003", "contest", "Blake Okonkwo is a city parks planner.", [planner], about_person=True, identity_attributes=["ballot_name", "occupation"]),
        claim("race-mayor.funding.001", "funding", "Both mayoral committees filed a report covering the quarter that ended September 30, 2026.", [both]),
        claim("race-mayor.logistics.001", "logistics", "Oak County publishes election information on its elections office page.", [office], drives_summary=False),
    ]
    return {"item_id": "race-mayor", "item_type": "race", "claims": claims}


def measure_claims():
    title = source(
        20,
        "Oak County Elections (fictional)",
        "Measure H ballot label",
        "Official ballot label",
        "2026-09-15",
        "Measure H asks whether Cedar Hollow should replace the expiring parks levy.",
        "https://fictional.example/oak-county/2026/measure-h",
        "Ballot label, verbatim",
    )
    qualify = source(
        21,
        "Cedar Hollow Council (fictional)",
        "Resolution 2026-14, referring Measure H",
        "Council resolution",
        "2026-07-09",
        "The council referred Measure H to the November ballot.",
        "https://fictional.example/cedar-hollow/resolutions/2026-14",
        "Referral clause",
    )
    law = source(
        22,
        "Cedar Hollow Code (fictional)",
        "Parks levy chapter",
        "Municipal code",
        "2020-01-01",
        "The current parks levy expires after the 2026 tax year.",
        "https://fictional.example/cedar-hollow/code/parks-levy",
        "Expiration section",
    )
    yes = source(
        23,
        "Oak County Elections (fictional)",
        "Measure H ballot label",
        "Official ballot label",
        "2026-09-15",
        "A yes vote replaces the expiring levy at the same rate.",
        "https://fictional.example/oak-county/2026/measure-h",
        "Yes effect sentence",
    )
    no = source(
        24,
        "Oak County Elections (fictional)",
        "Measure H ballot label",
        "Official ballot label",
        "2026-09-15",
        "A no vote lets the current levy expire.",
        "https://fictional.example/oak-county/2026/measure-h",
        "No effect sentence",
    )
    fiscal = source(
        25,
        "Westland fiscal office (fictional)",
        "Measure H fiscal note",
        "Official fiscal note",
        "2026-08-01",
        "The note estimates 1.2 million dollars a year for parks if the levy passes.",
        "https://fictional.example/westland-fiscal/measure-h",
        "Estimate table",
    )
    threshold = source(
        26,
        "Westland Elections Code (fictional)",
        "Local levy approval rule",
        "Statute",
        "2019-01-01",
        "A local levy passes with more than half the votes cast on the measure.",
        "https://fictional.example/westland-code/levy-threshold",
        "Section 4",
    )
    support_money = source(
        27,
        "Westland campaign finance office (fictional)",
        "Yes on H committee, quarter ending September 30, 2026",
        "Campaign filing",
        "2026-10-12",
        "The Yes on H committee reported 20000 dollars in receipts.",
        "https://fictional.example/westland-finance/yes-on-h-q3",
        "Receipts line",
    )
    oppose_money = source(
        28,
        "Westland campaign finance office (fictional)",
        "No on H committee, quarter ending September 30, 2026",
        "Campaign filing",
        "2026-10-12",
        "The No on H committee reported 18000 dollars in receipts.",
        "https://fictional.example/westland-finance/no-on-h-q3",
        "Receipts line",
    )
    support_names = source(
        29,
        "Cedar Hollow pamphlet (fictional)",
        "Official arguments, Measure H",
        "Voter pamphlet",
        "2026-09-20",
        "The parks board and the library board signed the argument for Measure H.",
        "https://fictional.example/oak-county/2026/pamphlet-h",
        "Argument for, signature block",
    )
    oppose_names = source(
        30,
        "Cedar Hollow pamphlet (fictional)",
        "Official arguments, Measure H",
        "Voter pamphlet",
        "2026-09-20",
        "The homeowners association and a grocer signed the argument against Measure H.",
        "https://fictional.example/oak-county/2026/pamphlet-h",
        "Argument against, signature block",
    )
    claims = [
        claim("measure-h.title.001", "title", "The official label is Measure H, Parks levy.", [title]),
        claim("measure-h.qualification.001", "qualification", "The city council referred Measure H to the ballot.", [qualify]),
        claim("measure-h.law.001", "law", "The current parks levy expires after the 2026 tax year.", [law]),
        claim("measure-h.yes.001", "yes", "A yes vote replaces the expiring levy at the same rate.", [yes]),
        claim("measure-h.no.001", "no", "A no vote lets the current levy expire.", [no]),
        claim("measure-h.fiscal.001", "fiscal", "The official note estimates 1.2 million dollars a year for parks if the levy passes.", [fiscal], as_of="2026-08-01"),
        claim("measure-h.threshold.001", "threshold", "The measure needs more than half the votes cast on it.", [threshold]),
        claim("measure-h.funding.001", "funding", "Yes on H reported 20000 dollars in receipts for the quarter ending September 30, 2026.", [support_money], as_of="2026-09-30", filing_period="2026-07-01 through 2026-09-30"),
        claim("measure-h.funding.002", "funding", "No on H reported 18000 dollars in receipts for the quarter ending September 30, 2026.", [oppose_money], as_of="2026-09-30", filing_period="2026-07-01 through 2026-09-30"),
        claim("measure-h.supporters.001", "supporters", "The parks board and the library board signed the argument for Measure H.", [support_names]),
        claim("measure-h.opponents.001", "opponents", "A homeowners association and a grocer signed the argument against Measure H.", [oppose_names]),
    ]
    return {"item_id": "measure-h", "item_type": "measure", "claims": claims}


FOOTER = """
## Sources and retrieval dates

Source records for this item live in `claims.yaml`. The guide works-cited list is built from those records.

## Item changelog

See `CHANGELOG.md`.

## Findings and disputes

See `findings.yaml`.
"""


def quinn_draft():
    return f"""
# Avery Quinn

> **FICTIONAL EXAMPLE.** Avery Quinn is not a real person. Cedar Hollow and Westland are not real places.

## Identity

Avery Quinn appears on the fictional Cedar Hollow mayoral ballot[^1]. The office is mayor, the party line says nonpartisan, and the ballot marks the candidate as the incumbent[^1]. The filing lists the campaign site quinn-for-cedar.example[^1].

## Prior offices and public service

Avery Quinn was elected to the Cedar Hollow city council for a four-year term that began after the 2018 election[^2]. The certificate says the voters elected Quinn, rather than an appointment[^2].

## Occupational history

Before that council term, Avery Quinn worked as a classroom teacher from 2004 through 2018[^3]. The staff directory lists the role as teacher and does not list an ownership share in a business[^3].

## Education

The State University of Westland registrar says Avery Quinn received a bachelor of arts degree in 2004[^4]. No later degree was listed on the filing checked for this fictional profile[^4].

## Campaign funding

The Quinn committee filed on October 15, 2026 for the quarter that ended September 30, 2026[^5]. The summary lines show 48200 dollars in receipts, 31000 dollars spent, 17200 dollars in cash on hand, and no debt[^5]. Cash on hand means money the report still showed at the end of that filing period[^5].

## Record vs rhetoric

On June 4, 2024, Mayor Quinn voted yes on the city parks budget[^6]. In the 2026 questionnaire, Quinn wrote that the levy should stay at the amount printed on the ballot[^7]. The vote is a budget vote, and the questionnaire sentence is about a later levy question[^6][^7].

## Positions in own words

The Cedar Hollow League of Voters asked each mayoral candidate the same parks question[^7]. Quinn answered, "I will ask the council to keep the levy at the amount printed on the ballot."[^7]

## Debates and forums

Quinn spoke at the September 20, 2026 library forum[^8]. At 00:14:10 Quinn said, "The parks budget I voted for is the one in the 2024 minutes."[^8]

## Endorsements

The Cedar Hollow Firefighters Association said on September 2, 2026 that it endorses Avery Quinn[^9]. That sentence is the association's position, not a finding about Quinn's record[^9].

## Legal issues

Not found (searched: fictional Oak County court index, fictional Westland court index, and the candidate filing on 2026-10-20).

## Strongest case

The cited record shows an elected council term, a yes vote on the 2024 parks budget, and a filed finance report[^2][^6][^5].

## Interest-group ratings

Not found (searched: fictional paired rating pages). Omitted because ratings are included only when a pair from opposite sides exists.
{FOOTER}
"""


def okonkwo_draft():
    return f"""
# Blake Okonkwo

> **FICTIONAL EXAMPLE.** Blake Okonkwo is not a real person. Cedar Hollow and Westland are not real places.

## Identity

Blake Okonkwo appears on the fictional Cedar Hollow mayoral ballot[^10]. The office is mayor, the party line says nonpartisan, and the ballot does not mark the candidate as the incumbent[^10]. The filing lists the campaign site okonkwo-for-cedar.example[^10].

## Prior offices and public service

Not found (searched: fictional council certificates and the 2026 ballot filing).

## Occupational history

A city personnel notice says the parks director appointed Blake Okonkwo as a planner in 2016[^11]. The notice lists the role as employee and does not list ownership of a firm[^11].

## Education

Westland State College says Blake Okonkwo received a master of public administration degree in 2015[^12]. No other degree was listed on the filing checked for this fictional profile[^12].

## Campaign funding

The Okonkwo committee filed on October 15, 2026 for the quarter that ended September 30, 2026[^14]. The summary lines show 30100 dollars in receipts, 18400 dollars spent, 11700 dollars in cash on hand, and no debt[^14].

A Quinn campaign mailer said Okonkwo's donors are mostly real-estate developers[^18]. The itemized filing instead lists a 2500 dollar receipt from Friends of the River Path as the largest line[^19]. This characterization is disputed and is not used in the summary[^18][^19].

## Record vs rhetoric

A 2025 parks department report names Blake Okonkwo as the lead on the river path repair[^13]. In the questionnaire, Okonkwo wrote that a levy change should follow a published repair list[^15]. The report describes a completed project, and the questionnaire talks about a future list[^13][^15].

## Positions in own words

The Cedar Hollow League of Voters asked each mayoral candidate the same parks question[^15]. Okonkwo answered, "I will publish the parks repair list before I ask for a levy change."[^15]

## Debates and forums

Okonkwo spoke at the September 20, 2026 library forum[^16]. At 00:28:40 Okonkwo said, "I managed the river path repair and I will publish the project list."[^16]

## Endorsements

Friends of the River Path said on September 5, 2026 that it endorses Blake Okonkwo[^17]. That sentence is the group's position, not a finding about Okonkwo's record[^17].

## Legal issues

Not found (searched: fictional Oak County court index, fictional Westland court index, and the candidate filing on 2026-10-20).

## Strongest case

The cited record shows a parks planner appointment, the river path project, and a filed finance report[^11][^13][^14].

## Interest-group ratings

Not found (searched: fictional paired rating pages). Omitted because ratings are included only when a pair from opposite sides exists.
{FOOTER}
"""


def race_draft():
    return """
# Mayor of Cedar Hollow

> **FICTIONAL EXAMPLE.** This race is invented.

<!-- summary -->
Two people are running for mayor of Cedar Hollow[^32]. Avery Quinn is the current mayor[^33]. Blake Okonkwo is a city parks planner[^34]. Both filed a campaign finance report for the quarter that ended in September 2026[^35].

## Contest

The fictional sample ballot lists the office of mayor of Cedar Hollow[^32]. The term and the seat are the ones printed on that ballot[^32].

## Comparison

| Topic | Avery Quinn | Blake Okonkwo |
| --- | --- | --- |
| Ballot line | Nonpartisan incumbent[^33] | Nonpartisan challenger[^10] |
| Work cited here | Teacher, then council and mayor[^3][^2] | Parks planner since 2016[^11] |
| Latest filing | Quarter ending September 30, 2026[^5] | Quarter ending September 30, 2026[^14] |

## Competitiveness

Not found (searched: fictional poll indexes and rating pages on 2026-10-20).

## Candidate profiles

- Avery Quinn profile: items/cand-quinn/draft.md[^32]
- Blake Okonkwo profile: items/cand-okonkwo/draft.md[^32]

## Write-in candidates

None.

## Withdrawn candidates

None.

## Uncontested

The sample ballot lists two active candidates for mayor[^32].

## Sources and retrieval dates

Source records for this item live in `claims.yaml`.

## Item changelog

See `CHANGELOG.md`.

## Findings and disputes

See `findings.yaml`.
"""


def measure_draft():
    return """
# Measure H, Cedar Hollow parks levy

> **FICTIONAL EXAMPLE.** This measure is invented.

<!-- summary -->
Measure H asks Cedar Hollow voters about a parks levy[^20]. A levy is a tax the ballot asks voters to accept or reject[^20]. A yes vote would replace the expiring levy at the same rate[^23]. A no vote would let that levy expire[^24].

## Official title

The official label is Measure H, a parks levy, and it asks whether Cedar Hollow should replace the expiring parks levy[^20].

## Measure type and qualification

Measure H is a referral[^21]. The Cedar Hollow council sent it to the ballot by Resolution 2026-14 on July 9, 2026[^21].

## Plain-language summary

The measure would replace a parks levy that is set to end[^22]. It does not add a second levy on top of a levy that continues[^22][^23].

## Current law and proposed change

The city code says the current parks levy expires after the 2026 tax year[^22]. A yes vote replaces it at the same rate[^23]. A no vote lets it expire[^24].

## What a yes vote does

A yes vote replaces the expiring parks levy at the same rate[^23]. The official fiscal note ties that rate to about 1.2 million dollars a year for parks[^25].

## What a no vote does

A no vote lets the current parks levy expire after the 2026 tax year[^24]. The code section on expiration is the same one cited for current law[^22].

## Fiscal impact

The Westland fiscal office note, dated August 1, 2026, estimates 1.2 million dollars a year for parks if the levy passes[^25].

Not found (searched: fictional university budget notes and fictional news budget notes).

## Vote threshold

Westland's levy rule says the measure passes with more than half the votes cast on it[^26].

## Funding by side

Yes on H reported 20000 dollars in receipts for the quarter that ended September 30, 2026[^27]. No on H reported 18000 dollars in receipts for that same quarter[^28].

## Arguments for

The pamphlet argument for Measure H says the levy keeps the current parks hours and repair work going[^29]. The parks board and the library board signed that argument[^29]. Supporters point to the fiscal note's yearly amount as the scale of the work[^25].

## Arguments against

The pamphlet argument against Measure H says the city should let the levy end and pay for parks from the existing budget[^30]. A homeowners association and a grocer signed that argument[^30]. Opponents also point to the fiscal note so readers can see the yearly amount[^25].

## Supporters and opponents

The parks board and the library board signed the argument for the measure[^29]. A homeowners association and a grocer signed the argument against it[^30].

## Sources and retrieval dates

Source records for this item live in `claims.yaml`.

## Item changelog

See `CHANGELOG.md`.

## Findings and disputes

See `findings.yaml`.
"""


def main() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    (DEST / "items").mkdir()
    (DEST / "final").mkdir()
    (DEST / "imports").mkdir()

    dump_yaml(
        DEST / "intake.yaml",
        {
            "election_id": "fictional-cedar-hollow-2026",
            "requester_label": "household",
            "election_date": "2026-11-03",
            "election_type": "general",
            "jurisdiction_label": "Cedar Hollow, Oak County, Westland",
            "scope": "whole_ballot",
            "contest_ids": ["race-mayor", "measure-h"],
            "include_legislation": False,
            "legislation_topics": [],
            "depth": "standard",
            "formats": ["md", "html", "pdf"],
            "languages": ["en"],
            "accessibility_needs": "Plain language summaries and a single HTML page.",
            "offline_archive": False,
            "parallel_subagents": False,
            "address_location": None,
            "sharing_approved": False,
            "sharing_approved_at": None,
            "ballot_photo_deleted": True,
            "notes": "Fictional fixture. No real requester and no street address.",
        },
    )
    dump_yaml(
        DEST / "ballot.yaml",
        {
            "election_id": "fictional-cedar-hollow-2026",
            "fiction": True,
            "confirmed_by_requester": True,
            "confirmed_at": "2026-10-20 10:00 ET",
            "report_version": "v1.0",
            "lookup_status": "manual_official_ballot",
            "lookup_source": None,
            "lookup_error": None,
            "election": {
                "name": "Cedar Hollow general election",
                "date": "2026-11-03",
                "type": "general",
                "jurisdiction": {"state": "Westland", "county": "Oak County", "city": "Cedar Hollow"},
            },
            "logistics": [
                {
                    "label": "Oak County elections office (fictional)",
                    "url": "https://fictional.example/oak-county/elections",
                    "marker": 40,
                }
            ],
            "contests": [
                {
                    "id": "race-mayor",
                    "item_id": "race-mayor",
                    "type": "race",
                    "title": "Mayor of Cedar Hollow",
                    "official_source_url": "https://fictional.example/oak-county/2026/sample-ballot",
                    "district": "Cedar Hollow",
                    "candidates": [
                        {
                            "id": "cand-quinn",
                            "item_id": "cand-quinn",
                            "name": "Avery Quinn",
                            "party": "nonpartisan",
                            "incumbent": True,
                            "withdrawn": False,
                            "write_in": False,
                            "limited_public_record": False,
                        },
                        {
                            "id": "cand-okonkwo",
                            "item_id": "cand-okonkwo",
                            "name": "Blake Okonkwo",
                            "party": "nonpartisan",
                            "incumbent": False,
                            "withdrawn": False,
                            "write_in": False,
                            "limited_public_record": False,
                        },
                    ],
                },
                {
                    "id": "measure-h",
                    "item_id": "measure-h",
                    "type": "measure",
                    "title": "Measure H, Cedar Hollow parks levy",
                    "official_source_url": "https://fictional.example/oak-county/2026/measure-h",
                    "district": "Cedar Hollow",
                    "candidates": [],
                },
            ],
            "conflicts": [],
            "notes": ["Fictional fixture. Contests were written from invented official documents, not a live API."],
        },
    )
    (DEST / "logistics.md").write_text(
        """# Official election office links

Use the official election office, not this guide, for dates, deadlines, and polling places[^40].

- Oak County elections office (fictional): https://fictional.example/oak-county/elections[^40]
""",
        encoding="utf-8",
    )
    (DEST / "sources-map.md").write_text(
        """# Source map

> **FICTIONAL EXAMPLE.** These publishers are invented.

## Official

- Oak County Elections (fictional). T1. Sample ballot and Measure H label. https://fictional.example/oak-county/2026/sample-ballot
- Westland campaign finance office (fictional). T1. Committee summaries. https://fictional.example/westland-finance/2026-mayor-index
- Westland fiscal office (fictional). T1. Measure H note. https://fictional.example/westland-fiscal/measure-h

## Nonpartisan reference

- Cedar Hollow League of Voters (fictional). T2 for this fixture's questionnaire. https://fictional.example/ch-league/questionnaire-2026

## Advocacy, attributed only

- Cedar Hollow Firefighters Association (fictional) and Friends of the River Path (fictional) for endorsements.
- Quinn for Cedar mailer (fictional), used only as the mailer's claim and marked disputed.

Ownership and funding of these fictional publishers: not found (searched: the invented pages above). Do not treat this map as a real source list.
""",
        encoding="utf-8",
    )
    (DEST / "env.md").write_text(
        "# Environment\n\nThis fixture does not claim a live machine rating. A real run copies `output/env.md` here after bootstrap.\n",
        encoding="utf-8",
    )
    changelog_header = (
        "# Changelog\n\n"
        "Format: `CL-id | round | finding id | claim id | before -> after | reason | timestamp ET`\n"
    )
    write_item(
        "cand-quinn",
        quinn_claims(),
        quinn_draft(),
        loop_state("cand-quinn", "signed-off", 1, True),
        effort("cand-quinn", 12, 8, 40),
        [
            {
                "id": "F-0001",
                "round": 1,
                "reviewer": "sourcing",
                "claim_id": "cand-quinn.funding.001",
                "type": "sourcing",
                "severity": "minor",
                "issue": "The first draft omitted the October 15, 2026 filing date.",
                "evidence": ["https://fictional.example/westland-finance/quinn-2026-q3", "Filing stamp line"],
                "status": "accepted",
                "response": {
                    "action": "fix",
                    "rationale": "Added the filing date and the quarter end to the funding section.",
                    "evidence": [],
                    "changelog_ref": "CL-0001",
                },
            }
        ],
        changelog_header
        + "\nCL-0001 | 1 | F-0001 | cand-quinn.funding.001 | funding sentence without a filing date -> filing date and quarter end added | The Q3 report was filed 2026-10-15 | 2026-10-20 11:00 ET\n",
        {
            "item_id": "cand-quinn",
            "full_legal_name": "Avery Jordan Quinn",
            "ballot_name": "Avery Quinn",
            "office": "Mayor of Cedar Hollow",
            "district": "Cedar Hollow",
            "city": "Cedar Hollow",
            "county": "Oak County",
            "state": "Westland",
            "filing_ids": ["WL-FICTION-1001"],
            "campaign_site": "https://quinn-for-cedar.example/",
            "description": "Adult candidate listed on the fictional Cedar Hollow mayoral ballot as the incumbent.",
            "photo_included": False,
        },
    )
    write_item(
        "cand-okonkwo",
        okonkwo_claims(),
        okonkwo_draft(),
        loop_state("cand-okonkwo", "capped-disputed", 3, False),
        effort("cand-okonkwo", 12, 9, 42),
        [
            {
                "id": "F-0002",
                "round": 1,
                "reviewer": "neutrality",
                "claim_id": "cand-okonkwo.funding.002",
                "type": "neutrality",
                "severity": "major",
                "issue": "The mailer's donor characterization was written as if it were a finding. The itemized filing does not show a developer majority.",
                "evidence": [
                    "https://fictional.example/westland-finance/okonkwo-2026-q3-items",
                    "Largest receipt is Friends of the River Path, 2500 dollars.",
                ],
                "status": "disputed",
                "coordinator_note": "Unresolved major at MAX_ROUNDS. The mailer stays attributed and disputed. It does not drive the summary.",
                "response": {
                    "action": "dispute",
                    "rationale": "The mailer sentence is kept only as the mailer's words, next to the filing line. It is not a fact about the donor list.",
                    "evidence": ["https://fictional.example/quinn-mailer/2026-10"],
                },
            }
        ],
        changelog_header
        + "\nCL-0002 | 3 | F-0002 | cand-okonkwo.funding.002 | mailer sentence stated as fact -> attributed and marked disputed | Cap on an unresolved major | 2026-10-20 11:30 ET\n",
        {
            "item_id": "cand-okonkwo",
            "full_legal_name": "Blake Amari Okonkwo",
            "ballot_name": "Blake Okonkwo",
            "office": "Mayor of Cedar Hollow",
            "district": "Cedar Hollow",
            "city": "Cedar Hollow",
            "county": "Oak County",
            "state": "Westland",
            "filing_ids": ["WL-FICTION-1002"],
            "campaign_site": "https://okonkwo-for-cedar.example/",
            "description": "Adult candidate listed on the fictional Cedar Hollow mayoral ballot as the challenger.",
            "photo_included": False,
        },
    )
    empty_findings_changelog = changelog_header + "\n"
    write_item(
        "race-mayor",
        race_claims(),
        race_draft(),
        loop_state("race-mayor", "signed-off", 1, True),
        {"item_id": "race-mayor", "searches": 6, "fetches": 4, "minutes": 20, "sections": {}, "explanation": ""},
        [],
        empty_findings_changelog,
    )
    write_item(
        "measure-h",
        measure_claims(),
        measure_draft(),
        loop_state("measure-h", "signed-off", 1, True),
        {"item_id": "measure-h", "searches": 8, "fetches": 6, "minutes": 30, "sections": {}, "explanation": ""},
        [],
        empty_findings_changelog,
    )
    (DEST / "README.md").write_text(
        """# Fictional sample election

**This entire folder is fiction.** Cedar Hollow, Oak County, and the State of Westland are invented. Avery Quinn and Blake Okonkwo are not real people. Every URL under `fictional.example` is a placeholder. Do not use this guide to vote. Do not cite it as a source about any real election.

It shows the file shape a real run keeps in git-ignored `output/`: intake, a confirmed ballot, item claims, a review finding that was fixed, a claim left disputed at the round cap, and `final/guide.md`.

Rebuild the guide after a script change:

```bash
.venv/bin/python examples/generate_sample_election.py
.venv/bin/python scripts/assemble.py --workspace examples/sample-election --today 2026-10-20 --now "2026-10-20 12:00 ET"
```

The generator already runs the assembler.
""",
        encoding="utf-8",
    )
    errors = assemble_guide(DEST, "2026-10-20")
    if errors:
        raise SystemExit("\n".join(errors))
    write_status(DEST, CLOCK)
    print(f"Wrote {DEST}")


if __name__ == "__main__":
    main()
