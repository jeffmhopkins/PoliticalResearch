"""Paths, time, config, and YAML/JSON helpers."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ET = ZoneInfo("America/New_York")
RETRIEVED_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} ET$")
ITEM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CLAIM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+\.[0-9]{3}$")
FINDING_ID_RE = re.compile(r"^F-[0-9]{4}$")
CHANGE_ID_RE = re.compile(r"^CL-[0-9]{4}$")

KEY_NAMES = (
    "OPENFEC_API_KEY",
    "GOOGLE_CIVIC_API_KEY",
    "DEMOCRACY_WORKS_API_KEY",
    "DEMOCRACY_WORKS_API_URL",
    "OPENSTATES_API_KEY",
    "CONGRESS_API_KEY",
    "LEGISCAN_API_KEY",
)

STREET_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,4}\s+"
    r"(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court)\b",
    re.IGNORECASE,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def now_et(override: str | None = None) -> str:
    if override:
        text = override.strip()
        if not text.endswith("ET"):
            text = f"{text} ET"
        if not RETRIEVED_RE.match(text):
            raise ValueError(f"Clock override must look like 'YYYY-MM-DD HH:MM ET', got {override!r}")
        return text
    current = datetime.now(ET)
    return current.strftime("%Y-%m-%d %H:%M ET")


def today_from(value: str | None, clock: str | None = None):
    from datetime import date

    if value:
        return date.fromisoformat(value)
    if clock:
        return date.fromisoformat(clock[:10])
    return datetime.now(ET).date()


def load_config(root: Path | None = None) -> dict:
    path = (root or repo_root()) / "config.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml must be a mapping")
    return data


def load_yaml(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_env_file(path: Path) -> dict[str, str]:
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


def load_dotenv(root: Path | None = None) -> dict[str, str]:
    root = root or repo_root()
    file_values = parse_env_file(root / ".env")
    merged = dict(file_values)
    for name in KEY_NAMES:
        if os.environ.get(name):
            merged[name] = os.environ[name]
    return merged


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[REDACTED]")
    return cleaned


def resolve_workspace(election_id: str | None, workspace: str | None, root: Path | None = None) -> Path:
    if workspace:
        return Path(workspace).expanduser().resolve()
    if not election_id:
        raise SystemExit("Provide --election-id or --workspace.")
    return (root or repo_root()) / "output" / election_id


def iter_items(workspace: Path) -> list[Path]:
    items = workspace / "items"
    if not items.is_dir():
        return []
    return sorted(path for path in items.iterdir() if path.is_dir())


def looks_like_street_address(value: str) -> bool:
    return bool(STREET_RE.search(value or ""))


def slugify(value: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "source")[:limit].strip("-")


def norm_heading(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"^\d+\.\s*", "", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text)
