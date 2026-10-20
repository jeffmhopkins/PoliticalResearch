#!/usr/bin/env python3
"""Check whether cited URLs respond. Dead links need an archive fallback."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import classify_link, iter_claim_sources, source_marker, wayback_api_url
from lib.util import dump_json, iter_items, load_yaml, safe_request, unsafe_fetch_target


def _has_archive(source: dict) -> bool:
    if source.get("archive_url"):
        return True
    return source.get("archive_failed") is True and bool(str(source.get("archive_failed_reason") or "").strip())


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("HEAD cited URLs and point dead links at the Wayback availability API.")
    parser.add_argument("--offline", action="store_true", help="Do not contact the network. Report archive presence only.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when a URL is dead and has no archive URL.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    failures = []
    checked = 0
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            url = str(source.get("url") or "")
            has_archive = _has_archive(source)
            marker = source_marker(claim, source)
            checked += 1
            blocked = unsafe_fetch_target(url) if url else "empty URL"
            if blocked:
                print(f"blocked\t{marker}\t{url}\t{blocked}")
                failures.append(url or claim.get("id"))
                continue
            status = None
            if not args.offline and url:
                try:
                    response = safe_request("HEAD", url, timeout=15)
                    status = response.status_code
                    if status in {403, 405}:
                        follow = safe_request("GET", url, timeout=20)
                        status = follow.status_code
                except RuntimeError as exc:
                    print(f"blocked-redirect\t{marker}\t{url}\t{exc}")
                    failures.append(url)
                    continue
                except Exception as exc:  # noqa: BLE001
                    print(f"UNCHECKED {url} ({exc})")
                    status = None
            kind = classify_link(status, has_archive)
            print(f"{kind}\t{marker}\t{url}\twayback={wayback_api_url(url or '')}")
            if kind == "dead":
                failures.append(url)
    dump_json(
        workspace / "link-check.json",
        {"mode": "offline" if args.offline else "live", "checked": checked, "errors": len(failures)},
    )
    if failures and (args.strict or args.offline):
        print(f"{len(failures)} link(s) failed the check.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
