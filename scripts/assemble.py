#!/usr/bin/env python3
"""Build final/guide.md from signed-off item drafts."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, today_of, workspace_from
from lib.workflow import assemble_guide, write_status


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Assemble the guide after every item is signed off or capped.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    errors = assemble_guide(workspace, today_of(args).isoformat())
    write_status(workspace, clock_from(args))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    final = workspace / "final"
    print(f"Wrote {final / 'guide.md'}")
    for name in ("guide-sources.md", "guide-full.md", "guide-full-sources.md"):
        path = final / name
        if path.exists():
            print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
