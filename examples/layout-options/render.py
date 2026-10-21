#!/usr/bin/env python3
"""Render the three Cedar Hollow layout themes as one three-page PDF.

Each page is the same fictional contest: a running header, a heading,
a comparison table, candidate nameplates, and a yes/no measure pair.
Sample text only. No requester address.

    python3 examples/layout-options/render.py [--out DIR]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES = (
    ("charter", "Option 1 · Charter"),
    ("folio", "Option 2 · Folio"),
)

BODY = """
<p class="option-label">{label}</p>
<h1 class="ballot-group">Races</h1>
<h2 class="contest-title">Mayor of Cedar Hollow</h2>
<p class="fiction-flag">Fictional example. Not an official ballot.</p>
<div class="summary-box">
  <p>Two people are running for mayor of Cedar Hollow. Avery Quinn is the current mayor. This guide does not rank candidates or recommend a vote.</p>
</div>
<div class="candidate-index">
  <div class="nameplate">
    <h3 class="candidate-name" id="candidate-cand-quinn">Avery Quinn</h3>
    <p>Incumbent, nonpartisan</p>
  </div>
  <div class="nameplate">
    <h3 class="candidate-name" id="candidate-cand-okonkwo">Blake Okonkwo</h3>
    <p>Challenger, nonpartisan</p>
  </div>
</div>
<h3>At a glance</h3>
<div class="comparison">
  <table>
    <thead>
      <tr>
        <th scope="col">Topic</th>
        <th scope="col">Avery Quinn</th>
        <th scope="col">Blake Okonkwo</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Ballot status</td>
        <td>Nonpartisan incumbent</td>
        <td>Nonpartisan challenger</td>
      </tr>
      <tr>
        <td>Occupation</td>
        <td>Classroom teacher, then council</td>
        <td>Parks crew leader</td>
      </tr>
      <tr>
        <td>Receipts</td>
        <td>48,200 dollars</td>
        <td>30,100 dollars</td>
      </tr>
      <tr>
        <td>Cash on hand</td>
        <td>Reported on the October filing</td>
        <td class="not-found">Not found (searched: cash on hand).</td>
      </tr>
    </tbody>
  </table>
</div>
<p class="not-found">Not found (searched: years in elected office).</p>
<h3 class="measure-title">Measure H, Cedar Hollow parks levy</h3>
<div class="vote-pair">
  <div class="vote-box">
    <h4>A YES vote means</h4>
    <p>A yes vote replaces the expiring parks levy at the same rate.</p>
  </div>
  <div class="vote-box">
    <h4>A NO vote means</h4>
    <p>A no vote lets the current parks levy expire after the 2026 tax year.</p>
  </div>
</div>
"""


def specimen_html(theme: str, label: str) -> str:
    guide = ROOT / "assets" / "guide.css"
    theme_css = ROOT / "assets" / "themes" / f"{theme}.css"
    specimen = ROOT / "examples" / "layout-options" / "specimen.css"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{label}</title>
  <link rel="stylesheet" href="{guide}" />
  <link rel="stylesheet" href="{theme_css}" />
  <link rel="stylesheet" href="{specimen}" />
</head>
<body>
  <a class="runhead" href="#your-ballot-at-a-glance" aria-label="Back to the ballot at a glance">&#8203;</a>
  <main id="content">
{BODY.format(label=label)}
  </main>
</body>
</html>
"""


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed").strip())


def render(out_dir: Path) -> Path:
    """Write cedar-hollow-layout-options.pdf and one PNG per page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    for theme, label in THEMES:
        html = out_dir / f"{theme}.html"
        pdf = out_dir / f"{theme}.pdf"
        html.write_text(specimen_html(theme, label), encoding="utf-8")
        _run(["weasyprint", str(html), str(pdf)])
        info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
        count = next(int(line.split()[1]) for line in info.splitlines() if line.startswith("Pages:"))
        if count != 1:
            raise RuntimeError(f"{theme} rendered {count} pages; the specimen must be one page")
        pages.append(pdf)
    merged = out_dir / "cedar-hollow-layout-options.pdf"
    _run(["pdfunite", *[str(path) for path in pages], str(merged)])
    prefix = out_dir / "page"
    _run(["pdftoppm", "-png", "-r", "150", str(merged), str(prefix)])
    names = (
        "cedar-hollow-layout-option-1-charter.png",
        "cedar-hollow-layout-option-2-folio.png",
    )
    for index, name in enumerate(names, start=1):
        source = out_dir / f"page-{index}.png"
        if not source.exists():
            raise RuntimeError(f"missing rendered page image {source.name}")
        source.replace(out_dir / name)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the three layout theme pages.")
    parser.add_argument("--out", type=Path, default=Path("/opt/cursor/artifacts"))
    args = parser.parse_args(argv)
    pdf = render(args.out)
    print(pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
