#!/usr/bin/env python3
"""Schema-check an election workspace and, with --gate, run the assembly gate."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, today_of, workspace_from
from lib.quality import content_gate_errors
from lib.workflow import gate_errors, structural_workspace_errors


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Validate claims, findings, loop state, and optional phase gates.")
    parser.add_argument("--gate", action="store_true", help="Also require confirmation, sign-off, citations, symmetry, and freshness.")
    parser.add_argument("--file", help="Validate one YAML or JSON file against a named schema.")
    parser.add_argument("--schema", help="Schema file name inside templates/, used with --file.")
    args = parser.parse_args(argv)
    if args.file:
        from pathlib import Path

        import json
        import yaml

        from lib.schema import instance_errors, load_schema

        path = Path(args.file)
        if not args.schema:
            print("Provide --schema with --file.", file=sys.stderr)
            return 2
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if path.suffix == ".json" else yaml.safe_load(raw)
        errors = instance_errors(data, load_schema(args.schema))
        for error in errors:
            print(error)
        return 1 if errors else 0
    workspace = workspace_from(args)
    errors = structural_workspace_errors(workspace)
    if args.gate:
        errors.extend(gate_errors(workspace))
        errors.extend(content_gate_errors(workspace, today_of(args), include_guide=True))
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"OK {workspace}")
    clock_from(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
