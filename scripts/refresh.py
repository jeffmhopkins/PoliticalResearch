#!/usr/bin/env python3
"""Plan a refresh pass, optionally open one capped review round, and bump the version."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.cli import base_parser, clock_from, today_of, workspace_from
from lib.quality import staleness_findings
from lib.util import dump_json, dump_yaml, load_config, load_json, load_yaml
from lib.workflow import bump_version, empty_signoffs, fresh_loop_state


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
    note = args.note or "Refresh pass opened."
    corrected_ids: list[str] = []
    saw_claims = False
    if args.open_round or args.bump:
        corrected_ids, saw_claims = _mark_corrected(workspace, note)
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
        logged_ids = corrected_ids if saw_claims else ["refresh"]
        if saw_claims and not corrected_ids:
            logged_ids = []
        for claim_id in logged_ids:
            corrections.append(
                {
                    "version": ballot["report_version"],
                    "date": today.isoformat(),
                    "claim_id": claim_id,
                    "change": note,
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
            state["signoffs"] = empty_signoffs()
            state["updated_at"] = clock
            dump_json(item / "loop-state.json", state)
            print(f"{name}: refresh round opened with max_rounds={cap}")
    return 0


def _claim_fingerprint(claim: dict) -> str:
    import json

    data = {key: value for key, value in claim.items() if key not in {"corrected", "correction_note"}}
    return json.dumps(data, sort_keys=True, default=str)


def _mark_corrected(workspace, note: str) -> tuple[list[str], bool]:
    """Mark claims whose content differs from the last published snapshot. Returns ids and whether any claims exist."""
    claim_ids: list[str] = []
    saw_claims = False
    items = workspace / "items"
    if not items.is_dir():
        return claim_ids, saw_claims
    for item in items.iterdir():
        if not item.is_dir():
            continue
        path = item / "claims.yaml"
        doc = load_yaml(path)
        if not isinstance(doc, dict):
            continue
        baseline_doc = load_yaml(workspace / "versions" / "claims" / f"{item.name}.yaml") or {}
        previous: dict[str, str] = {}
        if isinstance(baseline_doc, dict):
            for claim in baseline_doc.get("claims") or []:
                if isinstance(claim, dict) and claim.get("id"):
                    previous[str(claim.get("id"))] = _claim_fingerprint(claim)
        changed = False
        for claim in doc.get("claims") or []:
            if not isinstance(claim, dict) or claim.get("removed"):
                continue
            saw_claims = True
            cid = str(claim.get("id"))
            fingerprint = _claim_fingerprint(claim)
            if cid in previous and previous[cid] == fingerprint:
                continue
            if not previous and cid not in previous:
                # No published snapshot yet, so this pass cannot show a change.
                continue
            claim["corrected"] = True
            claim["correction_note"] = note
            claim_ids.append(cid)
            changed = True
        if changed:
            dump_yaml(path, doc)
    return claim_ids, saw_claims


if __name__ == "__main__":
    sys.exit(main())
