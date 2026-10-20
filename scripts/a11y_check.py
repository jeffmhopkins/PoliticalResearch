#!/usr/bin/env python3
"""Basic WCAG-oriented checks for a built guide HTML file."""

from __future__ import annotations

import sys
from pathlib import Path

import _boot  # noqa: F401
from lib.quality import html_a11y_errors


def main(argv: list[str] | None = None) -> int:
    if not argv:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: a11y_check.py guide.html", file=sys.stderr)
        return 2
    html = Path(argv[0]).read_text(encoding="utf-8")
    errors = html_a11y_errors(html)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("HTML accessibility checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
