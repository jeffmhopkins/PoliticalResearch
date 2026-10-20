#!/usr/bin/env python3
"""Pull an Open States bill JSON import. Does nothing without a key."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.api_clients import ApiError, get_json
from lib.cli import base_parser, workspace_from
from lib.util import dump_json, load_dotenv


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fetch one state bill from Open States API v3.")
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--identifier", help="Bill identifier such as HB 1. Omit to skip the network call.")
    parser.add_argument("--session", default="")
    parser.add_argument("--item")
    args = parser.parse_args(argv)
    key = load_dotenv().get("OPENSTATES_API_KEY", "").strip()
    if not key:
        print("OPENSTATES_API_KEY is not set. Skipping Open States. Read the official bill page and cite that text as T1.")
        return 0
    if not args.identifier:
        print("No --identifier. Nothing fetched.")
        return 0
    params = {"jurisdiction": args.jurisdiction, "identifier": args.identifier}
    if args.session:
        params["session"] = args.session
    try:
        payload = get_json("https://v3.openstates.org/bills", headers={"X-API-KEY": key}, params=params, secrets=[key])
    except ApiError as exc:
        print(f"Open States request failed ({exc}). No bill text was invented.")
        return 0
    if args.item and (args.workspace or args.election_id):
        dest = workspace_from(args) / "items" / args.item / "imports"
        dest.mkdir(parents=True, exist_ok=True)
        dump_json(dest / "openstates.json", payload)
        print(f"Wrote {dest / 'openstates.json'}. Cite the legislature's bill page, not only this JSON.")
    else:
        print(f"Open States returned {len(payload.get('results') or [])} result(s). Pass --item and --workspace to save the JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
