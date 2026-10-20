#!/usr/bin/env python3
"""Report Full / Reduced / Minimal tooling. Uses only the standard library."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KEY_NAMES = (
    "OPENFEC_API_KEY",
    "GOOGLE_CIVIC_API_KEY",
    "DEMOCRACY_WORKS_API_KEY",
    "DEMOCRACY_WORKS_API_URL",
    "OPENSTATES_API_KEY",
    "CONGRESS_API_KEY",
    "LEGISCAN_API_KEY",
)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def python_ok() -> tuple[bool, str]:
    version = sys.version_info
    if version >= (3, 10):
        return True, f"{version.major}.{version.minor}.{version.micro}"
    return False, f"{version.major}.{version.minor}.{version.micro}"


def command_ok(name: str, root: Path | None = None) -> bool:
    if shutil.which(name) is not None:
        return True
    if root is not None and (root / ".venv" / "bin" / name).is_file():
        return True
    return False


def module_ok(root: Path, module: str) -> bool:
    venv = root / ".venv" / "bin" / "python"
    python = str(venv) if venv.exists() else sys.executable
    result = subprocess.run([python, "-c", f"import {module}"], capture_output=True)
    return result.returncode == 0


def browser_ok() -> bool:
    return any(command_ok(name) for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"))


def deps_ok(root: Path) -> tuple[bool, str]:
    venv = root / ".venv" / "bin" / "python"
    if not venv.exists():
        return False, "missing .venv"
    result = subprocess.run(
        [str(venv), "-c", "import yaml, jsonschema, requests, pytest"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "import failed").strip().splitlines()
        return False, detail[-1] if detail else "import failed"
    return True, "pyyaml, jsonschema, requests, pytest"


def collect(root: Path) -> dict:
    py_ok, py_version = python_ok()
    pdf = command_ok("weasyprint") or command_ok("wkhtmltopdf")
    tools = {
        "bash": command_ok("bash"),
        "git": command_ok("git"),
        "python3": py_ok,
        "curl": command_ok("curl"),
        "jq": command_ok("jq"),
        "pandoc": command_ok("pandoc"),
        "pdftotext": command_ok("pdftotext"),
        "pdf_engine": pdf,
    }
    deps, deps_detail = deps_ok(root)
    tools["python_deps"] = deps
    optional = {
        "ffmpeg": command_ok("ffmpeg", root),
        "yt-dlp": command_ok("yt-dlp", root),
        "whisper": command_ok("whisper", root),
        "faster-whisper": module_ok(root, "faster_whisper"),
        "monolith": command_ok("monolith", root),
        "headless_browser": browser_ok(),
        "pa11y": command_ok("pa11y", root),
        "axe": command_ok("axe", root),
    }
    env = parse_env(root / ".env")
    keys = {name: bool(env.get(name, "").strip()) for name in KEY_NAMES}
    return {
        "python_version": py_version,
        "tools": tools,
        "deps_detail": deps_detail,
        "optional": optional,
        "keys": keys,
        "pdf_name": "weasyprint" if command_ok("weasyprint") else ("wkhtmltopdf" if command_ok("wkhtmltopdf") else "none"),
        "gitignore_ok": _gitignore_ok(root),
    }


def _gitignore_ok(root: Path) -> bool:
    path = root / ".gitignore"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return "output/" in text and "private/" in text


def rate(snapshot: dict) -> str:
    tools = snapshot["tools"]
    base = all(tools.get(name) for name in ("bash", "git", "python3", "curl"))
    if not base:
        return "Minimal"
    build = all(tools.get(name) for name in ("jq", "pandoc", "pdftotext", "pdf_engine", "python_deps"))
    if not build or not snapshot.get("gitignore_ok"):
        return "Reduced"
    return "Full"


def render(root: Path, snapshot: dict) -> str:
    rating = rate(snapshot)
    keys = snapshot["keys"]
    set_count = sum(1 for on in keys.values() if on)
    if set_count == 0:
        api_line = "none"
    elif set_count == len(keys):
        api_line = "ready"
    else:
        api_line = "partial"
    clock = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    lines = [
        "# Environment rating",
        "",
        f"- Rating: **{rating}**",
        f"- API access: **{api_line}**",
        f"- Python: {snapshot['python_version']}",
        f"- PDF engine: {snapshot['pdf_name']}",
        f"- Sandbox capabilities: **{sandbox_capability(snapshot['optional'])}**",
        f"- Whisper model: {configured_whisper_model(root)}",
        f"- Checked: {clock}",
        "",
        "The headline rating is local tooling. API keys are optional and disclosed on their own line. Missing keys do not by themselves lower a Full tooling rating.",
        "",
        "Sandbox capabilities are yt-dlp with ffmpeg, full-page capture, and the external accessibility check. `./bootstrap.sh` installs them. `./bootstrap.sh --minimal` skips ffmpeg, yt-dlp, monolith, Chromium, and pa11y. Whisper transcription is opt-in (`--with-transcription` or `whisper_transcription: true` in config.yaml). A failed install does not abort bootstrap; that capability stays reduced and the headline rating is unchanged.",
        "",
        "## Tools",
        "",
        "| Tool | Status |",
        "| --- | --- |",
    ]
    labels = {
        "bash": "bash",
        "git": "git",
        "python3": "python3 >= 3.10",
        "curl": "curl",
        "jq": "jq",
        "pandoc": "pandoc",
        "pdftotext": "poppler-utils (pdftotext)",
        "pdf_engine": "PDF engine",
        "python_deps": "Python packages in .venv",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | {'ok' if snapshot['tools'].get(key) else 'missing'} |")
    lines.append(f"| dependency detail | {snapshot['deps_detail']} |")
    lines.extend(["", "## Optional tools", ""])
    for name, ok in snapshot["optional"].items():
        lines.append(f"- {name}: {'ok' if ok else 'missing'}")
    lines.extend(["", "## Optional capabilities", ""])
    lines.extend(capability_lines(snapshot["optional"]))
    lines.append("")
    lines.append(
        "yt-dlp, monolith, a headless browser, and pa11y install with ./bootstrap.sh. "
        "./bootstrap.sh --minimal skips them. Whisper installs only with --with-transcription "
        "or whisper_transcription: true. None of these change the Full / Reduced / Minimal rating."
    )
    lines.extend(["", "## API keys", "", "Values are never printed.", ""])
    for name, present in keys.items():
        lines.append(f"- {name}: {'set' if present else 'unset'}")
    lines.extend(["", "## Gaps", ""])
    gaps = []
    if rating != "Full":
        for key, label in labels.items():
            if not snapshot["tools"].get(key):
                gaps.append(f"{label} is missing")
        if not snapshot.get("gitignore_ok"):
            gaps.append(".gitignore does not list output/ and private/")
    for name, ok in snapshot["optional"].items():
        if ok:
            continue
        if name == "whisper" and snapshot["optional"].get("faster-whisper"):
            continue
        if name == "faster-whisper" and snapshot["optional"].get("whisper"):
            continue
        if name == "axe" and snapshot["optional"].get("pa11y"):
            continue
        if name == "pa11y" and snapshot["optional"].get("axe"):
            continue
        gaps.append(f"{name} is not installed")
    for name, present in keys.items():
        if not present:
            gaps.append(f"{name} is unset")
    if not gaps:
        lines.append("- None.")
    else:
        for gap in gaps:
            lines.append(f"- {gap}")
    lines.extend(
        [
            "",
            "## What a report will lack if you continue",
            "",
        ]
    )
    if rating == "Minimal":
        lines.append("- The machine cannot run the research scripts reliably. Install Python 3.10+, git, bash, and curl before a session.")
    elif rating == "Reduced":
        lines.append("- Markdown drafts can still be written. HTML or PDF, PDF text extraction, or schema checks may be unavailable until the missing tools are installed.")
    else:
        lines.append("- Local build tools are present.")
    if api_line != "ready":
        lines.append("- Finance, bill, and ballot API scripts will skip live calls for every unset key. The agent must read official filings and sample ballots in the browser and cite those pages.")
    caps = {line.split(":")[0].lstrip("- ").strip(): line.split(":", 1)[1].strip() for line in capability_lines(snapshot["optional"])}
    if caps.get("transcripts") != "ready":
        lines.append(
            "- Whisper transcription is opt-in and not installed, so that capability is reduced. "
            "Run ./bootstrap.sh --with-transcription, or set whisper_transcription: true and re-run bootstrap. "
            "A failed install does not stop bootstrap."
        )
    archive_state = caps.get("archive capture", "not installed")
    if archive_state == "not installed":
        lines.append(
            "- Full-page monolith and screenshot capture are unavailable, so that capability is reduced. "
            "HTTP body and PDF print still run when offline_archive is true."
        )
    elif archive_state.startswith("partial"):
        lines.append("- Offline archive capture is only partly installed, so that capability is reduced. HTTP body and PDF print still run.")
    if caps.get("accessibility") == "built-in only":
        lines.append(
            "- Accessibility is reduced to the built-in HTML checks. "
            "pa11y installs with ./bootstrap.sh unless you passed --minimal."
        )
    lines.append("")
    return "\n".join(lines)


def configured_whisper_model(root: Path) -> str:
    path = root / "config.yaml"
    if not path.exists():
        return "base"
    match = re.search(
        r"(?m)^whisper_model:\s*['\"]?([A-Za-z0-9][A-Za-z0-9._-]{0,40})",
        path.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else "base"


def sandbox_capability(optional: dict) -> str:
    """Defaults only. Whisper is opt-in and does not change this line."""
    values = {line.split(":")[0].lstrip("- ").strip(): line.split(":", 1)[1].strip() for line in capability_lines(optional)}
    downloads = bool(optional.get("yt-dlp") and optional.get("ffmpeg"))
    archive_ready = values.get("archive capture") == "ready"
    accessibility = values.get("accessibility") in {"pa11y", "axe"}
    if downloads and archive_ready and accessibility:
        return "ready"
    return "reduced"


def capability_lines(optional: dict) -> list[str]:
    transcripts = bool(
        optional.get("yt-dlp") and optional.get("ffmpeg") and (optional.get("whisper") or optional.get("faster-whisper"))
    )
    monolith = bool(optional.get("monolith"))
    browser = bool(optional.get("headless_browser"))
    if monolith and browser:
        archive = "ready"
    elif monolith or browser:
        present = []
        if monolith:
            present.append("monolith")
        if browser:
            present.append("screenshot")
        archive = "partial (" + ", ".join(present) + ")"
    else:
        archive = "not installed"
    if optional.get("pa11y"):
        accessibility = "pa11y"
    elif optional.get("axe"):
        accessibility = "axe"
    else:
        accessibility = "built-in only"
    return [
        f"- transcripts: {'ready' if transcripts else 'opt-in, not installed'}",
        f"- archive capture: {archive}",
        f"- accessibility: {accessibility}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the environment rating.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--mode", choices=["check", "install"], default="check")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    snapshot = collect(root)
    text = render(root, snapshot)
    rating = rate(snapshot)
    out = root / "output" / "env.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    if args.mode == "check":
        return 0 if rating == "Full" else 2
    return 0 if rating in {"Full", "Reduced"} else 2


if __name__ == "__main__":
    sys.exit(main())
