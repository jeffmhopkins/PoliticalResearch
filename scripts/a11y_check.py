#!/usr/bin/env python3
"""Accessibility checks for a built guide HTML file.

Built-in checks always run. pa11y runs when it is on PATH; otherwise axe.
If neither external tool is installed, the built-in result stands and the
process still exits 0 when those checks pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import _boot  # noqa: F401
from lib.a11y import check_html


def main(argv: list[str] | None = None) -> int:
    if not argv:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: a11y_check.py guide.html", file=sys.stderr)
        return 2
    code, message = check_html(Path(argv[0]))
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
