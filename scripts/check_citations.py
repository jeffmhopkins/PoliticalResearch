#!/usr/bin/env python3
"""Check inline markers, works-cited lines, and claim records."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import citation_errors


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fail if factual prose has no marker or a marker does not resolve.")
    parser.add_argument("--guide", action="store_true", help="Require works-cited lines in final/guide.md.")
    args = parser.parse_args(argv)
    errors = citation_errors(workspace_from(args), guide=args.guide or (workspace_from(args) / "final" / "guide.md").exists())
    if errors:
        print("\n".join(errors))
        return 1
    print("Citations OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
