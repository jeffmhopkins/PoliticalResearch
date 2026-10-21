#!/usr/bin/env python3
"""Save local copies of cited sources when intake asked for an offline archive."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.archive import (
    archive_workspace,
    estimate_archive_size,
    find_browser,
    http_fetch,
    live_monolith,
    live_screenshot,
    live_wayback,
)
from lib.cli import base_parser, clock_from, workspace_from
from lib.util import load_yaml, resolve_bin


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Archive cited sources into output/<election>/archive and a zip bundle.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    intake = load_yaml(workspace / "intake.yaml") or {}
    tier = "html-pdf"
    if isinstance(intake, dict) and intake.get("archive_tier") == "full":
        tier = "full"
    code, message = archive_workspace(
        workspace,
        http_fetch,
        clock_from(args),
        monolith=live_monolith if tier == "full" and resolve_bin("monolith") else None,
        screenshot=live_screenshot if tier == "full" and find_browser() else None,
        wayback=live_wayback,
    )
    print(estimate_archive_size(_source_count(workspace), tier))
    print(message)
    return code


def _source_count(workspace) -> int:
    from lib.quality import iter_claim_sources
    from lib.util import iter_items

    total = 0
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml") or {}
        if not isinstance(doc, dict):
            continue
        for claim, _source in iter_claim_sources(doc):
            if not claim.get("removed"):
                total += 1
    return total


if __name__ == "__main__":
    sys.exit(main())
