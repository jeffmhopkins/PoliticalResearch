"""Paths, time, config, and YAML/JSON helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
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

_STREET_SUFFIX = (
    r"(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court|pl|place|pkwy|parkway)"
)
_SPELLED_NUMBER = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
STREET_RE = re.compile(
    rf"(?:"
    rf"\b\d{{1,6}}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){{0,4}}\s+{_STREET_SUFFIX}\b"
    rf"|"
    rf"\b{_SPELLED_NUMBER}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){{0,4}}\s+{_STREET_SUFFIX}\b"
    rf"|"
    rf"\b(?:P\.?\s*O\.?\s*Box|Post\s+Office\s+Box)\s+\d+\b"
    rf")",
    re.IGNORECASE,
)
# "circuit court" is a court, not a road named Court. "100 Oak Court" still matches.
_COURT_STREET_RE = re.compile(
    r"\b(?:supreme|district|circuit|county|appeals|appeal|trial|drug)\s+courts?\b",
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


def coerce_yaml_dates(value):
    """Turn YAML date objects into YYYY-MM-DD strings before schema checks."""
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: coerce_yaml_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [coerce_yaml_dates(item) for item in value]
    return value


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


def street_address_spans(value: str) -> list[str]:
    """Street-address hits. A court name such as Supreme Court is not one."""
    found = []
    for match in STREET_RE.finditer(value or ""):
        chunk = match.group(0)
        if _COURT_STREET_RE.search(chunk):
            continue
        found.append(chunk)
    return found


def looks_like_street_address(value: str) -> bool:
    return bool(street_address_spans(value))


def _blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    # is_global is true for multicast on this Python, so test multicast on its own.
    # is_private also misses shared address space (100.64.0.0/10).
    if address.is_multicast or address.is_reserved or address.is_unspecified or address.is_loopback:
        return True
    return not address.is_global


def _parse_ipv4_literal(host: str) -> ipaddress.IPv4Address | None:
    """Accept short, hex, decimal, and octal IPv4 forms such as 127.1 and 0x7f000001."""
    text = host.strip().lower()
    if re.fullmatch(r"0x[0-9a-f]+", text) or re.fullmatch(r"\d+", text):
        try:
            if text.startswith("0x"):
                number = int(text, 16)
            elif text.startswith("0") and len(text) > 1:
                number = int(text, 8)
            else:
                number = int(text, 10)
        except ValueError:
            return None
        if 0 <= number <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(number)
        return None
    parts = text.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values: list[int] = []
    for part in parts:
        if not re.fullmatch(r"(?:0x[0-9a-f]+|\d+)", part):
            return None
        try:
            if part.startswith("0x"):
                values.append(int(part, 16))
            elif len(part) > 1 and part.startswith("0"):
                values.append(int(part, 8))
            else:
                values.append(int(part, 10))
        except ValueError:
            return None
    widths = {1: [32], 2: [8, 24], 3: [8, 8, 16], 4: [8, 8, 8, 8]}[len(values)]
    number = 0
    for chunk, width in zip(values, widths):
        if chunk < 0 or chunk >= 2**width:
            return None
        number = (number << width) | chunk
    return ipaddress.IPv4Address(number)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if ":" in host:
        return None
    return _parse_ipv4_literal(host)


def _resolved_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    previous = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(3)
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return []
    finally:
        socket.setdefaulttimeout(previous)
    found: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            found.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    return found


def unsafe_fetch_target(url: str) -> str | None:
    """Return a reason when a URL must not be fetched. None means the target is allowed."""
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return f"scheme {parsed.scheme or 'missing'} is not http(s)"
    raw_host = parsed.hostname or ""
    host = raw_host.lower().strip().rstrip(".")
    if not host:
        return "missing host"
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal")):
        return f"host {host} is not allowed"
    literal = _literal_ip(host)
    if literal is not None:
        if _blocked_ip(literal):
            return f"address {literal} is not allowed"
        return None
    for resolved in _resolved_ips(host):
        if _blocked_ip(resolved):
            return f"host {host} resolves to {resolved}, which is not allowed"
    return None


def safe_request(method: str, url: str, *, headers: dict | None = None, params: dict | None = None, data: str | None = None, timeout: int = 30, max_redirects: int = 5):
    """HTTP request with redirects disabled. Each hop is checked before it is requested."""
    import requests

    current = url
    extra_params = params or None
    body = data
    verb = method
    for _hop in range(max_redirects + 1):
        reason = unsafe_fetch_target(current)
        if reason:
            raise RuntimeError(f"Refusing fetch: {reason}")
        response = requests.request(
            verb,
            current,
            headers=headers or {},
            params=extra_params,
            data=body,
            timeout=timeout,
            allow_redirects=False,
        )
        extra_params = None
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("Location") or response.headers.get("location")
        if not location:
            return response
        nxt = urljoin(response.url or current, location.strip())
        reason = unsafe_fetch_target(nxt)
        if reason:
            raise RuntimeError(f"Refusing redirect: {reason}")
        if verb.upper() == "POST" and response.status_code in {301, 302, 303}:
            verb = "GET"
            body = None
        current = nxt
    raise RuntimeError("Refusing fetch: too many redirects")


def vetted_fetch_url(url: str, *, timeout: int = 20) -> str:
    """Follow redirects with a check on every hop. Subprocess tools get only this URL."""
    reason = unsafe_fetch_target(url)
    if reason:
        raise RuntimeError(f"Refusing fetch: {reason}")
    headers = {"User-Agent": "PoliticalResearch-archive/0.1"}
    response = safe_request("HEAD", url, timeout=timeout, headers=headers)
    if response.status_code in {403, 405, 501}:
        response = safe_request("GET", url, timeout=max(timeout, 30), headers=headers)
    final = str(getattr(response, "url", None) or url)
    reason = unsafe_fetch_target(final)
    if reason:
        raise RuntimeError(f"Refusing fetch: {reason}")
    return final


def resolve_bin(name: str, root: Path | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    base = root or repo_root()
    candidates = (
        base / ".venv" / "bin" / name,
        base / ".tools" / "a11y" / "node_modules" / ".bin" / name,
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def slugify(value: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "source")[:limit].strip("-")


def norm_heading(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"^\d+\.\s*", "", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text)
