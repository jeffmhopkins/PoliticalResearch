"""Tests for schemas, the review loop, intake privacy, and degraded API scripts."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from lib.api_clients import contests_from_civic, fec_stub, scrub_civic_payload
from lib.archive import archive_workspace
from lib.quality import (
    classify_link,
    flesch_kincaid_grade,
    prose_marker_errors,
    semantic_claim_errors,
    wayback_api_url,
)
from lib.schema import check_schema_document, load_schema
from lib.util import dump_json, dump_yaml, repo_root
from lib.workflow import (
    confirm_ballot,
    enforce_cap,
    fresh_loop_state,
    init_workspace,
    scaffold_item,
    set_address,
    set_intake_field,
)

ROOT = repo_root()


def _source(**overrides):
    data = {
        "url": "https://fictional.example/doc",
        "archive_failed": True,
        "archive_failed_reason": "fixture",
        "publisher": "Fixture Office",
        "title": "Fixture document",
        "doc_type": "Official record",
        "published": "2026-09-01",
        "retrieved": "2026-10-20 09:00 ET",
        "tier": "T1",
        "locator": "page 1",
        "quote": "A fixture sentence.",
        "confidence": "verified",
        "marker": 1,
    }
    data.update(overrides)
    return data


def _claim(**overrides):
    data = {
        "id": "cand-fixture.identity.001",
        "section": "identity",
        "text": "A fixture sentence.",
        "marker": 1,
        "sources": [_source()],
        "confidence": "verified",
        "drives_summary": True,
        "polarity": "neutral",
        "about_person": False,
    }
    data.update(overrides)
    return data


def test_schema_files_are_valid_draft_2020():
    for name in (
        "claims.schema.yaml",
        "findings.schema.yaml",
        "loop-state.schema.json",
        "ballot.schema.yaml",
        "intake.schema.yaml",
        "identity.schema.yaml",
        "effort.schema.json",
    ):
        errors = check_schema_document(load_schema(name))
        assert errors == [], errors


def test_semantic_rules_reject_uncited_archive_and_t4_facts():
    missing = _claim(sources=[_source(archive_failed=False, archive_url=None, archive_failed_reason=None)])
    errors = semantic_claim_errors({"claims": [missing]}, "fixture")
    assert any("archive_url" in error for error in errors)

    t4 = _claim(
        sources=[_source(tier="T4")],
        confidence="verified",
        drives_summary=True,
    )
    errors = semantic_claim_errors({"claims": [t4]}, "fixture")
    assert any("attribution_only" in error for error in errors)
    assert any("cannot be verified" in error for error in errors)

    person = _claim(about_person=True, identity_attributes=["ballot_name"])
    errors = semantic_claim_errors({"claims": [person]}, "fixture")
    assert any("identity_attributes" in error for error in errors)


def test_prose_requires_a_marker_on_each_factual_sentence():
    bare = prose_marker_errors("The candidate filed on July 1, 2026.", "draft")
    assert bare
    cited = prose_marker_errors("The candidate filed on July 1, 2026[^1].", "draft")
    assert cited == []
    gap = prose_marker_errors("Not found (searched: the county index).", "draft")
    assert gap == []


def test_cap_removes_blockers_and_disputes_majors(tmp_path: Path):
    item = tmp_path / "items" / "cand-fixture"
    item.mkdir(parents=True)
    dump_yaml(
        item / "claims.yaml",
        {
            "item_id": "cand-fixture",
            "item_type": "candidate",
            "claims": [
                _claim(id="cand-fixture.identity.001", marker=1),
                _claim(id="cand-fixture.funding.001", marker=2, sources=[_source(marker=2)]),
            ],
        },
    )
    dump_yaml(
        item / "findings.yaml",
        [
            {
                "id": "F-0001",
                "round": 1,
                "reviewer": "privacy-legal",
                "claim_id": "cand-fixture.identity.001",
                "type": "privacy",
                "severity": "blocker",
                "issue": "The sentence publishes a home street.",
                "evidence": ["https://fictional.example/doc"],
                "status": "open",
            },
            {
                "id": "F-0002",
                "round": 1,
                "reviewer": "neutrality",
                "claim_id": "cand-fixture.funding.001",
                "type": "neutrality",
                "severity": "major",
                "issue": "The totals use a loaded label.",
                "evidence": ["https://fictional.example/doc"],
                "status": "open",
            },
            {
                "id": "F-0003",
                "round": 1,
                "reviewer": "sourcing",
                "claim_id": "cand-fixture.funding.001",
                "type": "sourcing",
                "severity": "minor",
                "issue": "Add the filing time.",
                "evidence": ["https://fictional.example/doc"],
                "status": "open",
            },
        ],
    )
    dump_json(item / "loop-state.json", fresh_loop_state("cand-fixture", "2026-10-20 12:00 ET"))
    state = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    state["round"] = 3
    dump_json(item / "loop-state.json", state)
    assert enforce_cap(item, "2026-10-20 12:05 ET") == []
    claims = yaml.safe_load((item / "claims.yaml").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in claims["claims"]}
    assert by_id["cand-fixture.identity.001"]["removed"] is True
    assert by_id["cand-fixture.funding.001"]["confidence"] == "disputed"
    assert by_id["cand-fixture.funding.001"]["drives_summary"] is False
    findings = yaml.safe_load((item / "findings.yaml").read_text(encoding="utf-8"))
    by_finding = {row["id"]: row for row in findings}
    assert by_finding["F-0001"]["status"] == "accepted"
    assert by_finding["F-0002"]["status"] == "disputed"
    assert by_finding["F-0003"]["status"] == "wontfix-approved"
    updated = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    assert updated["status"] == "capped-disputed"
    assert "CL-0001" in (item / "CHANGELOG.md").read_text(encoding="utf-8")


def test_signoff_blocks_open_findings_and_resume_waits_for_confirmation(tmp_path: Path):
    from lib.workflow import next_actions, signoff

    init_workspace(tmp_path, "demo", "household", "2026-10-20 12:00 ET")
    actions = " ".join(next_actions(tmp_path))
    assert "Finish intake" in actions
    item = tmp_path / "items" / "cand-fixture"
    item.mkdir(parents=True)
    dump_yaml(
        item / "findings.yaml",
        [
            {
                "id": "F-0001",
                "round": 1,
                "reviewer": "factcheck",
                "claim_id": "cand-fixture.identity.001",
                "type": "factual",
                "severity": "major",
                "issue": "The date does not match the certificate.",
                "evidence": ["https://fictional.example/doc"],
                "status": "open",
            }
        ],
    )
    dump_json(item / "loop-state.json", fresh_loop_state("cand-fixture", "2026-10-20 12:00 ET"))
    errors = signoff(item, "factcheck", "2026-10-20 12:10 ET")
    assert errors


def test_address_stays_out_of_intake_and_confirmation_gates_research(tmp_path: Path):
    init_workspace(tmp_path, "demo-session", "household", "2026-10-20 12:00 ET")
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    assert set_intake_field(intake, "jurisdiction_label", "123 Main Street")
    set_address(tmp_path, intake, "123 Main Street, Cedar Hollow")
    dump_yaml(tmp_path / "intake.yaml", intake)
    text = (tmp_path / "intake.yaml").read_text(encoding="utf-8")
    assert "123 Main Street" not in text
    assert "private/address.txt" in text
    assert "123 Main Street" in (tmp_path / "private" / "address.txt").read_text(encoding="utf-8")
    assert confirm_ballot(tmp_path, "2026-10-20 12:30 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["contests"] = [
        {
            "id": "race-mayor",
            "type": "race",
            "title": "Mayor",
            "official_source_url": "https://fictional.example/ballot",
            "candidates": [],
        }
    ]
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    (tmp_path / "private" / "ballot-photo.jpg").write_bytes(b"not-a-real-photo")
    assert confirm_ballot(tmp_path, "2026-10-20 12:40 ET") == []
    confirmed = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    assert confirmed["confirmed_by_requester"] is True
    assert not (tmp_path / "private" / "ballot-photo.jpg").exists()
    refused = scaffold_item(tmp_path, "cand-early", "candidate", "Early", "2026-10-20 12:00 ET")
    # Already confirmed, so scaffolding is allowed.
    assert refused == []
    fresh = tmp_path / "unconfirmed"
    init_workspace(fresh, "unconfirmed", "household", "2026-10-20 12:00 ET")
    blocked = scaffold_item(fresh, "cand-early", "candidate", "Early", "2026-10-20 12:00 ET")
    assert blocked


def test_civic_mapping_drops_the_normalized_address_and_does_not_confirm():
    payload = scrub_civic_payload(
        {
            "normalizedInput": {"line1": "123 Main Street"},
            "election": {"name": "Test", "electionDay": "2026-11-03"},
            "state": [{"sources": [{"name": "https://fictional.example/official", "official": True}]}],
            "contests": [
                {
                    "office": "Mayor",
                    "candidates": [{"name": "Example Person", "party": "Nonpartisan"}],
                }
            ],
        }
    )
    assert "normalizedInput" not in payload
    contests, notes = contests_from_civic(payload)
    assert contests[0]["title"] == "Mayor"
    assert contests[0]["official_source_url"] == "https://fictional.example/official"
    assert contests[0]["candidates"][0]["name"] == "Example Person"
    assert notes == [] or isinstance(notes, list)


def test_fec_stub_marks_itself_unreviewed():
    stub = fec_stub("P00000000", "2026", {"results": [{"receipts": 10, "coverage_end_date": "2026-09-30"}]})
    assert stub["status"] == "unreviewed_import"
    assert stub["receipts"] == 10


def test_link_helpers_do_not_need_a_network():
    assert classify_link(404, False) == "dead"
    assert classify_link(404, True) == "dead-with-archive"
    assert classify_link(200, False) == "live"
    assert wayback_api_url("https://fictional.example/a b").startswith("https://archive.org/wayback/available?url=")


def test_readability_scores_a_plain_sentence():
    grade = flesch_kincaid_grade("Two people are running for mayor. The guide does not say how to vote.")
    assert grade is not None
    assert grade < 9


def test_archive_records_a_capture_without_a_live_site(tmp_path: Path):
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
            "claims": [_claim(id="measure-h.title.001", text="A measure title.")],
        },
    )

    def fetch(_url):
        return 200, "https://fictional.example/doc", b"<html><body><p>Fixture</p></body></html>", "text/html"

    code, message = archive_workspace(tmp_path, fetch, "2026-10-20 12:00 ET")
    assert code == 0, message
    manifest = (tmp_path / "archive" / "manifest.csv").read_text(encoding="utf-8")
    assert "sha256" in manifest
    assert "capture_failed" not in manifest.splitlines()[1]
    claims = yaml.safe_load((item / "claims.yaml").read_text(encoding="utf-8"))
    assert claims["claims"][0]["sources"][0]["local_copy"].startswith("archive/")
    assert (tmp_path / "final" / "guide-with-sources.zip").exists()


def test_data_scripts_skip_without_keys(tmp_path: Path):
    env = os.environ.copy()
    for name in (
        "OPENFEC_API_KEY",
        "GOOGLE_CIVIC_API_KEY",
        "DEMOCRACY_WORKS_API_KEY",
        "DEMOCRACY_WORKS_API_URL",
        "OPENSTATES_API_KEY",
        "CONGRESS_API_KEY",
    ):
        env.pop(name, None)
    env["PR_NO_REEXEC"] = "1"
    # Hide any developer .env by pointing the process at a copy of the repo logic:
    # the scripts read the repo .env, which bootstrap leaves blank.
    fec = subprocess.run(
        ["python3", "scripts/fec.py", "--candidate-id", "P8", "--cycle", "2026"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert fec.returncode == 0, fec.stderr
    assert "Skipping FEC" in fec.stdout
    states = subprocess.run(
        ["python3", "scripts/openstates.py", "--jurisdiction", "Westland", "--identifier", "HB 1"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert states.returncode == 0, states.stderr
    assert "Skipping Open States" in states.stdout
    congress = subprocess.run(
        ["python3", "scripts/congress.py", "--congress", "119", "--bill-type", "hr", "--number", "1"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert congress.returncode == 0, congress.stderr
    assert "Skipping Congress.gov" in congress.stdout


def test_ballot_lookup_skips_without_a_key_and_invents_nothing(tmp_path: Path):
    init_workspace(tmp_path, "lookup-demo", "household", "2026-10-20 12:00 ET")
    intake = yaml.safe_load((tmp_path / "intake.yaml").read_text(encoding="utf-8"))
    set_address(tmp_path, intake, "1 Fictional Plaza")
    dump_yaml(tmp_path / "intake.yaml", intake)
    env = os.environ.copy()
    for name in (
        "OPENFEC_API_KEY",
        "GOOGLE_CIVIC_API_KEY",
        "DEMOCRACY_WORKS_API_KEY",
        "DEMOCRACY_WORKS_API_URL",
        "OPENSTATES_API_KEY",
        "CONGRESS_API_KEY",
    ):
        env.pop(name, None)
    env["PR_NO_REEXEC"] = "1"
    result = subprocess.run(
        ["python3", "scripts/ballot_lookup.py", "--workspace", str(tmp_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "skipped" in result.stdout.lower()
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    assert ballot["contests"] == []
    assert ballot["confirmed_by_requester"] is False
    assert "1 Fictional Plaza" not in (tmp_path / "ballot.yaml").read_text(encoding="utf-8")


def test_swap_replaces_names_and_drops_requester_views():
    from lib.quality import blinded_swap

    text = blinded_swap(
        "Avery Quinn leads.\nRequester view: prefers Avery Quinn.\n",
        [("Avery Quinn", "Candidate A")],
    )
    assert "Avery Quinn" not in text
    assert "Candidate A" in text
    assert "Requester view" not in text


def test_refresh_bumps_version_and_opens_one_round(tmp_path: Path):
    import refresh

    init_workspace(tmp_path, "refresh-demo", "household", "2026-10-20 12:00 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["report_version"] = "v1.0"
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    item = tmp_path / "items" / "measure-h"
    item.mkdir(parents=True)
    dump_json(item / "loop-state.json", fresh_loop_state("measure-h", "2026-10-20 12:00 ET"))
    code = refresh.main(
        [
            "--workspace",
            str(tmp_path),
            "--today",
            "2026-10-20",
            "--now",
            "2026-10-20 12:00 ET",
            "--bump",
            "--open-round",
            "--note",
            "Scheduled refresh.",
        ]
    )
    assert code == 0
    updated = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    assert updated["report_version"] == "v1.1"
    state = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    assert state["mode"] == "refresh"
    assert state["max_rounds"] == 1
    assert "Scheduled refresh." in (tmp_path / "corrections.yaml").read_text(encoding="utf-8")


def test_gitignore_covers_output_and_private():
    result = subprocess.run(
        ["git", "check-ignore", "-v", "output/report.md", "private/address.txt", "output/demo/private/address.txt"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "output/report.md" in result.stdout
    assert "private/address.txt" in result.stdout
