#!/usr/bin/env python3
"""Pull OpenFEC totals into an unreviewed import. Does nothing without a key."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.api_clients import ApiError, fec_stub, get_json
from lib.cli import base_parser, workspace_from
from lib.util import dump_json, dump_yaml, load_dotenv


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fetch OpenFEC candidate totals. The import is not a claim until a person cites the filing.")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--cycle", default="2026")
    parser.add_argument("--item", help="Item id. The stub is written to items/<id>/imports/.")
    args = parser.parse_args(argv)
    key = load_dotenv().get("OPENFEC_API_KEY", "").strip()
    if not key:
        print("OPENFEC_API_KEY is not set. Skipping FEC pull. Open the committee filing on fec.gov and cite that T1 document.")
        return 0
    try:
        payload = get_json(
            f"https://api.open.fec.gov/v1/candidate/{args.candidate_id}/totals/",
            params={"api_key": key, "cycle": args.cycle},
            secrets=[key],
        )
    except ApiError as exc:
        print(f"FEC request failed ({exc}). No totals were invented.")
        return 0
    stub = fec_stub(args.candidate_id, args.cycle, payload)
    workspace = workspace_from(args) if args.workspace or args.election_id else None
    if workspace and args.item:
        dest = workspace / "items" / args.item / "imports"
        dest.mkdir(parents=True, exist_ok=True)
        dump_json(dest / "fec.json", payload)
        dump_yaml(dest / "fec-citation-stub.yaml", stub)
        print(f"Wrote {dest / 'fec-citation-stub.yaml'}. Review the filing before adding a claim.")
    else:
        print(stub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
