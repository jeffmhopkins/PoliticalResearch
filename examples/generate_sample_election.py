#!/usr/bin/env python3
"""Write the fictional Cedar Hollow fixture. People, places, and documents are invented."""

from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.util import dump_json, dump_yaml, load_yaml
from lib.workflow import assemble_guide, write_status

DEST = ROOT / "examples" / "sample-election"
CLOCK = "2026-10-20 12:00 ET"
RETRIEVED = "2026-10-20 09:30 ET"


def source(marker, publisher, title, doc_type, published, quote, url, locator, tier="T1", confidence="verified", archive_url=None, local_copy=None):
    failed = archive_url is None
    row = {
        "marker": marker,
        "url": url,
        "archive_url": archive_url,
        "archive_failed": failed,
        "archive_failed_reason": "Fictional example; no live document exists." if failed else None,
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
    if local_copy:
        row["local_copy"] = local_copy
    return row


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
        "party": {"searches": 2, "fetches": 1},
        "endorsements": {"searches": 1, "fetches": 1},
        "outside spending": {"searches": 1, "fetches": 1},
        "attendance": {"searches": 1, "fetches": 1},
        "financial disclosure": {"searches": 1, "fetches": 1},
        "term limits": {"searches": 1, "fetches": 1},
        "promises versus record": {"searches": 1, "fetches": 1},
        "questionnaire answers": {"searches": 1, "fetches": 1},
        "fact checks": {"searches": 1, "fetches": 1},
        "ethics and elections orders": {"searches": 1, "fetches": 1},
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


def write_item(item_id, claims_doc, draft, state, effort_doc, findings, changelog, identity=None, profile=None):
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
    if profile:
        dump_yaml(item / "profile.yaml", profile)


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
        archive_url="https://fictional.example/archive/quinn-2026-q3",
        local_copy="saved/quinn-q3.html",
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
    depth = "saved/quinn-depth.html"
    depth_archive = "https://fictional.example/archive/quinn-depth"
    ballot_party = source(41, office, "Sample ballot, Cedar Hollow, November 3, 2026", "Official sample ballot", "2026-09-15", "Avery Quinn, Mayor, Nonpartisan.", "https://fictional.example/oak-county/2026/sample-ballot", "Mayor contest, party column")
    registration = source(42, office, "Voter registration extract, Avery Quinn", "Voter registration", "2026-09-01", "Avery Quinn, No Party Affiliation.", "https://fictional.example/oak-county/registration/quinn", "Party field")
    change = source(43, office, "Registration change, Avery Quinn", "Voter registration", "2019-03-12", "Party change from Republican to No Party Affiliation on 2019-03-12.", "https://fictional.example/oak-county/registration/quinn-2019", "Change line")
    small = source(46, "Westland campaign finance office (fictional)", "Quinn itemized receipts, small donors", "Campaign filing", "2026-10-15", "Small donors at or under 200 dollars gave 12000 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3-items", "Small-donor total", archive_url=depth_archive, local_copy=depth)
    large = source(47, "Westland campaign finance office (fictional)", "Quinn itemized receipts, large donors", "Campaign filing", "2026-10-15", "Large donors gave 20000 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3-items", "Large-donor total", archive_url=depth_archive, local_copy=depth)
    district_money = source(48, "Westland campaign finance office (fictional)", "Quinn itemized receipts, in-district", "Campaign filing", "2026-10-15", "In-district donors gave 15000 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3-items", "In-district total", archive_url=depth_archive, local_copy=depth)
    loans = source(49, "Westland campaign finance office (fictional)", "Quinn loans and self-funding", "Campaign filing", "2026-10-15", "Loans and self-funding were 0 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3", "Loan line", archive_url=depth_archive, local_copy=depth)
    pac = source(50, "Westland campaign finance office (fictional)", "Quinn PAC receipts", "Campaign filing", "2026-10-15", "PAC committees gave 8000 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3-items", "PAC total", archive_url=depth_archive, local_copy=depth)
    party_money = source(51, "Westland campaign finance office (fictional)", "Quinn party committee receipts", "Campaign filing", "2026-10-15", "Party committee money was 0 dollars.", "https://fictional.example/westland-finance/quinn-2026-q3-items", "Party total", archive_url=depth_archive, local_copy=depth)
    outside = source(52, "Westland campaign finance office (fictional)", "Independent expenditure index, mayor", "Independent expenditure filing", "2026-10-15", "Independent expenditures for Avery Quinn were 0 dollars and independent expenditures against Avery Quinn were 0 dollars.", "https://fictional.example/westland-finance/ie-mayor-2026", "Quinn row", archive_url=depth_archive, local_copy=depth)
    meetings = source(60, "Cedar Hollow Clerk (fictional)", "Council attendance, 2025", "Meeting roll", "2026-01-15", "Quinn attended 11 of 12 meetings. The median was 10 of 12.", "https://fictional.example/cedar-hollow/attendance/2025", "Attendance table")
    disclosure = source(61, "Cedar Hollow Clerk (fictional)", "Local disclosure, Avery Quinn, 2026", "Financial disclosure", "2026-07-01", "The disclosure lists a parks-bond holding.", "https://fictional.example/cedar-hollow/disclosure/quinn-2026", "Holdings line")
    promise = source(62, "Quinn for Cedar committee (fictional)", "Campaign site, first platform item", "Campaign site", "2026-09-01", "The first platform item says the levy stays at the ballot amount.", "https://quinn-for-cedar.example/platform", "First item")
    vote411 = source(64, "Vote411 (fictional extract)", "Vote411 mayor page", "Questionnaire", "2026-10-01", "Vote411 shows no reply from Avery Quinn.", "https://fictional.example/vote411/cedar-mayor", "Quinn row", tier="T2")
    ballotpedia = source(65, "Ballotpedia (fictional extract)", "Ballotpedia candidate survey", "Questionnaire", "2026-10-01", "No survey answers from Avery Quinn.", "https://fictional.example/ballotpedia/quinn", "Survey block", tier="T2")
    votesmart = source(66, "VoteSmart (fictional extract)", "VoteSmart candidate page", "Questionnaire", "2026-10-01", "No VoteSmart submission from Avery Quinn.", "https://fictional.example/votesmart/quinn", "Submission line", tier="T2")
    term = source(70, "Cedar Hollow Clerk (fictional)", "City charter, mayor term limit", "Charter", "2026-01-01", "Avery Quinn is eligible through 2030.", "https://fictional.example/cedar-hollow/charter/mayor", "Term section")
    fact = source(72, "PolitiFact Florida (fictional extract)", "Search method note", "Fact-check method", "2026-10-01", "A statement that was never checked is not the same as a statement checked out clean.", "https://fictional.example/politifact/method", "Absence note", tier="T2")
    parks_vote = source(76, "Cedar Hollow Clerk (fictional)", "Council minutes, June 4, 2024", "Meeting minutes", "2024-06-04", "Mayor Quinn voted yes on the parks budget.", "https://fictional.example/cedar-hollow/minutes/2024-06-04", "Vote table, parks budget")
    claims = [
        claim("cand-quinn.identity.001", "identity", "Avery Quinn is on the Cedar Hollow mayoral ballot as the nonpartisan incumbent.", [ballot], about_person=True),
        claim("cand-quinn.prior-offices.001", "prior-offices", "Avery Quinn was elected to the Cedar Hollow council for a term that began in 2018.", [council], about_person=True, identity_attributes=["ballot_name", "city"]),
        claim("cand-quinn.occupation.001", "occupation", "Avery Quinn worked as a classroom teacher from 2004 through 2018.", [job], about_person=True, identity_attributes=["ballot_name", "occupation"]),
        claim("cand-quinn.education.001", "education", "Avery Quinn received a bachelor of arts degree from the State University of Westland in 2004.", [school], about_person=True),
        claim(
            "cand-quinn.funding.001",
            "funding",
            "Avery Quinn's Cedar Hollow committee reported 48200 dollars in receipts and 17200 dollars in cash on hand for the quarter that ended September 30, 2026.",
            [filing],
            as_of="2026-09-30",
            filing_period="2026-07-01 through 2026-09-30",
            about_person=True,
        ),
        claim("cand-quinn.record.001", "record", "Mayor Avery Quinn of Cedar Hollow voted yes on the city parks budget on June 4, 2024.", [vote], about_person=True),
        claim("cand-quinn.positions.001", "positions", "Avery Quinn of Cedar Hollow wrote that the levy should stay at the amount printed on the ballot.", [questions], about_person=True),
        claim("cand-quinn.debates.001", "debates", "At a September 20, 2026 forum in Cedar Hollow, Avery Quinn pointed to the 2024 parks vote.", [debate], about_person=True),
        claim(
            "cand-quinn.endorsements.001",
            "endorsements",
            "The Cedar Hollow Firefighters Association says it endorses Avery Quinn.",
            [endorse],
            confidence="single-source",
            drives_summary=False,
            attribution_only=True,
            about_person=True,
            endorsement={"endorser": "Cedar Hollow Firefighters Association", "endorser_type": "union", "date": "2026-09-02", "source_role": "endorser_statement"},
        ),
        claim("cand-quinn.party.001", "party", "The sample ballot places Avery Quinn of Cedar Hollow in a Nonpartisan race.", [ballot_party], about_person=True),
        claim("cand-quinn.party.002", "party", "Voter registration lists Avery Quinn of Cedar Hollow as no party affiliation, a registered party on a nonpartisan race.", [registration], about_person=True),
        claim("cand-quinn.party.003", "party", "In 2019 Avery Quinn of Cedar Hollow left the Republican listing.", [change], about_person=True),
        claim("cand-quinn.funding.002", "funding", "Small donors at or under 200 dollars gave 12000 dollars to Avery Quinn of Cedar Hollow.", [small], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.funding.003", "funding", "Large donors gave 20000 dollars to Avery Quinn of Cedar Hollow.", [large], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.funding.004", "funding", "In-district donors gave 15000 dollars to Avery Quinn of Cedar Hollow.", [district_money], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.funding.005", "funding", "Loans and self-funding for Avery Quinn of Cedar Hollow were 0 dollars.", [loans], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.funding.006", "funding", "PAC committees gave 8000 dollars to Avery Quinn of Cedar Hollow.", [pac], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.funding.007", "funding", "Party committee money for Avery Quinn of Cedar Hollow was 0 dollars.", [party_money], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.outside.001", "outside spending", "Independent expenditures for and against Avery Quinn of Cedar Hollow were 0 dollars.", [outside], about_person=True, as_of="2026-09-30"),
        claim("cand-quinn.attendance.001", "attendance", "Avery Quinn of Cedar Hollow attended 11 of 12 council meetings in 2025, and the median was 10 of 12.", [meetings], about_person=True),
        claim("cand-quinn.disclosure.001", "financial disclosure", "The local disclosure for Avery Quinn of Cedar Hollow lists a parks-bond holding, and Avery Quinn of Cedar Hollow voted on the parks budget.", [disclosure], about_person=True),
        claim("cand-quinn.promises.001", "promises versus record", "The first platform item for Avery Quinn of Cedar Hollow matches the 2024 parks vote, so the status is kept.", [promise, parks_vote], promise_status="kept", about_person=True),
        claim("cand-quinn.survey.001", "questionnaire answers", "Vote411 shows did not respond for Avery Quinn of Cedar Hollow.", [vote411], about_person=True),
        claim("cand-quinn.survey.002", "questionnaire answers", "Ballotpedia shows did not respond for Avery Quinn of Cedar Hollow.", [ballotpedia], about_person=True),
        claim("cand-quinn.survey.003", "questionnaire answers", "VoteSmart shows did not respond for Avery Quinn of Cedar Hollow.", [votesmart], about_person=True),
        claim("cand-quinn.term.001", "term limits", "Avery Quinn of Cedar Hollow is eligible through 2030.", [term], about_person=True),
        claim("cand-quinn.facts.001", "fact checks", "Never checked is not the same as checked out clean for Avery Quinn of Cedar Hollow.", [fact], about_person=True, drives_summary=False),
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
        archive_url="https://fictional.example/archive/okonkwo-2026-q3",
        local_copy="saved/okonkwo-q3.html",
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
    depth = "saved/okonkwo-depth.html"
    depth_archive = "https://fictional.example/archive/okonkwo-depth"
    ballot_party = source(44, office, "Sample ballot, Cedar Hollow, November 3, 2026", "Official sample ballot", "2026-09-15", "Blake Okonkwo, Mayor, Nonpartisan.", "https://fictional.example/oak-county/2026/sample-ballot", "Mayor contest, party column")
    registration = source(45, office, "Voter registration extract, Blake Okonkwo", "Voter registration", "2026-09-01", "Blake Okonkwo, Democratic.", "https://fictional.example/oak-county/registration/okonkwo", "Party field")
    small = source(53, "Westland campaign finance office (fictional)", "Okonkwo itemized receipts, small donors", "Campaign filing", "2026-10-15", "Small donors at or under 200 dollars gave 9000 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3-items", "Small-donor total", archive_url=depth_archive, local_copy=depth)
    large = source(54, "Westland campaign finance office (fictional)", "Okonkwo itemized receipts, large donors", "Campaign filing", "2026-10-15", "Large donors gave 14000 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3-items", "Large-donor total", archive_url=depth_archive, local_copy=depth)
    district_money = source(55, "Westland campaign finance office (fictional)", "Okonkwo itemized receipts, in-district", "Campaign filing", "2026-10-15", "In-district donors gave 7000 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3-items", "In-district total", archive_url=depth_archive, local_copy=depth)
    loans = source(56, "Westland campaign finance office (fictional)", "Okonkwo loans and self-funding", "Campaign filing", "2026-10-15", "Loans and self-funding were 0 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3", "Loan line", archive_url=depth_archive, local_copy=depth)
    pac = source(57, "Westland campaign finance office (fictional)", "Okonkwo PAC receipts", "Campaign filing", "2026-10-15", "PAC committees gave 2000 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3-items", "PAC total", archive_url=depth_archive, local_copy=depth)
    party_money = source(58, "Westland campaign finance office (fictional)", "Okonkwo party committee receipts", "Campaign filing", "2026-10-15", "Party committee money was 0 dollars.", "https://fictional.example/westland-finance/okonkwo-2026-q3-items", "Party total", archive_url=depth_archive, local_copy=depth)
    outside = source(59, "Westland campaign finance office (fictional)", "Independent expenditure index, mayor", "Independent expenditure filing", "2026-10-15", "Independent expenditures for Blake Okonkwo were 0 dollars and independent expenditures against Blake Okonkwo were 0 dollars.", "https://fictional.example/westland-finance/ie-mayor-2026", "Okonkwo row", archive_url=depth_archive, local_copy=depth)
    promise = source(63, "Okonkwo for Cedar committee (fictional)", "Campaign site, first platform item", "Campaign site", "2026-09-01", "The first platform item says a repair list comes before a levy change.", "https://okonkwo-for-cedar.example/platform", "First item")
    vote411 = source(67, "Vote411 (fictional extract)", "Vote411 mayor page", "Questionnaire", "2026-10-01", "Vote411 shows no reply from Blake Okonkwo.", "https://fictional.example/vote411/cedar-mayor", "Okonkwo row", tier="T2")
    ballotpedia = source(68, "Ballotpedia (fictional extract)", "Ballotpedia candidate survey", "Questionnaire", "2026-10-01", "No survey answers from Blake Okonkwo.", "https://fictional.example/ballotpedia/okonkwo", "Survey block", tier="T2")
    votesmart = source(69, "VoteSmart (fictional extract)", "VoteSmart candidate page", "Questionnaire", "2026-10-01", "No VoteSmart submission from Blake Okonkwo.", "https://fictional.example/votesmart/okonkwo", "Submission line", tier="T2")
    term = source(71, "Cedar Hollow Clerk (fictional)", "City charter, mayor term limit", "Charter", "2026-01-01", "Blake Okonkwo is eligible through 2034.", "https://fictional.example/cedar-hollow/charter/mayor", "Challenger paragraph")
    fact = source(73, "FactCheck.org (fictional extract)", "Search method note", "Fact-check method", "2026-10-01", "Never checked is not the same as checked out clean.", "https://fictional.example/factcheck/method", "Absence note", tier="T2")
    disputed = claim(
        "cand-okonkwo.funding.002",
        "funding",
        "A Quinn campaign mailer said Blake Okonkwo of Cedar Hollow has donors who are mostly real-estate developers.",
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
        claim("cand-okonkwo.record.001", "record", "A 2025 Cedar Hollow parks report names Blake Okonkwo as the lead on the river path repair.", [project], about_person=True),
        claim(
            "cand-okonkwo.funding.001",
            "funding",
            "Blake Okonkwo's Cedar Hollow committee reported 30100 dollars in receipts and 11700 dollars in cash on hand for the quarter that ended September 30, 2026.",
            [filing],
            as_of="2026-09-30",
            filing_period="2026-07-01 through 2026-09-30",
            about_person=True,
        ),
        disputed,
        claim("cand-okonkwo.positions.001", "positions", "Blake Okonkwo of Cedar Hollow wrote that any levy change should follow a published repair list.", [questions], about_person=True),
        claim("cand-okonkwo.debates.001", "debates", "At a September 20, 2026 forum in Cedar Hollow, Blake Okonkwo described managing the river path repair.", [debate], about_person=True),
        claim(
            "cand-okonkwo.endorsements.001",
            "endorsements",
            "Friends of the River Path says it endorses Blake Okonkwo of Cedar Hollow.",
            [endorse],
            confidence="single-source",
            drives_summary=False,
            attribution_only=True,
            about_person=True,
            endorsement={"endorser": "Friends of the River Path", "endorser_type": "advocacy", "date": "2026-09-05", "source_role": "endorser_statement"},
        ),
        claim("cand-okonkwo.party.001", "party", "The sample ballot places Blake Okonkwo of Cedar Hollow in a Nonpartisan race.", [ballot_party], about_person=True),
        claim("cand-okonkwo.party.002", "party", "Voter registration lists Blake Okonkwo of Cedar Hollow as Democratic, a registered party on a nonpartisan race.", [registration], about_person=True),
        claim("cand-okonkwo.funding.003", "funding", "Small donors at or under 200 dollars gave 9000 dollars to Blake Okonkwo of Cedar Hollow.", [small], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.funding.004", "funding", "Large donors gave 14000 dollars to Blake Okonkwo of Cedar Hollow.", [large], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.funding.005", "funding", "In-district donors gave 7000 dollars to Blake Okonkwo of Cedar Hollow.", [district_money], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.funding.006", "funding", "Loans and self-funding for Blake Okonkwo of Cedar Hollow were 0 dollars.", [loans], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.funding.007", "funding", "PAC committees gave 2000 dollars to Blake Okonkwo of Cedar Hollow.", [pac], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.funding.008", "funding", "Party committee money for Blake Okonkwo of Cedar Hollow was 0 dollars.", [party_money], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.outside.001", "outside spending", "Independent expenditures for and against Blake Okonkwo of Cedar Hollow were 0 dollars.", [outside], about_person=True, as_of="2026-09-30"),
        claim("cand-okonkwo.promises.001", "promises versus record", "The first platform item for Blake Okonkwo of Cedar Hollow has no earlier vote, so the status is no record.", [promise], promise_status="no_record", about_person=True),
        claim("cand-okonkwo.survey.001", "questionnaire answers", "Vote411 shows did not respond for Blake Okonkwo of Cedar Hollow.", [vote411], about_person=True),
        claim("cand-okonkwo.survey.002", "questionnaire answers", "Ballotpedia shows did not respond for Blake Okonkwo of Cedar Hollow.", [ballotpedia], about_person=True),
        claim("cand-okonkwo.survey.003", "questionnaire answers", "VoteSmart shows did not respond for Blake Okonkwo of Cedar Hollow.", [votesmart], about_person=True),
        claim("cand-okonkwo.term.001", "term limits", "Blake Okonkwo of Cedar Hollow is eligible through 2034.", [term], about_person=True),
        claim("cand-okonkwo.facts.001", "fact checks", "Never checked is not the same as checked out clean for Blake Okonkwo of Cedar Hollow.", [fact], about_person=True, drives_summary=False),
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
        claim("race-mayor.contest.002", "contest", "Avery Quinn of Cedar Hollow is marked incumbent on the sample ballot.", [quinn], about_person=True, identity_attributes=["ballot_name", "office"]),
        claim("race-mayor.contest.003", "contest", "Blake Okonkwo, appointed in 2016, is a city parks planner.", [planner], about_person=True, identity_attributes=["ballot_name", "occupation"]),
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
    fiscal_press = source(
        31,
        "Westland Civic Ledger (fictional)",
        "Parks levy estimate, Measure H",
        "News report",
        "2026-08-03",
        "The note estimates 1.2 million dollars a year for parks if the levy passes.",
        "https://fictional.example/westland-ledger/measure-h-estimate",
        "Estimate paragraph",
        tier="T2",
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
        archive_url="https://fictional.example/archive/levy-threshold",
        local_copy="saved/levy-threshold.html",
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
        archive_url="https://fictional.example/archive/yes-on-h-q3",
        local_copy="saved/yes-on-h-q3.html",
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
        archive_url="https://fictional.example/archive/no-on-h-q3",
        local_copy="saved/no-on-h-q3.html",
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
    sponsor = source(36, "Cedar Hollow Council (fictional)", "Resolution 2026-14, referring Measure H", "Council resolution", "2026-07-09", "Yes on H is the sponsor committee for Measure H.", "https://fictional.example/cedar-hollow/resolutions/2026-14", "Sponsor clause")
    top_funder = source(37, "Westland campaign finance office (fictional)", "Yes on H itemized receipts", "Campaign filing", "2026-10-12", "The largest Yes on H receipt is 8000 dollars from the Cedar Hollow Parks Foundation.", "https://fictional.example/westland-finance/yes-on-h-q3-items", "Largest receipt", archive_url="https://fictional.example/archive/yes-on-h-items", local_copy="saved/measure-funders.html")
    claims = [
        claim("measure-h.title.001", "title", "The official label is Measure H, Parks levy.", [title]),
        claim("measure-h.qualification.001", "qualification", "The city council referred Measure H to the ballot.", [qualify]),
        claim("measure-h.law.001", "law", "The current parks levy, adopted in 2020, expires after the 2026 tax year.", [law]),
        claim("measure-h.yes.001", "yes", "A yes vote replaces the expiring levy at the same rate.", [yes]),
        claim("measure-h.no.001", "no", "A no vote lets the current levy expire.", [no]),
        claim("measure-h.fiscal.001", "fiscal", "The official note estimates 1.2 million dollars a year for parks if the levy passes.", [fiscal, fiscal_press], as_of="2026-08-01"),
        claim("measure-h.threshold.001", "threshold", "Under the 2019 levy rule, the measure needs more than half the votes cast on it.", [threshold]),
        claim("measure-h.funding.001", "funding", "Yes on H reported 20000 dollars in receipts for the quarter ending September 30, 2026.", [support_money], as_of="2026-09-30", filing_period="2026-07-01 through 2026-09-30"),
        claim("measure-h.funding.002", "funding", "No on H reported 18000 dollars in receipts for the quarter ending September 30, 2026.", [oppose_money], as_of="2026-09-30", filing_period="2026-07-01 through 2026-09-30"),
        claim("measure-h.supporters.001", "supporters", "The parks board and the library board signed the argument for Measure H.", [support_names], ballot_position={"role": "supporter", "organization": "Cedar Hollow Parks Board"}),
        claim("measure-h.opponents.001", "opponents", "A homeowners association and a grocer signed the argument against Measure H.", [oppose_names], ballot_position={"role": "opponent", "organization": "Cedar Hollow homeowners association"}),
        claim("measure-h.sponsor.001", "sponsor", "The council resolution names Yes on H as the sponsor committee for Measure H.", [sponsor], ballot_position={"role": "sponsor_committee", "organization": "Yes on H"}),
        claim("measure-h.funders.001", "funders", "Yes on H reported 8000 dollars from the Cedar Hollow Parks Foundation.", [top_funder], as_of="2026-09-30", ballot_position={"role": "funder_for", "organization": "Cedar Hollow Parks Foundation", "amount": "8000 dollars"}),
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

> **FICTIONAL EXAMPLE:** Avery Quinn is not a real person, and Cedar Hollow and Westland are not real places.

## Identity

Avery Quinn of Cedar Hollow appears on the fictional mayoral ballot[^1]. The ballot lists Avery Quinn of Cedar Hollow as the nonpartisan incumbent[^1]. The filing for Avery Quinn of Cedar Hollow lists the campaign site quinn-for-cedar.example[^1].

## Party

The sample ballot places Avery Quinn of Cedar Hollow in a Nonpartisan race and prints no party beside the name[^41]. Voter registration for Avery Quinn of Cedar Hollow lists no party affiliation, shown here as a registered party (race is nonpartisan)[^42]. A registration file from 2019 shows Avery Quinn of Cedar Hollow left the Republican listing on 2019-03-12[^43].

## Prior offices and public service

Avery Quinn of Cedar Hollow was elected to the city council for a four-year term that began after the 2018 election[^2]. The 2018 certificate says the voters elected Avery Quinn of Cedar Hollow, rather than an appointment[^2].

## Occupational history

Before that council term, Avery Quinn of Cedar Hollow worked as a classroom teacher from 2004 through 2018[^3]. The 2018 staff directory lists Avery Quinn of Cedar Hollow as a teacher and does not list an ownership share in a business[^3].

## Education

The State University of Westland registrar says Avery Quinn of Cedar Hollow received a bachelor of arts degree in 2004[^4]. No later degree was listed for Avery Quinn of Cedar Hollow on the 2004 filing checked for this fictional profile[^4].

## Campaign funding

Avery Quinn of Cedar Hollow filed on October 15, 2026 for the quarter that ended September 30, 2026[^5]. The summary for Avery Quinn of Cedar Hollow shows 48200 dollars in receipts, 31000 dollars spent, 17200 dollars in cash on hand, and no debt[^5]. Cash on hand for Avery Quinn of Cedar Hollow means money the report still showed at the end of that filing period[^5]. Small donors, at or under 200 dollars, gave 12000 dollars to Avery Quinn of Cedar Hollow[^46]. Large donors gave 20000 dollars to Avery Quinn of Cedar Hollow[^47]. In-district donors gave 15000 dollars to Avery Quinn of Cedar Hollow[^48]. Loans and self-funding for Avery Quinn of Cedar Hollow were 0 dollars[^49]. PAC committees gave 8000 dollars to Avery Quinn of Cedar Hollow[^50]. Party committee money for Avery Quinn of Cedar Hollow was 0 dollars[^51].

## Outside spending

Independent expenditures for Avery Quinn of Cedar Hollow were 0 dollars, and independent expenditures against Avery Quinn of Cedar Hollow were 0 dollars[^52]. Not found (searched: fictional committee filings that name Avery Quinn of Cedar Hollow as the person in control).

## Attendance

Avery Quinn of Cedar Hollow attended 11 of 12 council meetings in 2025, and the council median was 10 of 12[^60]. The clerk roll does not give a reason for the meeting Avery Quinn of Cedar Hollow missed[^60].

## Financial disclosure

The local disclosure for Avery Quinn of Cedar Hollow lists a parks-bond holding, and Avery Quinn of Cedar Hollow voted yes on the parks budget[^61]. The guide states that overlap for Avery Quinn of Cedar Hollow and reaches no conclusion[^61]. Not found (searched: fictional Form 6 filings, which this municipal office does not use).

## Term limits

Under the city charter's two-term rule, Avery Quinn of Cedar Hollow is eligible through 2030[^70].

## Record vs rhetoric

On June 4, 2024, Avery Quinn of Cedar Hollow voted yes on the city parks budget[^6]. In the 2026 questionnaire, Avery Quinn of Cedar Hollow wrote that the levy should stay at the amount printed on the ballot[^7]. The 2024 parks vote by Avery Quinn of Cedar Hollow is a budget vote, and the questionnaire sentence is about a later levy question[^6][^7].

## Promises versus record

The first platform item for Avery Quinn of Cedar Hollow says the levy stays at the ballot amount, and the 2024 parks vote matches that item, so the status is kept[^62][^76].

## Positions in own words

The Cedar Hollow League of Voters asked Avery Quinn of Cedar Hollow the same parks question[^7]. Avery Quinn of Cedar Hollow answered, "I will ask the council to keep the levy at the amount printed on the ballot."[^7]

## Questionnaire answers

Vote411 shows did not respond for Avery Quinn of Cedar Hollow, and the campaign site does not link a Vote411 reply[^64]. Ballotpedia's survey page for Avery Quinn of Cedar Hollow is did not respond[^65]. VoteSmart has did not respond for Avery Quinn of Cedar Hollow[^66].

## Debates and forums

Avery Quinn of Cedar Hollow spoke at the September 20, 2026 library forum[^8]. At 00:14:10 Avery Quinn of Cedar Hollow said, "The parks budget I voted for is the one in the 2024 minutes."[^8]

## Endorsements

On September 2, 2026 the Cedar Hollow Firefighters Association, a union, published its own statement endorsing Avery Quinn of Cedar Hollow[^9]. That notice is the union's own statement about Avery Quinn of Cedar Hollow, not a finding about the voting record[^9]. Not found (searched: fictional newspaper endorsement pages, business group pages, and elected official pages).

## Fact checks

No fact-check article names Avery Quinn of Cedar Hollow[^72]. Never checked is not the same as checked out clean, so this profile does not treat that silence as a pass for Avery Quinn of Cedar Hollow[^72].

## Legal issues

Not found (searched: fictional Oak County court index, fictional Westland court index, and the candidate filing on 2026-10-20).

## Ethics and elections orders

Not found (searched: fictional Florida Commission on Ethics final orders and fictional Florida Elections Commission final orders).

## Strongest case

The 2018 council term and the 2024 parks vote for Avery Quinn of Cedar Hollow are in the cited record, along with a filed finance report[^2][^6][^5].

## Interest-group ratings

Not found (searched: fictional paired rating pages from opposite sides).
{FOOTER}
"""


def okonkwo_draft():
    return f"""
# Blake Okonkwo

> **FICTIONAL EXAMPLE:** Blake Okonkwo is not a real person, and Cedar Hollow and Westland are not real places.

## Identity

Blake Okonkwo of Cedar Hollow appears on the fictional mayoral ballot[^10]. The ballot lists Blake Okonkwo of Cedar Hollow as a nonpartisan challenger and does not mark the candidate as the incumbent[^10]. The filing for Blake Okonkwo of Cedar Hollow lists the campaign site okonkwo-for-cedar.example[^10].

## Party

Blake Okonkwo of Cedar Hollow is listed in a Nonpartisan race on the sample ballot, with the party line left blank[^44]. The voter roll lists Blake Okonkwo of Cedar Hollow as Democratic, which this guide labels a registered party (race is nonpartisan)[^45]. Not found (searched: fictional Oak County voter registration index and the 2026 sample ballot).

## Prior offices and public service

Not found (searched: fictional council certificates and the 2026 ballot filing).

## Occupational history

A city personnel notice says the parks director appointed Blake Okonkwo of Cedar Hollow as a parks planner in 2016[^11]. The 2016 notice lists Blake Okonkwo of Cedar Hollow as an employee and does not list ownership of a firm[^11].

## Education

Westland State College says Blake Okonkwo of Cedar Hollow received a master of public administration degree in 2015[^12]. No other degree was listed for Blake Okonkwo of Cedar Hollow on the 2015 filing checked for this fictional profile[^12].

## Campaign funding

Blake Okonkwo of Cedar Hollow filed on October 15, 2026 for the quarter that ended September 30, 2026[^14]. The summary for Blake Okonkwo of Cedar Hollow shows 30100 dollars in receipts, 18400 dollars spent, 11700 dollars in cash on hand, and no debt[^14].

A Quinn campaign mailer said Blake Okonkwo of Cedar Hollow has donors who are mostly real-estate developers[^18]. The itemized filing for Blake Okonkwo of Cedar Hollow instead lists a 2500 dollar receipt from Friends of the River Path as the largest line[^19]. This characterization of Blake Okonkwo of Cedar Hollow is disputed and is not used in the summary[^18][^19]. Small donors at or under 200 dollars accounted for 9000 dollars of what Blake Okonkwo of Cedar Hollow reported[^53]. Large donors gave 14000 dollars to Blake Okonkwo of Cedar Hollow[^54]. Blake Okonkwo of Cedar Hollow took in 7000 dollars from in-district donors[^55]. PAC committees were 2000 dollars on the Blake Okonkwo of Cedar Hollow report[^57]. Party committee money on that report for Blake Okonkwo of Cedar Hollow was 0 dollars[^58]. Loans and self-funding stayed at 0 dollars for Blake Okonkwo of Cedar Hollow[^56].

## Outside spending

The independent expenditure filing for the Cedar Hollow mayor race lists 0 dollars on the for-line and 0 dollars on the against-line for Blake Okonkwo of Cedar Hollow[^59]. Not found (searched: fictional committee filings that name Blake Okonkwo of Cedar Hollow as the person in control).

## Attendance

Not found (searched: fictional council attendance rolls and fictional House vote journals).

## Financial disclosure

Not found (searched: fictional local disclosure filings and fictional Form 6 filings).

## Term limits

Blake Okonkwo of Cedar Hollow has not started a mayoral term, and the charter leaves Blake Okonkwo of Cedar Hollow eligible through 2034[^71].

## Record vs rhetoric

A 2025 parks department report names Blake Okonkwo of Cedar Hollow as the lead on the river path repair[^13]. In the questionnaire, Blake Okonkwo of Cedar Hollow wrote that a levy change should follow a published repair list[^15]. The 2025 report on Blake Okonkwo of Cedar Hollow describes a completed project, and the questionnaire talks about a future list[^13][^15].

## Promises versus record

The first platform item for Blake Okonkwo of Cedar Hollow asks for a repair list before any levy change, and no earlier council vote was found, so the status is no record[^63].

## Positions in own words

The Cedar Hollow League of Voters asked Blake Okonkwo of Cedar Hollow the same parks question[^15]. Blake Okonkwo of Cedar Hollow answered, "I will publish the parks repair list before I ask for a levy change."[^15]

## Questionnaire answers

On Ballotpedia, Blake Okonkwo of Cedar Hollow did not respond, and that page was opened before the other two surveys[^68]. Vote411 is did not respond for Blake Okonkwo of Cedar Hollow[^67]. VoteSmart is did not respond for Blake Okonkwo of Cedar Hollow[^69].

## Debates and forums

Blake Okonkwo of Cedar Hollow spoke at the September 20, 2026 library forum[^16]. At 00:28:40 Blake Okonkwo of Cedar Hollow said, "I managed the river path repair and I will publish the project list."[^16]

## Endorsements

Friends of the River Path, an advocacy group, wrote on its own site on September 5, 2026 that it endorses Blake Okonkwo of Cedar Hollow for the open mayoral seat[^17]. That sentence is the group's own statement about Blake Okonkwo of Cedar Hollow, not a finding about a voting record[^17]. Not found (searched: fictional union pages, newspaper endorsement pages, and party committee pages).

## Fact checks

FactCheck.org had no item about Blake Okonkwo of Cedar Hollow[^73]. Never checked is not the same as checked out clean, and the empty result is not a rating of Blake Okonkwo of Cedar Hollow[^73].

## Legal issues

Not found (searched: fictional Oak County court index, fictional Westland court index, and the candidate filing on 2026-10-20).

## Ethics and elections orders

Not found (searched: fictional Florida Commission on Ethics final orders and fictional Florida Elections Commission final orders).

## Strongest case

The cited record for Blake Okonkwo of Cedar Hollow shows a 2016 parks planner appointment, the 2025 river path project, and a filed finance report[^11][^13][^14].

## Interest-group ratings

Not found (searched: fictional paired rating pages from opposite sides).
{FOOTER}
"""


def race_draft():
    return """
# Mayor of Cedar Hollow

> **FICTIONAL EXAMPLE:** this race is invented.

<!-- summary -->
Two people are running for mayor of Cedar Hollow[^32]. Avery Quinn of Cedar Hollow is the current mayor[^33]. Blake Okonkwo of Cedar Hollow is a city parks planner appointed in 2016[^34]. Both filed a campaign finance report for the quarter that ended in September 2026[^35].

## Contest

The fictional sample ballot lists the office of mayor of Cedar Hollow[^32]. The term and the seat are the ones printed on that ballot[^32].

## Comparison

| Topic | Avery Quinn | Blake Okonkwo |
| --- | --- | --- |
| Ballot line | Avery Quinn of Cedar Hollow, nonpartisan incumbent[^33] | Blake Okonkwo of Cedar Hollow, nonpartisan challenger[^10] |
| Work cited here | Avery Quinn of Cedar Hollow, teacher, then council and mayor[^3][^2] | Blake Okonkwo of Cedar Hollow, parks planner since 2016[^11] |
| Latest filing | Avery Quinn of Cedar Hollow, quarter ending September 30, 2026[^5] | Blake Okonkwo of Cedar Hollow, quarter ending September 30, 2026[^14] |

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

> **FICTIONAL EXAMPLE:** this measure is invented.

<!-- summary -->
Measure H asks Cedar Hollow voters about a parks levy[^20]. A levy is a tax the ballot asks voters to accept or reject[^20]. A yes vote would replace the expiring levy at the same rate[^23]. A no vote would let that levy expire[^24].

## Official title

The official label is Measure H, a parks levy, and it asks whether Cedar Hollow should replace the expiring parks levy[^20].

## Measure type and qualification

Measure H is a referral[^21]. The Cedar Hollow council sent it to the ballot by Resolution 2026-14 on July 9, 2026[^21].

## Plain-language summary

The measure would replace a parks levy that is set to end, the one adopted in 2020[^22]. It does not add a second levy on top of the 2020 levy that continues[^22][^23].

## Current law and proposed change

The city code says the current parks levy, adopted in 2020, expires after the 2026 tax year[^22]. A yes vote replaces it at the same rate[^23]. A no vote lets it expire[^24].

## What a yes vote does

A yes vote replaces the expiring parks levy at the same rate[^23]. The official fiscal note ties that rate to about 1.2 million dollars a year for parks[^25].

## What a no vote does

A no vote lets the current parks levy expire after the 2026 tax year[^24]. The code section on the 2020 levy's expiration is the same one cited for current law[^22].

## Fiscal impact

The Westland fiscal office note, dated August 1, 2026, estimates 1.2 million dollars a year for parks if the levy passes[^25][^31].

Not found (searched: fictional university budget notes and fictional news budget notes).

## Vote threshold

Westland's 2019 levy rule says the measure passes with more than half the votes cast on it[^26].

## Funding by side

Yes on H reported 20000 dollars in receipts for the quarter that ended September 30, 2026[^27]. No on H reported 18000 dollars in receipts for that same quarter[^28].

## Arguments for

The pamphlet argument for Measure H says the levy keeps the current parks hours and repair work going[^29]. The parks board and the library board signed that argument[^29]. Supporters point to the fiscal note's yearly amount as the scale of the work[^25].

## Arguments against

The pamphlet argument against Measure H says the city should let the levy end and pay for parks from the existing budget[^30]. A homeowners association and a grocer signed that argument[^30]. Opponents also point to the fiscal note so readers can see the yearly amount[^25].

## Official sponsor or committee

The council resolution names Yes on H as the sponsor committee for Measure H[^36].

## Organizations supporting

The parks board and the library board signed the argument for Measure H[^29].

## Organizations opposing

A homeowners association and a grocer signed the argument against Measure H[^30].

## Top funders

Yes on H reported 8000 dollars from the Cedar Hollow Parks Foundation, the largest receipt in that quarter[^37]. Not found (searched: fictional No on H itemized receipts for a largest donor).

## Sources and retrieval dates

Source records for this item live in `claims.yaml`.

## Item changelog

See `CHANGELOG.md`.

## Findings and disputes

See `findings.yaml`.
"""


def legislation_claims():
    bill_page = "https://fictional.example/westland-house/2026/hb18"
    copy = "saved/bill-hb18.html"
    archive = "https://fictional.example/archive/hb18"
    identity = source(80, "Westland House (fictional)", "House Bill 18, bill page", "Bill page", "2026-03-01", "House Bill 18, parks repair reporting.", bill_page, "Title line")
    sponsors = source(81, "Westland House (fictional)", "House Bill 18 sponsors", "Bill page", "2026-03-01", "Morgan Hale (D-4) and Riley Chen (R-9).", bill_page, "Sponsor line")
    drafting = source(82, "Westland House (fictional)", "House Bill 18 staff analysis", "Staff analysis", "2026-03-10", "Legislative counsel drafted the posted text.", bill_page + "/analysis", "Drafting note")
    model = source(83, "Westland Civic Ledger (fictional)", "Parks posting language", "News report", "2026-03-20", "The posting lines resemble a union model bill.", "https://fictional.example/westland-ledger/hb18-model", "Comparison paragraph", tier="T3", confidence="single-source")
    prior = source(84, "Westland House (fictional)", "House Bill 7 of 2024", "Bill page", "2024-02-01", "House Bill 7 of 2024 required a parks inventory.", "https://fictional.example/westland-house/2024/hb7", "Summary line")
    changed = source(85, "Westland House (fictional)", "House Bill 18 staff analysis", "Staff analysis", "2026-03-10", "The 2026 text adds a yearly public posting.", bill_page + "/analysis", "Change note")
    committee = source(86, "Westland House (fictional)", "House Bill 18 history", "Bill history", "2026-03-12", "The Local Government Committee heard the bill on March 12, 2026.", bill_page, "History row")
    amendment = source(87, "Westland House (fictional)", "House Bill 18 amendment", "Amendment", "2026-03-12", "The committee set the posting date as June 1.", bill_page, "Amendment text")
    companion = source(88, "Westland Senate (fictional)", "Senate Bill 22", "Bill page", "2026-03-15", "Senate Bill 22 is the companion bill.", "https://fictional.example/westland-senate/2026/sb22", "Companion line")
    status = source(89, "Westland House (fictional)", "House Bill 18 history", "Bill history", "2026-04-02", "The House passed House Bill 18 on April 2, 2026.", bill_page, "Passage row")
    summary = source(90, "Westland House (fictional)", "House Bill 18 digest", "Staff analysis", "2026-03-10", "The bill would require a city to post its parks repair list each year.", bill_page + "/analysis", "Digest")
    law = source(91, "Westland Code (fictional)", "Parks inventory section", "Statute", "2020-01-01", "City code requires a parks inventory and does not require a public posting.", "https://fictional.example/westland-code/parks", "Section 12")
    affected = source(92, "Westland House (fictional)", "House Bill 18 staff analysis", "Staff analysis", "2026-03-10", "The bill applies to cities that run a parks department.", bill_page + "/analysis", "Effect paragraph")
    fiscal = source(93, "Westland fiscal office (fictional)", "House Bill 18 fiscal note", "Official fiscal note", "2026-03-08", "The note estimates 40000 dollars for the posting website.", "https://fictional.example/westland-fiscal/hb18", "Estimate line", archive_url=archive, local_copy=copy)
    staff = source(94, "Westland House (fictional)", "House Bill 18 staff analysis", "Staff analysis", "2026-03-10", "Staff analysis says the bill adds a public posting and does not change the tax rate.", bill_page + "/analysis", "Present situation")
    roll = source(95, "Westland House (fictional)", "House Bill 18 roll call", "Roll call", "2026-04-02", "The House vote was 28 yes and 12 no.", bill_page + "/votes", "Vote totals")
    parties = source(96, "Westland House (fictional)", "House Bill 18 roll call by party", "Roll call", "2026-04-02", "Democrats 18 yes and 2 no. Republicans 10 yes and 10 no.", bill_page + "/votes", "Party lines")
    lobby_for = source(98, "Westland lobbyist index (fictional)", "Lobbyist registrations, 2026", "Lobbyist registration", "2026-03-01", "The Parks Workers Guild registered to lobby for House Bill 18.", "https://fictional.example/westland-lobby/2026", "Guild row")
    lobby_against = source(99, "Westland lobbyist index (fictional)", "Lobbyist registrations, 2026", "Lobbyist registration", "2026-03-01", "The City Managers Association registered to lobby against House Bill 18.", "https://fictional.example/westland-lobby/2026", "Managers row")
    testimony = source(100, "Westland House (fictional)", "Local Government Committee hearing", "Hearing record", "2026-03-12", "A guild witness said the posting would show delayed repairs.", bill_page + "/hearing", "Witness line")
    gift = source(101, "Westland campaign finance office (fictional)", "Hale contributions, 2024", "Campaign filing", "2024-06-01", "The Parks Workers Guild gave 500 dollars on June 1, 2024.", "https://fictional.example/westland-finance/hale-2024", "Guild receipt", archive_url=archive, local_copy=copy)
    pro = source(102, "Parks Workers Guild (fictional)", "Hearing statement", "Hearing record", "2026-03-12", "The public list would show which repairs are waiting.", bill_page + "/hearing", "Guild statement", tier="T4", confidence="single-source")
    con = source(103, "City Managers Association (fictional)", "Hearing statement", "Hearing record", "2026-03-12", "The posting repeats the inventory the city already keeps.", bill_page + "/hearing", "Managers statement", tier="T4", confidence="single-source")
    redline = source(104, "Westland House (fictional)", "House Bill 18, section 12", "Bill text", "2026-03-01", "Section 12 would add a yearly public posting effective July 1, 2027.", bill_page + "/text", "Section 12")
    effective = source(105, "Westland House (fictional)", "House Bill 18 effective date", "Bill text", "2026-03-01", "The bill takes effect on July 1, 2027.", bill_page + "/text", "Effective date")
    agency = source(106, "Westland House (fictional)", "House Bill 18 implementing agency", "Bill text", "2026-03-01", "The bill assigns implementation to the Parks Division.", bill_page + "/text", "Agency line")
    member = source(107, "Westland House (fictional)", "House Bill 18 roll call", "Roll call", "2026-04-02", "The member for Westland House district 4 voted yes.", bill_page + "/votes", "District 4")
    ncsl = source(108, "NCSL (fictional extract)", "Parks posting laws", "50-state table", "2026-05-01", "Easton passed a parks-posting law in 2024.", "https://fictional.example/ncsl/parks-posting", "Easton row", tier="T2")
    oppaga = source(109, "OPPAGA (fictional extract)", "Easton posting site note", "Government evaluation", "2026-06-01", "Easton clerks used the posting site in its first year.", "https://fictional.example/oppaga/easton-posting", "Use finding", tier="T2")
    claims = [
        claim("bill-hb18.identity.001", "identity", "House Bill 18 is titled parks repair reporting.", [identity]),
        claim("bill-hb18.sponsors.001", "sponsors", "Morgan Hale, a Democrat from House district 4, is the primary sponsor, and Riley Chen, a Republican from House district 9, is the cosponsor.", [sponsors]),
        claim("bill-hb18.drafting.001", "drafting", "Legislative counsel drafted the posted text of House Bill 18.", [drafting]),
        claim("bill-hb18.model.001", "model", "A Westland Ledger article said the posting lines resemble a union model bill.", [model], confidence="single-source", drives_summary=False, attribution_only=True),
        claim("bill-hb18.history.001", "history", "House Bill 7 of 2024 required a parks inventory and did not require a public posting.", [prior]),
        claim("bill-hb18.history.002", "history", "The 2026 text adds a yearly public posting.", [changed]),
        claim("bill-hb18.committee.001", "committee", "The Local Government Committee heard House Bill 18 on March 12, 2026.", [committee]),
        claim("bill-hb18.committee.002", "committee", "The committee adopted an amendment that sets the posting date as June 1.", [amendment]),
        claim("bill-hb18.companion.001", "companion", "Senate Bill 22 is the companion bill.", [companion]),
        claim("bill-hb18.status.001", "status", "The House passed House Bill 18 on April 2, 2026, and the bill is in the Senate.", [status]),
        claim("bill-hb18.summary.001", "summary", "House Bill 18 would require a city to post its parks repair list each year.", [summary]),
        claim("bill-hb18.law.001", "law", "City code requires a parks inventory and does not require a public posting.", [law]),
        claim("bill-hb18.affected.001", "affected", "The staff analysis says the bill applies to cities that run a parks department.", [affected]),
        claim("bill-hb18.fiscal.001", "fiscal", "The fiscal note estimates 40000 dollars for the posting website.", [fiscal], as_of="2026-03-08"),
        claim("bill-hb18.staff.001", "staff", "The House staff analysis says House Bill 18 adds a public posting and does not change the tax rate.", [staff]),
        claim("bill-hb18.roll.001", "roll", "The House vote on April 2, 2026 was 28 yes and 12 no.", [roll]),
        claim("bill-hb18.parties.001", "parties", "Democrats cast 18 yes and 2 no, and Republicans cast 10 yes and 10 no.", [parties]),
        claim("bill-hb18.lobby.001", "lobby", "The Parks Workers Guild registered to lobby for House Bill 18.", [lobby_for]),
        claim("bill-hb18.lobby.002", "lobby", "The City Managers Association registered to lobby against House Bill 18.", [lobby_against]),
        claim("bill-hb18.testimony.001", "testimony", "A guild witness told the committee the posting would show delayed repairs.", [testimony]),
        claim("bill-hb18.gift.001", "contributions", "The Parks Workers Guild gave Morgan Hale 500 dollars in 2024.", [gift]),
        claim("bill-hb18.for.001", "arguments for", "The guild said the public list would show which repairs are waiting.", [pro], confidence="single-source", drives_summary=False, attribution_only=True),
        claim("bill-hb18.against.001", "arguments against", "The managers association said the posting repeats the inventory the city already keeps.", [con], confidence="single-source", drives_summary=False, attribution_only=True),
        claim("bill-hb18.redline.001", "redline", "Section 12 would add a yearly public posting, effective July 1, 2027.", [redline]),
        claim("bill-hb18.effective.001", "effective", "House Bill 18 takes effect on July 1, 2027.", [effective]),
        claim("bill-hb18.agency.001", "agency", "The bill names the Parks Division as the implementing agency.", [agency]),
        claim("bill-hb18.member.001", "members", "The member for Westland House district 4 voted yes on House Bill 18.", [member]),
        claim("bill-hb18.similar.001", "similar", "NCSL lists a parks-posting law Easton passed in 2024.", [ncsl]),
        claim("bill-hb18.similar.002", "similar", "OPPAGA reported that Easton clerks used the posting site in its first year.", [oppaga]),
    ]
    return {"item_id": "bill-hb18", "item_type": "legislation", "claims": claims}


def legislation_draft():
    return """
# House Bill 18, parks repair reporting

> **FICTIONAL EXAMPLE:** this bill is invented.

<!-- summary -->
House Bill 18 would make a city post its parks repair list each year[^90]. The House passed the bill on April 2, 2026[^89].

## Bill identity

House Bill 18 is the parks repair reporting bill on the fictional Westland House page[^80].

## Sponsors and cosponsors

Morgan Hale, a Democrat from House district 4, is the primary sponsor of House Bill 18, and Riley Chen, a Republican from House district 9, is the cosponsor[^81].

## Drafting and model legislation

Legislative counsel drafted the posted text of House Bill 18[^82]. A Westland Ledger article said the posting lines resemble a union model bill[^83]. The article is that paper's comparison, not a finding that the legislature copied a text[^83].

## Legislative history

House Bill 7 of 2024 required a parks inventory and did not require a public posting[^84]. The 2026 text of House Bill 18 adds a yearly public posting that the 2024 bill did not include[^85].

## Committee referrals and amendments

The Local Government Committee heard House Bill 18 on March 12, 2026[^86]. The committee adopted an amendment that sets the posting date as June 1[^87].

## Companion bills

Senate Bill 22 is the companion to House Bill 18[^88].

## Status timeline

The House passed House Bill 18 on April 2, 2026, and the bill is in the Senate[^89].

## Plain summary

House Bill 18 would require a city to post its parks repair list each year[^90].

## Current law and proposed change

The city code, in force since 2020, requires a parks inventory and does not require a public posting[^91]. The bill would add that posting[^90].

## Section-by-section changes

Section 12 of the parks code would add a yearly public posting, and that change is written to take effect on July 1, 2027[^104].

## Effective date

House Bill 18 takes effect on July 1, 2027[^105].

## Implementing agency

The bill names the Parks Division as the implementing agency[^106].

## Who is affected

The staff analysis says House Bill 18 applies to cities that run a parks department[^92].

## Fiscal note

The fiscal note estimates 40000 dollars for the posting website[^93].

## Staff analysis

The House staff analysis says House Bill 18 adds a public posting and does not change the tax rate[^94].

## Roll-call votes

The House vote on April 2, 2026 was 28 yes and 12 no[^95].

## Party vote counts

On that roll call, Democrats cast 18 yes and 2 no, and Republicans cast 10 yes and 10 no[^96]. Those totals are the journal lines for each party[^96].

## Veto and override

Not found (searched: fictional governor veto letters and fictional override journals).

## Your legislators votes

The member for Westland House district 4 voted yes on House Bill 18[^107].

## Similar laws

NCSL lists a parks-posting law that Easton passed in 2024[^108]. OPPAGA reported that Easton clerks used the posting site in its first year[^109].

## Legal and constitutional challenges

Not found (searched: fictional CourtListener dockets, fictional attorney general opinions, and the staff analysis constitutional issues heading).

## Interest groups and lobbying

The Parks Workers Guild registered to lobby for House Bill 18[^98]. The City Managers Association registered to lobby against House Bill 18[^99].

## Hearing testimony

A guild witness told the committee the posting would show delayed repairs[^100].

## Sponsor contributions

The Parks Workers Guild gave Morgan Hale 500 dollars in 2024[^101].

## Arguments for

The Parks Workers Guild told the committee the public list would show which repairs are waiting[^102]. The guild said residents cannot see that queue in the current inventory[^102].

## Arguments against

The City Managers Association told the committee the posting repeats the inventory the city already keeps[^103]. The association said the extra page would not change which repair is done first[^103].

## Related litigation

Not found (searched: fictional Westland appellate index and fictional Oak County civil docket).

## Sources and retrieval dates

Source records for this item live in `claims.yaml`.

## Item changelog

See `CHANGELOG.md`.

## Findings and disputes

See `findings.yaml`.
"""


def _money(marker, receipts, cash, small, large, district, pac, party, outside):
    return {
        "report_date": f"2026-09-30[^{marker}]",
        "receipts": f"{receipts} dollars in receipts[^{marker}]",
        "cash_on_hand": f"{cash} dollars in cash on hand[^{marker}]",
        "self_funding": "0 dollars in loans and self-funding",
        "small_donors": f"{small} dollars from small donors",
        "large_donors": f"{large} dollars from large donors",
        "in_district": f"{district} dollars in-district",
        "pac_money": f"{pac} dollars from PAC committees",
        "party_money": f"{party} dollars in party committee money",
        "outside_spending": f"{outside} dollars in independent expenditures",
    }


def _profile(item_id, party, endorsements, money):
    return {"item_id": item_id, "party": party, "endorsements": endorsements, "money": money}


def materialize_local_copies() -> None:
    """Write new saved HTML pages from claim quotes. Leave existing pages untouched."""
    pages: dict[str, list[str]] = {}
    for claims_path in sorted((DEST / "items").glob("*/claims.yaml")):
        doc = load_yaml(claims_path) or {}
        if not isinstance(doc, dict):
            continue
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            for source in claim.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                rel = str(source.get("local_copy") or "").strip()
                quote = str(source.get("quote") or "").strip()
                if not rel or not quote:
                    continue
                bucket = pages.setdefault(rel, [])
                if quote not in bucket:
                    bucket.append(quote)
    for rel, quotes in pages.items():
        path = DEST / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(f"<p>{html.escape(quote)}</p>" for quote in quotes)
        path.write_text(f"<!DOCTYPE html><html><body>\n{body}\n</body></html>\n", encoding="utf-8")


def main() -> None:
    saved = DEST / "saved"
    backup = ROOT / "examples" / ".cedar-saved-backup"
    if backup.exists():
        shutil.rmtree(backup)
    if saved.exists():
        shutil.copytree(saved, backup)
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    (DEST / "items").mkdir()
    (DEST / "final").mkdir()
    (DEST / "imports").mkdir()
    if backup.exists():
        shutil.copytree(backup, DEST / "saved")
        shutil.rmtree(backup)

    dump_yaml(
        DEST / "intake.yaml",
        {
            "election_id": "fictional-cedar-hollow-2026",
            "requester_label": "household",
            "election_date": "2026-11-03",
            "election_type": "general",
            "jurisdiction_label": "Cedar Hollow, Oak County, Westland",
            "scope": "whole_ballot",
            "contest_ids": ["race-mayor", "measure-h", "bill-hb18"],
            "include_legislation": True,
            "legislation_topics": ["parks repair reporting"],
            "districts": ["Westland House district 4"],
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
            "districts": ["Westland House district 4"],
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
                    "nonpartisan": True,
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
                {
                    "id": "bill-hb18",
                    "item_id": "bill-hb18",
                    "type": "legislation",
                    "title": "House Bill 18, parks repair reporting",
                    "official_source_url": "https://fictional.example/westland-house/2026/hb18",
                    "district": "Westland",
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

> **FICTIONAL EXAMPLE:** these publishers are invented.

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
        effort("cand-quinn", 22, 17, 55),
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
            "occupation": "classroom teacher",
            "campaign_site": "https://quinn-for-cedar.example/",
            "description": "Adult candidate listed on the fictional Cedar Hollow mayoral ballot as the incumbent.",
            "photo_included": False,
        },
        _profile(
            "cand-quinn",
            {
                "race_nonpartisan": True,
                "source_kind": "ballot",
                "ballot_label": "Nonpartisan",
                "registered_party": "No Party Affiliation",
                "registered_source_kind": "voter_registration",
                "display": "Nonpartisan race, No Party Affiliation, registered party (race is nonpartisan)[^41][^42]",
                "changes_display": "From Republican to No Party Affiliation on 2019-03-12[^43]",
                "changes": [
                    {
                        "from_party": "Republican",
                        "to_party": "No Party Affiliation",
                        "date": "2019-03-12",
                        "source_url": "https://fictional.example/oak-county/registration/quinn-2019",
                    }
                ],
            },
            [
                {
                    "endorser": "Cedar Hollow Firefighters Association",
                    "endorser_type": "union",
                    "date": "2026-09-02",
                    "source_role": "endorser_statement",
                    "source_url": "https://fictional.example/ch-firefighters/endorsement-2026",
                }
            ],
            {
                "report_date": "2026-09-30[^5]",
                "receipts": "48200 dollars in receipts[^5]",
                "cash_on_hand": "17200 dollars in cash on hand[^5]",
                "self_funding": "0 dollars in loans and self-funding[^49]",
                "small_donors": "12000 dollars from small donors[^46]",
                "large_donors": "20000 dollars from large donors[^47]",
                "in_district": "15000 dollars in-district[^48]",
                "pac_money": "8000 dollars from PAC committees[^50]",
                "party_money": "0 dollars in party committee money[^51]",
                "outside_spending": "0 dollars in independent expenditures[^52]",
            },
        ),
    )
    write_item(
        "cand-okonkwo",
        okonkwo_claims(),
        okonkwo_draft(),
        loop_state("cand-okonkwo", "capped-disputed", 3, False),
        effort("cand-okonkwo", 22, 18, 57),
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
            "occupation": "parks planner",
            "campaign_site": "https://okonkwo-for-cedar.example/",
            "description": "Adult candidate listed on the fictional Cedar Hollow mayoral ballot as the challenger.",
            "photo_included": False,
        },
        _profile(
            "cand-okonkwo",
            {
                "race_nonpartisan": True,
                "source_kind": "ballot",
                "ballot_label": "Nonpartisan",
                "registered_party": "Democratic",
                "registered_source_kind": "voter_registration",
                "display": "Nonpartisan race, Democratic, registered party (race is nonpartisan)[^44][^45]",
            },
            [
                {
                    "endorser": "Friends of the River Path",
                    "endorser_type": "advocacy",
                    "date": "2026-09-05",
                    "source_role": "endorser_statement",
                    "source_url": "https://fictional.example/river-path/endorsement-2026",
                }
            ],
            {
                "report_date": "2026-09-30[^14]",
                "receipts": "30100 dollars in receipts[^14]",
                "cash_on_hand": "11700 dollars in cash on hand[^14]",
                "self_funding": "0 dollars in loans and self-funding[^56]",
                "small_donors": "9000 dollars from small donors[^53]",
                "large_donors": "14000 dollars from large donors[^54]",
                "in_district": "7000 dollars in-district[^55]",
                "pac_money": "2000 dollars from PAC committees[^57]",
                "party_money": "0 dollars in party committee money[^58]",
                "outside_spending": "0 dollars in independent expenditures[^59]",
            },
        ),
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
    write_item(
        "bill-hb18",
        legislation_claims(),
        legislation_draft(),
        loop_state("bill-hb18", "signed-off", 1, True),
        {"item_id": "bill-hb18", "searches": 8, "fetches": 6, "minutes": 40, "sections": {}, "explanation": ""},
        [],
        empty_findings_changelog,
    )
    materialize_local_copies()
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
