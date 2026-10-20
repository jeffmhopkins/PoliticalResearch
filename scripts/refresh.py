#!/usr/bin/env python3
"""Plan a refresh pass, optionally open one capped review round, and bump the version."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, today_of, workspace_from
from lib.quality import staleness_findings
from lib.util import dump_json, dump_yaml, load_config, load_json, load_yaml
from lib.workflow import bump_version, fresh_loop_state


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Prepare a refresh. Changed items get one review round when --open-round is set.")
    parser.add_argument("--open-round", action="store_true")
    parser.add_argument("--bump", action="store_true", help="Copy the current guide aside and increment report_version.")
    parser.add_argument("--note", default="", help="Correction note stored when --bump is set.")
    parser.add_argument("--items", nargs="*", default=None)
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    today = today_of(args)
    clock = clock_from(args)
    rows = staleness_findings(workspace, today, int(load_config().get("staleness_days", 7)))
    plan = workspace / "refresh-plan.md"
    lines = [
        f"# Refresh plan {today.isoformat()}",
        "",
        "Re-check the official ballot, finance filings, endorsements, withdrawals, and any stale T1 source.",
        "A refresh uses one review round (`max_rounds_refresh`).",
        "",
        "## Staleness",
        "",
    ]
    if rows:
        lines.extend(f"- {row}" for row in rows)
    else:
        lines.append("- No retrieved date is past the staleness window.")
    lines.append("")
    plan.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {plan}")
    if args.bump:
        ballot_path = workspace / "ballot.yaml"
        ballot = load_yaml(ballot_path) or {}
        previous = ballot.get("report_version") or "v1.0"
        guide = workspace / "final" / "guide.md"
        versions = workspace / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        if guide.exists():
            (versions / f"guide-{previous}.md").write_text(guide.read_text(encoding="utf-8"), encoding="utf-8")
        ballot["report_version"] = bump_version(previous)
        dump_yaml(ballot_path, ballot)
        corrections_path = workspace / "corrections.yaml"
        corrections = load_yaml(corrections_path) or []
        if not isinstance(corrections, list):
            corrections = []
        corrections.append(
            {
                "version": ballot["report_version"],
                "date": today.isoformat(),
                "claim_id": "refresh",
                "change": args.note or "Refresh pass opened.",
                "reason": "Post-share correction or scheduled refresh.",
            }
        )
        dump_yaml(corrections_path, corrections)
        print(f"Version {previous} -> {ballot['report_version']}")
    if args.open_round:
        cap = int(load_config().get("max_rounds_refresh", 1))
        targets = args.items or [item.name for item in (workspace / "items").iterdir() if item.is_dir()]
        for name in targets:
            item = workspace / "items" / name
            state = load_json(item / "loop-state.json") or fresh_loop_state(name, clock, cap)
            state["mode"] = "refresh"
            state["max_rounds"] = cap
            state["round"] = 0
            state["status"] = "researching"
            state["updated_at"] = clock
            dump_json(item / "loop-state.json", state)
            print(f"{name}: refresh round opened with max_rounds={cap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
