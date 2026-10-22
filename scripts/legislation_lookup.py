#!/usr/bin/env python3
"""Save an unreviewed bill import. Florida uses free public pages. Other states do not get invented records."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.legislation import collect_legislation
from lib.util import dump_json
from portals.fetch import SafePortalFetcher


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fetch one bill import from free official pages. Does not create claims.")
    parser.add_argument("--state", required=True, help="Postal abbreviation. FL uses the Florida adapters.")
    parser.add_argument("--bill", default="", help="Bill number such as SB 2 or HB 18. Omit to skip the network call.")
    parser.add_argument("--session", default="")
    parser.add_argument("--item")
    args = parser.parse_args(argv)
    if not args.bill:
        print("No --bill. Nothing fetched and nothing invented.")
        return 0
    record = collect_legislation(args.state, args.bill, args.session, SafePortalFetcher())
    if args.item and (args.workspace or args.election_id):
        dest = workspace_from(args) / "items" / args.item / "imports"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / "legislation.json"
        dump_json(path, record)
        print(f"Wrote {path}. Status: {record.get('status')}. Cite the official bill page, not only this JSON.")
    else:
        print(f"Status: {record.get('status')}. Pass --item and --workspace to save the JSON.")
        for note in record.get("notes") or []:
            print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
