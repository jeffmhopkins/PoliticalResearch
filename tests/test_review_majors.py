"""Adversarial cases for the party, endorsement, measure, legislation, and depth gates.

A sentence that merely contains "not found" is not a gap. A finance filler is not
a number. A party label is not an official citation. An HB import is not the SB
of the same number.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.guide_layout import (
    _ATTENDANCE_RE,
    _COMPARISON_GROUPS,
    _PARTY_CHANGE_RE,
    _assign_cells,
    _short_fact,
)
from lib.legislation import collect_legislation
from lib.quality import (
    FINANCE_KEYS,
    depth_record_errors,
    endorsement_record_errors,
    iso_date_appears,
    legislation_depth_errors,
    measure_side_errors,
    party_record_errors,
    rendered_party_errors,
)
from lib.util import dump_yaml, repo_root
from portals.fl_campaign_finance import parse_contributions
from portals.fl_house import search_url
from portals.fl_lobbyists import parse_lobbyist_page
from portals.fl_senate import bill_url

ROOT = repo_root()
EXAMPLE = ROOT / "examples" / "sample-election"
GAP = "Not found (searched: the official file)."


def _source(**overrides) -> dict:
    data = {
        "url": "https://fictional.example/ballot",
        "publisher": "Oak County Elections",
        "title": "Sample ballot",
        "doc_type": "Official sample ballot",
        "published": "2026-09-15",
        "retrieved": "2026-10-20 09:00 ET",
        "tier": "T1",
        "locator": "party column",
        "quote": "Nonpartisan.",
        "confidence": "verified",
        "marker": 1,
    }
    data.update(overrides)
    return data


def _claim(claim_id: str, section: str, text: str, **overrides) -> dict:
    data = {
        "id": claim_id,
        "section": section,
        "text": text,
        "marker": 1,
        "sources": [_source()],
        "confidence": "verified",
    }
    data.update(overrides)
    return data


def _item(
    root: Path,
    item_id: str,
    item_type: str,
    draft: str,
    claims: list[dict] | None = None,
    profile: dict | None = None,
    *,
    status: str = "research",
) -> None:
    item = root / "items" / item_id
    item.mkdir(parents=True, exist_ok=True)
    (item / "draft.md").write_text(draft, encoding="utf-8")
    dump_yaml(
        item / "claims.yaml",
        {"item_id": item_id, "item_type": item_type, "claims": claims or []},
    )
    if profile is not None:
        dump_yaml(item / "profile.yaml", profile)
    (item / "loop-state.json").write_text(
        json.dumps({"item_id": item_id, "status": status}),
        encoding="utf-8",
    )


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "election"
    root.mkdir()
    dump_yaml(root / "ballot.yaml", {"contests": [], "districts": ["Westland House district 4"]})
    return root


def _party_profile(**overrides) -> dict:
    party = {
        "race_nonpartisan": True,
        "source_kind": "ballot",
        "display": "Nonpartisan race[^1]",
    }
    party.update(overrides)
    return {"item_id": "cand-ada", "party": party}


def _money(**overrides) -> dict:
    values = {key: "1 dollars[^1]" for key in FINANCE_KEYS}
    values["report_date"] = "2026-09-30[^1]"
    values.update(overrides)
    return values


def _candidate_draft(funding: str) -> str:
    return f"""# Ada Hale

## Campaign funding

{funding}

## Outside spending

{GAP}

## Attendance

{GAP}

## Financial disclosure

{GAP}

## Fact checks

Never checked is not the same as checked out clean.

## Ethics and elections orders

Not found (searched: ethics final orders).

## Term limits

{GAP}

## Promises versus record

{GAP}

## Questionnaire answers

Not found (searched: Vote411, Ballotpedia, and VoteSmart).
"""


def _bill_draft(staff: str, similar: str | None = None, model: str | None = None) -> str:
    similar_body = similar if similar is not None else GAP
    model_body = model if model is not None else GAP
    return f"""# House Bill 18

## Section-by-section changes

{GAP}

## Effective date

{GAP}

## Implementing agency

{GAP}

## Party vote counts

{GAP}

## Veto and override

{GAP}

## Your legislators votes

{GAP}

## Similar laws

{similar_body}

## Legal and constitutional challenges

{GAP}

## Staff analysis

{staff}

## Drafting and model legislation

{model_body}

## Sponsors and cosponsors

{GAP}
"""


def test_measure_side_requires_a_real_gap_line_or_a_record(tmp_path: Path):
    root = _workspace(tmp_path)
    slipped = """# Measure H

