#!/usr/bin/env python3
"""Save local copies of cited sources when intake asked for an offline archive."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.archive import (
    archive_workspace,
    find_browser,
    http_fetch,
    live_monolith,
    live_screenshot,
    live_wayback,
)
from lib.cli import base_parser, clock_from, workspace_from
from lib.util import resolve_bin


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Archive cited sources into output/<election>/archive and a zip bundle.")
    args = parser.parse_args(argv)
    code, message = archive_workspace(
        workspace_from(args),
        http_fetch,
        clock_from(args),
        monolith=live_monolith if resolve_bin("monolith") else None,
        screenshot=live_screenshot if find_browser() else None,
        wayback=live_wayback,
    )
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
