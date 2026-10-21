#!/usr/bin/env python3
"""Check whether cited URLs respond. Dead links need an archive fallback.

Each distinct URL is fetched once. archive_failed does not count as a completed
live check: a live run still requests the URL.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import classify_link, iter_claim_sources, source_marker, wayback_api_url
from lib.util import dump_json, iter_items, load_yaml, safe_request, unsafe_fetch_target


def _has_archive(source: dict) -> bool:
    if source.get("archive_url"):
        return True
    return source.get("archive_failed") is True and bool(str(source.get("archive_failed_reason") or "").strip())


def _rows(workspace):
    rows = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            rows.append(
                {
                    "marker": source_marker(claim, source),
                    "url": str(source.get("url") or ""),
                    "has_archive": _has_archive(source),
                    "claim_id": claim.get("id"),
                }
            )
    return rows


def _fetch_status(url: str, request) -> tuple[int | None, str | None]:
    try:
        response = request("HEAD", url, timeout=15)
        status = response.status_code
        if status in {403, 429}:
            return status, f"{status}; not retried"
        if status == 405:
            follow = request("GET", url, timeout=20)
            status = follow.status_code
        return status, None
    except RuntimeError as exc:
        return None, f"blocked-redirect: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"unchecked: {exc}"


def live_statuses(urls: list[str], request=safe_request, workers: int = 8) -> dict[str, tuple[int | None, str | None]]:
    """Fetch each URL once. Callers still report every claim that cites it."""
    unique = []
    seen = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    if not unique:
        return {}
    pool = max(1, min(int(workers or 1), 8, len(unique)))
    found: dict[str, tuple[int | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=pool) as executor:
        futures = {executor.submit(_fetch_status, url, request): url for url in unique}
        for future, url in futures.items():
            try:
                found[url] = future.result()
            except Exception as exc:  # noqa: BLE001
                found[url] = (None, f"unchecked: {exc}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("HEAD cited URLs and point dead links at the Wayback availability API.")
    parser.add_argument("--offline", action="store_true", help="Do not contact the network. Report archive presence only.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when a URL is dead and has no archive URL.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    rows = _rows(workspace)
    failures = []
    blocked = {}
    fetchable = []
    for row in rows:
        url = row["url"]
        reason = unsafe_fetch_target(url) if url else "empty URL"
        if reason:
            blocked[id(row)] = reason
            continue
        if url:
            fetchable.append(url)
    statuses = {} if args.offline else live_statuses(fetchable)
    for row in rows:
        url = row["url"]
        marker = row["marker"]
        has_archive = row["has_archive"]
        if id(row) in blocked:
            print(f"blocked\t{marker}\t{url}\t{blocked[id(row)]}")
            failures.append(url or row["claim_id"])
            continue
        status = None
        note = None
        if not args.offline and url:
            status, note = statuses.get(url, (None, "unchecked: missing"))
            if note and note.startswith("blocked-redirect"):
                print(f"blocked-redirect\t{marker}\t{url}\t{note}")
                failures.append(url)
                continue
            if note and status is None:
                print(f"UNCHECKED {url} ({note})")
        kind = classify_link(status, has_archive)
        print(f"{kind}\t{marker}\t{url}\twayback={wayback_api_url(url or '')}")
        if kind == "dead":
            failures.append(url)
    dump_json(
        workspace / "link-check.json",
        {"mode": "offline" if args.offline else "live", "checked": len(rows), "errors": len(failures)},
    )
    if failures and (args.strict or args.offline):
        print(f"{len(failures)} link(s) failed the check.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
