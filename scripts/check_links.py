#!/usr/bin/env python3
"""Check whether cited URLs respond. Dead links need an archive fallback."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import classify_link, iter_claim_sources, source_marker, wayback_api_url
from lib.util import iter_items, load_yaml


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("HEAD cited URLs and point dead links at the Wayback availability API.")
    parser.add_argument("--offline", action="store_true", help="Do not contact the network. Report archive presence only.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when a URL is dead and has no archive URL.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    failures = []
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, source in iter_claim_sources(doc):
            if claim.get("removed"):
                continue
            url = source.get("url")
            has_archive = bool(source.get("archive_url")) or source.get("archive_failed") is True
            status = None
            if not args.offline and url:
                try:
                    import requests

                    response = requests.head(url, timeout=15, allow_redirects=True)
                    status = response.status_code
                    if status in {403, 405}:
                        status = requests.get(url, timeout=20, allow_redirects=True).status_code
                except Exception as exc:  # noqa: BLE001
                    print(f"UNCHECKED {url} ({exc})")
                    status = None
            kind = classify_link(status, has_archive)
            marker = source_marker(claim, source)
            print(f"{kind}\t{marker}\t{url}\twayback={wayback_api_url(url or '')}")
            if kind == "dead":
                failures.append(url)
    if failures and args.strict:
        print(f"{len(failures)} dead link(s) without an archive fallback.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
