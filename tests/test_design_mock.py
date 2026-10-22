"""The design sample is separate from the default guide renderer."""

from __future__ import annotations

from pathlib import Path

from build_design_mock import blank_page_errors, letter_errors, privacy_errors

ROOT = Path(__file__).resolve().parents[1]


def test_sample_uses_real_research_and_keeps_the_default_sheet_alone():
    html = (ROOT / "design" / "mock" / "sample.html").read_text(encoding="utf-8")
    css = (ROOT / "design" / "mock" / "mock.css").read_text(encoding="utf-8")
    guide = (ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    assert "design/mock" not in build
    assert "mock.css" not in guide
    assert "break-before: page" in css
    assert ".sheet-first" in css
    assert html.count("data-run=") == 9
    assert "font-size: 9pt" in css
    assert "font-size: 8.5pt" not in css.split(".notes")[1]
    assert "font-size: 8pt" not in css
    assert "size: letter portrait" in css
    assert "font-size: 11pt" in css
    assert "#0000ff" not in css.casefold()
    assert "#ff0000" not in css.casefold()
    for phrase in (
        "What's on your ballot",
        "What does this office do?",
        "Where do they stand?",
        "Who is paying for their campaign?",
        "Who supports them?",
        "Any legal or ethics issues?",
        "Who is Mike Haridopolos?",
        "What is this about?",
        "What does your vote mean?",
        "Exact words on your ballot",
        "No public statement found on housing costs.",
        "No public statement found on health care costs.",
        "The rest of this ballot is not in this sample.",
        "Pay was not in the sources checked.",
        "Where do they stand? continued",
        "House bill 3838, the 2026 defense bill",
        "voted yes",
        "voted no",
        "No dated endorsement found.",
        "No public record found in the sources checked.",
        "Who is Jennifer Jenkins?",
        "Make housing more affordable",
        "$1,994,333",
        "$976,256",
        "$205,896",
        "My opponent voted no",
    ):
        assert phrase in html
    for banned in (
        "expanding access to affordable housing",
        "Qualified",
        "Single source",
        "Unconfirmed as a vote record",
        "not profiled",
        "Aye",
        "Nay",
        "$1,994,333.29",
    ):
        assert banned not in html
    assert "..." not in html
    assert "…" not in html
    assert privacy_errors(html) == []
    assert "lorem" not in html.casefold()


def test_letter_and_blank_page_checks_read_bbox_pages():
    letter = (
        '<doc><page width="612" height="792">'
        '<word xMin="72" yMin="80" xMax="140" yMax="92">Housing</word>'
        "</page></doc>"
    )
    assert letter_errors(letter) == []
    assert blank_page_errors(letter) == []
    landscape = (
        '<doc><page width="792" height="612">'
        '<word xMin="72" yMin="80" xMax="140" yMax="92">Money</word>'
        "</page></doc>"
    )
    assert letter_errors(landscape) == []
    wide = (
        '<doc><page width="500" height="700">'
        '<word xMin="72" yMin="80" xMax="140" yMax="92">Nope</word>'
        "</page></doc>"
    )
    assert letter_errors(wide)
    furniture = (
        '<doc><page width="612" height="792">'
        '<word xMin="40" yMin="20" xMax="120" yMax="30">Header</word>'
        '<word xMin="40" yMin="760" xMax="90" yMax="770">Footer</word>'
        "</page></doc>"
    )
    assert blank_page_errors(furniture)
    assert privacy_errors("precinct 122") == []
    assert privacy_errors("6070 Chapman")
