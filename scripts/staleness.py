#!/usr/bin/env python3
"""Flag sources retrieved more than N days ago."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, today_of, workspace_from
from lib.quality import staleness_findings
from lib.util import load_config


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Report stale retrieval dates and sources published before the election year.")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args(argv)
    days = args.days if args.days is not None else int(load_config().get("staleness_days", 7))
    rows = staleness_findings(workspace_from(args), today_of(args), days)
    hard = [row for row in rows if not row.startswith("NOTE ")]
    for row in rows:
        print(row)
    if not rows:
        print("No stale sources.")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
