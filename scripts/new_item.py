#!/usr/bin/env python3
"""Scaffold items/<id>/ from a template."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, workspace_from
from lib.workflow import TEMPLATE_BY_TYPE, scaffold_item, write_status


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Create an item directory with empty claims, findings, and loop state.")
    parser.add_argument("--id", required=True)
    parser.add_argument("--type", required=True, choices=sorted(TEMPLATE_BY_TYPE))
    parser.add_argument("--title", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-unconfirmed", action="store_true", help="Scaffold even if the ballot is not confirmed.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    errors = scaffold_item(
        workspace,
        args.id,
        args.type,
        args.title,
        clock_from(args),
        force=args.force,
        allow_unconfirmed=args.allow_unconfirmed,
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    write_status(workspace, clock_from(args))
    print(f"Scaffolded items/{args.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
