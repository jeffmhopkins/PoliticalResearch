"""Reader length, citation addendums, table shape, and the rerun gate fixes."""

from __future__ import annotations

from pathlib import Path

import yaml

from check_pdf_layout import errors_from_bbox
from lib.guide_layout import (
    CELL_CHAR_CAP,
    NOT_FOUND_CELL,
    TRANSPOSE_CANDIDATES,
    _GuideModel,
    _duplicate_issue_row,
    _short_fact,
    comparison_tables,
)
from lib.quality import (
    number_quote_errors,
    prose_marker_errors,
    quote_verbatim_errors,
    reader_contest_budget_errors,
    semantic_claim_errors,
    structured_symmetry_errors,
    templated_prose_errors,
)
from lib.util import dump_yaml
from lib.workflow import init_workspace


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


def test_many_candidates_become_rows_and_cells_stay_short():
    names = [f"Candidate {index}" for index in range(TRANSPOSE_CANDIDATES)]
    rows = [("Receipts", ["10 dollars[^1]"] * len(names)), ("Cash on hand", ["2 dollars[^2]"] * len(names))]
    tables = comparison_tables(names, rows)
    assert tables[0][0][0] == "Candidate"
    assert tables[0][1][0][0] == "Candidate 0"
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
    assert prose_marker_errors(text, "ballot") == []


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


def test_reader_budget_flags_a_long_contest():
    words = " ".join(["alpha"] * 50)
    short = f"## Mayor {{#contest-race-1 .contest-title}}\n\n{words}[^1].\n"
    assert reader_contest_budget_errors(short, 40)
    assert reader_contest_budget_errors(short, 80) == []
