#!/usr/bin/env python3
"""Open and close review rounds, record sign-off, and enforce the round cap."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, workspace_from
from lib.util import iter_items
from lib.workflow import (
    REVIEWERS,
    close_round,
    enforce_cap,
    open_round,
    record_unchecked,
    review_queue,
    signoff,
    write_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Coordinator helper for the correction loop.")
    parser.add_argument(
        "command",
        choices=["open-round", "close-round", "signoff", "enforce-cap", "status", "note-unchecked", "review-order"],
    )
    parser.add_argument("--item")
    parser.add_argument("--reviewer", choices=REVIEWERS)
    parser.add_argument("--note", action="append", default=None, help="One unchecked item. Repeat for more. Omit for an empty list.")
    parser.add_argument(
        "--same-context",
        action="store_true",
        help="Record that this sign-off happened in the same context as the research.",
    )
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    clock = clock_from(args)
    if args.command == "status":
        print(write_status(workspace, clock))
        return 0
    if args.command == "review-order":
        items = [workspace / "items" / args.item] if args.item else iter_items(workspace)
        if not items:
            print("No items.", file=sys.stderr)
            return 1
        for item in items:
            print(f"## {item.name}")
            print("\n".join(review_queue(item)))
        return 0
    items = [workspace / "items" / args.item] if args.item else iter_items(workspace)
    if not items:
        print("No items.", file=sys.stderr)
        return 1
    errors = []
    for item in items:
        if args.command == "open-round":
            errors.extend(open_round(item, clock))
        elif args.command == "close-round":
            errors.extend(close_round(item, clock))
        elif args.command == "enforce-cap":
            errors.extend(enforce_cap(item, clock))
        elif args.command == "note-unchecked":
            if not args.reviewer:
                print("note-unchecked needs --reviewer.", file=sys.stderr)
                return 2
            errors.extend(record_unchecked(item, args.reviewer, clock, args.note))
        else:
            if not args.reviewer:
                print("signoff needs --reviewer.", file=sys.stderr)
                return 2
            errors.extend(signoff(item, args.reviewer, clock, same_context=args.same_context))
    write_status(workspace, clock)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"{args.command} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
