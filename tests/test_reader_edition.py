"""Reader length, citation addendums, table shape, and the rerun gate fixes."""

from __future__ import annotations

import re
import subprocess
import zlib
from pathlib import Path

import yaml

from check_pdf_layout import errors_from_bbox, html_layout_errors
from lib.guide_layout import (
    CELL_CHAR_CAP,
    NOT_FOUND_CELL,
    _GuideModel,
    _chunks,
    _duplicate_issue_row,
    _emit_table,
    _short_fact,
    comparison_tables,
)
from lib.quality import (
    assembled_guide_errors,
    number_quote_errors,
    official_restatement_sentences,
    organization_list_errors,
    prose_marker_errors,
    quote_verbatim_errors,
    reader_contest_budget_errors,
    semantic_claim_errors,
    structured_symmetry_errors,
    templated_prose_errors,
)
from lib.util import dump_yaml
from lib.workflow import init_workspace, structural_workspace_errors


def _person_doc(text: str = "Avery Quinn of Cedar Hollow is the incumbent.") -> dict:
    return {
        "item_type": "candidate",
        "claims": [
            {
                "id": "cand-a.identity.001",
                "text": text,
                "about_person": True,
                "identity_attributes": ["ballot_name", "city"],
                "confidence": "verified",
                "drives_summary": False,
                "sources": [
                    {
                        "marker": 1,
                        "url": "https://fictional.example/a",
                        "tier": "T1",
                        "archive_failed": True,
                        "archive_failed_reason": "fixture",
                        "retrieved": "2026-10-20 09:00 ET",
                        "quote": "Avery Quinn of Cedar Hollow is the incumbent.",
                        "publisher": "Fixture",
                    }
                ],
            }
        ],
    }


def test_pronoun_continues_the_previous_sentence_and_claim_text_still_needs_anchors():
    record = {"ballot_name": "Avery Quinn", "city": "Cedar Hollow", "office": "Mayor"}
    followed = (
        "# Avery\n\n## Identity\n\n"
        "Avery Quinn of Cedar Hollow is the incumbent[^1]. He filed on 03/18/2026[^1].\n"
    )
    errors = semantic_claim_errors(_person_doc(), "claims", [record], followed)
    assert not any("does not identify" in error for error in errors)
    bare = "# Avery\n\n## Identity\n\nHe filed on 03/18/2026[^1].\n"
    bare_errors = semantic_claim_errors(_person_doc(), "claims", [record], bare)
    assert any("does not identify" in error for error in bare_errors)
    claim_errors = semantic_claim_errors(_person_doc("He filed on 03/18/2026."), "claims", [record], followed)
    assert any("claim text does not contain" in error for error in claim_errors)


def test_table_cell_uses_the_column_name_and_still_rejects_a_different_person():
    record = {"ballot_name": "Avery Quinn", "city": "Cedar Hollow", "office": "Mayor"}
    table = (
        "# Avery\n\n## Identity\n\n"
        "| | Avery Quinn |\n"
        "| --- | --- |\n"
        "| Filing | filed on 03/18/2026[^1] |\n"
    )
    errors = semantic_claim_errors(_person_doc(), "claims", [record], table)
    assert not any("does not identify" in error for error in errors)
    foreign = table.replace("filed on 03/18/2026", "John Smith filed on 03/18/2026")
    foreign_errors = semantic_claim_errors(_person_doc(), "claims", [record], foreign)
    assert any("different person" in error for error in foreign_errors)


def test_parallel_official_records_are_not_a_near_copy(tmp_path: Path):
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "contests": [
                {
                    "id": "race-1",
                    "type": "race",
                    "candidates": [
                        {"id": "cand-a", "item_id": "cand-a", "name": "Aldon Bookhardt"},
                        {"id": "cand-b", "item_id": "cand-b", "name": "Nathan Slusher"},
                    ],
                }
            ]
        },
    )
    for item_id, name, when in (
        ("cand-a", "Aldon Bookhardt", "June 9"),
        ("cand-b", "Nathan Slusher", "July 12"),
    ):
        item = tmp_path / "items" / item_id
        item.mkdir(parents=True)
        (item / "draft.md").write_text(
            f"# {name}\n\n## Identity\n\n"
            f"{name} is on the ballot as a nonpartisan candidate. "
            f"The Division of Elections says {name} qualified by a paid qualifying fee on {when}[^1].\n",
            encoding="utf-8",
        )
    assert templated_prose_errors(tmp_path) == []


