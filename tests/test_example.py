"""The fictional Cedar Hollow fixture and the HTML/PDF build."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from lib.quality import citation_errors, edge_errors, readability_errors, symmetry_errors
from lib.util import repo_root
from lib.workflow import assemble_guide, structural_workspace_errors

ROOT = repo_root()
EXAMPLE = ROOT / "examples" / "sample-election"


def test_fiction_fixture_passes_the_assembly_gate():
    assert EXAMPLE.joinpath("final", "guide.md").exists()
    guide = EXAMPLE.joinpath("final", "guide.md").read_text(encoding="utf-8")
    assert "FICTIONAL" in guide
    template = (ROOT / "assets" / "guide.html.tmpl").read_text(encoding="utf-8")
    assert "Not an official ballot" in template
    assert "Avery Quinn" in guide and "Blake Okonkwo" in guide
    assert "Disputed" in guide or "disputed" in guide
    errors = structural_workspace_errors(EXAMPLE)
    assert errors == [], errors
    from datetime import date

    from lib.quality import stale_errors
    from lib.workflow import gate_errors

    errors = gate_errors(EXAMPLE)
    errors.extend(citation_errors(EXAMPLE, guide=True))
    errors.extend(symmetry_errors(EXAMPLE))
    errors.extend(edge_errors(EXAMPLE))
    errors.extend(readability_errors(EXAMPLE))
    errors.extend(stale_errors(EXAMPLE, date(2026, 10, 20)))
    assert errors == [], errors


def test_assemble_is_deterministic(tmp_path: Path):
    copy = tmp_path / "sample"
    shutil.copytree(EXAMPLE, copy)
    original = (copy / "final" / "guide.md").read_text(encoding="utf-8")
    assert assemble_guide(copy, "2026-10-20") == []
    assert (copy / "final" / "guide.md").read_text(encoding="utf-8") == original


def test_edge_case_banner_is_required(tmp_path: Path):
    from lib.util import dump_yaml

    item = tmp_path / "items" / "cand-gone"
    item.mkdir(parents=True)
    (item / "draft.md").write_text("# Gone\n\n## Identity\n\nStill listed.\n", encoding="utf-8")
    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "contests": [
                {
                    "id": "race-one",
                    "type": "race",
                    "candidates": [
                        {"id": "cand-gone", "name": "Gone Example", "withdrawn": True},
                    ],
                }
            ]
        },
    )
    errors = edge_errors(tmp_path)
    assert any("withdrawn on" in error for error in errors)


def test_build_writes_html_and_pdf(tmp_path: Path):
    copy = tmp_path / "sample"
    shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("guide.html", "guide.pdf", "guide.css"))
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--workspace", str(copy)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    html = (copy / "final" / "guide.html").read_text(encoding="utf-8")
    assert "Not an official ballot" in html
    assert 'lang="en"' in html
    assert (copy / "final" / "guide.pdf").exists()
    text = subprocess.run(["pdftotext", str(copy / "final" / "guide.pdf"), "-"], capture_output=True, text=True, check=True)
    assert "Not an official ballot" in text.stdout
    assert "FICTIONAL" in text.stdout or "Fictional" in text.stdout or "fiction" in text.stdout.lower()
