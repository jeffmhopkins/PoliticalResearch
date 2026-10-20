"""Shared command-line arguments."""

from __future__ import annotations

import argparse

from lib.util import now_et, resolve_workspace, today_from


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--election-id", "--election", dest="election_id")
    parser.add_argument("--workspace", help="Election workspace path. Defaults to output/<election-id>.")
    parser.add_argument("--today", help="Override today's date as YYYY-MM-DD.")
    parser.add_argument("--now", help="Override the clock as 'YYYY-MM-DD HH:MM ET'.")
    return parser


def workspace_from(args):
    return resolve_workspace(getattr(args, "election_id", None), getattr(args, "workspace", None))


def clock_from(args) -> str:
    return now_et(getattr(args, "now", None))


def today_of(args):
    return today_from(getattr(args, "today", None), getattr(args, "now", None))
