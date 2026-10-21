#!/usr/bin/env python3
"""Write one blinded draft that covers every race and measure on the ballot."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import blinded_swap
from lib.records import redact_rendered_birth
from lib.util import load_yaml

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _add(pairs: list[tuple[str, str]], real: str, alias: str) -> None:
    text = (real or "").strip()
    if len(text) < 3 or text == alias:
        return
    pairs.append((text, alias))


def _names_for(candidate: dict, identity: dict, alias: str, site_alias: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    full_names = [
        str(candidate.get("name") or ""),
        str(identity.get("full_legal_name") or ""),
        str(identity.get("ballot_name") or ""),
    ]
    for row in identity.get("aliases") or []:
        if isinstance(row, dict):
            full_names.append(str(row.get("name") or ""))
        else:
            full_names.append(str(row or ""))
    for name in full_names:
        _add(pairs, name, alias)
        tokens = [token for token in name.replace(",", " ").split() if token]
        if not tokens:
            continue
        _add(pairs, tokens[0], alias)
        if len(tokens[-1]) >= 3:
            _add(pairs, tokens[-1], alias)
    site = str(identity.get("campaign_site") or candidate.get("campaign_site") or "").strip()
    if site:
        _add(pairs, site, site_alias)
        _add(pairs, site.rstrip("/"), site_alias)
        host = (urlparse(site).hostname or "").lower()
        _add(pairs, host, site_alias.removeprefix("https://").rstrip("/"))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Build one blinded swap draft for every race and measure.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    contests = [item for item in (ballot.get("contests") or []) if isinstance(item, dict)]
    if not contests:
        print("No contests found.", file=sys.stderr)
        return 1
    replacements: list[tuple[str, str]] = []
    birth_years: list[int] = []
    chunks: list[str] = []
    person_index = 0
    covered = False
    for contest in contests:
        kind = contest.get("type")
        if kind in {"race", "primary", "local-office"}:
            covered = True
            for candidate in contest.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                letter = LETTERS[person_index] if person_index < len(LETTERS) else str(person_index + 1)
                alias = f"Candidate {letter}"
                site_alias = f"https://candidate-{letter.lower()}.example"
                item_id = str(candidate.get("item_id") or candidate.get("id") or "")
                identity = load_yaml(workspace / "items" / item_id / "identity.yaml") or {}
                if not isinstance(identity, dict):
                    identity = {}
                birth = identity.get("birth_year")
                if isinstance(birth, int):
                    birth_years.append(birth)
                replacements.extend(_names_for(candidate, identity, alias, site_alias))
                draft = workspace / "items" / item_id / "draft.md"
                if draft.exists():
                    chunks.append(draft.read_text(encoding="utf-8"))
                person_index += 1
            race_id = str(contest.get("item_id") or contest.get("id") or "")
            race_draft = workspace / "items" / race_id / "draft.md"
            if race_draft.exists():
                chunks.append(race_draft.read_text(encoding="utf-8"))
        elif kind == "measure":
            covered = True
            item_id = str(contest.get("item_id") or contest.get("id") or "")
            draft = workspace / "items" / item_id / "draft.md"
            if draft.exists():
                chunks.append(draft.read_text(encoding="utf-8"))
    if not covered:
        print("No race or measure contest found.", file=sys.stderr)
        return 1
    blinded = blinded_swap("\n\n".join(chunks), replacements)
    blinded = redact_rendered_birth(blinded, birth_years)
    header = (
        "# Blinded swap draft\n\n"
        "Names, surnames, and campaign web addresses are replaced across the whole ballot. "
        "Do not open intake.yaml or any note of the requester's views while reviewing this file.\n\n"
    )
    dest = workspace / "swap-draft.md"
    dest.write_text(header + blinded, encoding="utf-8")
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
