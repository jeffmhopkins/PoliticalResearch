#!/usr/bin/env python3
"""Score summary paragraphs with a Flesch-Kincaid grade estimate."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, workspace_from
from lib.quality import flesch_kincaid_grade, readability_errors, summary_text
from lib.util import iter_items


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Check that summaries stay near an 8th-grade reading level.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    for item in iter_items(workspace):
        path = item / "draft.md"
        if not path.exists() or "<!-- summary -->" not in path.read_text(encoding="utf-8"):
            continue
        grade = flesch_kincaid_grade(summary_text(path.read_text(encoding="utf-8")))
        if grade is not None:
            print(f"{item.name}: grade {grade:.1f}")
    errors = readability_errors(workspace)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Readability OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