## Official sponsor or committee

The county clerk was not found to have written a sponsor letter[^1].

## Organizations supporting

The county clerk was not found to have written a support letter[^1].

## Organizations opposing

The county clerk was not found to have written an opposition letter[^1].

## Top funders

The county clerk was not found to have listed a funder[^1].
"""
    _item(root, "measure-h", "measure", slipped, [_claim("measure-h.side.001", "arguments", "A sentence.")])
    errors = measure_side_errors(root)
    for role in ("sponsor_committee", "supporter", "opponent", "funder_for", "funder_against"):
        assert any(role in error for error in errors), errors

    gap = """# Measure H

## Official sponsor or committee

Not found (searched: the county resolution).

## Organizations supporting

Not found (searched: the voter pamphlet).

## Organizations opposing

Not found (searched: the voter pamphlet).

## Top funders

Not found (searched: the itemized receipts).
"""
    _item(root, "measure-h", "measure", gap, [])
    assert measure_side_errors(root) == []

    recorded = """# Measure H

## Official sponsor or committee

Yes on H is the sponsor committee[^1].

## Organizations supporting

The parks board supports the measure[^2].

## Organizations opposing

A grocer opposes the measure[^3].

## Top funders

Yes on H reported 8000 dollars[^4]. Not found (searched: the No on H itemized receipts).
"""
    claims = [
        _claim("measure-h.sponsor.001", "sponsor", "Yes on H is the sponsor committee.", ballot_position={"role": "sponsor_committee", "organization": "Yes on H"}),
        _claim("measure-h.supporters.001", "supporters", "The parks board supports the measure.", marker=2, sources=[_source(marker=2)], ballot_position={"role": "supporter", "organization": "Parks Board"}),
        _claim("measure-h.opponents.001", "opponents", "A grocer opposes the measure.", marker=3, sources=[_source(marker=3)], ballot_position={"role": "opponent", "organization": "Grocer"}),
        _claim("measure-h.funders.001", "funders", "Yes on H reported 8000 dollars.", marker=4, sources=[_source(marker=4)], ballot_position={"role": "funder_for", "organization": "Parks Foundation", "amount": "8000 dollars"}),
    ]
    _item(root, "measure-h", "measure", recorded, claims)
    assert measure_side_errors(root) == []


def test_staff_analysis_requires_a_staff_analysis_source_or_a_gap_line(tmp_path: Path):
    root = _workspace(tmp_path)
    filing = _source(title="Filing", doc_type="Campaign filing", marker=1)
    elsewhere = _source(title="House Bill 18 staff analysis", doc_type="Staff analysis", marker=2)
    slipped = _bill_draft("The fiscal effect was not found to exceed the estimate[^1].")
    _item(
        root,
        "bill-hb18",
        "legislation",
        slipped,
        [
            _claim("bill-hb18.staff.001", "fiscal", "The fiscal effect was not found to exceed the estimate.", sources=[filing]),
            _claim("bill-hb18.other.001", "plain summary", "Another section cites the analysis.", marker=2, sources=[elsewhere]),
        ],
        status="signed-off",
    )
    errors = depth_record_errors(root)
    assert any("staff analysis" in error for error in errors), errors

    _item(
        root,
        "bill-hb18",
        "legislation",
        _bill_draft("Not found (searched: the House staff analysis)."),
        [],
        status="signed-off",
    )
    assert not any("staff analysis source" in error for error in depth_record_errors(root))

    cited = _bill_draft("The House staff analysis says the bill adds a posting[^2].")
    _item(
        root,
        "bill-hb18",
        "legislation",
        cited,
        [_claim("bill-hb18.staff.002", "staff", "The House staff analysis says the bill adds a posting.", marker=2, sources=[elsewhere])],
        status="signed-off",
    )
    assert not any("staff analysis source" in error for error in depth_record_errors(root))


def test_pac_is_a_whole_word_or_a_real_finance_field(tmp_path: Path):
    root = _workspace(tmp_path)
    funding = (
        "Small donors gave 10 dollars[^1]. Large donors gave 20 dollars[^1]. "
        "The in-district share was 5 dollars[^1]. Loans were 0 dollars[^1]. "
        "Party committee money was 0 dollars[^1]. "
        "The space left on the summary page describes the impact[^1]."
    )
    _item(
        root,
        "cand-ada",
        "candidate",
        _candidate_draft(funding),
        [],
        {"item_id": "cand-ada", "money": _money(pac_money="see the filing[^1]", small_donors="see the filing[^1]")},
        status="signed-off",
    )
    errors = depth_record_errors(root)
    assert any("missing PAC money" in error for error in errors), errors
    assert any("money.pac_money must be a number" in error for error in errors), errors
    assert any("money.small_donors must be a number" in error for error in errors), errors
    assert not any("money.receipts must be a number" in error for error in errors), errors

    _item(
        root,
        "cand-ada",
        "candidate",
        _candidate_draft(funding + " PAC committees gave 8 dollars[^1]."),
        [],
        {"item_id": "cand-ada", "money": _money(pac_money="see the filing[^1]")},
        status="signed-off",
    )
    word_errors = depth_record_errors(root)
    assert not any("missing PAC money" in error for error in word_errors), word_errors
    assert any("money.pac_money must be a number" in error for error in word_errors), word_errors

    _item(
        root,
        "cand-ada",
        "candidate",
        _candidate_draft(funding),
        [],
        {"item_id": "cand-ada", "money": _money(pac_money="8 dollars[^1]")},
        status="signed-off",
    )
    field_errors = depth_record_errors(root)
    assert not any("PAC" in error or "pac_money" in error for error in field_errors), field_errors


def test_party_section_needs_an_official_citation_not_a_label(tmp_path: Path):
    root = _workspace(tmp_path)
    newspaper = _source(
        publisher="Cedar Hollow Gazette",
        title="Candidate listings",
        doc_type="News article",
        tier="T3",
        quote="Ada Hale, Republican.",
    )
    draft = """# Ada Hale