def test_report_dates_match_on_the_day_and_missing_cash_stays_a_gap(tmp_path: Path):
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "contests": [
                {
                    "id": "race-1",
                    "type": "race",
                    "candidates": [
                        {"id": "cand-a", "item_id": "cand-a", "name": "Avery Quinn"},
                        {"id": "cand-b", "item_id": "cand-b", "name": "Blake Okonkwo"},
                    ],
                }
            ]
        },
    )
    for item_id, report_date in (
        ("cand-a", "2026-09-30"),
        ("cand-b", "quarter ending 2026-09-30"),
    ):
        item = tmp_path / "items" / item_id
        item.mkdir(parents=True)
        dump_yaml(
            item / "profile.yaml",
            {"item_id": item_id, "issues": {"parks": "Keep the levy[^1]."}, "money": {"report_date": report_date}},
        )
    assert not any("report_date" in error for error in structured_symmetry_errors(tmp_path))
    from lib.guide_layout import _MONEY_ROWS, _assign_cells

    missing_cash = _assign_cells(
        {"campaign funding": ("Funding", "The summary shows 48200 dollars in receipts[^5].")},
        {"money": {"receipts": "48200 dollars in receipts[^5].", "report_date": "2026-09-30[^5]."}},
        _MONEY_ROWS,
    )
    assert missing_cash["Cash on hand"] == NOT_FOUND_CELL
    assert "48200" in missing_cash["Receipts"]


def test_duplicate_issue_text_is_not_a_second_row():
    positions = ["Keep the levy at the printed amount[^7].", "Publish the project list[^17]."]
    same = ["Keep the levy at the printed amount[^7].", "Publish the project list[^17]."]
    assert _duplicate_issue_row(same, positions) is True
    different = ["Keep the levy at the printed amount[^7].", "A different parks sentence[^17]."]
    assert _duplicate_issue_row(different, positions) is False


def test_many_candidates_stay_in_short_columns_and_cells_stay_short():
    two = comparison_tables(
        ["Ada", "Bo"],
        [("Receipts", ["1[^1]", "2[^2]"]), ("Cash on hand", ["3[^3]", "4[^4]"])],
    )
    assert len(two) == 1
    assert two[0][0] == ["Topic", "Ada", "Bo"]
    assert two[0][1][0] == ["Receipts", "1[^1]", "2[^2]"]
    names = [f"Candidate {index}" for index in range(9)]
    rows = [("Receipts", [f"{index} dollars[^1]" for index in range(9)]), ("Cash on hand", ["2 dollars[^2]"] * 9)]
    tables = comparison_tables(names, rows)
    assert len(tables) == 3
    assert [headers[0] for headers, _body in tables] == ["Topic", "Topic", "Topic"]
    assert [headers[1:] for headers, _body in tables] == [
        ["Candidate 0", "Candidate 1", "Candidate 2"],
        ["Candidate 3", "Candidate 4", "Candidate 5"],
        ["Candidate 6", "Candidate 7", "Candidate 8"],
    ]
    assert all(body[0][0] == "Receipts" for _headers, body in tables)
    assert tables[0][1][0][1:] == ["0 dollars[^1]", "1 dollars[^1]", "2 dollars[^1]"]
    assert tables[2][1][0][1:] == ["6 dollars[^1]", "7 dollars[^1]", "8 dollars[^1]"]
    assert _chunks(list(range(6)), 5) == [[0, 1, 2, 3, 4], [5]]
    portrait = "\n".join(_emit_table(["Topic", "A", "B", "C"], [["Receipts", "1", "2", "3"]]))
    assert "::: landscape" not in portrait
    landscape = "\n".join(_emit_table(["A", "B", "C", "D", "E", "F"], [["1", "2", "3", "4", "5", "6"]]))
    assert "::: landscape" in landscape
    short = _short_fact(
        "Avery Quinn of Cedar Hollow reported 48200 dollars in receipts and a long explanation of the filing period[^5].",
        "Receipts",
    )
    assert short.startswith("48200 dollars in receipts")
    assert len(short) <= CELL_CHAR_CAP + 8
    assert "[^5]" in short


