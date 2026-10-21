#!/usr/bin/env python3
"""Record intake answers, store an address privately, and confirm a ballot."""

from __future__ import annotations

import sys
from pathlib import Path

import _boot  # noqa: F401
import yaml
from lib.cli import base_parser, clock_from, workspace_from
from lib.util import dump_yaml, load_yaml
from lib.workflow import approve_sharing, confirm_ballot, init_workspace, set_address, set_intake_field, write_status


def _coerce(value: str):
    lowered = value.strip().lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if value.startswith("[") or value.startswith("{"):
        return yaml.safe_load(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Intake interview recorder.")
    parser.add_argument("command", choices=["init", "set", "set-address", "show", "confirm", "gate", "approve-sharing"])
    parser.add_argument("--label", default="requester")
    parser.add_argument("--field")
    parser.add_argument("--value")
    parser.add_argument("--address", help="Avoid this. It stores the street address in shell history.")
    parser.add_argument("--address-file", help="Read the address from a mode-600 file instead of the command line.")
    args = parser.parse_args(argv)
    if args.command == "init" and not args.election_id and not args.workspace:
        print("init needs --election-id.", file=sys.stderr)
        return 2
    election_id = args.election_id or "session"
    workspace = workspace_from(args) if args.command != "init" or args.workspace or args.election_id else None
    if args.command == "init":
        workspace = workspace_from(args)
        init_workspace(workspace, election_id, args.label, clock_from(args))
        write_status(workspace, clock_from(args))
        print(f"Initialized {workspace}")
        return 0
    workspace = workspace_from(args)
    intake_path = workspace / "intake.yaml"
    intake = load_yaml(intake_path)
    if not isinstance(intake, dict):
        print("intake.yaml is missing. Run init first.", file=sys.stderr)
        return 1
    clock = clock_from(args)
    if args.command == "set":
        if not args.field or args.value is None:
            print("set needs --field and --value.", file=sys.stderr)
            return 2
        errors = set_intake_field(intake, args.field, _coerce(args.value))
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        dump_yaml(intake_path, intake)
        write_status(workspace, clock)
        if args.field == "offline_archive":
            from lib.archive import estimate_archive_size

            tier = str(intake.get("archive_tier") or "html-pdf")
            print(estimate_archive_size(0, tier if intake.get("offline_archive") is True else "html-pdf"))
            if intake.get("offline_archive") == "pending":
                print("offline_archive is pending. The archive does not run until it is set to true.")
        print(f"Set {args.field}.")
        return 0
    if args.command == "set-address":
        parser_file = getattr(args, "address_file", None)
        if parser_file:
            address = Path(parser_file).read_text(encoding="utf-8")
        elif args.address:
            print(
                "Warning: --address puts the street address in shell history. Prefer stdin or --address-file.",
                file=sys.stderr,
            )
            address = args.address
        elif not sys.stdin.isatty():
            address = sys.stdin.read()
        else:
            print(
                "set-address reads the address from stdin or --address-file. "
                "--address is recorded in shell history.",
                file=sys.stderr,
            )
            return 2
        if not address.strip():
            print("set-address received an empty address.", file=sys.stderr)
            return 2
        set_address(workspace, intake, address)
        dump_yaml(intake_path, intake)
        write_status(workspace, clock)
        print("Address stored at private/address.txt. It is not in intake.yaml.")
        return 0
    if args.command == "show":
        print(intake_path.read_text(encoding="utf-8"))
        return 0
    if args.command == "confirm":
        errors = confirm_ballot(workspace, clock)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        write_status(workspace, clock)
        print("Ballot confirmed. Research may start.")
        return 0
    if args.command == "gate":
        ballot = load_yaml(workspace / "ballot.yaml") or {}
        if not isinstance(ballot, dict) or ballot.get("confirmed_by_requester") is not True:
            print("Ballot is not confirmed. Do not start research.", file=sys.stderr)
            return 1
        print("Ballot confirmation gate is open.")
        return 0
    errors = approve_sharing(workspace, clock)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    write_status(workspace, clock)
    print("Sharing approval recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
