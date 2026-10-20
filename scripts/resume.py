#!/usr/bin/env python3
"""Print the next action for an existing election workspace."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, workspace_from
from lib.workflow import next_actions, write_status


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Read files on disk and print the next action. Run this first when a workspace already exists.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    if not workspace.exists():
        print(f"No workspace at {workspace}. Start with scripts/intake.py init.")
        return 0
    write_status(workspace, clock_from(args))
    print(f"Workspace: {workspace}")
    for action in next_actions(workspace):
        print(f"- {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