def test_office_links_and_precinct_render_from_the_ballot(tmp_path: Path):
    init_workspace(tmp_path, "precinct-demo", "household", "2026-10-20 12:00 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["precinct"] = "122"
    ballot["districts"] = ["State House 8"]
    ballot["logistics"] = [{"label": "Supervisor of Elections", "url": "https://fictional.example/elections"}]
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    model = _GuideModel(tmp_path, "2026-10-21")
    text = "\n".join(model._election_office() + model._precinct_line())
    assert "https://fictional.example/elections" in text
    assert "Not found (searched: election office" not in text
    assert "Precinct 122, districts State House 8, restates the confirmed ballot." in text
    assert "Not found (searched: precinct" not in text
    exempt = official_restatement_sentences(ballot)
    assert prose_marker_errors(text, "ballot", exempt) == []
    allegation = "The candidate was convicted of fraud in 2019: https://fictional.example/doc"
    districts = "districts John Smith was convicted of fraud, restates the confirmed ballot."
    bare = "John Smith was convicted of fraud, restates the confirmed ballot."
    assert prose_marker_errors(allegation, "ballot", exempt)
    assert prose_marker_errors(districts, "ballot", exempt)
    assert prose_marker_errors(bare, "ballot", exempt)
    assert prose_marker_errors(text, "ballot")


def test_quote_must_be_verbatim_and_a_number_can_live_on_the_archived_page(tmp_path: Path):
    init_workspace(tmp_path, "quote-demo", "household", "2026-10-20 12:00 ET")
    archive = tmp_path / "archive"
    archive.mkdir()
    page = archive / "precinct-122.html"
    page.write_text("<html><body><h1>Precinct 122</h1><p>Wilton Simpson</p></body></html>", encoding="utf-8")
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)

    def write(quote: str, body: str) -> None:
        (page).write_text(body, encoding="utf-8")
        dump_yaml(
            item / "claims.yaml",
            {
                "item_id": "cand-a",
                "item_type": "candidate",
                "claims": [
                    {
                        "id": "cand-a.identity.001",
                        "text": "The precinct 122 sample ballot lists Wilton Simpson.",
                        "confidence": "single-source",
                        "sources": [
                            {
                                "marker": 7,
                                "url": "https://fictional.example/ballot",
                                "tier": "T1",
                                "archive_failed": True,
                                "archive_failed_reason": "fixture",
                                "retrieved": "2026-10-20 09:00 ET",
                                "publisher": "Elections",
                                "quote": quote,
                                "local_copy": "archive/precinct-122.html",
                            }
                        ],
                    }
                ],
            },
        )
        (item / "draft.md").write_text(
            "# Wilton\n\n## Identity\n\nThe precinct 122 sample ballot lists Wilton Simpson[^7].\n",
            encoding="utf-8",
        )

    write("Wilton Simpson extra", "<html><body><p>Precinct 122</p><p>Wilton Simpson</p></body></html>")
    assert any("verbatim" in error for error in quote_verbatim_errors(tmp_path))
    write("Wilton Simpson", "<html><body><p>Wilton Simpson</p></body></html>")
    assert quote_verbatim_errors(tmp_path) == []
    assert any("122" in error for error in number_quote_errors(tmp_path))
    write("Wilton Simpson", "<html><body><p>Precinct 122</p><p>Wilton Simpson</p></body></html>")
    assert quote_verbatim_errors(tmp_path) == []
    assert number_quote_errors(tmp_path) == []


