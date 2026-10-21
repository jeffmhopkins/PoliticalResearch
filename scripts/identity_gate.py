#!/usr/bin/env python3
"""Check court records, aliases, birth year, and the legal-record rules.

birth_year stays in identity.yaml. This script reports it only as an internal
gate failure when a draft, claim, or assembled guide would publish it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.records import (
    identity_name_keys,
    item_record_errors,
    person_name_key,
    rendered_birth_errors,
    street_address_errors,
)
from lib.util import iter_items, load_yaml


def _ballot_name_keys(workspace: Path) -> dict[str, set[str]]:
    ballot = load_yaml(workspace / "ballot.yaml")
    found: dict[str, set[str]] = {}
    if not isinstance(ballot, dict):
        return found
    for contest in ballot.get("contests") or []:
        if not isinstance(contest, dict):
            continue
        for candidate in contest.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            item_id = str(candidate.get("item_id") or candidate.get("id") or "")
            keys = found.setdefault(item_id, set())
            for field in ("name", "ballot_name", "full_legal_name"):
                key = person_name_key(str(candidate.get(field) or ""))
                if key:
                    keys.add(key)
    return found


def _other_name_keys(
    item_name: str,
    identities: list[tuple[str, dict]],
    ballot_keys: dict[str, set[str]],
) -> set[str]:
    others: set[str] = set()
    for other_name, other_identity in identities:
        if other_name == item_name:
            continue
        others |= identity_name_keys(other_identity)
    for other_name, keys in ballot_keys.items():
        if other_name != item_name:
            others |= keys
    return others


def _extend(errors: list[str], messages: list[str]) -> None:
    for message in messages:
        if message not in errors:
            errors.append(message)


def identity_gate_errors(workspace: Path) -> list[str]:
    errors: list[str] = []
    years: list[int] = []
    loaded: list[tuple[str, dict, list[dict], str, dict, str]] = []
    for item in iter_items(workspace):
        identity = load_yaml(item / "identity.yaml")
        if not isinstance(identity, dict):
            identity = {}
        birth = identity.get("birth_year")
        if isinstance(birth, int):
            years.append(birth)
        doc = load_yaml(item / "claims.yaml")
        claims = []
        claims_text = ""
        claims_path = item / "claims.yaml"
        if claims_path.exists():
            claims_text = claims_path.read_text(encoding="utf-8")
        if isinstance(doc, dict):
            claims = [claim for claim in (doc.get("claims") or []) if isinstance(claim, dict)]
        draft_path = item / "draft.md"
        draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        profile = load_yaml(item / "profile.yaml")
        if not isinstance(profile, dict):
            profile = {}
        loaded.append((item.name, identity, claims, draft, profile, claims_text))
    ballot_keys = _ballot_name_keys(workspace)
    identities = [(name, identity) for name, identity, _claims, _draft, _profile, _text in loaded]
    for name, identity, claims, draft, profile, claims_text in loaded:
        others = _other_name_keys(name, identities, ballot_keys)
        for message in item_record_errors(identity, claims, draft, profile, others):
            _extend(errors, [f"{name}: {message}"])
        _extend(errors, street_address_errors(f"{name}/draft.md", draft))
        _extend(errors, street_address_errors(f"{name}/claims.yaml", claims_text))
        _extend(errors, [f"{name}: {message}" for message in rendered_birth_errors(claims_text, years)])
    final = workspace / "final"
    if final.is_dir():
        for guide in sorted(final.glob("guide*.md")):
            text = guide.read_text(encoding="utf-8")
            _extend(errors, [f"{guide.name}: {message}" for message in rendered_birth_errors(text, years)])
            _extend(errors, street_address_errors(guide.name, text))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Run the record-ownership identity gate and the legal-record checks.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    errors = identity_gate_errors(workspace)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Identity gate OK {workspace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
