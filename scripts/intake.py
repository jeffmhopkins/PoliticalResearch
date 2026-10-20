#!/usr/bin/env python3
"""Record intake answers, store an address privately, and confirm a ballot."""

from __future__ import annotations

import sys

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
    parser.add_argument("--address")
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
        print(f"Set {args.field}.")
        return 0
    if args.command == "set-address":
        if not args.address:
            print("set-address needs --address. The value is written only under private/.", file=sys.stderr)
            return 2
        set_address(workspace, intake, args.address)
        dump_yaml(intake_path, intake)
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