def test_bbox_check_flags_overflow_and_tiny_type():
    inside = (
        '<doc><page width="612.000" height="792.000">'
        '<word xMin="72" yMin="72" xMax="140" yMax="82">Receipts</word>'
        '<word xMin="150" yMin="70" xMax="160" yMax="76">5</word>'
        "</page></doc>"
    )
    assert errors_from_bbox(inside) == []
    overflow = (
        '<doc><page width="612.000" height="792.000">'
        '<word xMin="600" yMin="72" xMax="700" yMax="82">Receipts</word>'
        "</page></doc>"
    )
    assert any("outside the page" in error for error in errors_from_bbox(overflow))
    tiny = (
        '<doc><page width="612.000" height="792.000">'
        '<word xMin="72" yMin="72" xMax="120" yMax="76">Receipts</word>'
        '<word xMin="130" yMin="72" xMax="160" yMax="76">48200</word>'
        "</page></doc>"
    )
    tiny_errors = errors_from_bbox(tiny)
    assert any("Receipts" in error and "below" in error for error in tiny_errors)
    assert any("48200" in error and "below" in error for error in tiny_errors)
    narrow = ['<doc><page width="792" height="612">']
    for index in range(8):
        x_min = 36 + index * 60
        narrow.append(f'<word xMin="{x_min}" yMin="100" xMax="{x_min + 40}" yMax="112">Name{index}</word>')
    narrow.append("</page></doc>")
    assert any("columns" in error for error in errors_from_bbox("".join(narrow)))
    stack = ["<doc><page width=\"612\" height=\"792\">"]
    for index, word in enumerate(("Alpha", "Bravo", "Charlie", "Delta")):
        y_min = 100 + index * 14
        stack.append(f'<word xMin="40" yMin="{y_min}" xMax="80" yMax="{y_min + 10}">{word}</word>')
    stack.append("</page></doc>")
    assert any("column" in error for error in errors_from_bbox("".join(stack)))
    leaders = (
        '<doc><page width="612" height="792">'
        '<word xMin="72" yMin="100" xMax="140" yMax="112">Mayor</word>'
        '<word xMin="160" yMin="100" xMax="168" yMax="112">.</word>'
        '<word xMin="190" yMin="100" xMax="198" yMax="112">.</word>'
        '<word xMin="220" yMin="100" xMax="228" yMax="112">.</word>'
        '<word xMin="400" yMin="100" xMax="420" yMax="112">4</word>'
        "</page></doc>"
    )
    assert errors_from_bbox(leaders) == []
    wide_candidates = (
        "<div class='comparison'><table><tr>"
        + "".join(f"<th>H{index}</th>" for index in range(5))
        + "</tr></table></div>"
    )
    assert any("candidates" in error for error in html_layout_errors(wide_candidates))
    portrait_wide = "<table><tr>" + "".join(f"<td>{index}</td>" for index in range(5)) + "</tr></table>"
    assert any("portrait" in error for error in html_layout_errors(portrait_wide))
    landscape_wide = (
        "<div class='landscape'><table><tr>"
        + "".join(f"<td>{index}</td>" for index in range(7))
        + "</tr></table></div>"
    )
    assert any("landscape" in error for error in html_layout_errors(landscape_wide))
    fits = (
        "<div class='comparison'><table><tr>"
        "<th>Topic</th><th>Ada</th><th>Bo</th><th>Cara</th>"
        "</tr></table></div>"
    )
    assert html_layout_errors(fits) == []


