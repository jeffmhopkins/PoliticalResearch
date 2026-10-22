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
    assert "::: {.sheet" in body
    assert "::: pair count-many" not in body
    assert "::: {.pair}" in body
    assert 'class="contents"' in body
    assert "No public statement found for the other candidates." in body
    assert "housing costs" in body
    assert "Months in this report" in body
    assert "21" in body and "15" in body
    assert "What is this about?" in body
    assert "Exact words on your ballot" in body
    assert "What is the history of this bill?" in body
    assert "Who sponsored it, and who drafted it?" in body
    assert "Who lobbied or testified?" not in body
    assert "How did the chambers vote?" in body
    assert "| House | 100" in body
    assert "| Senate | 29" in body
    assert "How did your legislators vote?" not in body
    assert "Related litigation" in body
    assert "The two cards are the same size" not in body
    assert "..." not in body
    assert "### Background" in body
    assert "degree in 2001" in body
    assert "No public record found for" in body
    assert "### Where do they stand?" in body


def test_contents_page_column_blurbs_and_local_footnotes(tmp_path: Path):
    from lib.docket_pages import _ballot_exact_words, _quote_is_complete
    from lib.quality import prose_marker_errors

    assert _quote_is_complete(
        "Proposing an amendment to the State Constitution to increase the reserve from 10% to 25% of revenue."
    )
    assert not _quote_is_complete("Proposing an amendment to the State Constitution to")
    assert not _quote_is_complete("This amendment takes effect")
    assert not _quote_is_complete("Muñiz of the Supreme Court be retained in office?")
    assert not _quote_is_complete("Of the Fifth District Court of Appeal be retained in office?")
    assert _quote_is_complete(
        "Shall Justice Carlos G. Muñiz of the Supreme Court be retained in office?"
    )
    assert _quote_is_complete(
        "This amendment increases the homestead exemption for non-school taxes to $150,000 in 2027."
    )
    assert _quote_is_complete(
        "To restore the Indian River Lagoon, shall the county renew the half-cent sales tax for ten years?"
    )
    from lib.ballot_text import official_english_question

    raw = """
Justice of the Supreme Court
Juez de la Corte Suprema
Shall Justice Carlos G. Muñiz of the Supreme Court be retained in office?
¿Deberá el juez seguir en su cargo?
Yes / Sí
No. 1 Constitutional Amendment
Article III, Section 19
Budget Stabilization Fund
Proposing an amendment to the State Constitution to increase the reserve.
Fondo de la Estabilización
Yes / Sí
No. 2 Constitutional Amendment
Article VII, Section 3
Exemption of Tangible Personal Property on Agricultural Land from Taxation
Proposing an amendment to the State Constitution to exempt farm equipment from taxation.
Exención Impositiva
Yes / Sí
Increased Homestead Exemption
This amendment increases the homestead exemption to $150,000 in 2027. This amendment takes effect January 1, 2027.
Mayor Exención
Yes / Sí
Renewal of the Save Our Indian River Lagoon Half-Cent Sales Tax
To restore the Indian River Lagoon, shall the county renew the half-cent sales tax for ten years?
Renovación del impuesto
Yes / Sí
"""
    muniz = official_english_question(
        raw,
        ["Muñiz of the Supreme Court be retained in office?"],
        "Justice of the Supreme Court: Shall Justice Carlos G. Muñiz of the Supreme Court be retained in office?",
    )
    assert muniz == "Shall Justice Carlos G. Muñiz of the Supreme Court be retained in office?"
    farm = official_english_question(
        raw,
        ["Proposing an amendment to the State Constitution to"],
        "No. 2 Constitutional Amendment: Exemption of Tangible Personal Property on Agricultural Land from Taxation",
    )
    assert farm.startswith("Proposing an amendment")
    assert "farm equipment" in farm
    assert "increase the reserve" not in farm
    homestead = official_english_question(
        raw,
        ["This amendment takes effect"],
        "Increased Homestead Exemption",
    )
    assert homestead.startswith("This amendment increases")
    assert "takes effect January 1, 2027." in homestead
    lagoon = official_english_question(
        raw,
        ["shall the county renew the half-cent sales tax"],
        "Renewal of the Save Our Indian River Lagoon Half-Cent Sales Tax",
    )
    assert lagoon.startswith("To restore the Indian River Lagoon")
    dump_yaml(tmp_path / "ballot.yaml", {"fiction": True, "contests": []})
    dump_yaml(tmp_path / "intake.yaml", {})
    model = _GuideModel(tmp_path, "2026-10-22")
    linked = model._link_markers(
        "## Mayor {#contest-a .contest-title data-part=\"Races\"}\n\n"
        "Ada won[^10]. Bo also won[^11]<!--fn-end:12-->.\n\n"
        "## Measure {#contest-b .contest-title data-part=\"Measures\"}\n\n"
        "It would raise the cap[^20].\n\n"
        "# Glossary {#glossary .back-matter}\n\n"
        "A later note[^30].\n"
    )
    assert '[<sup>1</sup>](guide-sources.md#source-10)' in linked
    assert 'id="cite-10"' in linked
    assert '[<sup>2–3</sup>](guide-sources.md#source-11)' in linked
    assert '[<sup>1</sup>](guide-sources.md#source-20)' in linked
    assert '[<sup>30</sup>](guide-sources.md#source-30)' in linked
    assert "{.ballot-group}" not in linked
    model.index = {
        9: (
            "measure-one",
            {"id": "q"},
            {
                "locator": "No. 1 ballot summary",
                "quote": "Proposing an amendment to increase the reserve from 10% to 25% of general revenue.",
            },
        )
    }
    exact = _ballot_exact_words(model, {"title": "Amendment 1"}, "measure-one", {}, "official title")
    assert exact.startswith("Proposing an amendment to increase the reserve")
    assert "[^9]." in exact
    assert "not captured" not in exact
    model.index = {
        8: (
            "measure-two",
            {"id": "q"},
            {"locator": "No. 2 ballot summary", "quote": "Proposing an amendment to the State Constitution to"},
        )
    }
    titled = _ballot_exact_words(
        model,
        {"title": "No. 2 Constitutional Amendment: Farm equipment"},
        "measure-two",
        {},
        "official title",
    )
    assert "The full ballot wording was not captured." in titled
    assert "Farm equipment" in titled or "Amendment 2" in titled
    assert prose_marker_errors("# Measure\n\nThe full ballot wording was not captured.\n", "guide") == []


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
    assert docket_layout_errors(measure + bare_bill) == []
    early = (
        "<!-- docket-bill -->\n"
        "### What is the history of this bill?\n"
        "## House Bill 18\n"
        "### What is this about?\n"
        "::: vote-box\n#### YES\n:::\n"
        "::: vote-box\n#### NO\n:::\n"
        "### Who supports it, and who opposes it?\n"
        "### What would it cost?\n"
        "::: ballot-words\n#### Exact words on your ballot\n:::\n"
    )
    errors = docket_layout_errors(measure + early)
    assert any("history starts before" in error for error in errors), errors


