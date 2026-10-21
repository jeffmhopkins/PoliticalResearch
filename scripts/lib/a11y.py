"""Built-in HTML checks plus an optional pa11y or axe run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.quality import html_a11y_errors
from lib.util import load_yaml, resolve_bin


def _which(name: str) -> str | None:
    return resolve_bin(name)


def check_html(path: Path, *, which=None, run=subprocess.run) -> tuple[int, str]:
    which = which or _which
    html = path.read_text(encoding="utf-8")
    errors = html_a11y_errors(html)
    lines = list(errors)
    code = 1 if errors else 0
    if not errors:
        lines.append("HTML accessibility checks passed.")
    external_code, external_message = external_a11y(path, which=which, run=run)
    if external_message:
        lines.append(external_message)
    if external_code != 0:
        code = 1
    return code, "\n".join(lines)


def _asked_for_external_a11y(path: Path) -> bool:
    """True when intake asked for pa11y or a screen reader. Plain language does not."""
    intake_path = path.parent.parent / "intake.yaml"
    if not intake_path.is_file():
        return False
    data = load_yaml(intake_path) or {}
    if not isinstance(data, dict):
        return False
    text = str(data.get("accessibility_needs") or "").lower()
    return "pa11y" in text or "screen reader" in text or "screen-reader" in text


def external_a11y(path: Path, *, which=None, run=subprocess.run) -> tuple[int, str]:
    which = which or _which
    pa11y = which("pa11y")
    axe = which("axe")
    if _asked_for_external_a11y(path) and not pa11y and not axe:
        return (
            1,
            "Requester asked for pa11y or a screen-reader check, and neither pa11y nor axe is installed.",
        )
    if pa11y:
        return _run_pa11y(path, run, pa11y)
    if axe:
        return _run_axe(path, run, axe)
    return 0, "pa11y and axe are not installed. Built-in HTML checks still ran."


def _run_pa11y(path: Path, run, binary: str) -> tuple[int, str]:
    result = run(
        [binary, "--runner", "htmlcs", "--reporter", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    issues = _parse_pa11y(result.stdout)
    errors = [item for item in issues if str(item.get("type") or "error").lower() == "error"]
    if errors:
        lines = [f"pa11y: {item.get('message') or item}" for item in errors[:20]]
        return 1, "\n".join(lines)
    if result.returncode != 0:
        if issues:
            return 0, "pa11y reported warnings only."
        detail = (result.stderr or result.stdout or "pa11y failed").strip()
        return 1, "pa11y failed: " + detail[:800]
    return 0, "pa11y reported no errors."


def _run_axe(path: Path, run, binary: str) -> tuple[int, str]:
    result = run(
        [binary, str(path), "--exit"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "axe reported violations").strip()
        return 1, "axe: " + detail[:800]
    return 0, "axe reported no violations."


def _parse_pa11y(stdout: str) -> list[dict]:
    text = (stdout or "").strip()
    if not text:
        return []
    start = text.find("[")
    if start == -1:
        start = text.find("{")
    if start == -1:
        return []
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        issues = payload.get("issues") or payload.get("results") or []
        return [item for item in issues if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []
