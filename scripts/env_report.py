#!/usr/bin/env python3
"""Report Full / Reduced / Minimal tooling. Uses only the standard library."""

from __future__ import annotations

import argparse
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


def command_ok(name: str) -> bool:
    return shutil.which(name) is not None


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
        "ffmpeg": command_ok("ffmpeg"),
        "yt-dlp": command_ok("yt-dlp"),
        "whisper": command_ok("whisper"),
        "monolith": command_ok("monolith"),
        "pa11y": command_ok("pa11y"),
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
        f"- Checked: {clock}",
        "",
        "The headline rating is local tooling. API keys are optional and disclosed on their own line. Missing keys do not by themselves lower a Full tooling rating.",
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
        if not ok:
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
    if not snapshot["optional"].get("yt-dlp") or not snapshot["optional"].get("ffmpeg"):
        lines.append("- Forum video transcripts are not captured automatically.")
    if not snapshot["optional"].get("monolith"):
        lines.append("- Offline page capture saves the HTTP body and, when it is HTML, a PDF print. It does not build a single-file monolith copy or a screenshot unless those tools exist.")
    lines.append("")
    return "\n".join(lines)


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
