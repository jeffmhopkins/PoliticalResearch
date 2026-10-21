#!/usr/bin/env python3
"""Run a Florida portal search and print detail-page citations.

The status line is searched-none, portal-down, or search-form-only when there
are no citations. searched-none counts as a completed search only when executed
is true. A form page and an outage are not evidence that no record exists.
"""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser
from portals import search_portal
from portals.fetch import SafePortalFetcher


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Search a government portal and print detail-page citations.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--state", default="FL")
    parser.add_argument("--kind", required=True, choices=["business", "license"])
    parser.add_argument("--base-url", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    result = search_portal(
        args.kind,
        args.name,
        state=args.state,
        fetcher=SafePortalFetcher(),
        base_url=args.base_url,
        limit=args.limit,
    )
    print(f"status: {result.status}")
    print(f"executed: {str(result.executed).lower()}")
    if result.note:
        print(f"note: {result.note}")
    if result.citations:
        print("detail_citations:")
        for url in result.citations:
            print(f"- {url}")
    else:
        print("detail_citations: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
