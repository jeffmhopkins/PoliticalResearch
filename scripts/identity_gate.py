#!/usr/bin/env python3
"""Check court records, aliases, birth year, and the legal-record rules.

birth_year stays in identity.yaml. This script reports it only as an internal
gate failure when a draft or claim would publish it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.records import item_record_errors, rendered_birth_errors
from lib.util import iter_items, load_yaml


def identity_gate_errors(workspace: Path) -> list[str]:
    errors: list[str] = []
    years: list[int] = []
    for item in iter_items(workspace):
        identity = load_yaml(item / "identity.yaml")
        if not isinstance(identity, dict):
            identity = {}
        birth = identity.get("birth_year")
        if isinstance(birth, int):
            years.append(birth)
        doc = load_yaml(item / "claims.yaml")
        claims = []
        if isinstance(doc, dict):
            claims = [claim for claim in (doc.get("claims") or []) if isinstance(claim, dict)]
        draft_path = item / "draft.md"
        draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        profile = load_yaml(item / "profile.yaml")
        if not isinstance(profile, dict):
            profile = {}
        for message in item_record_errors(identity, claims, draft, profile):
            errors.append(f"{item.name}: {message}")
    final = workspace / "final"
    if final.is_dir():
        for guide in sorted(final.glob("guide*.md")):
            text = guide.read_text(encoding="utf-8")
            for message in rendered_birth_errors(text, years):
                errors.append(f"{guide.name}: {message}")
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
