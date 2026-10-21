"""Save local copies of cited sources and write a manifest.

Full-page extras (monolith HTML and a headless screenshot) run only when the
caller supplies them. The HTTP body and a PDF print still run without those tools.
A failed fetch is recorded as capture_failed and, when a Wayback callable is
supplied, a fallback copy is saved. Each URL is captured once per run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing
import os
import pickle
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from lib.quality import iter_claim_sources, source_marker, wayback_api_url
from lib.util import dump_yaml, load_yaml, now_et, resolve_bin, safe_request, slugify, unsafe_fetch_target, vetted_fetch_url

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

# Prefer a real browser binary. /usr/local/bin/google-chrome on the cloud VM is a
# wrapper that forces one shared profile and never finishes --screenshot.
BROWSERS = (
    "/usr/bin/google-chrome-stable",
    "/opt/google/chrome/chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "google-chrome",
)
PDF_TIMEOUT_SECONDS = 45
SCREENSHOT_TIMEOUT_SECONDS = 15
PAGE_TIMEOUT_SECONDS = 60
# Set in the parent before fork so a test closure does not have to be pickled.
_ACTIVE_FETCH = None
_ACTIVE_WAYBACK = None
# Pids started by the most recent capture, so a test can see that a hung worker died.
last_worker_pids: list[int] = []


def estimate_archive_size(source_count: int, tier: str = "html-pdf") -> str:
    """Rough size before duplicate URLs are collapsed. html-pdf is the default tier."""
    per_source = 300_000
    if tier == "full":
        per_source += 2_500_000
    total = max(0, int(source_count)) * per_source
    megabytes = total / 1_000_000
    return (
        f"About {megabytes:.0f} MB for {source_count} sources at the {tier} tier, "
        "before duplicate URLs are stored once. html-pdf keeps the HTTP body and a PDF. "
        "full also saves a monolith mirror and a screenshot."
    )


def archive_workspace(
    workspace: Path,
    fetch,
    clock: str | None = None,
    *,
    monolith=None,
    screenshot=None,
    html_to_pdf=None,
    wayback=None,
    workers: int = 4,
) -> tuple[int, str]:
    intake = load_yaml(workspace / "intake.yaml") or {}
    if not isinstance(intake, dict) or intake.get("offline_archive") is not True:
        return 0, "Offline archive was not requested. Set offline_archive: true in intake.yaml to capture sources."
    clock = clock or now_et()
    pdf_writer = html_to_pdf or _html_to_pdf
    archive_dir = workspace / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    jobs = _collect_jobs(workspace)
    cache = _capture_urls(jobs, fetch, workers=workers, wayback=wayback)
    rows = []
    seen = 0
    captured = 0
    changed_items: set[Path] = set()
    url_files: dict[str, dict] = {}
    for item_dir, doc, claim, source, marker, url in jobs:
        seen += 1
        slug = slugify(source.get("title") or url)
        row = _blank_row(marker, slug, url, clock)
        cached = cache.get(url) or {"error": "capture_failed: missing cache entry", "body": None, "status": None}
        if cached.get("error") and cached.get("body") is None and not cached.get("wayback_body"):
            row["http_status"] = "" if cached.get("status") is None else str(cached.get("status"))
            row["final_url"] = cached.get("final_url") or ""
            row["error"] = cached["error"]
            if cached.get("wayback_url"):
                row["wayback_url"] = cached["wayback_url"]
            rows.append(row)
            _log_failure(archive_dir, row)
            continue
        body = cached.get("body")
        if body is None and cached.get("wayback_body"):
            saved = _materialize_wayback(
                row, source, cached, archive_dir, marker, slug, monolith, screenshot, pdf_writer, url_files
            )
            if saved:
                changed_items.add(item_dir)
                captured += 1
            rows.append(row)
            continue
        ext = _extension(url, cached.get("content_type") or "", body or b"")
        saved_path = _store_body(archive_dir, url_files, url, "body", marker, slug, ext, body or b"")
        digest = hashlib.sha256(body or b"").hexdigest()
        page_url = cached.get("final_url") or url
        row.update(
            {
                "final_url": page_url,
                "http_status": str(cached.get("status") or ""),
                "sha256": digest,
                "bytes": len(body or b""),
                "path": f"archive/{saved_path.name}",
                "error": "",
            }
        )
        notes = []
        if ext == "html":
            notes.extend(
                _save_monolith_cached(row, monolith, page_url, archive_dir, marker, slug, url, url_files)
            )
            pdf_path = _store_pdf(pdf_writer, body or b"", archive_dir, url_files, url, marker, slug)
            if pdf_path is not None:
                row["pdf_path"] = f"archive/{pdf_path.name}"
                row["pdf_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            else:
                notes.append("pdf print skipped")
            _save_screenshot_cached(row, screenshot, page_url, archive_dir, marker, slug, url, url_files)
        source["local_copy"] = row["path"]
        changed_items.add(item_dir)
        captured += 1
        if notes:
            row["error"] = "; ".join(notes)
        rows.append(row)
    dumped: set[Path] = set()
    for item_dir, doc, _claim, _source, _marker, _url in jobs:
        if item_dir in changed_items and item_dir not in dumped:
            dump_yaml(item_dir / "claims.yaml", doc)
            dumped.add(item_dir)
    manifest = archive_dir / "manifest.csv"
    _write_manifest(manifest, rows)
    zip_path = workspace / "final" / "guide-with-sources.zip"
    _write_zip(workspace, zip_path)
    message = f"Archived {captured} of {seen} sources. Manifest: {manifest}."
    return 0, message


def _collect_jobs(workspace: Path) -> list[tuple]:
    jobs = []
    seen = 0
    for item_dir in sorted((workspace / "items").glob("*")):
        claims_path = item_dir / "claims.yaml"
        doc = load_yaml(claims_path)
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            seen += 1
            marker = source_marker(claim, source) or seen
            url = str(source.get("url") or "")
            jobs.append((item_dir, doc, claim, source, marker, url))
    return jobs


def _worker_main(url: str, dest: str) -> None:
    """Run one fetch in a forked process the parent can kill."""
    try:
        payload = _fetch_one(url, _ACTIVE_FETCH, _ACTIVE_WAYBACK)
    except Exception as exc:  # noqa: BLE001
        payload = {"error": f"capture_failed: {exc}", "body": None, "status": None, "final_url": ""}
    Path(dest).write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))


def _read_worker_payload(dest: str) -> dict:
    try:
        payload = pickle.loads(Path(dest).read_bytes())
    except Exception as exc:  # noqa: BLE001
        return {"error": f"capture_failed: {exc}", "body": None, "status": None}
    if not isinstance(payload, dict):
        return {"error": "capture_failed: bad capture payload", "body": None, "status": None}
    return payload


def _capture_urls(jobs, fetch, *, workers: int, wayback) -> dict[str, dict]:
    """Fetch each URL in its own process and kill the process at the page deadline.

    A thread pool's timeout only stops waiting. The worker keeps running, and
    leaving the pool waits for it. Forked processes can be killed. The fetch
    callable is stored on a module global before the fork so a test closure
    does not have to be pickled.
    """
    global _ACTIVE_FETCH, _ACTIVE_WAYBACK, last_worker_pids
    urls = []
    for _item, _doc, _claim, _source, _marker, url in jobs:
        if url and url not in urls:
            urls.append(url)
    cache: dict[str, dict] = {}
    last_worker_pids = []
    if not urls:
        return cache
    _ACTIVE_FETCH = fetch
    _ACTIVE_WAYBACK = wayback
    ctx = multiprocessing.get_context("fork")
    pool = max(1, min(int(workers or 1), 8, len(urls)))
    pending = list(urls)
    inflight: list[dict] = []

    def launch(url: str) -> dict:
        fd, dest = tempfile.mkstemp(prefix="pr-fetch-", suffix=".pkl")
        os.close(fd)
        proc = ctx.Process(target=_worker_main, args=(url, dest))
        proc.start()
        if proc.pid:
            last_worker_pids.append(proc.pid)
        return {"url": url, "proc": proc, "dest": dest, "started": time.monotonic()}

    def finish(job: dict, payload: dict) -> None:
        cache[job["url"]] = payload
        try:
            os.unlink(job["dest"])
        except OSError:
            pass

    while pending and len(inflight) < pool:
        inflight.append(launch(pending.pop(0)))
    while inflight:
        still = []
        for job in inflight:
            proc = job["proc"]
            elapsed = time.monotonic() - job["started"]
            if proc.is_alive() and elapsed < PAGE_TIMEOUT_SECONDS:
                proc.join(timeout=min(0.2, PAGE_TIMEOUT_SECONDS - elapsed))
                elapsed = time.monotonic() - job["started"]
            if proc.is_alive() and elapsed >= PAGE_TIMEOUT_SECONDS:
                proc.kill()
                proc.join(timeout=5)
                finish(
                    job,
                    {"error": "capture_failed: page deadline exceeded", "body": None, "status": None},
                )
                continue
            if proc.is_alive():
                still.append(job)
                continue
            finish(job, _read_worker_payload(job["dest"]))
        while pending and len(still) < pool:
            still.append(launch(pending.pop(0)))
        inflight = still
    for url in urls:
        cache.setdefault(url, {"error": "capture_failed: page deadline exceeded", "body": None, "status": None})
    return cache


def _fetch_one(url: str, fetch, wayback) -> dict:
    try:
        status, final_url, body, content_type = fetch(url)
    except Exception as exc:  # noqa: BLE001
        payload = {"error": f"capture_failed: {exc}", "body": None, "status": None, "final_url": ""}
        _attach_wayback(payload, url, wayback)
        return payload
    if status is None or body is None or status >= 400:
        payload = {
            "error": "capture_failed: HTTP error or empty body",
            "body": None,
            "status": status,
            "final_url": final_url or "",
            "content_type": content_type or "",
        }
        _attach_wayback(payload, url, wayback)
        return payload
    return {
        "error": "",
        "body": body,
        "status": status,
        "final_url": final_url or url,
        "content_type": content_type or "",
    }


def _attach_wayback(payload: dict, url: str, wayback) -> None:
    if wayback is None or not url:
        payload["error"] = f"{payload.get('error', '')}; wayback not attempted".strip("; ")
        return
    try:
        found = wayback(url)
    except Exception as exc:  # noqa: BLE001
        payload["error"] = f"{payload.get('error', '')}; wayback failed: {exc}"
        return
    if not found:
        payload["error"] = f"{payload.get('error', '')}; wayback checked: no snapshot"
        return
    wayback_url, body = found
    payload["wayback_url"] = wayback_url or ""
    payload["wayback_body"] = body or b""


def _extension(url: str, content_type: str, body: bytes) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return "pdf"
    if "json" in content_type or body[:1] in (b"{", b"["):
        return "json"
    return "html"


def _store_body(archive_dir: Path, url_files: dict, url: str, kind: str, marker, slug: str, ext: str, body: bytes) -> Path:
    key = f"{kind}:{ext}"
    existing = (url_files.get(url) or {}).get(key)
    filename = f"{marker}-{slug}.{ext}" if kind == "body" else f"{marker}-{slug}.{kind}"
    if kind == "wayback":
        filename = f"{marker}-{slug}.wayback.html"
    dest = archive_dir / filename
    if existing and existing.exists():
        _link_or_copy(existing, dest)
        return dest
    dest.write_bytes(body)
    url_files.setdefault(url, {})[key] = dest
    return dest


def _store_pdf(pdf_writer, body: bytes, archive_dir: Path, url_files: dict, url: str, marker, slug: str) -> Path | None:
    existing = (url_files.get(url) or {}).get("pdf")
    dest = archive_dir / f"{marker}-{slug}.pdf"
    if existing and existing.exists():
        _link_or_copy(existing, dest)
        return dest
    if pdf_writer(body, dest) and dest.exists():
        url_files.setdefault(url, {})["pdf"] = dest
        return dest
    return None


def _link_or_copy(source: Path, dest: Path) -> None:
    if dest.exists():
        return
    try:
        os.link(source, dest)
    except OSError:
        shutil.copyfile(source, dest)


def _materialize_wayback(row, source, cached, archive_dir, marker, slug, monolith, screenshot, pdf_writer, url_files) -> bool:
    body = cached.get("wayback_body") or b""
    if not body:
        return False
    wayback_url = cached.get("wayback_url") or ""
    row["wayback_url"] = wayback_url
    row["error"] = cached.get("error") or "capture_failed"
    dest = _store_body(archive_dir, url_files, wayback_url or row["original_url"], "wayback", marker, slug, "html", body)
    row["sha256"] = hashlib.sha256(body).hexdigest()
    row["bytes"] = len(body)
    row["path"] = f"archive/{dest.name}"
    source["local_copy"] = row["path"]
    if wayback_url and not source.get("archive_url"):
        source["archive_url"] = wayback_url
    page_url = wayback_url or row["original_url"]
    notes = _save_monolith_cached(row, monolith, page_url, archive_dir, marker, slug, page_url, url_files)
    pdf_path = _store_pdf(pdf_writer, body, archive_dir, url_files, page_url, marker, slug)
    if pdf_path is not None:
        row["pdf_path"] = f"archive/{pdf_path.name}"
        row["pdf_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    else:
        notes.append("pdf print skipped")
    _save_screenshot_cached(row, screenshot, page_url, archive_dir, marker, slug, page_url, url_files)
    if notes:
        row["error"] = f"{row['error']}; " + "; ".join(note for note in notes if note)
    return True


def _log_failure(archive_dir: Path, row: dict) -> None:
    path = archive_dir / "failures.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{row.get('n')}\t{row.get('original_url')}\t{row.get('error')}\n")


def _is_chrome_wrapper(path: str) -> bool:
    if path.rstrip("/").endswith("/usr/local/bin/google-chrome"):
        return True
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return False
    if "\0" in text:
        return False
    return "user-data-dir=/home" in text and "remote-debugging-port=9222" in text


def find_browser() -> str | None:
    for name in BROWSERS:
        if name.startswith("/"):
            if os.path.isfile(name) and os.access(name, os.X_OK) and not _is_chrome_wrapper(name):
                return name
            continue
        found = shutil.which(name)
        if found and not _is_chrome_wrapper(found):
            return found
    return None


def live_monolith(url: str) -> bytes | None:
    page = vetted_fetch_url(url)
    binary = resolve_bin("monolith")
    if not binary:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    dest = handle.name
    handle.close()
    try:
        code, _out, err = _run_group([binary, "-o", dest, page], timeout=90)
        if code != 0:
            detail = (err or b"").decode()[:300] or "monolith failed"
            raise RuntimeError(detail)
        data = Path(dest).read_bytes()
        return data or None
    finally:
        try:
            os.unlink(dest)
        except OSError:
            pass


def live_screenshot(url: str) -> bytes | None:
    page = vetted_fetch_url(url)
    browser = find_browser()
    if not browser:
        return None
    profile = tempfile.mkdtemp(prefix="pr-chrome-")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "page.png"
            code, _out, err = _run_group(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    f"--user-data-dir={profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=1280,1600",
                    f"--screenshot={dest}",
                    page,
                ],
                timeout=SCREENSHOT_TIMEOUT_SECONDS,
                cwd=tmp,
            )
            if not dest.exists():
                fallback = Path(tmp) / "screenshot.png"
                if fallback.exists():
                    dest = fallback
            if not dest.exists() or dest.stat().st_size == 0:
                if code != 0:
                    detail = (err or b"").decode()[:300] or "screenshot failed"
                    raise RuntimeError(detail)
                return None
            return dest.read_bytes()
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def live_wayback(url: str):
    api = wayback_api_url(url)
    try:
        response = safe_request("GET", api, timeout=20, headers={"User-Agent": "PoliticalResearch-archive/0.1"})
        payload = json.loads(response.content.decode("utf-8"))
    except Exception:
        return None
    snapshot = ((payload.get("archived_snapshots") or {}).get("closest") or {})
    if not snapshot or not snapshot.get("available"):
        return None
    wayback_url = str(snapshot.get("url") or "")
    if not wayback_url:
        return None
    try:
        response = safe_request(
            "GET",
            wayback_url,
            timeout=30,
            headers={"User-Agent": "PoliticalResearch-archive/0.1"},
        )
        body = response.content
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


def _save_monolith_cached(row, monolith, url: str, archive_dir: Path, marker, slug, cache_key: str, url_files: dict) -> list[str]:
    if monolith is None:
        return []
    existing = (url_files.get(cache_key) or {}).get("monolith")
    filename = f"{marker}-{slug}.monolith.html"
    dest = archive_dir / filename
    if existing and existing.exists():
        _link_or_copy(existing, dest)
        row["monolith_path"] = f"archive/{filename}"
        row["monolith_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        return []
    try:
        body = monolith(url)
    except Exception as exc:  # noqa: BLE001
        return [f"monolith failed: {exc}"]
    if not body:
        return ["monolith skipped"]
    dest.write_bytes(body)
    url_files.setdefault(cache_key, {})["monolith"] = dest
    row["monolith_path"] = f"archive/{filename}"
    row["monolith_sha256"] = hashlib.sha256(body).hexdigest()
    return []


def _save_screenshot_cached(row, screenshot, url: str, archive_dir: Path, marker, slug, cache_key: str, url_files: dict) -> None:
    if screenshot is None:
        row["screenshot_status"] = "skipped, no headless browser configured"
        return
    existing = (url_files.get(cache_key) or {}).get("screenshot")
    filename = f"{marker}-{slug}.png"
    dest = archive_dir / filename
    if existing and existing.exists():
        _link_or_copy(existing, dest)
        row["screenshot_path"] = f"archive/{filename}"
        row["screenshot_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        row["screenshot_status"] = "captured"
        return
    try:
        body = screenshot(url)
    except Exception as exc:  # noqa: BLE001
        row["screenshot_status"] = f"failed: {exc}"
        return
    if not body:
        row["screenshot_status"] = "skipped, screenshot returned nothing"
        return
    dest.write_bytes(body)
    url_files.setdefault(cache_key, {})["screenshot"] = dest
    row["screenshot_path"] = f"archive/{filename}"
    row["screenshot_sha256"] = hashlib.sha256(body).hexdigest()
    row["screenshot_status"] = "captured"


def _write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in MANIFEST_FIELDS})


def _run_group(cmd: list[str], *, timeout: int, cwd: str | None = None) -> tuple[int, bytes, bytes]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        raise
    return proc.returncode or 0, out or b"", err or b""


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _html_to_pdf(body: bytes, dest: Path) -> bool:
    handle = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    try:
        handle.write(body)
        handle.close()
        try:
            code, _out, _err = _run_group(["weasyprint", handle.name, str(dest)], timeout=PDF_TIMEOUT_SECONDS)
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            return False
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    return code == 0 and dest.exists()


def _write_zip(workspace: Path, zip_path: Path) -> None:
    import zipfile

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
    response = safe_request(
        "GET",
        url,
        timeout=30,
        headers={"User-Agent": "PoliticalResearch-archive/0.1"},
    )
    return response.status_code, str(response.url or url), response.content, response.headers.get("Content-Type", "")
