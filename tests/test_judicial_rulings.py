"""Judicial retention and judicial races cite opinions or name the gap."""

from __future__ import annotations

import json
from pathlib import Path

from lib.quality import depth_record_errors
from lib.util import dump_yaml

GAP_RULINGS = "Not found (searched: majority opinions and dissents)."
GAP_JQC = "Not found (searched: Judicial Qualifications Commission)."
GAP_POLL = "Not found (searched: bar retention poll)."
THIN_GAP = "Not found (searched: the official file)."


def _source(**overrides) -> dict:
    data = {
        "url": "https://fictional.example/opinion",
        "publisher": "Example Court",
        "title": "Example v. Sample",
        "doc_type": "court opinion",
        "published": "2024-06-01",
        "retrieved": "2026-10-20 09:00 ET",
        "tier": "T1",
        "locator": "slip opinion page 4",
        "quote": "The court held the statute did not apply.",
        "confidence": "verified",
        "marker": 1,
    }
    data.update(overrides)
    return data


def _item(root: Path, item_id: str, item_type: str, draft: str, claims: list[dict]) -> None:
    item = root / "items" / item_id
    item.mkdir(parents=True, exist_ok=True)
    (item / "draft.md").write_text(draft, encoding="utf-8")
    dump_yaml(item / "claims.yaml", {"item_id": item_id, "item_type": item_type, "claims": claims})
    (item / "loop-state.json").write_text(
        json.dumps({"item_id": item_id, "status": "signed-off"}),
        encoding="utf-8",
    )


def _workspace(tmp_path: Path, contests: list[dict] | None = None) -> Path:
    root = tmp_path / "election"
    root.mkdir()
    dump_yaml(root / "ballot.yaml", {"contests": contests or [], "districts": []})
    return root


def _draft(rulings: str, discipline: str, poll: str) -> str:
    return f"""# Judge Ada Hale

## Notable rulings

{rulings}

## Discipline record

{discipline}

## Performance evaluation

{poll}
"""


def _ruling_errors(root: Path) -> list[str]:
    return [
        error
        for error in depth_record_errors(root)
        if any(
            phrase in error
            for phrase in (
                "rulings gap",
                "court decided",
                "drew attention",
                "court opinion",
                "reputable coverage",
                "discipline gap",
                "Judicial Qualifications Commission",
                "JQC complaint",
                "JQC document",
                "bar retention poll",
                "how to vote",
            )
        )
    ]


def test_a_rulings_gap_names_the_three_searches(tmp_path: Path):
    root = _workspace(tmp_path)
    _item(
        root,
        "retention-ada",
        "judicial-retention",
        _draft(THIN_GAP, THIN_GAP, THIN_GAP),
        [],
    )
    errors = _ruling_errors(root)
    assert any("majority opinions and dissents" in error for error in errors)
    assert any("Judicial Qualifications Commission" in error for error in errors)
    assert any("bar retention poll" in error for error in errors)

    _item(
        root,
        "retention-ada",
        "judicial-retention",
        _draft(GAP_RULINGS, GAP_JQC, GAP_POLL),
        [],
    )
    assert _ruling_errors(root) == []


def test_a_cited_ruling_needs_the_opinion_and_coverage(tmp_path: Path):
    root = _workspace(tmp_path)
    text = "The court held the statute did not apply, and a dissent drew attention."
    claim = {
        "id": "retention-ada.notable-rulings.001",
        "section": "notable rulings",
        "text": "The court held the statute did not apply.",
        "marker": 1,
        "sources": [_source()],
        "confidence": "verified",
    }
    _item(root, "retention-ada", "judicial-retention", _draft(text + "[^1]", GAP_JQC, GAP_POLL), [claim])
    errors = _ruling_errors(root)
    assert any("drew attention" in error for error in errors)
    assert any("reputable coverage" in error for error in errors)

    claim["text"] = text
    claim["sources"] = [
        _source(),
        _source(
            marker=2,
            url="https://fictional.example/news/opinion",
            publisher="Example News",
            title="Court splits on the statute",
            doc_type="news article",
            tier="T3",
            quote="The dissent drew attention.",
        ),
    ]
    _item(root, "retention-ada", "judicial-retention", _draft(text + "[^1]", GAP_JQC, GAP_POLL), [claim])
    assert _ruling_errors(root) == []


def test_a_complaint_is_not_written_as_a_finding(tmp_path: Path):
    root = _workspace(tmp_path)
    body = "The Judicial Qualifications Commission complaint says the judge erred[^1]."
    claim = {
        "id": "retention-ada.discipline-record.001",
        "section": "discipline record",
        "text": body,
        "marker": 1,
        "sources": [_source(doc_type="jqc complaint", title="JQC complaint", quote="A complaint was filed.")],
        "confidence": "single-source",
    }
    _item(root, "retention-ada", "judicial-retention", _draft(GAP_RULINGS, body, GAP_POLL), [claim])
    assert any("not a finding" in error for error in _ruling_errors(root))

    fixed = "The Judicial Qualifications Commission complaint is allegation only[^1]."
    claim["text"] = fixed
    _item(root, "retention-ada", "judicial-retention", _draft(GAP_RULINGS, fixed, GAP_POLL), [claim])
    assert not any("not a finding" in error for error in _ruling_errors(root))


def test_a_judicial_race_uses_the_same_step(tmp_path: Path):
    root = _workspace(
        tmp_path,
        [{"id": "race-judge", "type": "race", "level": "judicial", "candidates": [{"id": "cand-ada"}]}],
    )
    _item(root, "cand-ada", "candidate", _draft(THIN_GAP, GAP_JQC, GAP_POLL), [])
    errors = _ruling_errors(root)
    assert any("majority opinions and dissents" in error for error in errors)

    _item(root, "cand-ada", "candidate", _draft(GAP_RULINGS, GAP_JQC, GAP_POLL), [])
    assert _ruling_errors(root) == []


def test_a_nonjudicial_candidate_skips_the_rulings_step(tmp_path: Path):
    root = _workspace(tmp_path, [{"id": "race-mayor", "type": "race", "level": "county", "candidates": [{"id": "cand-ada"}]}])
    _item(root, "cand-ada", "candidate", _draft(THIN_GAP, THIN_GAP, THIN_GAP), [])
    assert _ruling_errors(root) == []
