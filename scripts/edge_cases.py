#!/usr/bin/env python3
"""Require banners for withdrawn, write-in, thin-record, and uncontested contests."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import edge_errors


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Check edge-case banners required by the templates.")
    args = parser.parse_args(argv)
    errors = edge_errors(workspace_from(args))
    if errors:
        print("\n".join(errors))
        return 1
    print("Edge cases OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