def test_a_repeated_quote_is_not_a_second_answer():
    from lib.docket_pages import _issue_already_said

    quote = (
        "The office biography says she is focused on the border and the rule of law[^3]."
    )
    base = quote[:-1] + " (not found: see the search log)."
    assert _issue_already_said(quote, base)
    assert not _issue_already_said(
        "She wrote a different sentence about housing costs[^4].",
        base,
    )


def test_reader_voice_drops_process_sentences():
    from lib.quality import plain_reader_sentence, reader_voice_errors

    assert plain_reader_sentence("The sample ballot lists Ada for mayor[^1].") == "Ada for mayor[^1]."
    assert plain_reader_sentence("Not found (searched: a degree).") == "No public record found."
    kept = plain_reader_sentence("Ada raised 10 dollars, and this figure is a single source[^2].")
    assert kept == "Ada raised 10 dollars[^2]."
    assert plain_reader_sentence(
        "The 2025 House final bill analysis says the bill adds a posting[^3]."
    ) == "The bill adds a posting[^3]."
    assert plain_reader_sentence("The precinct 122 sample ballot prints Ada for mayor[^4].") == "Ada for mayor[^4]."
    assert plain_reader_sentence(
        "The Brevard County precinct 122 sample ballot prints this measure as No. 1 Constitutional Amendment, titled Budget Stabilization Fund[^6]."
    ) == "No. 1 Constitutional Amendment, titled Budget Stabilization Fund[^6]."
    assert (
        plain_reader_sentence("The 2025 House final bill analysis lists the sponsor as McClure[^5].")
        == "The sponsor is McClure[^5]."
    )
    assert plain_reader_sentence(
        "In a single source, the 2025 Senate bill history says officers signed HJR 5019 on June 17, 2025[^7]."
    ) == "Officers signed HJR 5019 on June 17, 2025[^7]."
    assert plain_reader_sentence(
        "The 2025 House analysis says an ad valorem tax is a yearly tax[^8]."
    ) == "An ad valorem tax is a yearly tax[^8]."
    assert plain_reader_sentence(
        "In a single source, the 2025 House final bill analysis says the Revenue Estimating Conference estimated a loss[^9]."
    ) == "The Revenue Estimating Conference estimated a loss[^9]."
    assert plain_reader_sentence(
        "The June 16, 2026 analysis says the joint resolution is not subject to the Governor's veto[^10]."
    ) == "The joint resolution is not subject to the Governor's veto[^10]."
    assert plain_reader_sentence(
        "The Florida house member list does not name Ada, and that list is a single source[^11]."
    ) == "The Florida house member list does not name Ada[^11]."
    assert plain_reader_sentence(
        "The campaign site for Matt Woodside, says that since 2006 he has served as an educator, and that statement is a single source[^12]."
    ) == "The campaign site for Matt Woodside says that since 2006 he has served as an educator[^12]."
    assert plain_reader_sentence(
        "The staff analysis says House Bill 18 applies to cities that run a parks department[^13]."
    ) == "House Bill 18 applies to cities that run a parks department[^13]."
    assert plain_reader_sentence(
        "The House clerk recorded Ada as voting Aye, and the record label is MATCH[^14]."
    ) == "The House clerk recorded Ada as voting Aye[^14]."
    assert plain_reader_sentence(
        "The index lists a letter dated 10/08/26, and the PDF was not opened, so this row is allegation only, and response requested, not found[^15]."
    ) == "The index lists a letter dated 10/08/26[^15]."
    assert plain_reader_sentence(
        "The index lists an audit letter dated 09/28/26, and those PDFs were not opened, so the rows are allegation only, and response requested, not found[^16]."
    ) == "The index lists an audit letter dated 09/28/26[^16]."
    assert any("Says officers" in error for error in reader_voice_errors("Says officers signed the bill.\n"))
    assert any("analysis says" in error for error in reader_voice_errors("The 2025 House analysis says the tax is yearly.\n"))
    assert (
        plain_reader_sentence(
            "Florida business records could not be retrieved automatically; ownership was not verified."
        )
        == "No public record found."
    )
    leaked = "# Race\n\n::: pair count-many\n\nThe sample ballot lists Ada.\n"
    errors = reader_voice_errors(leaked)
    assert any("leaked fence" in error for error in errors)
    assert any("sample ballot lists" in error for error in errors)
    assert reader_voice_errors("# Race\n\n::: {.pair .count-many}\n\nAda is the mayor[^1].\n") == []