## Party

A newspaper lists Ada Hale as Republican in a Nonpartisan race, a registered party (race is nonpartisan)[^1].
"""
    profile = _party_profile(
        display="Nonpartisan race, Republican, registered party (race is nonpartisan)[^1]",
        registered_party="Republican",
        registered_source_kind="voter_registration",
    )
    _item(
        root,
        "cand-ada",
        "candidate",
        draft,
        [_claim("cand-ada.identity.001", "identity", "A newspaper lists Ada Hale as Republican.", sources=[newspaper])],
        profile,
    )
    errors = party_record_errors(root)
    assert any("T3 or newspaper" in error for error in errors), errors
    assert any("official T1 citation" in error for error in errors), errors

    official = """# Ada Hale

## Party

The sample ballot places Ada Hale in a Nonpartisan race[^1]. Not found (searched: the voter registration index).
"""
    _item(
        root,
        "cand-ada",
        "candidate",
        official,
        [_claim("cand-ada.identity.001", "identity", "The sample ballot places Ada Hale in a Nonpartisan race.")],
        _party_profile(),
    )
    assert party_record_errors(root) == []

    changed = """# Ada Hale

## Party

The 2019 filing is the party history for Ada Hale in a Nonpartisan race[^1].
"""
    _item(
        root,
        "cand-ada",
        "candidate",
        changed,
        [_claim("cand-ada.identity.001", "identity", "The 2019 filing is the party history.")],
        _party_profile(
            changes=[{"from_party": "Republican", "to_party": "Green", "date": "2019-03-12"}],
        ),
    )
    dated = party_record_errors(root)
    assert any("2019-03-12" in error for error in dated), dated
    assert not iso_date_appears("2019-03-12", "The 2019 filing")
    assert iso_date_appears("2019-03-12", "on 2019-03-12")
    assert iso_date_appears("2019-03-12", "March 12, 2019")


def test_endorsement_date_must_be_the_full_day(tmp_path: Path):
    root = _workspace(tmp_path)
    claim = _claim(
        "cand-ada.endorsements.001",
        "endorsements",
        "River Fund endorsed Ada Hale.",
        endorsement={
            "endorser": "River Fund",
            "endorser_type": "advocacy",
            "date": "2026-09-02",
            "source_role": "endorser_statement",
        },
    )
    _item(root, "cand-ada", "candidate", "# Ada Hale\n\n## Endorsements\n\nIn 2026 the group spoke[^1].\n", [claim])
    errors = endorsement_record_errors(root)
    assert any("2026-09-02" in error for error in errors), errors

    _item(
        root,
        "cand-ada",
        "candidate",
        "# Ada Hale\n\n## Endorsements\n\nOn September 2, 2026 River Fund endorsed Ada Hale[^1].\n",
        [claim],
    )
    assert endorsement_record_errors(root) == []


def test_model_bill_needs_a_citation_when_sponsors_are_a_gap(tmp_path: Path):
    root = _workspace(tmp_path)
    _item(
        root,
        "bill-hb18",
        "legislation",
        _bill_draft(GAP, model="This bill copies an ALEC model bill."),
    )
    errors = legislation_depth_errors(root)
    assert any("model-legislation" in error for error in errors), errors

    _item(
        root,
        "bill-hb18",
        "legislation",
        _bill_draft(GAP, model="This bill copies an ALEC model bill[^1]."),
        [_claim("bill-hb18.model.001", "drafting", "This bill copies an ALEC model bill.")],
    )
    assert legislation_depth_errors(root) == []


def test_similar_laws_need_two_distinct_citations(tmp_path: Path):
    root = _workspace(tmp_path)
    repeated = "NCSL and OPPAGA describe the same posting law[^1][^1]."
    _item(root, "bill-hb18", "legislation", _bill_draft(GAP, similar=repeated), status="signed-off")
    errors = depth_record_errors(root)
    assert any("two independent sources" in error for error in errors), errors

    distinct = "NCSL lists the posting law[^1]. OPPAGA reported the same outcome[^2]."
    _item(root, "bill-hb18", "legislation", _bill_draft(GAP, similar=distinct), status="signed-off")
    assert not any("two independent sources" in error for error in depth_record_errors(root))


def test_rendered_party_rejects_red_and_blue_coding(tmp_path: Path):
    root = _workspace(tmp_path)
    final = root / "final"
    final.mkdir()
    snippets = [
        "party-democrat",
        "party-republican",
        "party-dem",
        "party-rep",
        "party-blue",
        "party-red",
        "party-d",
        "color: #ff0000",
        "color: #0000ff",
        "color:#0000ee",
        "color:#f00",
        "color:#00f",
        "color: red",
        "color: blue",
        "color: darkblue",
        "rgb(255, 0, 0)",
        "rgb(0, 0, 255)",
        "#ff0000",
    ]
    for snippet in snippets:
        (final / "guide.md").write_text(f"A class {snippet} sits on the name.\n", encoding="utf-8")
        errors = rendered_party_errors(root)
        assert any("colored" in error for error in errors), snippet
    (final / "guide.md").write_text(
        "| Party | Ada |\n| --- | --- |\n| Endorsements | None |\n\nThe bill discusses redistricting and a blue pamphlet.\n",
        encoding="utf-8",
    )
    dump_yaml(root / "ballot.yaml", {"contests": [{"type": "race", "title": "Mayor", "candidates": []}]})
    assert rendered_party_errors(root) == []


def test_attendance_cell_keeps_the_count_and_the_median():
    body = (
        "Avery Quinn of Cedar Hollow attended 11 of 12 council meetings in 2025, "
        "and the council median was 10 of 12[^60]. "
        "The clerk roll does not give a reason for the meeting Avery Quinn of Cedar Hollow missed[^60]."
    )
    rows = [row for _heading, group in _COMPARISON_GROUPS for row in group]
    assigned = _assign_cells({"attendance": ("Attendance", body)}, {}, rows)
    assert "11 of 12" in assigned["Attendance"]
    assert "median" in assigned["Attendance"].lower()
    assert "10 of 12" in assigned["Attendance"]
    assert "missed" not in assigned["Attendance"].lower()
    short = _short_fact(assigned["Attendance"], "Attendance")
    assert "11 of 12" in short and "10 of 12" in short and "median" in short.lower()
    assert _ATTENDANCE_RE.search("The meeting was missed") is None


def test_party_change_row_matches_any_party():
    assert _PARTY_CHANGE_RE.search("The filing records a change from Green")
    assert _PARTY_CHANGE_RE.search("The filing records a change from Libertarian")
    assert _PARTY_CHANGE_RE.search("The filing records a change from NPA")
    assert _PARTY_CHANGE_RE.search("The label comes from the ballot") is None
    rows = [row for _heading, group in _COMPARISON_GROUPS for row in group]
    for party in ("Green", "Libertarian", "NPA"):
        sentence = f"The filing records a change from {party} on 2015-01-01[^1]."
        assigned = _assign_cells({"party": ("Party", sentence)}, {}, rows)
        assert party in assigned["Party changes"], assigned["Party changes"]


def test_contribution_parser_keeps_the_gift_and_drops_the_street():
    page = """
    <table>
      <tr><th>Date</th><th>Candidate</th><th>Contributor</th><th>Amount</th></tr>
      <tr><td>2026-03-01</td><td>Bo Chen</td><td>Ada 12 Oak Street</td><td>500</td></tr>
    </table>
    """
    record = parse_contributions(page, "https://finance.test/contributions")
    row = record["contributions"][0]
    assert row["contributor"] == "Ada"
    assert "Oak" not in row["contributor"]
    assert "12" not in row["contributor"]
    assert row["candidate"] == "Bo Chen"
    assert row["date"] == "2026-03-01"
    assert row["amount"] == "500"


def test_lobbyist_parser_keeps_bill_and_position_for_that_bill_only():
    page = """
    <table>
      <tr><th>Lobbyist</th><th>Principal</th><th>Bill</th><th>Position</th></tr>
      <tr><td>Ada Cole</td><td>Parks Fund</td><td>HB 18</td><td>Support</td></tr>
      <tr><td>Bo Nguyen</td><td>Other Fund</td><td>SB 99</td><td>Oppose</td></tr>
    </table>
    """
    parsed = parse_lobbyist_page(page, "https://senate.test/lobbyists")
    assert parsed["lobbyists"][0]["bill"] == "HB 18"
    assert parsed["lobbyists"][0]["position"] == "Support"
    assert parsed["lobbyists"][1]["position"] == "Oppose"


def test_florida_import_keeps_the_chamber_prefix_and_the_matching_bill():
    assert "HB" in bill_url("2026", "HB 18")
    assert bill_url("2026", "HB 18").rstrip("/").endswith("HB18")
    assert bill_url("2026", "SB 18").rstrip("/").endswith("SB18")
    assert "BillType=HB" in search_url("2026", "HB 18")
    senate_request = search_url("2026", "SB 18")
    assert "BillType=SB" in senate_request
    assert "BillType=HB" not in senate_request

    senate_page = "<html><body><p>SB 18: Senate parks reporting bill.</p><p>Senator Ada Hale (D-4)</p></body></html>"
    house_page = "<html><body><p>HB 18: House parks reporting bill.</p><p>Representative Bo Chen (R-9)</p></body></html>"
    lobby_page = """
    <table>
      <tr><th>Lobbyist</th><th>Principal</th><th>Bill</th><th>Position</th></tr>
      <tr><td>Ada Cole</td><td>Parks Fund</td><td>HB 18</td><td>Support</td></tr>
      <tr><td>Bo Nguyen</td><td>Other Fund</td><td>SB 99</td><td>Oppose</td></tr>
    </table>
    """
    bases = {
        "senate": "https://senate.test",
        "house": "https://house.test",
        "lobbyists": "https://senate.test",
        "finance": "https://finance.test",
    }

    class Router:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def fetch_html(self, url, **kwargs):
            self.urls.append(url)
            if "Lobbyist" in url:
                return url, lobby_page
            if "contributions" in url:
                return url, "<html><body><p>Search contributions</p></body></html>"
            if "billsdetail" in url:
                return url, house_page
            return url, senate_page

    house_fetch = Router()
    house_record = collect_legislation("FL", "HB 18", "2026", house_fetch, base_urls=bases)
    assert any("Session/Bill" in url and "HB" in url for url in house_fetch.urls)
    assert any("BillType=HB" in url for url in house_fetch.urls)
    assert house_record["title"].startswith("HB 18")
    assert house_record["sponsors"][0]["name"] == "Bo Chen"
    assert house_record["sponsors"][0]["party"] == "Republican"
    assert "Ada Hale" not in json.dumps(house_record["sponsors"])
    assert house_record["lobbyists"] == [
        {"lobbyist": "Ada Cole", "principal": "Parks Fund", "bill": "HB 18", "position": "Support"}
    ]

    senate_fetch = Router()
    senate_record = collect_legislation("FL", "SB 18", "2026", senate_fetch, base_urls=bases)
    assert any("Session/Bill" in url and "SB" in url for url in senate_fetch.urls)
    assert any("BillType=SB" in url for url in senate_fetch.urls)
    assert not any("BillType=HB" in url for url in senate_fetch.urls)
    assert senate_record["title"].startswith("SB 18")
    assert senate_record["sponsors"][0]["name"] == "Ada Hale"
    assert senate_record["sponsors"][0]["party"] == "Democratic"
    assert "Bo Chen" not in json.dumps(senate_record["sponsors"])
    assert senate_record["lobbyists"] == []


def test_sample_election_passes_the_record_gates():
    assert party_record_errors(EXAMPLE) == []
    assert endorsement_record_errors(EXAMPLE) == []
    assert measure_side_errors(EXAMPLE) == []
    assert legislation_depth_errors(EXAMPLE) == []
    assert depth_record_errors(EXAMPLE) == []
    assert rendered_party_errors(EXAMPLE) == []