def test_running_header_names_the_section_and_updates_per_contest(tmp_path: Path):
    """The cover stays clear. Later pages name the section, the current contest, and the page."""
    html = tmp_path / "header.html"
    css = Path(__file__).resolve().parents[1] / "assets" / "guide.css"
    html.write_text(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="{css}">
</head><body>
<section class="cover"><h1>Cover</h1><p>No running header on the cover.</p></section>
<a class="runhead" href="#your-ballot-at-a-glance" aria-label="Back to the ballot at a glance">&#8203;</a>
<main id="content">
<h1 class="ballot-glance" id="your-ballot-at-a-glance">Your ballot at a glance</h1>
<p>Glance body.</p>
<h1 class="ballot-group">Races</h1>
<h2 class="contest-title">Mayor of Cedar Hollow</h2>
<p>Mayor body.</p>
<p style="break-before: page">Mayor continued onto the next page.</p>
<h2 class="contest-title">Measure H</h2>
<p>Measure body.</p>
</main></body></html>
""",
        encoding="utf-8",
    )
    pdf = tmp_path / "header.pdf"
    result = subprocess.run(
        ["weasyprint", str(html), str(pdf)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert pdf.stat().st_size > 1000, pdf.stat().st_size
    text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], text=True)
    pages = [page for page in text.split("\f") if page.strip()]
    assert pages, text
    cover = pages[0]
    assert "No running header" in cover
    assert not re.search(r"Mayor of Cedar Hollow\s+\d", cover)
    contest = next(page for page in pages if "Mayor body" in page)
    header = next(line for line in contest.splitlines() if line.strip())
    assert "Races" in header
    assert "Mayor of Cedar Hollow" in header
    assert re.search(r"\d\s*$", header)
    continued = next(page for page in pages if "Mayor continued" in page)
    continued_header = next(line for line in continued.splitlines() if line.strip())
    assert "Mayor of Cedar Hollow" in continued_header
    measure = next(page for page in pages if "Measure body" in page)
    measure_header = next(line for line in measure.splitlines() if line.strip())
    assert "Measure H" in measure_header
    assert "Mayor of Cedar Hollow" not in measure_header
    raw = pdf.read_bytes()
    streams = []
    for chunk in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        try:
            streams.append(zlib.decompress(chunk))
        except zlib.error:
            streams.append(chunk)
    blob = b"\n".join(streams)
    assert b"your-ballot-at-a-glance" in blob
    assert errors_from_bbox(subprocess.check_output(["pdftotext", "-bbox", str(pdf), "-"], text=True)) == []


def test_running_header_names_the_section_at_the_top_of_the_page(tmp_path: Path):
    """A heading lower on the page does not rename the section still at the top."""
    html = tmp_path / "header-top.html"
    css = Path(__file__).resolve().parents[1] / "assets" / "guide.css"
    html.write_text(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="{css}">
</head><body>
<a class="runhead" href="#your-ballot-at-a-glance">&#8203;</a>
<main>
<h1 id="glossary" class="back-matter">Glossary</h1>
<p>Glossary terms stay on this page.</p>
<h1 id="methodology" class="back-matter">How we researched</h1>
<p>Version line for the research section.</p>
<div style="break-before: page">
<h2>Effort</h2>
<p>Effort rows stay in the research section.</p>
</div>
<h1 id="disputed-claims" class="back-matter">Disputed claims</h1>
<p>The dispute starts with its own heading.</p>
</main></body></html>
""",
        encoding="utf-8",
    )
    pdf = tmp_path / "header-top.pdf"
    result = subprocess.run(
        ["weasyprint", str(html), str(pdf)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], text=True)
    pages = [page for page in text.split("\f") if page.strip()]
    effort = next(page for page in pages if "Effort rows stay" in page)
    effort_header = next(line for line in effort.splitlines() if line.strip())
    assert "How we researched" in effort_header
    assert "Disputed claims" not in effort_header
    dispute = next(page for page in pages if "dispute starts" in page)
    dispute_header = next(line for line in dispute.splitlines() if line.strip())
    assert "Disputed claims" in dispute_header
    assert "How we researched" not in dispute_header
    assert errors_from_bbox(subprocess.check_output(["pdftotext", "-bbox", str(pdf), "-"], text=True)) == []


def test_reader_budget_flags_a_long_contest():
    words = " ".join(["alpha"] * 50)
    short = f"## Mayor {{#contest-race-1 .contest-title}}\n\n{words}[^1].\n"
    assert reader_contest_budget_errors(short, 40)
    assert reader_contest_budget_errors(short, 80) == []


def _marker_index(*numbers: int) -> dict:
    return {
        number: ("cand", {"id": f"c{number}", "confidence": "verified", "drives_summary": False}, {})
        for number in numbers
    }


def test_addendum_ids_do_not_treat_marker_10_as_marker_1():
    body = (
        "The ballot lists Avery Quinn"
        '<a id="cite-1"></a>[<sup>1</sup>](guide-sources.md#source-1). '
        "The ballot lists Blake Okonkwo"
        '<a id="cite-10"></a>[<sup>10</sup>](guide-sources.md#source-10).\n'
    )
    missing_one = (
        "[1] Elections. https://fictional.example/one.\n\n"
        "[10] Elections. https://fictional.example/ten.\n\n"
        "### Source 10 {#source-10}\n\n"
        "[Back to the guide](guide.md#cite-10)\n"
    )
    errors = assembled_guide_errors(body, _marker_index(1, 10), missing_one)
    assert any("marker 1 does not link to an addendum entry" in error for error in errors)
    assert any("marker 1 addendum entry does not link back" in error for error in errors)
    present = (
        "[1] Elections. https://fictional.example/one.\n\n"
        "[10] Elections. https://fictional.example/ten.\n\n"
        "### Source 1 {#source-1}\n\n"
        "[Back to the guide](guide.md#cite-1)\n\n"
        "### Source 10 {#source-10}\n\n"
        "[Back to the guide](guide.md#cite-10)\n"
    )
    ok = assembled_guide_errors(body, _marker_index(1, 10), present)
    assert not any("marker 1" in error and "addendum" in error for error in ok)
    assert not any("marker 10" in error and "addendum" in error for error in ok)