def test_a_bill_named_in_the_measure_is_not_a_second_contest(tmp_path: Path):
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "fiction": True,
            "report_version": "v1.0",
            "election": {"name": "Sample", "date": "2026-11-03"},
            "contests": [
                {"id": "measure-one", "item_id": "measure-one", "type": "measure", "title": "Amendment 1: Reserve"},
                {"id": "bill-one", "item_id": "bill-one", "type": "legislation", "title": "HJR 5019, Reserve"},
            ],
        },
    )
    dump_yaml(tmp_path / "intake.yaml", {})
    _item(
        tmp_path,
        "measure-one",
        "# Amendment\n\n<!-- summary -->\nThe amendment raises a reserve[^4].\n\n"
        "## Plain-language summary\n\nHJR 5019 raises the reserve cap[^4].\n\n"
        "## What a yes vote does\n\nA yes vote raises the cap[^4].\n\n"
        "## What a no vote does\n\nA no vote leaves the cap[^4].\n\n"
        "## Official title\n\nAmendment 1[^4].\n",
    )
    _item(
        tmp_path,
        "bill-one",
        "# HJR\n\n## Plain summary\n\nThe bill raises the cap[^5].\n\n"
        "## Legislative history\n\nThe fund was created in 1992[^5].\n\n"
        "## Roll-call votes\n\nThe House passed the bill by 100 yeas and 1 nay[^5].\n\n"
        "## Related litigation\n\nNot found (searched: a filed case).\n",
    )
    body, _sources = _GuideModel(tmp_path, "2026-10-22").render("reader")
    assert "{#contest-bill-one" not in body
    assert "{#contest-measure-one" in body
    assert "What is the history of this bill?" in body
    assert "| House | 100" in body
    assert "Related litigation" in body
    assert "HJR 5019, Reserve" not in body.split("What's on your ballot")[0]


def test_sparse_pages_fail_and_the_cover_is_exempt():
    from check_pdf_layout import sparse_page_errors

    sparse = (
        '<doc><page width="612" height="792">'
        '<word xMin="72" yMin="72" xMax="140" yMax="84">Cover</word>'
        '</page><page width="612" height="792">'
        '<word xMin="72" yMin="72" xMax="140" yMax="84">Only</word>'
        "</page></doc>"
    )
    errors = sparse_page_errors(sparse)
    assert any("page 2" in error for error in errors)
    assert not any("page 1" in error for error in errors)
    wide = 400 * 12
    dense = (
        '<doc><page width="612" height="792">'
        '<word xMin="72" yMin="72" xMax="472" yMax="84">Cover</word>'
        '</page><page width="612" height="792">'
        + "".join(
            f'<word xMin="72" yMin="{80 + index * 14}" xMax="{72 + wide}" yMax="{92 + index * 14}">Line</word>'
            for index in range(30)
        )
        + "</page></doc>"
    )
    assert sparse_page_errors(dense) == []


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
