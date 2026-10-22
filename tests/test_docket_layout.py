"""The default guide uses the approved Docket pages for every contest type."""

from __future__ import annotations

from pathlib import Path

from check_pdf_layout import errors_from_bbox
from lib.docket_pages import coverage_months
from lib.guide_layout import _GuideModel, comparison_tables
from lib.quality import docket_layout_errors
from lib.util import dump_yaml


def _item(root: Path, item_id: str, body: str) -> None:
    folder = root / "items" / item_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "draft.md").write_text(body, encoding="utf-8")
    dump_yaml(folder / "profile.yaml", {"item_id": item_id, "party": {"race_nonpartisan": False}})


def test_coverage_months_uses_the_stated_range_or_a_quarter():
    assert coverage_months("coverage from January 1, 2025 through September 30, 2026") == "21"
    assert coverage_months("coverage from July 1, 2025 through September 30, 2026") == "15"
    assert coverage_months("from February 24, 2025, through October 9, 2026") == "21"
    assert coverage_months("from June 2, 2025, through October 9, 2026") == "17"
    assert coverage_months("filed for the quarter that ended September 30, 2026") == "3"
    assert coverage_months("as of September 30, 2026") is None
    assert coverage_months("a first period of 11/13/2025 through 12/31/2025") is None


def test_three_candidates_split_money_tables_and_an_uncontested_race_stays_brief():
    names = ["Ada", "Bo", "Cara", "Dee"]
    tables = comparison_tables(names, [("Raised", ["$1", "$2", "$3", "$4"])])
    assert len(tables) == 2
    assert tables[0][0] == ["Topic", "Ada", "Bo", "Cara"]
    assert tables[1][0] == ["Topic", "Dee"]


def test_reader_pages_cover_a_race_a_measure_and_a_bill(tmp_path: Path):
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "fiction": True,
            "report_version": "v1.0",
            "election": {"name": "Sample", "date": "2026-11-03"},
            "contests": [
                {
                    "id": "race-one",
                    "item_id": "race-one",
                    "type": "race",
                    "title": "Mayor",
                    "candidates": [
                        {"id": "cand-a", "item_id": "cand-a", "name": "Ada One", "party": "REP", "incumbent": True},
                        {"id": "cand-b", "item_id": "cand-b", "name": "Bo Two", "party": "DEM"},
                    ],
                },
                {
                    "id": "measure-one",
                    "item_id": "measure-one",
                    "type": "measure",
                    "title": "Amendment 1, Budget reserve",
                },
                {
                    "id": "bill-one",
                    "item_id": "bill-one",
                    "type": "legislation",
                    "title": "HJR 1, Budget reserve",
                },
            ],
        },
    )
    dump_yaml(tmp_path / "intake.yaml", {})
    _item(
        tmp_path,
        "race-one",
        "# Mayor\n\n<!-- summary -->\nOne candidate is on the ballot[^1].\n\n## Contest\n\nThe office is mayor[^1].\n",
    )
    _item(
        tmp_path,
        "cand-a",
        "# Ada One\n\n## Education\n\nAda One earned a degree in 2001[^2].\n\n## Occupational history\n\nAda One teaches[^2].\n\n"
        "## Prior offices and public service\n\nAda One has been mayor since 2018[^2].\n\n## Record vs rhetoric\n\n"
        "Not found (searched: a recorded vote).\n\n## Campaign funding\n\n"
        "Coverage from January 1, 2025 through September 30, 2026 shows 10 dollars in receipts and 4 dollars spent[^3].\n\n"
        "## Positions in own words\n\nNot found (searched: a public statement).\n\n"
        "## Endorsements\n\nNot found (searched: a dated endorsement).\n\n"
        "## Legal issues\n\nNot found (searched: a court record).\n",
    )
    _item(
        tmp_path,
        "cand-b",
        "# Bo Two\n\n## Education\n\nNot found (searched: a degree).\n\n## Occupational history\n\nBo Two is a nurse[^6].\n\n"
        "## Prior offices and public service\n\nNot found (searched: a prior office).\n\n## Record vs rhetoric\n\n"
        "Not found (searched: a recorded vote).\n\n## Campaign funding\n\n"
        "Coverage from July 1, 2025 through September 30, 2026 shows 8 dollars in receipts[^6].\n\n"
        "## Positions in own words\n\nBo Two wrote about housing costs[^6].\n\n"
        "## Endorsements\n\nNot found (searched: a dated endorsement).\n\n"
        "## Legal issues\n\nNot found (searched: a court record).\n",
    )
    _item(
        tmp_path,
        "measure-one",
        "# Amendment\n\n<!-- summary -->\nThe amendment raises a reserve cap[^4].\n\n"
        "## Official title\n\nThe ballot prints Amendment 1[^4].\n\n"
        "## Plain-language summary\n\nIt raises the reserve cap[^4].\n\n"
        "## What a yes vote does\n\nA yes vote raises the cap[^4].\n\n"
        "## What a no vote does\n\nA no vote leaves the cap[^4].\n\n"
        "## Fiscal impact\n\nThe fiscal note says the cost is indeterminate[^4].\n\n"
        "## Organizations supporting\n\nA party endorsed it[^4].\n\n"
        "## Organizations opposing\n\nA league opposes it[^4].\n",
    )
    _item(
        tmp_path,
        "bill-one",
        "# HJR 1\n\n<!-- summary -->\nThe bill raises a reserve cap[^5].\n\n"
        "## Bill identity\n\nThe official title is Budget reserve[^5].\n\n"
        "## Plain summary\n\nThe bill raises the reserve cap[^5].\n\n"
        "## Arguments for\n\nA sponsor supports the bill[^5].\n\n"
        "## Arguments against\n\nNot found (searched: an opponent).\n\n"
        "## Fiscal note\n\nThe fiscal note says the cost is indeterminate[^5].\n\n"
        "## Legislative history\n\nThe fund was created in 1992[^5].\n\n"
        "## Sponsors and cosponsors\n\nThe sponsor is listed on the analysis[^5].\n\n"
        "## Interest groups and lobbying\n\nNot found (searched: a lobbying disclosure).\n\n"
        "## Roll-call votes\n\nThe 2025 Senate bill history says the House passed the bill by 100 yeas and 1 nay[^5]. "
        "The 2025 Senate bill history says the Senate passed the bill by 29 yeas and 4 nays[^5].\n\n"
        "## Your legislators votes\n\nNot found (searched: a member roll call).\n\n"
        "## Related litigation\n\nNot found (searched: a filed case).\n",
    )
    model = _GuideModel(tmp_path, "2026-10-22")
    body, _sources = model.render("reader")
    assert docket_layout_errors(body) == []
    assert "::: sheet" in body
    assert 'class="contents"' in body
    assert "No public statement found on positions." in body
    assert "Months in this report" in body
    assert "21" in body and "15" in body
    assert "What is this about?" in body
    assert "Exact words on your ballot" in body
    assert "What is the history of this bill?" in body
    assert "Who sponsored it, and who drafted it?" in body
    assert "Who lobbied or testified?" in body
    assert "How did the chambers vote?" in body
    assert "| House | 100" in body
    assert "| Senate | 29" in body
    assert "How did your legislators vote?" in body
    assert "Related litigation" in body
    assert "The two cards are the same size" not in body
    assert "..." not in body
    assert body.count("### Education") == body.count("### Work") == body.count("### Recorded votes")
    assert "### Where do they stand?" in body


