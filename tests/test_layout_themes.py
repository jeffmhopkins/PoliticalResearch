"""Docket Color is the default print sheet. Grayscale Docket, Charter, and Folio are optional."""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
THEMES = ("charter", "folio")


def _luminance(hex_color: str) -> float:
    value = hex_color.removeprefix("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _root_colors(css: str) -> dict[str, str]:
    block = re.search(r":root\s*\{([^}]+)\}", css)
    assert block, "theme is missing :root"
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block.group(1)))


def test_default_build_loads_docket_color():
    build = (ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    guide = (ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
    assert "PANDOC_CSS=(--css guide.css)" in build
    assert '""|docket-color) THEME=docket-color' in build
    assert '[[ "$THEME" != "docket" ]]' in build
    assert "docket|charter|folio" in build
    assert "assets/themes" not in guide
    assert "#1D5C63" not in guide
    assert "#161616" in guide
    assert "h2.contest-title::before" not in guide
    assert "IBM Plex Sans" in guide
    assert "--band:" in guide
    assert "content: counter(page)" in guide
    assert "element(runhead)" not in guide


def test_theme_faces_are_vendored_under_the_ofl():
    notice = (ROOT / "assets" / "fonts" / "OFL.txt").read_text(encoding="utf-8")
    for family in ("Source Serif", "Public Sans", "Fraunces", "Source Sans", "IBM Plex"):
        assert family in notice
    for theme in THEMES:
        css = (ROOT / "assets" / "themes" / f"{theme}.css").read_text(encoding="utf-8")
        faces = re.findall(r'url\("\.\./fonts/([^"]+)"\)', css)
        assert faces, theme
        for filename in faces:
            assert (ROOT / "assets" / "fonts" / filename).is_file(), filename
        assert "font-weight: 650" not in css
        assert not re.search(r"(?m)^\s*gap\s*:", css)


def _ttf_table(data: bytes, tag: bytes) -> bytes:
    count = int.from_bytes(data[4:6], "big")
    for index in range(count):
        start = 12 + index * 16
        if data[start : start + 4] == tag:
            offset = int.from_bytes(data[start + 8 : start + 12], "big")
            length = int.from_bytes(data[start + 12 : start + 16], "big")
            return data[offset : offset + length]
    raise AssertionError(tag)


def _ttf_name(data: bytes, name_id: int) -> str:
    table = _ttf_table(data, b"name")
    count = int.from_bytes(table[2:4], "big")
    string_offset = int.from_bytes(table[4:6], "big")
    fallback = ""
    for index in range(count):
        platform, encoding, _language, nid, length, offset = struct.unpack(
            ">HHHHHH", table[6 + index * 12 : 18 + index * 12]
        )
        if nid != name_id:
            continue
        raw = table[string_offset + offset : string_offset + offset + length]
        text = raw.decode("utf-16-be") if platform == 3 else raw.decode("latin-1", "replace")
        if platform == 3 and encoding in (1, 10):
            return text
        fallback = text
    return fallback


def _ttf_weight(data: bytes) -> int:
    return int.from_bytes(_ttf_table(data, b"OS/2")[4:6], "big")


def test_plex_sans_and_fraunces_names_match_the_cut():
    """Official Plex weights keep their own names, and Fraunces is the display cut."""
    fonts = ROOT / "assets" / "fonts"
    medium = (fonts / "IBMPlexSans-Medium.ttf").read_bytes()
    semibold = (fonts / "IBMPlexSans-Semibold.ttf").read_bytes()
    assert _ttf_name(medium, 4) == "IBM Plex Sans Medm"
    assert _ttf_name(medium, 6) == "IBMPlexSans-Medm"
    assert _ttf_name(medium, 17) == "Medium"
    assert _ttf_name(semibold, 4) == "IBM Plex Sans SmBld"
    assert _ttf_name(semibold, 6) == "IBMPlexSans-SmBld"
    assert _ttf_name(semibold, 17) == "SemiBold"
    assert _ttf_weight(medium) == 500
    assert _ttf_weight(semibold) == 600
    for blob in (medium, semibold):
        for name_id in (1, 4, 6):
            assert _ttf_name(blob, name_id) not in {"IBM Plex Sans Regular", "IBMPlexSans-Regular"}
    expected = {
        "Fraunces-Medium.ttf": (500, "Fraunces-Medium", "Fraunces 144pt Medium"),
        "Fraunces-MediumItalic.ttf": (500, "Fraunces-MediumItalic", "Fraunces 144pt Medium Italic"),
        "Fraunces-SemiBold.ttf": (600, "Fraunces-SemiBold", "Fraunces 144pt SemiBold"),
    }
    for filename, (weight, postscript, full_name) in expected.items():
        blob = (fonts / filename).read_bytes()
        full = _ttf_name(blob, 4)
        assert full == full_name
        assert "9pt" not in full
        assert _ttf_name(blob, 1) == "Fraunces"
        assert _ttf_name(blob, 6) == postscript
        assert _ttf_weight(blob) == weight


def test_themes_keep_neutral_aa_contrast_and_drop_the_stray_bar():
    for theme in THEMES:
        css = (ROOT / "assets" / "themes" / f"{theme}.css").read_text(encoding="utf-8")
        colors = _root_colors(css)
        assert _contrast(colors["ink"], colors["paper"]) >= 4.5
        assert _contrast(colors["muted"], colors["paper"]) >= 4.5
        assert _contrast(colors["rule"], colors["paper"]) >= 3.0
        if "link" in colors:
            assert _contrast(colors["link"], colors["paper"]) >= 4.5
        if "band" in colors:
            assert _contrast(colors["band-text"], colors["band"]) >= 4.5
        assert "content: none" in css
        assert "Not an official ballot" in css
        assert not re.search(r"democrat|republican|#0000ff|#ff0000|#0000ee", css, re.I)


def test_docket_color_is_the_default_and_neutral():
    """Teal is the default sheet. The grayscale base stays in guide.css."""
    build = (ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    guide = (ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
    css = (ROOT / "assets" / "themes" / "docket-color.css").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    assert "PANDOC_CSS=(--css guide.css)" in build
    assert '""|docket-color) THEME=docket-color' in build
    assert "#1D5C63" not in guide
    assert "#161616" in guide
    assert not re.search(r"(?m)^\s*gap\s*:", code)
    assert "display:grid" not in code.replace(" ", "")
    assert "display: table" not in code.lower()
    assert re.search(r"\.vote-pair\s*\{[^}]*display:\s*flex", code)
    assert "padding: 6pt" in code
    assert "padding-left: 9pt" in code
    assert "padding-right: 9pt" in code
    assert "padding-top: 4pt" in code
    assert "border-top: 1.25pt" not in code
    assert "border-bottom: 0.4pt solid #C9D3D4" in code
    assert "vote-box:first-child" not in css
    assert "Not an official ballot" in css
    assert "string(section, first)" in css
    assert "content: counter(page)" in css
    assert "print-color-adjust" in css
    assert not re.search(r"democrat|republican|#0000ff|#ff0000|#0000ee|#008000|#00ff00", css, re.I)
    allowed = {
        "#1d5c63",
        "#e8f0f0",
        "#f5f1e8",
        "#1f2328",
        "#5a6470",
        "#c9d3d4",
        "#ffffff",
    }
    used = {color.lower() for color in re.findall(r"#[0-9a-fA-F]{6}", css)}
    assert used <= allowed
    assert _contrast("#1D5C63", "#FFFFFF") >= 7.0
    assert _contrast("#1D5C63", "#E8F0F0") >= 4.5
    assert _contrast("#1F2328", "#E8F0F0") >= 4.5
    assert _contrast("#1F2328", "#F5F1E8") >= 4.5
    assert _contrast("#5A6470", "#FFFFFF") >= 4.5
    assert _luminance("#E8F0F0") >= 0.85
    assert _luminance("#F5F1E8") >= 0.85
    colors = _root_colors(css)
    assert colors["band"].lower() == "#e8f0f0"
    assert colors["band-text"].lower() == "#1d5c63"
    assert "ink" not in colors


def test_tall_card_rows_keep_their_heading_and_short_lists_stay_whole():
    from polish_html import polish_html

    css = (ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
    assert ".pair > h3.pair-label" in css
    assert "flex: 1 0 100%" in css
    assert "ul.keep-together" in css
    assert "break-inside: avoid" in css
    assert "table:has(+ h4)" in css
    assert ".bill-close" in css
    assert ".profile-pair" in css
    assert "li.keep-tail + li.keep-tail" in css
    assert "blockquote + h1.back-matter" in css
    assert "h1.sources-title + p + h2.source-group" in css
    html = """
    <h3 id="office">What does this office do?</h3>
    <p>The office runs the election.</p>
    <h3 id="legal">Any legal or ethics issues?</h3>
    <div class="pair count-many">
    <section class="card"><h3>Ada</h3><p>A long card.</p></section>
    </div>
    <h3 id="where">Where do they stand?</h3>
    <p>Candidates appear in ballot order.</p>
    <div class="pair"><section class="card"><p>Stays put.</p></section></div>
    <div class="vote-pair"><section class="vote-box"><h4>YES</h4></section></div>
    <h3 id="gaps">retention-supreme-muniz</h3>
    <ul>
    <li>factcheck signed off.</li>
    <li>sourcing signed off.</li>
    <li>neutrality signed off.</li>
    <li>privacy-legal signed off.</li>
    </ul>
    <h1 id="changelog">Changelog</h1>
    <ul>
    <li>one</li><li>two</li><li>three</li><li>four</li><li>five</li>
    <li>six</li><li>seven</li><li>eight</li><li>nine</li><li>ten</li>
    </ul>
    <h2 class="source-group">Next contest</h2>
    <h3 id="who-sponsored-it-and-who-drafted-it">Who sponsored it, and who drafted it?</h3>
    <h4 id="sponsors-and-cosponsors">Sponsors and cosponsors</h4>
    <p>The sponsor is McClure.</p>
    <h3 id="how-did-the-chambers-vote">How did the chambers vote?</h3>
    <div class="tail"><h3 id="who-is-affected">Who is affected</h3><p>Electors.</p></div>
    """
    polished = polish_html(html)
    assert '<div class="pair count-many">' in polished
    assert polished.index('id="legal"') < polished.index("A long card.")
    assert polished.index("<div class=\"pair count-many\">") < polished.index('id="legal"')
    assert 'id="office"' in polished
    assert "The office runs the election." in polished
    assert "<h3>Ada</h3>" in polished
    assert "Where do they stand?" in polished
    assert "Candidates appear in ballot order." in polished
    assert '<div class="vote-pair">' in polished
    assert "pair-label" not in polished.split("vote-pair", 1)[1]
    assert '<ul class="keep-together">' in polished
    assert polished.count("pair-label") == 1
    assert polished.count("keep-tail") == 12
    tail = polished.split("<h1 id=\"changelog\">", 1)[1]
    assert "keep-tail" not in tail.split(">two<", 1)[0]
    assert "keep-tail" in tail.split(">three<", 1)[0]
    short = """
    <section class="profile"><h2>Ada Short</h2><p>One line.</p></section>
    <section class="profile"><h2>Bo Short</h2><p>One line.</p></section>
    <p><a href="#your-ballot-at-a-glance">Back to ballot</a></p>
    <div class="sheet opener"><h2>Next</h2></div>
    """
    paired = polish_html(short)
    assert paired.count("profile-pair") == 1
    assert paired.count("Ada Short") == 1
    assert polish_html(paired).count("Ada Short") == 1
    assert '<div class="bill-close">' in polished
    assert polished.index("bill-close") < polished.index("who-sponsored-it-and-who-drafted-it")
    assert polished.index("who-is-affected") < polished.index("</div>", polished.index("bill-close") + 1)


def test_specimen_renders_one_page_per_theme(tmp_path: Path):
    if shutil.which("weasyprint") is None or shutil.which("pdftotext") is None:
        pytest.skip("weasyprint or pdftotext is not installed")
    subprocess.run(
        ["python3", str(ROOT / "examples" / "layout-options" / "render.py"), "--out", str(tmp_path)],
        check=True,
    )
    pdf = tmp_path / "cedar-hollow-layout-options.pdf"
    layout = subprocess.run(
        ["python3", str(ROOT / "scripts" / "check_pdf_layout.py"), str(pdf)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert layout.returncode == 0, layout.stderr or layout.stdout
    text = subprocess.check_output(["pdftotext", str(pdf), "-"], text=True)
    folded = text.casefold()
    assert "option 1" in folded and "charter" in folded
    assert "option 2" in folded and "folio" in folded
    assert text.count("Not an official ballot") >= 2
    assert "Avery Quinn" in text and "Blake Okonkwo" in text
    assert "A YES vote means" in text
    assert "recommend a vote" in text
    for name in (
        "cedar-hollow-layout-option-1-charter.png",
        "cedar-hollow-layout-option-2-folio.png",
    ):
        assert (tmp_path / name).stat().st_size > 1000
