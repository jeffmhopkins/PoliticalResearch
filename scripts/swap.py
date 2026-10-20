#!/usr/bin/env python3
"""Write a blinded draft that swaps candidate names for Candidate A and Candidate B."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import blinded_swap
from lib.util import load_yaml


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Build a blinded swap draft for the neutrality reviewer.")
    parser.add_argument("--contest", help="Contest id. Defaults to the first race.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    contest = None
    for item in ballot.get("contests") or []:
        if not isinstance(item, dict):
            continue
        if args.contest and item.get("id") != args.contest:
            continue
        if item.get("type") in {"race", "primary", "local-office"}:
            contest = item
            break
    if not contest:
        print("No race contest found.", file=sys.stderr)
        return 1
    names = []
    chunks = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    candidates = [c for c in contest.get("candidates") or [] if isinstance(c, dict)]
    for index, candidate in enumerate(candidates):
        alias = f"Candidate {letters[index]}" if index < len(letters) else f"Candidate {index + 1}"
        names.append((candidate.get("name") or "", alias))
        item_id = candidate.get("item_id") or candidate.get("id")
        draft = workspace / "items" / str(item_id) / "draft.md"
        if draft.exists():
            chunks.append(draft.read_text(encoding="utf-8"))
    race_id = contest.get("item_id") or contest.get("id")
    race_draft = workspace / "items" / str(race_id) / "draft.md"
    if race_draft.exists():
        chunks.insert(0, race_draft.read_text(encoding="utf-8"))
    blinded = blinded_swap("\n\n".join(chunks), names)
    header = (
        "# Blinded swap draft\n\n"
        "Names are replaced. Do not open intake.yaml or any note of the requester's views while reviewing this file.\n\n"
    )
    dest = workspace / "items" / str(race_id) / "swap-draft.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(header + blinded, encoding="utf-8")
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
