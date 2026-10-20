#!/usr/bin/env python3
"""Download forum audio and write a timestamped, unreviewed transcript stub."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, workspace_from
from lib.transcripts import transcribe_item
from lib.util import ITEM_ID_RE


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Transcribe a forum or debate URL into items/<id>/imports/transcripts.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--title", default="Forum recording")
    parser.add_argument("--publisher", default="Forum recording")
    parser.add_argument("--keep-media", action="store_true", help="Keep the extracted audio. Off by default.")
    args = parser.parse_args(argv)
    if not ITEM_ID_RE.match(args.item_id):
        print("item-id must be lowercase letters, numbers, and hyphens.", file=sys.stderr)
        return 2
    code, message = transcribe_item(
        workspace_from(args),
        args.item_id,
        args.url,
        title=args.title,
        publisher=args.publisher,
        clock=clock_from(args),
        keep_media=args.keep_media,
    )
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
