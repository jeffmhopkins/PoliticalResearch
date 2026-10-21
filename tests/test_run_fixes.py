"""Tests for the first real-run fixes. Each test locks one gate or layout rule."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import yaml

from lib.api_clients import scrub_civic_payload
from lib.archive import PDF_TIMEOUT_SECONDS, _is_chrome_wrapper, _run_group, archive_workspace, estimate_archive_size
from lib.quality import (
    _year_is_on_claim,
    figure_source_errors,
    heading_errors,
    number_quote_errors,
    prose_marker_errors,
    semantic_claim_errors,
    structured_symmetry_errors,
    templated_prose_errors,
)
from lib.schema import instance_errors, load_schema
from lib.sentences import split_sentences
from lib.util import coerce_yaml_dates, dump_json, dump_yaml, repo_root, unsafe_fetch_target
from lib.workflow import _draft_looks_ready, confirm_ballot, fresh_loop_state, init_workspace, signoff

ROOT = repo_root()
EXAMPLE = ROOT / "examples" / "sample-election"


def test_sentence_splitter_keeps_initials_degrees_and_hostnames():
    assert split_sentences("Dr. Jane Roe filed.") == ["Dr. Jane Roe filed."]
    assert split_sentences("She holds a J.D. degree.") == ["She holds a J.D. degree."]
    assert split_sentences("See congress.gov today.") == ["See congress.gov today."]
    assert split_sentences("Hollow.John filed.") == ["Hollow.", "John filed."]


def test_gap_notes_cannot_smuggle_a_second_clause():
    assert prose_marker_errors("Not found (searched: the clerk; the docket shows a plea).", "draft")
    assert prose_marker_errors("Not found (searched: pages that are official).", "draft")
    assert prose_marker_errors("Not found (searched: congress.gov and the county clerk).", "draft") == []
    assert prose_marker_errors("None.", "draft") == []
    assert prose_marker_errors("Not found (searched: county index, the 2019 conviction).", "draft")
    assert prose_marker_errors("Not found (searched: the 2019 conviction).", "draft")
    for event in ("arrest", "plea", "embezzlement", "kickback"):
        assert prose_marker_errors(f"Not found (searched: the 2019 {event}).", "draft")
        assert prose_marker_errors(f"Not found (searched: county index, the 2019 {event}).", "draft")
    assert prose_marker_errors("Not found (searched: the June arrest).", "draft")
    assert prose_marker_errors("Not found (searched: conviction of 2019).", "draft")
    assert prose_marker_errors("Not found (searched: the 2026 ballot filing).", "draft") == []
    assert prose_marker_errors("Not found (searched: years in elected office).", "draft") == []
    assert (
        prose_marker_errors(
            "Not found (searched: fictional Oak County court index, fictional Westland court index, and the candidate filing on 2026-10-20).",
            "draft",
        )
        == []
    )


def test_year_tokens_do_not_count_as_the_year():
    assert _year_is_on_claim("", "In 2018a the council sat[^2].", 2, "2018") is False
    assert _year_is_on_claim("", "In fy2018 the council sat[^2].", 2, "2018") is False
    assert _year_is_on_claim("", "In 2018 the council sat[^2].", 2, "2018") is True


def test_multicast_is_not_a_public_fetch_target():
    assert unsafe_fetch_target("http://224.0.0.1/ballot")
    assert unsafe_fetch_target("http://[ff02::1]/ballot")


def test_confirm_deletes_every_private_image_and_pdf(tmp_path: Path):
    init_workspace(tmp_path, "confirm-demo", "household", "2026-10-20 12:00 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["contests"] = [
        {
            "id": "race-1",
            "title": "Mayor",
            "official_source_url": "https://fictional.example/ballot",
            "type": "race",
        }
    ]
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    private = tmp_path / "private"
    private.mkdir(exist_ok=True)
    media = [
        private / "ballot-photo.png",
        private / "sample-ballot-precinct-122.pdf",
        private / "photo.jpg",
        private / "IMG_2044.jpg",
    ]
    for path in media:
        path.write_bytes(b"img")
    (private / "address.txt").write_text("PO Box 12\n", encoding="utf-8")
    (private / "notes.txt").write_text("keep\n", encoding="utf-8")
    assert confirm_ballot(tmp_path, "2026-10-20 12:00 ET") == []
    for path in media:
        assert not path.exists()
    assert (private / "address.txt").read_text(encoding="utf-8") == "PO Box 12\n"
    assert (private / "notes.txt").read_text(encoding="utf-8") == "keep\n"
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    assert intake["ballot_photo_deleted"] is True

    leftover = tmp_path / "leftover"
    init_workspace(leftover, "confirm-leftover", "household", "2026-10-20 12:00 ET")
    second = yaml.safe_load((leftover / "ballot.yaml").read_text(encoding="utf-8"))
    second["contests"] = ballot["contests"]
    dump_yaml(leftover / "ballot.yaml", second)
    held = leftover / "private" / "IMG_2044.jpg"
    held.write_bytes(b"phone")
    (leftover / "private" / "photo.jpg").write_bytes(b"phone")
    real_unlink = Path.unlink

    def refuse(self, *args, **kwargs):
        if self.name == "IMG_2044.jpg":
            raise OSError("refusing to delete")
        return real_unlink(self, *args, **kwargs)

    Path.unlink = refuse
    try:
        assert confirm_ballot(leftover, "2026-10-20 12:00 ET") == []
    finally:
        Path.unlink = real_unlink
    kept = yaml.safe_load((leftover / "intake.yaml").read_text(encoding="utf-8"))
    assert kept["ballot_photo_deleted"] is not True
    assert held.exists()
    assert not (leftover / "private" / "photo.jpg").exists()


def test_pending_archive_is_valid_and_not_a_yes(tmp_path: Path):
    init_workspace(tmp_path, "pending-demo", "household", "2026-10-20 12:00 ET")
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    intake["offline_archive"] = "pending"
    errors = instance_errors(intake, load_schema("intake.schema.yaml"))
    assert errors == [], errors
    assert intake["offline_archive"] is not True


def test_set_address_stdin_and_status_refresh(tmp_path: Path, monkeypatch, capsys):
    import intake as intake_cli

    init_workspace(tmp_path, "addr-demo", "household", "2026-10-20 12:00 ET")
    (tmp_path / "STATUS.md").write_text("STALE\n", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("1 Fictional Plaza\n"))
    code = intake_cli.main(
        ["--workspace", str(tmp_path), "--now", "2026-10-20 12:00 ET", "set-address"]
    )
    assert code == 0
    assert (tmp_path / "private" / "address.txt").read_text(encoding="utf-8").strip() == "1 Fictional Plaza"
    assert "1 Fictional Plaza" not in (tmp_path / "intake.yaml").read_text(encoding="utf-8")
    assert "STALE" not in (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    mode = (tmp_path / "private" / "address.txt").stat().st_mode & 0o777
    assert mode == 0o600

    code = intake_cli.main(
        [
            "--workspace",
            str(tmp_path),
            "--now",
            "2026-10-20 12:05 ET",
            "set",
            "--field",
            "notes",
            "--value",
            "refreshed",
        ]
    )
    assert code == 0
    status = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "2026-10-20 12:05 ET" in status
    capsys.readouterr()
    code = intake_cli.main(
        [
            "--workspace",
            str(tmp_path),
            "--now",
            "2026-10-20 12:06 ET",
            "set-address",
            "--address",
            "2 Fictional Plaza",
        ]
    )
    assert code == 0
    assert "shell history" in capsys.readouterr().err


def test_civic_scrub_keeps_precinct_id():
    cleaned = scrub_civic_payload({"precinctId": "122", "normalizedInput": {"line1": "1 Main St"}})
    assert cleaned["precinctId"] == "122"
    assert "normalizedInput" not in cleaned


def test_ballot_schema_accepts_precinct_districts_and_level():
    data = yaml.safe_load((EXAMPLE / "ballot.yaml").read_text(encoding="utf-8"))
    data["precinct"] = "122"
    data["districts"] = ["Cedar Hollow"]
    data["contests"][0]["level"] = "local"
    errors = instance_errors(coerce_yaml_dates(data), load_schema("ballot.schema.yaml"))
    assert errors == [], errors


def test_yaml_dates_are_coerced_before_the_schema():
    raw = yaml.safe_load("published: 2026-09-15\n")
    assert not isinstance(raw["published"], str)
    assert coerce_yaml_dates(raw)["published"] == "2026-09-15"


def test_templated_prose_and_headings_are_rejected(tmp_path: Path):
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
    for item_id, name in (("cand-a", "Avery Quinn"), ("cand-b", "Blake Okonkwo")):
        item = tmp_path / "items" / item_id
        item.mkdir(parents=True)
        (item / "draft.md").write_text(
            f"# {name}\n\n## Identity\n\n{name} of Cedar Hollow filed a long report on the parks levy and the budget[^1].\n",
            encoding="utf-8",
        )
    errors = templated_prose_errors(tmp_path)
    assert any("templated" in error for error in errors)
    for item_id, name, extra in (
        ("cand-a", "Avery Quinn", ""),
        ("cand-b", "Blake Okonkwo", " plus one extra word"),
    ):
        (tmp_path / "items" / item_id / "draft.md").write_text(
            f"# {name}\n\n## Identity\n\n{name} of Cedar Hollow filed a long report on the parks levy and the budget{extra}[^1].\n",
            encoding="utf-8",
        )
    near = templated_prose_errors(tmp_path)
    assert any("near-copy" in error or "templated" in error for error in near)
    assert any("cand-b" in error for error in near)
    bare = tmp_path / "items" / "cand-a" / "draft.md"
    bare.write_text("No title here.\n", encoding="utf-8")
    assert any("level-1" in error for error in heading_errors(tmp_path))


def test_figure_and_number_rules(tmp_path: Path):
    init_workspace(tmp_path, "fig-demo", "household", "2026-10-20 12:00 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["fiction"] = False
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    dump_yaml(
        item / "claims.yaml",
        {
            "item_id": "cand-a",
            "item_type": "candidate",
            "claims": [
                {
                    "id": "cand-a.funding.001",
                    "text": "The committee reported 48200 dollars in receipts.",
                    "confidence": "verified",
                    "sources": [
                        {
                            "marker": 5,
                            "url": "https://fictional.example/filing",
                            "tier": "T1",
                            "archive_failed": True,
                            "publisher": "Finance office",
                            "quote": "Receipts 100.",
                        }
                    ],
                }
            ],
        },
    )
    (item / "draft.md").write_text(
        "# Avery\n\n## Campaign funding\n\nThe committee reported 48200 dollars in receipts[^5].\n",
        encoding="utf-8",
    )
    assert any("second independent" in error for error in figure_source_errors(tmp_path))
    assert any("48200" in error for error in number_quote_errors(tmp_path))
    ballot["fiction"] = True
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    assert any("second independent" in error for error in figure_source_errors(tmp_path))
    fiscal = yaml.safe_load((EXAMPLE / "items" / "measure-h" / "claims.yaml").read_text(encoding="utf-8"))
    figure = next(claim for claim in fiscal["claims"] if claim["id"] == "measure-h.fiscal.001")
    publishers = {source["publisher"] for source in figure["sources"]}
    assert len(publishers) >= 2
    assert any(source.get("archive_failed") is True and not source.get("archive_url") for source in figure["sources"])
    assert figure_source_errors(EXAMPLE) == []


def test_section_anchor_allows_a_later_sentence_and_rejects_a_second_person():
    record = {"ballot_name": "Avery Quinn", "city": "Cedar Hollow", "office": "Mayor"}
    doc = {
        "item_type": "candidate",
        "claims": [
            {
                "id": "cand-a.identity.001",
                "text": "Avery Quinn of Cedar Hollow is the incumbent.",
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
    unnamed = "# Avery\n\n## Legal issues\n\nAvery Quinn of Cedar Hollow is the incumbent[^1]. The defendant was convicted of fraud in 2019[^1].\n"
    unnamed_errors = semantic_claim_errors(doc, "claims", [record], unnamed)
    assert any("draft sentence" in error for error in unnamed_errors)
    assert any("does not identify" in error for error in unnamed_errors)
    mixed = (
        "# Avery\n\n## Legal issues\n\n"
        "Avery Quinn of Cedar Hollow said John Smith was convicted of fraud in 2019[^1].\n"
    )
    mixed_errors = semantic_claim_errors(doc, "claims", [record], mixed)
    assert any("different person" in error for error in mixed_errors)
    bad = "# Avery\n\n## Identity\n\nAvery Quinn of Cedar Hollow is the incumbent[^1]. Blake Okonkwo also filed[^1].\n"
    errors = semantic_claim_errors(doc, "claims", [record], bad)
    assert any("draft sentence" in error for error in errors)
    assert any("different person" in error for error in errors)


def test_structured_symmetry_requires_the_same_issue_rows(tmp_path: Path):
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
    for item_id, issues, report_date in (
        ("cand-a", {"parks": "Keep the levy[^1]."}, "2026-09-30"),
        ("cand-b", {"roads": "Publish the list[^2]."}, "2026-08-31"),
    ):
        item = tmp_path / "items" / item_id
        item.mkdir(parents=True)
        dump_yaml(
            item / "profile.yaml",
            {"item_id": item_id, "issues": issues, "money": {"report_date": report_date}},
        )
    errors = structured_symmetry_errors(tmp_path)
    assert any("shared issue" in error for error in errors)
    assert any("report_date" in error for error in errors)
    profile = {"item_id": "cand-a", "issues": {"parks": "Keep the levy[^1]."}, "money": {"report_date": "2026-09-30"}}
    assert instance_errors(profile, load_schema("profile.schema.yaml")) == []


def test_navigation_link_is_not_an_uncited_sentence():
    assert prose_marker_errors("[Back to ballot](#your-ballot-at-a-glance)", "guide") == []


def test_reader_and_full_editions_follow_the_layout_rules():
    guide = (EXAMPLE / "final" / "guide.md").read_text(encoding="utf-8")
    sources = (EXAMPLE / "final" / "guide-sources.md").read_text(encoding="utf-8")
    full = (EXAMPLE / "final" / "guide-full.md").read_text(encoding="utf-8")
    full_sources = (EXAMPLE / "final" / "guide-full-sources.md").read_text(encoding="utf-8")
    assert "# Your ballot at a glance" in guide
    assert "# Compare across the ballot" in guide
    assert "# Official election office links" in guide
    assert "# Search log" not in guide
    assert "# Works cited" not in guide
    assert "# Search log" in sources or "### Search log" in sources
    assert "# Works cited" in sources
    anchors = re.findall(r"\{#([^}]+)\}", sources)
    assert len(anchors) == len(set(anchors))
    assert "draft.md" not in guide
    assert "## Uncontested" not in guide
    assert "## Write-in candidates" not in guide
    assert "See `CHANGELOG.md`." not in guide
    assert "# Marker index" not in guide
    assert "# Changelog" not in guide
    assert "- cand-quinn:" not in guide
    assert "{#profile-cand-quinn}" not in guide
    assert "{#profile-cand-quinn}" in full
    assert "guide-full.md#profile-cand-quinn" in guide
    assert "guide-sources.md#source-" in guide
    assert "#source-1" in sources
    assert "#cite-1" in sources
    assert 'id="cite-1"' in guide or "#cite-1" in guide
    assert "[Back to ballot](#your-ballot-at-a-glance)" in guide
    assert "Not found (searched: self-funding or loans, share from small donors, outside spending)." in guide
    assert "Not found (searched: years in elected office)." in guide
    assert not any(line.startswith("| Years in elected office |") for line in guide.splitlines())
    table = {}
    for line in guide.splitlines():
        if line.startswith("| ") and line.count("|") >= 4:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            table[cells[0]] = cells
    assert "48200 dollars in receipts" in table["Receipts"][1]
    assert "Cash on hand for Avery Quinn" in table["Cash on hand"][1]
    assert table["Receipts"][1] != table["Cash on hand"][1]
    assert "30100 dollars in receipts" in table["Receipts"][2]
    assert table["Cash on hand"][2] == "Not found"
    assert "four-year term" in table["Current or most recent office"][1]
    assert "2018 certificate" in table["Prior offices"][1]
    assert table["Current or most recent office"][1] != table["Prior offices"][1]
    assert len(table["Receipts"][1]) < 180
    quinn_money = next(line for line in guide.splitlines() if line.startswith("| Mayor of Cedar Hollow | Avery Quinn |"))
    quinn_cells = [cell.strip() for cell in quinn_money.strip().strip("|").split("|")]
    assert "48200" in quinn_cells[2]
    assert "Cash on hand for Avery Quinn" in quinn_cells[3]
    assert quinn_cells[2] != quinn_cells[3]
    assert "# Marker index" in full
    assert "# Changelog" in full
    assert "- cand-quinn:" in full
    assert "# Works cited" not in full
    assert "# Works cited" in full_sources
    assert "Not an official ballot" in guide
    assert "disputed" in guide
    from lib.quality import READER_CONTEST_WORD_BUDGET, reader_contest_budget_errors

    assert reader_contest_budget_errors(guide, READER_CONTEST_WORD_BUDGET) == []


def test_archive_fetches_each_url_once_and_skips_the_chrome_wrapper(tmp_path: Path):
    init_workspace(tmp_path, "archive-demo", "household", "2026-10-20 12:00 ET")
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    intake["offline_archive"] = True
    dump_yaml(tmp_path / "intake.yaml", intake)
    item = tmp_path / "items" / "measure-h"
    item.mkdir(parents=True)
    dump_yaml(
        item / "claims.yaml",
        {
            "item_id": "measure-h",
            "item_type": "measure",
            "claims": [
                {
                    "id": "measure-h.title.001",
                    "text": "A measure title.",
                    "sources": [{"marker": 1, "url": "https://fictional.example/doc", "tier": "T1"}],
                },
                {
                    "id": "measure-h.title.002",
                    "text": "The same page again.",
                    "sources": [{"marker": 2, "url": "https://fictional.example/doc", "tier": "T1"}],
                },
            ],
        },
    )
    log = tmp_path / "fetch-log.txt"

    def fetch(url):
        with log.open("a", encoding="utf-8") as handle:
            handle.write(url + "\n")
        return 200, url, b"<html><body>Fixture</body></html>", "text/html"

    code, message = archive_workspace(tmp_path, fetch, "2026-10-20 12:00 ET")
    assert code == 0, message
    assert log.read_text(encoding="utf-8").splitlines() == ["https://fictional.example/doc"]
    assert _is_chrome_wrapper("/usr/local/bin/google-chrome") is True
    assert "html-pdf" in estimate_archive_size(2, "html-pdf")
    assert PDF_TIMEOUT_SECONDS == 45
    try:
        _run_group(["sleep", "5"], timeout=1)
    except Exception as exc:
        assert "timed out" in str(exc).lower() or type(exc).__name__ == "TimeoutExpired"
    else:
        raise AssertionError("sleep was not killed at the timeout")


def test_comparison_cell_picks_the_specific_sentence_or_structured_field():
    from lib.guide_layout import NOT_FOUND_CELL, _COMPARISON_GROUPS, _MONEY_ROWS, _YEARS_IN_OFFICE_RE, _assign_cells

    assert _YEARS_IN_OFFICE_RE.search("a four-year term that began after the election") is None
    assert _YEARS_IN_OFFICE_RE.search("served 8 years in office")
    prior = (
        "Avery Quinn of Cedar Hollow was elected for a four-year term that began after the 2018 election[^2]. "
        "The 2018 certificate says the voters elected Avery Quinn of Cedar Hollow[^2]."
    )
    funding = (
        "Avery Quinn of Cedar Hollow filed on October 15, 2026 for the quarter that ended September 30, 2026[^5]. "
        "The summary shows 48200 dollars in receipts and 17200 dollars in cash on hand[^5]. "
        "Cash on hand for Avery Quinn of Cedar Hollow means money the report still showed[^5]."
    )
    only_cash_and_receipts = (
        "Blake Okonkwo of Cedar Hollow filed the quarter report[^14]. "
        "The summary shows 30100 dollars in receipts and 11700 dollars in cash on hand[^14]."
    )
    rows = [row for _heading, group in _COMPARISON_GROUPS for row in group]
    quinn = _assign_cells(
        {
            "prior offices and public service": ("Prior", prior),
            "campaign funding": ("Funding", funding),
        },
        {},
        rows,
    )
    assert quinn["Years in elected office"] == NOT_FOUND_CELL
    assert "four-year term" in quinn["Current or most recent office"]
    assert "certificate" in quinn["Prior offices"]
    assert quinn["Current or most recent office"] != quinn["Prior offices"]
    assert "48200" in quinn["Receipts"]
    assert "means money the report still showed" in quinn["Cash on hand"]
    assert quinn["Receipts"] != quinn["Cash on hand"]
    okonkwo = _assign_cells({"campaign funding": ("Funding", only_cash_and_receipts)}, {}, _MONEY_ROWS)
    assert "30100" in okonkwo["Receipts"]
    assert okonkwo["Cash on hand"] == NOT_FOUND_CELL
    structured = _assign_cells(
        {"campaign funding": ("Funding", funding)},
        {"money": {"receipts": "Structured receipts are 10 dollars[^9]."}},
        _MONEY_ROWS,
    )
    assert structured["Receipts"].startswith("Structured receipts")
    assert "means money the report still showed" in structured["Cash on hand"]


def test_hung_fetch_worker_is_killed(tmp_path: Path, monkeypatch):
    import os
    import time

    from lib import archive as archive_mod

    monkeypatch.setattr(archive_mod, "PAGE_TIMEOUT_SECONDS", 1)
    init_workspace(tmp_path, "hang-demo", "household", "2026-10-20 12:00 ET")
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    intake["offline_archive"] = True
    dump_yaml(tmp_path / "intake.yaml", intake)
    item = tmp_path / "items" / "measure-h"
    item.mkdir(parents=True)
    dump_yaml(
        item / "claims.yaml",
        {
            "item_id": "measure-h",
            "item_type": "measure",
            "claims": [
                {
                    "id": "measure-h.title.001",
                    "text": "A measure title.",
                    "sources": [{"marker": 1, "url": "https://fictional.example/slow", "tier": "T1"}],
                }
            ],
        },
    )

    def fetch(url):
        time.sleep(30)
        return 200, url, b"late", "text/html"

    started = time.monotonic()
    code, message = archive_mod.archive_workspace(tmp_path, fetch, "2026-10-20 12:00 ET")
    elapsed = time.monotonic() - started
    assert elapsed < 8, elapsed
    assert code == 0, message
    manifest = (tmp_path / "archive" / "manifest.csv").read_text(encoding="utf-8")
    assert "page deadline exceeded" in manifest
    assert archive_mod.last_worker_pids
    for pid in archive_mod.last_worker_pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"fetch worker {pid} is still running")


def test_build_sh_times_out_weasyprint():
    import re
    import subprocess
    import time

    script = (ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    assert re.search(r"timeout\s+-k\s+\d+\s+\d+\s+weasyprint", script)
    assert re.search(r"timeout\s+-k\s+\d+\s+\d+\s+wkhtmltopdf", script)
    started = time.monotonic()
    result = subprocess.run(["timeout", "-k", "2", "1", "sleep", "30"], check=False)
    assert result.returncode != 0
    assert time.monotonic() - started < 8


def test_link_check_fetches_a_url_once():
    from check_links import live_statuses

    calls = []

    class Response:
        status_code = 200

    def request(method, url, timeout=15):
        calls.append((method, url))
        return Response()

    found = live_statuses(
        ["https://fictional.example/a", "https://fictional.example/a"],
        request,
    )
    assert calls == [("HEAD", "https://fictional.example/a")]
    assert found["https://fictional.example/a"][0] == 200


def test_a11y_requires_pa11y_only_when_intake_asks(tmp_path: Path):
    from lib.a11y import check_html

    final = tmp_path / "final"
    final.mkdir()
    html = final / "guide.html"
    html.write_text(
        '<html lang="en"><body><a href="#content">Skip</a><main><h1>Guide</h1>'
        "<p>Not an official ballot</p></main></body></html>",
        encoding="utf-8",
    )
    dump_yaml(tmp_path / "intake.yaml", {"accessibility_needs": "Plain language summaries and a single HTML page."})
    code, message = check_html(html, which=lambda _name: None)
    assert code == 0, message
    dump_yaml(tmp_path / "intake.yaml", {"accessibility_needs": "Please run pa11y for a screen reader."})
    code, message = check_html(html, which=lambda _name: None)
    assert code == 1
    assert "pa11y" in message


def test_same_context_signoff_is_a_process_gap(tmp_path: Path):
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    dump_json(item / "loop-state.json", fresh_loop_state("cand-a", "2026-10-20 12:00 ET"))
    assert signoff(item, "factcheck", "2026-10-20 12:00 ET", same_context=True) == []
    state = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    assert state["signoffs"]["factcheck"]["signed"] is True
    assert state["process_gaps"]
    assert "process gap" in state["process_gaps"][0]


def test_finished_draft_is_not_treated_as_the_scaffold(tmp_path: Path):
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    dump_yaml(item / "claims.yaml", {"claims": [{"id": "cand-a.identity.001"}]})
    (item / "draft.md").write_text("# Name\n\nNot found (searched: not started).\n", encoding="utf-8")
    assert _draft_looks_ready(item) is False
    (item / "draft.md").write_text("# Name\n\nThe ballot lists the candidate[^1].\n", encoding="utf-8")
    assert _draft_looks_ready(item) is True


def test_ballot_text_uses_raw_nodiag(monkeypatch, tmp_path: Path):
    from lib.ballot_text import extract_ballot_text

    seen = {}

    def fake_run(cmd, check, capture_output, text):
        seen["cmd"] = cmd

        class Result:
            returncode = 0
            stdout = "Shall the judge be retained"
            stderr = ""

        return Result()

    monkeypatch.setattr("lib.ballot_text.subprocess.run", fake_run)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF")
    assert "judge" in extract_ballot_text(pdf)
    assert seen["cmd"][1:3] == ["-raw", "-nodiag"]
