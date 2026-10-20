"""Save local copies of cited sources and write a manifest."""

from __future__ import annotations

import csv
import hashlib
import zipfile
from pathlib import Path

from lib.quality import iter_claim_sources, source_marker
from lib.util import dump_yaml, load_yaml, now_et, slugify


def archive_workspace(workspace: Path, fetch, clock: str | None = None) -> tuple[int, str]:
    intake = load_yaml(workspace / "intake.yaml") or {}
    if not isinstance(intake, dict) or intake.get("offline_archive") is not True:
        return 0, "Offline archive was not requested. Set offline_archive: true in intake.yaml to capture sources."
    clock = clock or now_et()
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
            row = {
                "n": marker,
                "slug": slug,
                "original_url": url,
                "final_url": "",
                "http_status": "",
                "sha256": "",
                "captured_at": clock,
                "bytes": 0,
                "path": "",
                "pdf_path": "",
                "screenshot_status": "skipped, no headless browser configured",
                "error": "",
            }
            try:
                status, final_url, body, content_type = fetch(url)
            except Exception as exc:  # noqa: BLE001 - capture failure is data, not a crash
                row["error"] = f"capture_failed: {exc}"
                rows.append(row)
                continue
            if status is None or body is None or status >= 400:
                row["http_status"] = "" if status is None else str(status)
                row["final_url"] = final_url or ""
                row["error"] = "capture_failed: HTTP error or empty body"
                rows.append(row)
                continue
            ext = "json" if "json" in (content_type or "") or body[:1] in (b"{", b"[") else "html"
            if "pdf" in (content_type or "") or url.lower().endswith(".pdf"):
                ext = "pdf"
            filename = f"{marker}-{slug}.{ext}"
            dest = archive_dir / filename
            dest.write_bytes(body)
            digest = hashlib.sha256(body).hexdigest()
            row.update(
                {
                    "final_url": final_url or url,
                    "http_status": str(status),
                    "sha256": digest,
                    "bytes": len(body),
                    "path": f"archive/{filename}",
                    "error": "",
                }
            )
            pdf_note = ""
            if ext == "html":
                pdf_path = archive_dir / f"{marker}-{slug}.pdf"
                wrote = _html_to_pdf(body, pdf_path)
                if wrote:
                    row["pdf_path"] = f"archive/{pdf_path.name}"
                else:
                    pdf_note = "pdf print skipped"
            source["local_copy"] = row["path"]
            changed = True
            captured += 1
            if pdf_note and not row["error"]:
                row["error"] = pdf_note
            rows.append(row)
        if changed:
            dump_yaml(claims_path, doc)
    manifest = archive_dir / "manifest.csv"
    _write_manifest(manifest, rows)
    zip_path = workspace / "final" / "guide-with-sources.zip"
    _write_zip(workspace, zip_path)
    message = f"Archived {captured} of {seen} sources. Manifest: {manifest}."
    return 0, message


def _write_manifest(path: Path, rows: list[dict]) -> None:
    fieldnames = [
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
        "screenshot_status",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _html_to_pdf(body: bytes, dest: Path) -> bool:
    import os
    import subprocess
    import tempfile

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
    import requests

    response = requests.get(url, timeout=30, headers={"User-Agent": "PoliticalResearch-archive/0.1"})
    return response.status_code, response.url, response.content, response.headers.get("Content-Type", "")
