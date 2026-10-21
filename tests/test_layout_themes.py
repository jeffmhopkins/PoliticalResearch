"""The three print themes are optional. The default guide stylesheet stays in place."""

from __future__ import annotations

import re
import shutil
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


def test_default_build_does_not_load_a_theme():
    build = (ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    guide = (ROOT / "assets" / "guide.css").read_text(encoding="utf-8")
    assert "PANDOC_CSS=(--css guide.css)" in build
    assert "charter|folio" in build
    assert "assets/themes" not in guide
    assert "h2.contest-title::before" not in guide
    assert "IBM Plex Sans" in guide
    assert "--band:" in guide
    assert "element(runhead)" in guide


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
