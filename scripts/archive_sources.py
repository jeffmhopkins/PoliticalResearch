#!/usr/bin/env python3
"""Save local copies of cited sources when intake asked for an offline archive."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.archive import archive_workspace, http_fetch
from lib.cli import base_parser, clock_from, workspace_from


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Archive cited sources into output/<election>/archive and a zip bundle.")
    args = parser.parse_args(argv)
    code, message = archive_workspace(workspace_from(args), http_fetch, clock_from(args))
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