def test_a_multi_class_fence_is_not_an_uncited_sentence():
    from lib.quality import prose_marker_errors

    text = "# Race\n\n::: pair count-many\n\nAda said the parks levy is funded[^1].\n\n:::\n"
    errors = prose_marker_errors(text, "guide")
    assert errors == []


def test_every_measure_and_bill_is_checked_in_order():
    measure = """
<!-- docket-measure -->
## Amendment 1
### What is this about?
::: vote-pair
::: vote-box
#### YES
:::
::: vote-box
#### NO
:::
### Who supports it, and who opposes it?
### What would it cost?
::: ballot-words
#### Exact words on your ballot
:::
"""
    bill = """
<!-- docket-bill -->
## House Bill 18
### What is this about?
::: vote-box
#### YES
:::
::: vote-box
#### NO
:::
### Who supports it, and who opposes it?
### What would it cost?
::: ballot-words
#### Exact words on your ballot
:::
### What is the history of this bill?
### Who sponsored it, and who drafted it?
### Who lobbied or testified?
### How did the chambers vote?
### How did your legislators vote?
"""
    assert docket_layout_errors(measure + measure.replace("Amendment 1", "Amendment 2") + bill) == []
    skipped = measure + measure.replace("### What would it cost?\n", "") + bill
    errors = docket_layout_errors(skipped)
    assert any("measure 2 is missing What would it cost?" in error for error in errors), errors
    bare_bill = bill.replace("### How did your legislators vote?\n", "")
    errors = docket_layout_errors(measure + bare_bill)
    assert any("How did your legislators vote?" in error for error in errors), errors


def test_letter_pages_reject_a_non_letter_size():
    letter = (
        '<doc><page width="612" height="792">'
        '<word xMin="72" yMin="72" xMax="140" yMax="82">Raised</word>'
        "</page></doc>"
    )
    assert errors_from_bbox(letter) == []
    wide = (
        '<doc><page width="700" height="900">'
        '<word xMin="72" yMin="72" xMax="140" yMax="82">Raised</word>'
        "</page></doc>"
    )
    assert any("not US Letter" in error for error in errors_from_bbox(wide))
