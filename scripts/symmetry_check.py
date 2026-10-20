#!/usr/bin/env python3
"""Check section parity and effort parity across candidates in a race."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import symmetry_errors


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Compare candidate sections and effort logs.")
    args = parser.parse_args(argv)
    errors = symmetry_errors(workspace_from(args))
    if errors:
        print("\n".join(errors))
        return 1
    print("Symmetry OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
