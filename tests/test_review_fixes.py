"""Regression tests for the PR #1 review findings."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import yaml

from lib.api_clients import contests_from_civic, scrub_civic_payload
from lib.quality import (
    argument_length_errors,
    citation_errors,
    content_gate_errors,
    edge_errors,
    environment_rating_sentence,
    prose_marker_errors,
    semantic_claim_errors,
    symmetry_errors,
    year_label_errors,
)
from lib.util import dump_json, dump_yaml, looks_like_street_address, repo_root, unsafe_fetch_target
from lib.workflow import confirm_ballot, init_workspace, scaffold_item, snapshot_guide

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


def _identity():
    return {
        "item_id": "cand-fixture",
        "full_legal_name": "Avery Jordan Quinn",
        "ballot_name": "Avery Quinn",
        "office": "Mayor",
        "city": "Cedar Hollow",
        "occupation": "classroom teacher",
        "filing_ids": ["WL-FICTION-1001"],
        "photo_included": False,
    }


def test_gap_prefix_allows_only_not_found_and_a_whole_sentence_none():
    assert prose_marker_errors("Not found (searched: the county index).", "draft") == []
    assert prose_marker_errors("None.", "draft") == []
    nonetheless = prose_marker_errors("Nonetheless, the filing shows 10000 dollars.", "draft")
    none_of = prose_marker_errors("None of the candidates filed a finance report.", "draft")
    assert nonetheless and none_of


def test_blockquotes_need_markers_unless_they_are_banners():
    banner = prose_marker_errors("> **FICTIONAL EXAMPLE.** This race is invented.", "draft")
    official = prose_marker_errors("> **Not an official ballot. Not voting instructions.**", "draft")
    factual = prose_marker_errors("> The candidate was convicted in 2019.", "draft")
    assert banner == []
    assert official == []
    assert factual


def test_marker_reuse_on_one_claim_and_across_the_election_is_an_error(tmp_path: Path):
    shared = _claim(
        sources=[_source(marker=4), _source(marker=4, url="https://fictional.example/other")],
    )
    errors = semantic_claim_errors({"claims": [shared]}, "fixture")
    assert any("marker 4" in error for error in errors)
    item_a = tmp_path / "items" / "cand-a"
    item_b = tmp_path / "items" / "cand-b"
    item_a.mkdir(parents=True)
    item_b.mkdir(parents=True)
    dump_yaml(item_a / "claims.yaml", {"item_id": "cand-a", "item_type": "candidate", "claims": [_claim(id="cand-a.identity.001")]})
    dump_yaml(
        item_b / "claims.yaml",
        {"item_id": "cand-b", "item_type": "candidate", "claims": [_claim(id="cand-b.identity.001", sources=[_source(url="https://fictional.example/second")])]},
    )
    collisions = citation_errors(tmp_path)
    assert any("reused across sources" in error and "cand-a" in error and "cand-b" in error for error in collisions)


def test_identity_unconfirmed_sentence_cannot_be_published(tmp_path: Path):
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    claim = _claim(confidence="identity-unconfirmed", drives_summary=False, about_person=True, identity_attributes=["ballot_name", "office"])
    dump_yaml(item / "claims.yaml", {"item_id": "cand-a", "item_type": "candidate", "claims": [claim]})
    dump_yaml(item / "identity.yaml", _identity())
    (item / "draft.md").write_text("# A\n\nThe candidate filed on July 1, 2026[^1].\n", encoding="utf-8")
    errors = citation_errors(tmp_path)
    assert any("identity-unconfirmed" in error and "must not be published" in error for error in errors)


def test_suspected_injection_on_a_source_cannot_be_sole_support():
    only = _claim(sources=[_source(suspected_injection=True)])
    errors = semantic_claim_errors({"claims": [only]}, "fixture")
    assert any("suspected_injection source cannot be the only support" in error for error in errors)
    assert any("cannot be verified" in error for error in errors)
    assert any("cannot drive a summary" in error for error in errors)
    mixed = _claim(sources=[_source(suspected_injection=True), _source(marker=2, url="https://fictional.example/clean")])
    assert semantic_claim_errors({"claims": [mixed]}, "fixture") == []


def test_identity_anchors_must_match_identity_yaml():
    fake = _claim(about_person=True, identity_attributes=["not-a-real-anchor", "also-fake"])
    errors = semantic_claim_errors({"item_type": "candidate", "claims": [fake]}, "fixture", identities=[_identity()])
    assert any("do not match one identity.yaml" in error for error in errors)
    missing = semantic_claim_errors({"claims": [_claim(about_person=True, identity_attributes=["ballot_name", "office"])]}, "fixture")
    assert any("no identity.yaml" in error for error in missing)
    matched = semantic_claim_errors(
        {"item_type": "candidate", "claims": [_claim(about_person=True, identity_attributes=["ballot_name", "occupation"])]},
        "fixture",
        identities=[_identity()],
    )
    assert matched == []
    skipped = _claim(section="funding", about_person=False)
    funding = semantic_claim_errors({"item_type": "candidate", "claims": [skipped]}, "fixture", identities=[_identity()])
    assert funding == []
    hidden = semantic_claim_errors(
        {"item_type": "candidate", "claims": [_claim(section="record", about_person=False)]},
        "fixture",
        identities=[_identity()],
    )
    assert any("must set about_person" in error for error in hidden)


def test_swap_blinds_surnames_aliases_and_urls_across_the_ballot(tmp_path: Path):
    import shutil

    copy = tmp_path / "sample"
    shutil.copytree(ROOT / "examples" / "sample-election", copy)
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/swap.py"), "--workspace", str(copy)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    blinded = (copy / "swap-draft.md").read_text(encoding="utf-8")
    assert "Quinn" not in blinded
    assert "Okonkwo" not in blinded
    assert "quinn-for-cedar.example" not in blinded
    assert "Measure H" in blinded
    assert "Candidate A" in blinded and "Candidate B" in blinded


def test_civic_does_not_invent_party_or_incumbent_and_keeps_candidate_url():
    payload = scrub_civic_payload(
        {
            "normalizedInput": {"line1": "123 Main Street"},
            "pollingLocations": [{"address": {"line1": "1 City Hall"}}],
            "earlyVoteSites": [{"address": "9 Vote Lane"}],
            "contests": [
                {
                    "office": "Mayor",
                    "candidates": [
                        {"name": "Example Person", "candidateUrl": "https://fictional.example/example"},
                    ],
                }
            ],
        }
    )
    assert "pollingLocations" not in payload
    assert "earlyVoteSites" not in payload
    contests, _notes = contests_from_civic(payload)
    candidate = contests[0]["candidates"][0]
    assert "party" not in candidate
    assert "incumbent" not in candidate
    assert contests[0]["official_source_url"] == "https://fictional.example/example"


def test_democracy_works_lookup_sends_the_address(tmp_path: Path, monkeypatch):
    import ballot_lookup

    init_workspace(tmp_path, "dw-demo", "household", "2026-10-20 12:00 ET")
    (tmp_path / "private" / "address.txt").write_text("PO Box 12\n", encoding="utf-8")
    captured = {}

    def fake_get_json(url, headers=None, params=None, secrets=None, timeout=30):
        captured["url"] = url
        captured["params"] = params
        captured["secrets"] = secrets
        return {"contests": [], "address": "PO Box 12", "pollingLocations": [{"line1": "1 Hall"}]}

    monkeypatch.setattr(ballot_lookup, "get_json", fake_get_json)
    monkeypatch.setenv("DEMOCRACY_WORKS_API_URL", "https://democracy.example/v1")
    monkeypatch.setenv("DEMOCRACY_WORKS_API_KEY", "test-token")
    monkeypatch.delenv("GOOGLE_CIVIC_API_KEY", raising=False)
    code = ballot_lookup.main(["--workspace", str(tmp_path)])
    assert code == 0
    assert captured["params"]["address"] == "PO Box 12"
    assert captured["url"] == "https://democracy.example/v1"
    saved = json.loads((tmp_path / "private" / "democracy-works.json").read_text(encoding="utf-8"))
    assert "address" not in saved
    assert "pollingLocations" not in saved
    assert "PO Box 12" not in (tmp_path / "private" / "democracy-works.json").read_text(encoding="utf-8")


def test_force_does_not_skip_ballot_confirmation(tmp_path: Path):
    import new_item

    init_workspace(tmp_path, "early", "household", "2026-10-20 12:00 ET")
    code = new_item.main(
        [
            "--workspace",
            str(tmp_path),
            "--id",
            "cand-early",
            "--type",
            "candidate",
            "--title",
            "Early",
            "--force",
            "--now",
            "2026-10-20 12:00 ET",
        ]
    )
    assert code == 1
    assert not (tmp_path / "items" / "cand-early" / "draft.md").exists()


def test_primary_and_local_drafts_append_to_the_candidate_template(tmp_path: Path):
    init_workspace(tmp_path, "addons", "household", "2026-10-20 12:00 ET")
    ballot = yaml.safe_load((tmp_path / "ballot.yaml").read_text(encoding="utf-8"))
    ballot["contests"] = [
        {
            "id": "race-one",
            "type": "race",
            "title": "Mayor",
            "official_source_url": "https://fictional.example/ballot",
            "candidates": [],
        }
    ]
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    assert confirm_ballot(tmp_path, "2026-10-20 12:00 ET") == []
    assert scaffold_item(tmp_path, "cand-pri", "primary", "Primary person", "2026-10-20 12:00 ET") == []
    primary = (tmp_path / "items" / "cand-pri" / "draft.md").read_text(encoding="utf-8")
    assert "## Identity" in primary and "## Primary type" in primary
    claims = yaml.safe_load((tmp_path / "items" / "cand-pri" / "claims.yaml").read_text(encoding="utf-8"))
    assert claims["item_type"] == "primary"
    assert scaffold_item(tmp_path, "cand-local", "local-office", "Local person", "2026-10-20 12:00 ET") == []
    local = (tmp_path / "items" / "cand-local" / "draft.md").read_text(encoding="utf-8")
    assert "## Identity" in local and "## What the office controls" in local


def test_legislation_arguments_have_a_length_check(tmp_path: Path):
    item = tmp_path / "items" / "bill-1"
    item.mkdir(parents=True)
    (item / "draft.md").write_text(
        "# Bill\n\n## Arguments for\n\n"
        + ("alpha " * 50)
        + "\n\n## Arguments against\n\nbeta.\n",
        encoding="utf-8",
    )
    dump_yaml(item / "claims.yaml", {"item_id": "bill-1", "item_type": "legislation", "claims": []})
    dump_yaml(tmp_path / "ballot.yaml", {"contests": []})
    errors = argument_length_errors(tmp_path)
    assert any("arguments for" in error for error in errors)
    template = (ROOT / "templates" / "legislation.md").read_text(encoding="utf-8")
    assert "## Arguments for" in template and "## Arguments against" in template


def test_refresh_resets_signoffs_and_marks_claims(tmp_path: Path):
    import refresh
    from lib.workflow import fresh_loop_state

    init_workspace(tmp_path, "refresh-demo", "household", "2026-10-20 12:00 ET")
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    state = fresh_loop_state("cand-a", "2026-10-20 12:00 ET")
    state["signoffs"]["factcheck"] = {"signed": True, "at": "2026-10-20 12:00 ET", "round": 1}
    dump_json(item / "loop-state.json", state)
    dump_yaml(item / "claims.yaml", {"item_id": "cand-a", "item_type": "candidate", "claims": [_claim()]})
    code = refresh.main(
        ["--workspace", str(tmp_path), "--today", "2026-10-20", "--now", "2026-10-20 12:00 ET", "--open-round", "--note", "New filing."]
    )
    assert code == 0
    updated = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    assert updated["signoffs"]["factcheck"]["signed"] is False
    claim = yaml.safe_load((item / "claims.yaml").read_text(encoding="utf-8"))["claims"][0]
    assert claim["corrected"] is True
    assert claim["correction_note"] == "New filing."


def test_same_day_version_snapshots_do_not_overwrite(tmp_path: Path):
    versions = tmp_path / "versions"
    first = snapshot_guide(versions, "---\nversion: v1.0\n---\n\nOld\n", "2026-10-20")
    second = snapshot_guide(versions, "---\nversion: v1.0\n---\n\nOlder\n", "2026-10-20")
    assert first.name == "guide-v1.0-2026-10-20.md"
    assert second.name == "guide-v1.0-2026-10-20-2.md"
    assert "Old" in first.read_text(encoding="utf-8")
    assert "Older" in second.read_text(encoding="utf-8")


def test_year_label_and_offline_link_check_are_part_of_the_gate(tmp_path: Path):
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    claim = _claim(text="The certificate is on file.", sources=[_source(published="2018-11-20")])
    dump_yaml(item / "claims.yaml", {"item_id": "cand-a", "item_type": "candidate", "claims": [claim]})
    (item / "draft.md").write_text("# A\n\nThe certificate is on file[^1].\n", encoding="utf-8")
    dump_yaml(tmp_path / "ballot.yaml", {"election": {"date": "2026-11-03"}, "contests": []})
    assert any("2018" in error for error in year_label_errors(tmp_path))
    errors = content_gate_errors(tmp_path, date(2026, 10, 20), include_guide=False)
    assert any("label the year" in error for error in errors)
    record = json.loads((tmp_path / "link-check.json").read_text(encoding="utf-8"))
    assert record["mode"] == "offline"
    assert record["checked"] == 1


def test_edge_banners_are_not_substrings(tmp_path: Path):
    race = tmp_path / "items" / "race-one"
    gone = tmp_path / "items" / "cand-gone"
    thin = tmp_path / "items" / "cand-thin"
    for path in (race, gone, thin):
        path.mkdir(parents=True)
    (race / "draft.md").write_text(
        "# Race\n\nThis is not an uncontested mention buried in prose.\n\n## Uncontested\n\nThe race is not uncontested.\n",
        encoding="utf-8",
    )
    (gone / "draft.md").write_text("# Gone\n\n## Identity\n\nThe candidate was withdrawn on 2026-09-01 in a sentence.\n", encoding="utf-8")
    (thin / "draft.md").write_text("# Thin\n\n## Identity\n\nLimited public record appears only after the heading.\n", encoding="utf-8")
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "contests": [
                {
                    "id": "race-one",
                    "item_id": "race-one",
                    "type": "race",
                    "candidates": [
                        {"id": "cand-only", "item_id": "cand-only"},
                        {"id": "cand-gone", "item_id": "cand-gone", "withdrawn": True},
                        {"id": "cand-thin", "item_id": "cand-thin", "limited_public_record": True, "write_in": True},
                    ],
                }
            ]
        },
    )
    errors = edge_errors(tmp_path)
    assert any("Uncontested section" in error for error in errors)
    assert any("withdrawn on" in error for error in errors)
    assert any("before the first section" in error for error in errors)
    assert any("Write-in candidates" in error for error in errors)


def test_effort_explanation_does_not_waive_a_miss(tmp_path: Path):
    ballot = {
        "contests": [
            {
                "id": "race-one",
                "type": "race",
                "item_id": "race-one",
                "candidates": [
                    {"id": "cand-a", "item_id": "cand-a"},
                    {"id": "cand-b", "item_id": "cand-b"},
                ],
            }
        ]
    }
    dump_yaml(tmp_path / "ballot.yaml", ballot)
    for name, searches in (("cand-a", 10), ("cand-b", 1)):
        item = tmp_path / "items" / name
        item.mkdir(parents=True)
        (item / "draft.md").write_text("# C\n\n## Identity\n\nNot found (searched: files).\n", encoding="utf-8")
        dump_json(
            item / "effort.json",
            {
                "item_id": name,
                "searches": searches,
                "fetches": 0,
                "minutes": 1,
                "sections": {"identity": {"searches": searches, "fetches": 0}},
                "explanation": "Ran out of time." if name == "cand-b" else "",
            },
        )
    race = tmp_path / "items" / "race-one"
    race.mkdir()
    (race / "draft.md").write_text("# Race\n\n## Contest\n\nNone.\n", encoding="utf-8")
    errors = symmetry_errors(tmp_path)
    assert any("cand-b: effort" in error for error in errors)
    assert any("section 'identity'" in error for error in errors)
    assert any("missing 'comparison'" in error for error in errors)


def test_privacy_patterns_and_link_local_fetches():
    assert looks_like_street_address("PO Box 44")
    assert looks_like_street_address("Twelve Oak Street")
    assert unsafe_fetch_target("http://127.0.0.1/secret")
    assert unsafe_fetch_target("http://169.254.169.254/latest")
    assert unsafe_fetch_target("http://localhost/admin")
    assert unsafe_fetch_target("https://fictional.example/doc") is None
    from lib.archive import http_fetch

    try:
        http_fetch("http://127.0.0.1/secret")
    except RuntimeError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("link-local fetch was allowed")


def test_environment_rating_is_quoted_and_readability_uses_a_relative_path(tmp_path: Path):
    (tmp_path / "env.md").write_text("# Environment rating\n\n- Rating: **Reduced**\n", encoding="utf-8")
    assert environment_rating_sentence(tmp_path) == "Environment rating: Reduced."
    bare = tmp_path / "plain"
    bare.mkdir()
    (bare / "env.md").write_text("This fixture does not claim a live machine rating.\n", encoding="utf-8")
    assert "not recorded" in environment_rating_sentence(bare)
    item = tmp_path / "items" / "cand-a"
    item.mkdir(parents=True)
    hard = "The extraordinarily complicated municipal redistricting recommendation nevertheless remained controversial. "
    (item / "draft.md").write_text("<!-- summary -->\n\n" + hard * 8, encoding="utf-8")
    from lib.quality import readability_errors

    errors = readability_errors(tmp_path)
    assert errors
    assert errors[0].startswith("items/cand-a/draft.md")


def test_relative_workspace_build_finds_the_guide():
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--workspace", "examples/sample-election"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Built" in result.stdout


def test_bootstrap_help_says_minimal_skips_ffmpeg():
    result = subprocess.run(["./bootstrap.sh", "--help"], cwd=ROOT, capture_output=True, text=True, check=False)
    assert "ffmpeg" in result.stdout
    assert "--minimal" in result.stdout
