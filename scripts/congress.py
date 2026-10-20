#!/usr/bin/env python3
"""Pull a Congress.gov bill JSON import. Does nothing without a key."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.api_clients import ApiError, get_json
from lib.cli import base_parser, workspace_from
from lib.util import dump_json, load_dotenv


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fetch one bill from the Congress.gov API.")
    parser.add_argument("--congress", required=True, help="Congress number, such as 119.")
    parser.add_argument("--bill-type", required=True, help="hr, s, hjres, sjres, hconres, sconres, hres, or sres.")
    parser.add_argument("--number", required=True)
    parser.add_argument("--item")
    args = parser.parse_args(argv)
    key = load_dotenv().get("CONGRESS_API_KEY", "").strip()
    if not key:
        print("CONGRESS_API_KEY is not set. Skipping Congress.gov. Cite the bill text on congress.gov directly.")
        return 0
    url = f"https://api.congress.gov/v3/bill/{args.congress}/{args.bill_type}/{args.number}"
    try:
        payload = get_json(url, params={"api_key": key, "format": "json"}, secrets=[key])
    except ApiError as exc:
        print(f"Congress.gov request failed ({exc}). No bill text was invented.")
        return 0
    if args.item and (args.workspace or args.election_id):
        dest = workspace_from(args) / "items" / args.item / "imports"
        dest.mkdir(parents=True, exist_ok=True)
        dump_json(dest / "congress.json", payload)
        print(f"Wrote {dest / 'congress.json'}. Cite the bill text and roll calls, not only this JSON.")
    else:
        title = ((payload.get("bill") or {}).get("title")) or "untitled"
        print(f"Congress.gov returned a bill ({title}). Pass --item and --workspace to save the JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