def test_organization_word_does_not_hide_another_persons_name():
    record = {"ballot_name": "Avery Quinn", "city": "Cedar Hollow", "office": "Mayor"}
    draft = (
        "# Avery\n\n## Legal issues\n\n"
        "Avery Quinn of Cedar Hollow said the John Smith Committee was convicted in 2019[^1].\n"
    )
    errors = semantic_claim_errors(_person_doc(), "claims", [record], draft)
    assert any("different person" in error for error in errors)
    registered = {**record, "organizations": ["the John Smith Committee"]}
    cleared = semantic_claim_errors(_person_doc(), "claims", [registered], draft)
    assert not any("different person" in error for error in cleared)
    alone = draft.replace("the John Smith Committee", "John Smith")
    alone_errors = semantic_claim_errors(_person_doc(), "claims", [registered], alone)
    assert any("different person" in error for error in alone_errors)
    bare_list = {**record, "organizations": ["John Smith"]}
    bare_errors = semantic_claim_errors(_person_doc(), "claims", [bare_list], alone)
    assert any("different person" in error for error in bare_errors)
    listed_errors = organization_list_errors(
        {"organizations": ["John Smith", "the John Smith Committee", "Smith PAC", "Quinn LLC"]}
    )
    assert listed_errors == [
        "organizations/0: 'John Smith' is a personal name; an organization entry needs an "
        "organization word such as Committee, PAC, Inc, LLC, Party, Association, or Fund"
    ]


def test_identity_validation_rejects_a_bare_person_name(tmp_path: Path):
    init_workspace(tmp_path, "org-demo", "household", "2026-10-20 12:00 ET")
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    dump_yaml(item / "claims.yaml", {"item_id": "cand-a", "item_type": "candidate", "claims": []})
    dump_yaml(
        item / "identity.yaml",
        {
            "item_id": "cand-a",
            "full_legal_name": "Avery Jordan Quinn",
            "ballot_name": "Avery Quinn",
            "office": "Mayor",
            "photo_included": False,
            "organizations": ["John Smith", "John Smith Committee"],
        },
    )
    errors = structural_workspace_errors(tmp_path)
    assert any("identity.yaml: organizations/0:" in error and "personal name" in error for error in errors)
    assert not any("organizations/1:" in error for error in errors)


def test_a_quote_without_a_local_copy_is_not_skipped(tmp_path: Path):
    init_workspace(tmp_path, "quote-gap", "household", "2026-10-20 12:00 ET")
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    (item / "draft.md").write_text("# Avery\n\n## Funding\n\nReported 48200 dollars[^1].\n", encoding="utf-8")

    def write(sources: list, text: str = "The committee reported 48200 dollars in receipts.") -> None:
        dump_yaml(
            item / "claims.yaml",
            {
                "item_id": "cand-a",
                "item_type": "candidate",
                "claims": [
                    {
                        "id": "cand-a.funding.001",
                        "text": text,
                        "confidence": "verified",
                        "sources": sources,
                    }
                ],
            },
        )

    bare = {
        "marker": 1,
        "url": "https://fictional.example/filing",
        "tier": "T1",
        "archive_failed": False,
        "retrieved": "2026-10-20 09:00 ET",
        "publisher": "Elections",
        "quote": "Receipts 48200.",
    }
    write([bare])
    assert any("no readable local copy" in error for error in quote_verbatim_errors(tmp_path))
    failed = {**bare, "archive_failed": True, "archive_failed_reason": "fixture"}
    write([failed])
    assert any("second independent source" in error for error in quote_verbatim_errors(tmp_path))
    second = {
        **failed,
        "marker": 2,
        "publisher": "Ledger",
        "url": "https://fictional.example/ledger",
        "quote": "Receipts 48200.",
    }
    write([failed, second])
    assert quote_verbatim_errors(tmp_path) == []
    write(
        [failed],
        text="The precinct list names the candidate.",
    )
    assert quote_verbatim_errors(tmp_path) == []


def test_sample_saved_page_is_checked_verbatim():
    from lib.util import repo_root

    example = repo_root() / "examples" / "sample-election"
    page = (example / "saved" / "quinn-q3.html").read_text(encoding="utf-8")
    assert "Receipts 48200, disbursements 31000, cash on hand 17200, debt 0." in page
    assert quote_verbatim_errors(example) == []
