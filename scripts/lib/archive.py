"""Save local copies of cited sources and write a manifest.

Full-page extras (monolith HTML and a headless screenshot) run only when the
caller supplies them. The HTTP body and a PDF print still run without those tools.
A failed fetch is recorded as capture_failed and, when a Wayback callable is
supplied, a fallback copy is saved.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from lib.quality import iter_claim_sources, source_marker, wayback_api_url
from lib.util import dump_yaml, load_yaml, now_et, resolve_bin, slugify, unsafe_fetch_target

MANIFEST_FIELDS = [
    "n",
    "slug",
    "original_url",
    "final_url",
    "http_status",
    "sha256",
    "captured_at",
    "bytes",
    "path",
    "pdf_path",
    "pdf_sha256",
    "monolith_path",
    "monolith_sha256",
    "screenshot_path",
    "screenshot_sha256",
    "screenshot_status",
    "wayback_url",
    "error",
]

BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


def archive_workspace(
    workspace: Path,
    fetch,
    clock: str | None = None,
    *,
    monolith=None,
    screenshot=None,
    html_to_pdf=None,
    wayback=None,
) -> tuple[int, str]:
    intake = load_yaml(workspace / "intake.yaml") or {}
    if not isinstance(intake, dict) or intake.get("offline_archive") is not True:
        return 0, "Offline archive was not requested. Set offline_archive: true in intake.yaml to capture sources."
    clock = clock or now_et()
    pdf_writer = html_to_pdf or _html_to_pdf
    archive_dir = workspace / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = 0
    captured = 0
    for item_dir in sorted((workspace / "items").glob("*")):
        claims_path = item_dir / "claims.yaml"
        doc = load_yaml(claims_path)
        if not isinstance(doc, dict):
            continue
        changed = False
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            seen += 1
            marker = source_marker(claim, source) or seen
            url = str(source.get("url") or "")
            slug = slugify(source.get("title") or url)
            row = _blank_row(marker, slug, url, clock)
            try:
                status, final_url, body, content_type = fetch(url)
            except Exception as exc:  # noqa: BLE001 - capture failure is data, not a crash
                row["error"] = f"capture_failed: {exc}"
                if _save_wayback(
                    row, source, wayback, url, archive_dir, marker, slug, monolith, screenshot, pdf_writer
                ):
                    changed = True
                    captured += 1
                rows.append(row)
                continue
            if status is None or body is None or status >= 400:
                row["http_status"] = "" if status is None else str(status)
                row["final_url"] = final_url or ""
                row["error"] = "capture_failed: HTTP error or empty body"
                if _save_wayback(
                    row, source, wayback, url, archive_dir, marker, slug, monolith, screenshot, pdf_writer
                ):
                    changed = True
                    captured += 1
                rows.append(row)
                continue
            ext = "json" if "json" in (content_type or "") or body[:1] in (b"{", b"[") else "html"
            if "pdf" in (content_type or "") or url.lower().endswith(".pdf"):
                ext = "pdf"
            filename = f"{marker}-{slug}.{ext}"
            dest = archive_dir / filename
            dest.write_bytes(body)
            digest = hashlib.sha256(body).hexdigest()
            page_url = final_url or url
            row.update(
                {
                    "final_url": page_url,
                    "http_status": str(status),
                    "sha256": digest,
                    "bytes": len(body),
                    "path": f"archive/{filename}",
                    "error": "",
                }
            )
            notes = []
            if ext == "html":
                notes.extend(_save_monolith(row, monolith, page_url, archive_dir, marker, slug))
                pdf_path = archive_dir / f"{marker}-{slug}.pdf"
                if pdf_writer(body, pdf_path) and pdf_path.exists():
                    row["pdf_path"] = f"archive/{pdf_path.name}"
                    row["pdf_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                else:
                    notes.append("pdf print skipped")
                _save_screenshot(row, screenshot, page_url, archive_dir, marker, slug)
            source["local_copy"] = row["path"]
            changed = True
            captured += 1
            if notes:
                row["error"] = "; ".join(notes)
            rows.append(row)
        if changed:
            dump_yaml(claims_path, doc)
    manifest = archive_dir / "manifest.csv"
    _write_manifest(manifest, rows)
    zip_path = workspace / "final" / "guide-with-sources.zip"
    _write_zip(workspace, zip_path)
    message = f"Archived {captured} of {seen} sources. Manifest: {manifest}."
    return 0, message


def find_browser() -> str | None:
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def live_monolith(url: str) -> bytes | None:
    reason = unsafe_fetch_target(url)
    if reason:
        raise RuntimeError(f"Refusing fetch: {reason}")
    binary = resolve_bin("monolith")
    if not binary:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    dest = handle.name
    handle.close()
    try:
        result = subprocess.run(
            [binary, "-o", dest, url],
            capture_output=True,
            timeout=90,
        )
        if result.returncode != 0:
            detail = (result.stderr or b"").decode()[:300] or "monolith failed"
            raise RuntimeError(detail)
        data = Path(dest).read_bytes()
        return data or None
    finally:
        try:
            os.unlink(dest)
        except OSError:
            pass


def live_screenshot(url: str) -> bytes | None:
    reason = unsafe_fetch_target(url)
    if reason:
        raise RuntimeError(f"Refusing fetch: {reason}")
    browser = find_browser()
    if not browser:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "page.png"
        result = subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--window-size=1280,1600",
                f"--screenshot={dest}",
                url,
            ],
            capture_output=True,
            timeout=90,
            cwd=tmp,
        )
        if not dest.exists():
            fallback = Path(tmp) / "screenshot.png"
            if fallback.exists():
                dest = fallback
        if not dest.exists() or dest.stat().st_size == 0:
            if result.returncode != 0:
                detail = (result.stderr or b"").decode()[:300] or "screenshot failed"
                raise RuntimeError(detail)
            return None
        return dest.read_bytes()


def live_wayback(url: str):
    api = wayback_api_url(url)
    try:
        with urllib.request.urlopen(api, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    snapshot = ((payload.get("archived_snapshots") or {}).get("closest") or {})
    if not snapshot or not snapshot.get("available"):
        return None
    wayback_url = str(snapshot.get("url") or "")
    if not wayback_url:
        return None
    try:
        request = urllib.request.Request(wayback_url, headers={"User-Agent": "PoliticalResearch-archive/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except Exception:
        return None
    if not body:
        return None
    return wayback_url, body


def _blank_row(marker, slug, url: str, clock: str) -> dict:
    row = {key: "" for key in MANIFEST_FIELDS}
    row.update(
        {
            "n": marker,
            "slug": slug,
            "original_url": url,
            "captured_at": clock,
            "bytes": 0,
            "screenshot_status": "skipped, no headless browser configured",
        }
    )
    return row


def _save_monolith(row, monolith, url: str, archive_dir: Path, marker, slug) -> list[str]:
    if monolith is None:
        return []
    try:
        body = monolith(url)
    except Exception as exc:  # noqa: BLE001
        return [f"monolith failed: {exc}"]
    if not body:
        return ["monolith skipped"]
    filename = f"{marker}-{slug}.monolith.html"
    dest = archive_dir / filename
    dest.write_bytes(body)
    row["monolith_path"] = f"archive/{filename}"
    row["monolith_sha256"] = hashlib.sha256(body).hexdigest()
    return []


def _save_screenshot(row, screenshot, url: str, archive_dir: Path, marker, slug) -> None:
    if screenshot is None:
        row["screenshot_status"] = "skipped, no headless browser configured"
        return
    try:
        body = screenshot(url)
    except Exception as exc:  # noqa: BLE001
        row["screenshot_status"] = f"failed: {exc}"
        return
    if not body:
        row["screenshot_status"] = "skipped, screenshot returned nothing"
        return
    filename = f"{marker}-{slug}.png"
    dest = archive_dir / filename
    dest.write_bytes(body)
    row["screenshot_path"] = f"archive/{filename}"
    row["screenshot_sha256"] = hashlib.sha256(body).hexdigest()
    row["screenshot_status"] = "captured"


def _save_wayback(row, source, wayback, url: str, archive_dir: Path, marker, slug, monolith, screenshot, pdf_writer) -> bool:
    if wayback is None or not url:
        return False
    try:
        found = wayback(url)
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{row['error']}; wayback failed: {exc}"
        return False
    if not found:
        return False
    wayback_url, body = found
    row["wayback_url"] = wayback_url or ""
    if not body:
        return False
    filename = f"{marker}-{slug}.wayback.html"
    dest = archive_dir / filename
    dest.write_bytes(body)
    row["sha256"] = hashlib.sha256(body).hexdigest()
    row["bytes"] = len(body)
    row["path"] = f"archive/{filename}"
    source["local_copy"] = row["path"]
    if wayback_url and not source.get("archive_url"):
        source["archive_url"] = wayback_url
    page_url = wayback_url or url
    notes = _save_monolith(row, monolith, page_url, archive_dir, marker, slug)
    pdf_path = archive_dir / f"{marker}-{slug}.pdf"
    if pdf_writer(body, pdf_path) and pdf_path.exists():
        row["pdf_path"] = f"archive/{pdf_path.name}"
        row["pdf_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    else:
        notes.append("pdf print skipped")
    _save_screenshot(row, screenshot, page_url, archive_dir, marker, slug)
    if notes:
        row["error"] = f"{row['error']}; " + "; ".join(notes)
    return True


def _write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in MANIFEST_FIELDS})


def _html_to_pdf(body: bytes, dest: Path) -> bool:
    handle = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    try:
        handle.write(body)
        handle.close()
        result = subprocess.run(["weasyprint", handle.name, str(dest)], capture_output=True)
    except FileNotFoundError:
        return False
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    return result.returncode == 0 and dest.exists()


def _write_zip(workspace: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        final = workspace / "final"
        for path in final.glob("guide*.md"):
            bundle.write(path, path.name)
        for path in final.glob("guide*.html"):
            bundle.write(path, path.name)
        for path in final.glob("guide*.pdf"):
            bundle.write(path, path.name)
        archive = workspace / "archive"
        if archive.is_dir():
            for path in sorted(archive.rglob("*")):
                if path.is_file():
                    bundle.write(path, str(path.relative_to(workspace)))


def http_fetch(url: str):
    from lib.util import safe_request

    response = safe_request(
        "GET",
        url,
        timeout=30,
        headers={"User-Agent": "PoliticalResearch-archive/0.1"},
    )
    return response.status_code, response.url, response.content, response.headers.get("Content-Type", "")
