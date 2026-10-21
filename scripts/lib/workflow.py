"""Intake files, review-loop state, resume hints, and guide assembly."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from lib.quality import (
    assembled_guide_errors,
    claim_index,
    content_gate_errors,
    environment_rating_sentence,
    identities_for_item,
    iter_claim_sources,
    semantic_claim_errors,
    source_marker,
)
from lib.schema import instance_errors, load_schema
from lib.util import (
    CLAIM_ID_RE,
    FINDING_ID_RE,
    coerce_yaml_dates,
    dump_json,
    dump_yaml,
    iter_items,
    load_config,
    load_json,
    load_yaml,
    looks_like_street_address,
    now_et,
    repo_root,
)

REVIEWERS = ("factcheck", "sourcing", "neutrality", "privacy-legal")
OPEN_STATUSES = {"open", "reopened", "addressed"}
CLOSED_STATUSES = {"accepted", "disputed", "wontfix-approved"}
TEMPLATE_BY_TYPE = {
    "candidate": "candidate.md",
    "race": "race.md",
    "measure": "measure.md",
    "legislation": "legislation.md",
    "judicial-retention": "judicial-retention.md",
    "primary": "primary.md",
    "local-office": "local-office.md",
}
INTAKE_FIELDS = {
    "election_date",
    "election_type",
    "jurisdiction_label",
    "scope",
    "include_legislation",
    "legislation_topics",
    "depth",
    "formats",
    "languages",
    "accessibility_needs",
    "offline_archive",
    "archive_tier",
    "parallel_subagents",
    "notes",
    "requester_label",
}


def empty_signoffs() -> dict:
    return {name: {"signed": False, "at": None, "round": None} for name in REVIEWERS}


def fresh_loop_state(item_id: str, clock: str, max_rounds: int | None = None) -> dict:
    config = load_config()
    return {
        "item_id": item_id,
        "round": 0,
        "max_rounds": int(max_rounds if max_rounds is not None else config.get("max_rounds", 3)),
        "mode": "initial",
        "status": "researching",
        "open_counts": {"blocker": 0, "major": 0, "minor": 0},
        "signoffs": empty_signoffs(),
        "gaps": [],
        "removed_claims": [],
        "updated_at": clock,
    }


def blank_intake(election_id: str, label: str) -> dict:
    return {
        "election_id": election_id,
        "requester_label": label,
        "election_date": "",
        "election_type": "",
        "jurisdiction_label": "",
        "scope": "whole_ballot",
        "contest_ids": [],
        "include_legislation": False,
        "legislation_topics": [],
        "depth": "standard",
        "formats": ["md", "html", "pdf"],
        "languages": ["en"],
        "accessibility_needs": "",
        "offline_archive": False,
        "parallel_subagents": False,
        "address_location": None,
        "sharing_approved": False,
        "sharing_approved_at": None,
        "ballot_photo_deleted": False,
        "notes": "",
    }


def blank_ballot(election_id: str) -> dict:
    return {
        "election_id": election_id,
        "fiction": False,
        "confirmed_by_requester": False,
        "confirmed_at": None,
        "report_version": "v1.0",
        "lookup_status": "not_run",
        "lookup_source": None,
        "lookup_error": None,
        "election": {"name": "", "date": "", "type": "", "jurisdiction": {"state": "", "county": "", "city": ""}},
        "logistics": [],
        "contests": [],
        "conflicts": [],
        "notes": [],
    }


def init_workspace(workspace: Path, election_id: str, label: str, clock: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "items").mkdir(exist_ok=True)
    (workspace / "final").mkdir(exist_ok=True)
    (workspace / "private").mkdir(exist_ok=True)
    (workspace / "imports").mkdir(exist_ok=True)
    intake_path = workspace / "intake.yaml"
    ballot_path = workspace / "ballot.yaml"
    if not intake_path.exists():
        dump_yaml(intake_path, blank_intake(election_id, label))
    if not ballot_path.exists():
        dump_yaml(ballot_path, blank_ballot(election_id))
    env_src = repo_root() / "output" / "env.md"
    env_dest = workspace / "env.md"
    if env_src.exists() and not env_dest.exists():
        env_dest.write_text(env_src.read_text(encoding="utf-8"), encoding="utf-8")
    elif not env_dest.exists():
        env_dest.write_text(
            "# Environment\n\nNot recorded. Run `./bootstrap.sh` and copy `output/env.md` here.\n",
            encoding="utf-8",
        )


def set_intake_field(intake: dict, field: str, value) -> list[str]:
    if field not in INTAKE_FIELDS:
        return [f"Unknown intake field {field}. Address and other personal data are not intake fields."]
    if isinstance(value, str) and looks_like_street_address(value):
        return ["That value looks like a street address. Store it with set-address, not in intake.yaml."]
    intake[field] = value
    return []


def set_address(workspace: Path, intake: dict, address: str) -> None:
    private = workspace / "private"
    private.mkdir(parents=True, exist_ok=True)
    path = private / "address.txt"
    path.write_text(address.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    intake["address_location"] = "private/address.txt"


def confirm_ballot(workspace: Path, clock: str) -> list[str]:
    ballot_path = workspace / "ballot.yaml"
    ballot = load_yaml(ballot_path)
    if not isinstance(ballot, dict):
        return ["ballot.yaml is missing or not a mapping"]
    if ballot.get("confirmed_by_requester") is True:
        return []
    errors = []
    contests = ballot.get("contests") or []
    if not contests:
        errors.append("ballot.yaml has no contests to confirm")
    for contest in contests:
        if not isinstance(contest, dict):
            errors.append("a contest is not a mapping")
            continue
        if not contest.get("id") or not contest.get("official_source_url") or not contest.get("title"):
            errors.append(f"contest {contest.get('id') or '?'} needs id, title, and official_source_url")
        url = str(contest.get("official_source_url") or "")
        if url and not url.startswith(("https://", "http://")):
            errors.append(f"contest {contest.get('id')} official_source_url must be an http(s) URL")
    if errors:
        return errors
    cleanup = _delete_ballot_images(workspace)
    if cleanup == "symlink":
        return [
            "Refusing to confirm: a symlink under private/ points outside private/. "
            "Ballot photos may still be reachable. confirmed_by_requester was not set."
        ]
    ballot["confirmed_by_requester"] = True
    ballot["confirmed_at"] = clock
    dump_yaml(ballot_path, ballot)
    intake_path = workspace / "intake.yaml"
    intake = load_yaml(intake_path) or {}
    if isinstance(intake, dict) and cleanup == "ok":
        intake["ballot_photo_deleted"] = True
        warning = _private_html_address_warning(workspace / "private")
        if warning:
            notes = str(intake.get("notes") or "")
            if warning not in notes:
                intake["notes"] = (notes + " " + warning).strip()
        dump_yaml(intake_path, intake)
    return []


def _resolves_inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


_PRIVATE_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".pdf", ".webp", ".gif", ".tif", ".tiff"}


def _is_private_media(path: Path, target_suffix: str = "") -> bool:
    """Every image and PDF under private/ is a ballot photo, whatever its file name."""
    suffix = path.suffix.lower()
    return suffix in _PRIVATE_MEDIA_SUFFIXES or target_suffix in _PRIVATE_MEDIA_SUFFIXES


def _private_html_address_warning(private: Path) -> str | None:
    if not private.is_dir() or private.is_symlink():
        return None
    for path in private.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if looks_like_street_address(text):
            return (
                f"{path.name} under private/ contains a street address. "
                "Leave it in private/ and do not copy it into the guide, a commit, or an artifact."
            )
    return None


def _delete_ballot_images(workspace: Path) -> str:
    """Delete every image and PDF under private/.

    Returns ``ok`` when none remain, ``stuck`` when one could not be removed,
    or ``symlink`` when a link points outside private/. Only ``symlink`` blocks
    confirmation. The caller sets ``ballot_photo_deleted`` only after ``ok``.
    ``address.txt`` and other non-image files stay.
    """
    private = workspace / "private"
    if private.is_symlink():
        return "symlink"
    if not private.is_dir():
        return "ok"
    symlink_hit = False
    for root, dirnames, filenames in os.walk(private, followlinks=False):
        root_path = Path(root)
        for dirname in dirnames:
            entry = root_path / dirname
            try:
                if entry.is_symlink() and not _resolves_inside(entry, private):
                    symlink_hit = True
            except OSError:
                symlink_hit = True
        for filename in filenames:
            entry = root_path / filename
            try:
                target_suffix = ""
                if entry.is_symlink():
                    try:
                        target_suffix = entry.resolve(strict=False).suffix.lower()
                    except (OSError, RuntimeError):
                        symlink_hit = True
                        continue
                    inside = _resolves_inside(entry, private)
                    if not inside and not _is_private_media(entry, target_suffix):
                        continue
                    if not inside:
                        symlink_hit = True
                        continue
                if _is_private_media(entry, target_suffix):
                    try:
                        entry.unlink()
                    except OSError:
                        pass
            except OSError:
                pass
    if symlink_hit:
        return "symlink"
    for root, dirnames, filenames in os.walk(private, followlinks=False):
        root_path = Path(root)
        for dirname in dirnames:
            entry = root_path / dirname
            if entry.is_symlink() and not _resolves_inside(entry, private):
                return "symlink"
        for filename in filenames:
            entry = root_path / filename
            target_suffix = ""
            if entry.is_symlink():
                try:
                    if not _resolves_inside(entry, private):
                        return "symlink"
                    target_suffix = entry.resolve(strict=False).suffix.lower()
                except (OSError, RuntimeError):
                    return "symlink"
            if _is_private_media(entry, target_suffix):
                return "stuck"
    return "ok"


def approve_sharing(workspace: Path, clock: str) -> list[str]:
    guide = workspace / "final" / "guide.md"
    if not guide.exists():
        return ["final/guide.md does not exist yet. Assemble the guide before recording approval to share."]
    intake_path = workspace / "intake.yaml"
    intake = load_yaml(intake_path) or {}
    if not isinstance(intake, dict):
        return ["intake.yaml is missing"]
    intake["sharing_approved"] = True
    intake["sharing_approved_at"] = clock
    dump_yaml(intake_path, intake)
    return []


def load_findings(item: Path) -> list:
    data = load_yaml(item / "findings.yaml")
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{item / 'findings.yaml'} must be a list")
    return data


def save_findings(item: Path, findings: list) -> None:
    dump_yaml(item / "findings.yaml", findings)


def recount(findings: list) -> dict:
    counts = {"blocker": 0, "major": 0, "minor": 0}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("status") in OPEN_STATUSES:
            severity = finding.get("severity")
            if severity in counts:
                counts[severity] += 1
    return counts


def next_changelog_id(item: Path) -> str:
    text = ""
    path = item / "CHANGELOG.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    numbers = [int(value) for value in re.findall(r"CL-(\d{4})", text)]
    return f"CL-{(max(numbers) if numbers else 0) + 1:04d}"


def append_changelog(item: Path, line: str) -> None:
    path = item / "CHANGELOG.md"
    if not path.exists():
        path.write_text(
            "# Changelog\n\n"
            "Format: `CL-id | round | finding id | claim id | before -> after | reason | timestamp ET`\n\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def open_round(item: Path, clock: str) -> list[str]:
    state_path = item / "loop-state.json"
    state = load_json(state_path)
    if not isinstance(state, dict):
        return ["loop-state.json is missing"]
    if state.get("status") in {"signed-off", "capped-disputed"}:
        return [f"Item is already {state.get('status')}"]
    state["round"] = int(state.get("round") or 0) + 1
    state["status"] = "in-review"
    state["signoffs"] = empty_signoffs()
    state["open_counts"] = recount(load_findings(item))
    state["updated_at"] = clock
    dump_json(state_path, state)
    return []


def signoff(item: Path, reviewer: str, clock: str, *, same_context: bool = False) -> list[str]:
    if reviewer not in REVIEWERS:
        return [f"Unknown reviewer {reviewer}. Use one of: {', '.join(REVIEWERS)}"]
    state_path = item / "loop-state.json"
    state = load_json(state_path)
    if not isinstance(state, dict):
        return ["loop-state.json is missing"]
    pending = [
        finding.get("id")
        for finding in load_findings(item)
        if isinstance(finding, dict)
        and finding.get("reviewer") == reviewer
        and finding.get("status") not in CLOSED_STATUSES
    ]
    if pending:
        return [f"{reviewer} still has unresolved findings: {', '.join(str(item_id) for item_id in pending)}"]
    if same_context:
        state.setdefault("process_gaps", []).append(
            f"{reviewer} signed off in the same context as the research. "
            "This is a process gap, not a fresh-context review."
        )
    state["signoffs"][reviewer] = {"signed": True, "at": clock, "round": state.get("round")}
    state["updated_at"] = clock
    dump_json(state_path, state)
    return []


def close_round(item: Path, clock: str) -> list[str]:
    state_path = item / "loop-state.json"
    state = load_json(state_path)
    if not isinstance(state, dict):
        return ["loop-state.json is missing"]
    findings = load_findings(item)
    state["open_counts"] = recount(findings)
    unresolved = [f for f in findings if isinstance(f, dict) and f.get("status") in OPEN_STATUSES]
    signoffs = state.get("signoffs") or {}
    all_signed = all((signoffs.get(name) or {}).get("signed") for name in REVIEWERS)
    if unresolved and int(state.get("round") or 0) >= int(state.get("max_rounds") or 3):
        dump_json(state_path, state)
        return enforce_cap(item, clock)
    if unresolved:
        state["status"] = "fixing"
    elif all_signed and int(state.get("round") or 0) >= 1:
        state["status"] = "signed-off"
    else:
        state["status"] = "in-review"
    state["updated_at"] = clock
    dump_json(state_path, state)
    return []


def enforce_cap(item: Path, clock: str) -> list[str]:
    state_path = item / "loop-state.json"
    claims_path = item / "claims.yaml"
    state = load_json(state_path)
    claims_doc = load_yaml(claims_path)
    if not isinstance(state, dict) or not isinstance(claims_doc, dict):
        return ["loop-state.json and claims.yaml are required before cap enforcement"]
    findings = load_findings(item)
    claims = {claim.get("id"): claim for claim in claims_doc.get("claims") or [] if isinstance(claim, dict)}
    notes = []
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("status") not in OPEN_STATUSES:
            continue
        severity = finding.get("severity")
        claim = claims.get(finding.get("claim_id"))
        change_id = next_changelog_id(item)
        if severity == "blocker":
            if claim is not None:
                before = "active"
                claim["removed"] = True
                claim["removal_reason"] = finding.get("issue") or "Unresolved blocker at round cap"
                claim["drives_summary"] = False
                claim["confidence"] = "unconfirmed"
                state.setdefault("removed_claims", []).append(claim.get("id"))
                state.setdefault("gaps", []).append(f"Removed {claim.get('id')}: {finding.get('issue')}")
            else:
                before = "missing claim"
            finding["status"] = "accepted"
            finding["coordinator_note"] = "Blocker at cap: claim removed and gap noted. Coordinator script only."
            after = "REMOVED"
            reason = "Unresolved blocker at MAX_ROUNDS"
        elif severity == "major":
            before = (claim or {}).get("confidence", "unknown") if claim else "missing claim"
            if claim is not None:
                claim["confidence"] = "disputed"
                claim["drives_summary"] = False
            finding["status"] = "disputed"
            finding["coordinator_note"] = (
                "Major finding unresolved at MAX_ROUNDS. Both the reviewer concern and the claim stay visible. "
                "This claim cannot drive a summary."
            )
            after = "disputed"
            reason = "Unresolved major at MAX_ROUNDS"
        else:
            before = finding.get("status")
            finding["status"] = "wontfix-approved"
            finding["coordinator_note"] = "Minor finding left at cap with coordinator approval."
            after = "wontfix-approved"
            reason = "Minor at MAX_ROUNDS"
        append_changelog(
            item,
            f"{change_id} | {state.get('round')} | {finding.get('id')} | {finding.get('claim_id')} | "
            f"{before} -> {after} | {reason} | {clock}",
        )
        notes.append(f"{finding.get('id')} -> {finding.get('status')}")
    remaining = [
        f for f in findings if isinstance(f, dict) and f.get("severity") == "blocker" and f.get("status") in OPEN_STATUSES
    ]
    disputed = [f for f in findings if isinstance(f, dict) and f.get("status") == "disputed"]
    state["open_counts"] = recount(findings)
    state["status"] = "capped-disputed" if disputed else "signed-off"
    state["updated_at"] = clock
    if remaining:
        notes.append("Blockers remain open after cap; assembly stays blocked.")
    save_findings(item, findings)
    dump_yaml(claims_path, claims_doc)
    dump_json(state_path, state)
    return []


def item_statuses(workspace: Path) -> list[tuple[str, str]]:
    rows = []
    for item in iter_items(workspace):
        state = load_json(item / "loop-state.json") or {}
        rows.append((item.name, str((state or {}).get("status") or "missing")))
    return rows


def gate_errors(workspace: Path) -> list[str]:
    errors = []
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    if not isinstance(ballot, dict) or ballot.get("confirmed_by_requester") is not True:
        errors.append("Ballot is not confirmed by the requester. Research and assembly stay closed.")
    rows = item_statuses(workspace)
    if not rows:
        errors.append("No items exist yet.")
    for name, status in rows:
        if status not in {"signed-off", "capped-disputed"}:
            errors.append(f"{name}: status is {status}, not signed-off or capped-disputed")
        findings = load_findings(workspace / "items" / name)
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            if finding.get("severity") == "blocker" and finding.get("status") in OPEN_STATUSES | {"disputed"}:
                errors.append(f"{name}: blocker {finding.get('id')} is still {finding.get('status')}")
            if finding.get("status") in {"open", "reopened"}:
                errors.append(f"{name}: finding {finding.get('id')} is {finding.get('status')}")
        identity_path = workspace / "items" / name / "identity.yaml"
        if identity_path.exists() and status in {"signed-off", "capped-disputed"}:
            identity = load_yaml(identity_path) or {}
            if not str(identity.get("full_legal_name") or "").strip() or not str(identity.get("ballot_name") or "").strip():
                errors.append(f"{name}: identity.yaml needs a full legal name and ballot name before assembly")
            if identity.get("photo_included") is True:
                errors.append(f"{name}: identity.yaml must stay photo-free")
    return errors


def _draft_looks_ready(item: Path) -> bool:
    """True when claims exist and the draft is no longer the untouched scaffold."""
    doc = load_yaml(item / "claims.yaml") or {}
    claims = doc.get("claims") if isinstance(doc, dict) else None
    if not claims:
        return False
    draft_path = item / "draft.md"
    if not draft_path.exists():
        return False
    text = draft_path.read_text(encoding="utf-8")
    if "Not found (searched: not started)." in text and "[^" not in text:
        return False
    return "[^" in text


def next_actions(workspace: Path) -> list[str]:
    if not workspace.exists():
        return ["Create a workspace with scripts/intake.py init."]
    intake = load_yaml(workspace / "intake.yaml")
    ballot = load_yaml(workspace / "ballot.yaml")
    actions = []
    if not isinstance(intake, dict):
        actions.append("Run intake init. intake.yaml is missing.")
        return actions
    if not str(intake.get("election_date") or "").strip() or not str(intake.get("jurisdiction_label") or "").strip():
        actions.append("Finish intake: set election_date, election_type, jurisdiction_label, scope, depth, formats, offline_archive.")
    if not isinstance(ballot, dict):
        actions.append("Create ballot.yaml with the ballot finder. Do not invent contests.")
        return actions
    if ballot.get("lookup_status") in {None, "not_run", "skipped_no_api_key", "missing_address"} and not ballot.get("contests"):
        actions.append("Run ballot_lookup.py or fill ballot.yaml from an official sample ballot. Every contest needs an official source URL.")
    if ballot.get("confirmed_by_requester") is not True:
        actions.append("Stop. Ask the requester to confirm or correct the contest list, then run intake.py confirm.")
        return actions
    for name, status in item_statuses(workspace):
        if status == "researching":
            item = workspace / "items" / name
            if _draft_looks_ready(item):
                actions.append(f"{name}: draft is in place. Run loop.py open-round.")
            else:
                actions.append(f"{name}: research and draft, then loop.py open-round.")
        elif status == "in-review":
            actions.append(f"{name}: reviewers file findings or sign off, then loop.py close-round.")
        elif status == "fixing":
            actions.append(f"{name}: researcher answers every open finding, then reviewers re-review.")
        elif status in {"signed-off", "capped-disputed"}:
            continue
        else:
            actions.append(f"{name}: unrecognized status {status}.")
    if not item_statuses(workspace):
        actions.append("Ballot is confirmed. Scaffold one item per contest with new_item.py. Do not start before confirmation on a real run.")
    blocked = gate_errors(workspace)
    guide = workspace / "final" / "guide.md"
    if blocked:
        return actions
    if not guide.exists():
        actions.append("All items are signed off or capped. Run assemble.py, then build.sh.")
        return actions
    actions.append("Guide exists. Run build.sh if HTML or PDF is missing.")
    if intake.get("sharing_approved") is not True:
        actions.append("Ask the requester to review the guide. Record approval with intake.py approve-sharing before any sharing.")
    else:
        actions.append("Requester approved sharing. A refresh pass is optional.")
    return actions


def write_status(workspace: Path, clock: str) -> str:
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    intake = load_yaml(workspace / "intake.yaml") or {}
    lines = [
        "# Status",
        "",
        f"Updated: {clock}",
        "",
        f"- Election: `{ballot.get('election_id', '')}`",
        f"- Ballot confirmed: {ballot.get('confirmed_by_requester')}",
        f"- Sharing approved: {intake.get('sharing_approved') if isinstance(intake, dict) else False}",
        "",
        "## Items",
        "",
        "| Item | Status | Round | Open blocker | Open major | Open minor |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in iter_items(workspace):
        state = load_json(item / "loop-state.json") or {}
        counts = state.get("open_counts") or {}
        lines.append(
            f"| {item.name} | {state.get('status', 'missing')} | {state.get('round', '')} | "
            f"{counts.get('blocker', '')} | {counts.get('major', '')} | {counts.get('minor', '')} |"
        )
    lines.extend(["", "## Next actions", ""])
    for action in next_actions(workspace):
        lines.append(f"- {action}")
    blockers = gate_errors(workspace)
    lines.extend(["", "## Assembly gate", ""])
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- Open. Every item is signed off or capped, and no blocker is open.")
    text = "\n".join(lines) + "\n"
    (workspace / "STATUS.md").write_text(text, encoding="utf-8")
    return text


def scaffold_item(
    workspace: Path,
    item_id: str,
    item_type: str,
    title: str,
    clock: str,
    force: bool = False,
    allow_unconfirmed: bool = False,
) -> list[str]:
    if item_type not in TEMPLATE_BY_TYPE:
        return [f"Unknown item type {item_type}"]
    ballot = load_yaml(workspace / "ballot.yaml") or {}
    confirmed = isinstance(ballot, dict) and ballot.get("confirmed_by_requester") is True
    if not confirmed and not allow_unconfirmed:
        return ["Refusing to scaffold research items before the requester confirms the ballot."]
    item = workspace / "items" / item_id
    item.mkdir(parents=True, exist_ok=True)
    (item / "sources").mkdir(exist_ok=True)
    claims_path = item / "claims.yaml"
    if claims_path.exists() and not force:
        return []
    templates = repo_root() / "templates"
    if item_type == "primary":
        template = (templates / "candidate.md").read_text(encoding="utf-8") + "\n" + (templates / "primary.md").read_text(encoding="utf-8")
    elif item_type == "local-office":
        template = (templates / "candidate.md").read_text(encoding="utf-8") + "\n" + (templates / "local-office.md").read_text(encoding="utf-8")
    else:
        template = (templates / TEMPLATE_BY_TYPE[item_type]).read_text(encoding="utf-8")
    draft = f"# {title}\n\n" + template
    (item / "draft.md").write_text(draft, encoding="utf-8")
    dump_yaml(claims_path, {"item_id": item_id, "item_type": item_type, "claims": []})
    save_findings(item, [])
    dump_json(item / "loop-state.json", fresh_loop_state(item_id, clock))
    dump_json(
        item / "effort.json",
        {"item_id": item_id, "searches": 0, "fetches": 0, "minutes": 0, "sections": {}, "explanation": ""},
    )
    changelog = item / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text(
            "# Changelog\n\n"
            "Format: `CL-id | round | finding id | claim id | before -> after | reason | timestamp ET`\n",
            encoding="utf-8",
        )
    if item_type in {"candidate", "primary", "local-office"}:
        dump_yaml(
            item / "identity.yaml",
            {
                "item_id": item_id,
                "full_legal_name": "",
                "ballot_name": title,
                "office": "",
                "district": "",
                "city": "",
                "county": "",
                "state": "",
                "filing_ids": [],
                "campaign_site": "",
                "description": "",
                "photo_included": False,
            },
        )
    return []


def format_work(marker: int, source: dict) -> str:
    published = source.get("published")
    published_bit = "undated" if published == "undated" else published
    if source.get("archive_url"):
        archived = source["archive_url"]
    else:
        archived = f"capture failed ({source.get('archive_failed_reason') or 'unspecified'})"
    line = (
        f'[{marker}] {source.get("publisher")}. "{source.get("title")}." '
        f'{source.get("doc_type")}, published {published_bit}. {source.get("url")} — '
        f'Archived: {archived}. Retrieved {source.get("retrieved")}. '
        f'Tier {source.get("tier")}. Locator: {source.get("locator")}.'
    )
    if source.get("local_copy"):
        line += f' Local copy: {source["local_copy"]}.'
    return line


def footnote_line(marker: int, source: dict) -> str:
    published = source.get("published")
    published_bit = "undated" if published == "undated" else published
    if source.get("archive_url"):
        archived = source["archive_url"]
    else:
        archived = f"capture failed ({source.get('archive_failed_reason') or 'unspecified'})"
    body = (
        f'{source.get("publisher")}. "{source.get("title")}." {source.get("doc_type")}, published {published_bit}. '
        f'{source.get("url")} — Archived: {archived}. Retrieved {source.get("retrieved")}. '
        f'Tier {source.get("tier")}. Locator: {source.get("locator")}.'
    )
    if source.get("local_copy"):
        body += f' Local copy: {source["local_copy"]}.'
    return f"[^{marker}]: {body}"


def _effort_rows(workspace: Path) -> list[str]:
    rows = ["| Item | Searches | Fetches | Minutes |", "| --- | --- | --- | --- |"]
    for item in iter_items(workspace):
        effort = load_json(item / "effort.json") or {}
        rows.append(
            f"| {item.name} | {effort.get('searches', '')} | {effort.get('fetches', '')} | {effort.get('minutes', '')} |"
        )
    return rows


def _finding_counts(workspace: Path) -> dict[str, int]:
    counts = {"total": 0, "disputed": 0, "blocker": 0, "major": 0, "minor": 0, "accepted": 0}
    for item in iter_items(workspace):
        for finding in load_findings(item):
            if not isinstance(finding, dict):
                continue
            counts["total"] += 1
            status = finding.get("status")
            severity = finding.get("severity")
            if status == "disputed":
                counts["disputed"] += 1
            if status == "accepted":
                counts["accepted"] += 1
            if severity in counts:
                counts[severity] += 1
    return counts


def snapshot_guide(versions: Path, previous: str, today: str) -> Path:
    """Copy a previous guide using the version inside that file. Never overwrite a same-day snapshot."""
    match = re.search(r"^version:\s*(\S+)", previous, re.M)
    old = match.group(1) if match else "v0"
    dest = versions / f"guide-{old}-{today}.md"
    suffix = 2
    while dest.exists():
        dest = versions / f"guide-{old}-{today}-{suffix}.md"
        suffix += 1
    versions.mkdir(parents=True, exist_ok=True)
    dest.write_text(previous, encoding="utf-8")
    return dest


def assemble_guide(workspace: Path, today: str) -> list[str]:
    blocked = gate_errors(workspace)
    blocked.extend(structural_workspace_errors(workspace))
    blocked.extend(content_gate_errors(workspace, date.fromisoformat(today), include_guide=False))
    if blocked:
        return blocked
    from lib.guide_layout import build_editions

    reader, reader_sources, full, full_sources = build_editions(workspace, today)
    index = claim_index(workspace)
    guide_problems = assembled_guide_errors(reader, index, reader_sources, reader=True)
    guide_problems.extend(assembled_guide_errors(full, index, full_sources, reader=False))
    if guide_problems:
        return guide_problems
    final = workspace / "final"
    final.mkdir(parents=True, exist_ok=True)
    versions = workspace / "versions"
    for name, text in (
        ("guide.md", reader),
        ("guide-sources.md", reader_sources),
        ("guide-full.md", full),
        ("guide-full-sources.md", full_sources),
    ):
        guide = final / name
        if guide.exists():
            previous = guide.read_text(encoding="utf-8")
            if previous != text:
                snapshot_guide(versions, previous, today)
        guide.write_text(text, encoding="utf-8")
    _write_claim_baselines(workspace)
    return []





def _write_claim_baselines(workspace: Path) -> None:
    dest = workspace / "versions" / "claims"
    dest.mkdir(parents=True, exist_ok=True)
    for item in iter_items(workspace):
        doc = load_yaml(item / "claims.yaml")
        if isinstance(doc, dict):
            dump_yaml(dest / f"{item.name}.yaml", doc)


def structural_workspace_errors(workspace: Path) -> list[str]:
    errors: list[str] = []
    root = repo_root()
    file_map = {
        workspace / "ballot.yaml": "ballot.schema.yaml",
        workspace / "intake.yaml": "intake.schema.yaml",
    }
    for path, schema_name in file_map.items():
        if not path.exists():
            errors.append(f"Missing {path.name}")
            continue
        data = coerce_yaml_dates(load_yaml(path))
        errors.extend(f"{path.name}: {message}" for message in instance_errors(data, load_schema(schema_name, str(root))))
        blob = path.read_text(encoding="utf-8")
        if looks_like_street_address(blob):
            errors.append(f"{path.name} contains a street address. Keep addresses in private/ only.")
    draft_parts = []
    for item in iter_items(workspace):
        draft_path = item / "draft.md"
        if draft_path.exists():
            draft_parts.append(draft_path.read_text(encoding="utf-8"))
    combined_draft = "\n".join(draft_parts)
    for item in iter_items(workspace):
        claims_path = item / "claims.yaml"
        if claims_path.exists():
            doc = coerce_yaml_dates(load_yaml(claims_path))
            errors.extend(
                f"{item.name}/claims.yaml: {message}"
                for message in instance_errors(doc, load_schema("claims.schema.yaml", str(root)))
            )
            if isinstance(doc, dict):
                errors.extend(
                    semantic_claim_errors(
                        doc,
                        f"{item.name}/claims.yaml",
                        identities_for_item(workspace, item, doc),
                        draft=combined_draft,
                    )
                )
                if doc.get("item_type") == "candidate":
                    identity_path = item / "identity.yaml"
                    if not identity_path.exists():
                        errors.append(f"{item.name}: candidate item is missing identity.yaml")
                    else:
                        identity = load_yaml(identity_path)
                        errors.extend(
                            f"{item.name}/identity.yaml: {message}"
                            for message in instance_errors(identity, load_schema("identity.schema.yaml", str(root)))
                        )
        findings_path = item / "findings.yaml"
        if findings_path.exists():
            findings = load_yaml(findings_path)
            errors.extend(
                f"{item.name}/findings.yaml: {message}"
                for message in instance_errors(findings, load_schema("findings.schema.yaml", str(root)))
            )
            errors.extend(_finding_semantic_errors(item, findings if isinstance(findings, list) else []))
        state_path = item / "loop-state.json"
        if state_path.exists():
            state = load_json(state_path)
            errors.extend(
                f"{item.name}/loop-state.json: {message}"
                for message in instance_errors(state, load_schema("loop-state.schema.json", str(root)))
            )
        profile_path = item / "profile.yaml"
        if profile_path.exists():
            profile = coerce_yaml_dates(load_yaml(profile_path))
            errors.extend(
                f"{item.name}/profile.yaml: {message}"
                for message in instance_errors(profile, load_schema("profile.schema.yaml", str(root)))
            )
        effort_path = item / "effort.json"
        if effort_path.exists():
            effort = load_json(effort_path)
            errors.extend(
                f"{item.name}/effort.json: {message}"
                for message in instance_errors(effort, load_schema("effort.schema.json", str(root)))
            )
    return errors


def _finding_semantic_errors(item: Path, findings: list) -> list[str]:
    errors = []
    changelog = ""
    path = item / "CHANGELOG.md"
    if path.exists():
        changelog = path.read_text(encoding="utf-8")
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        fid = str(finding.get("id"))
        if not FINDING_ID_RE.match(fid):
            errors.append(f"{item.name}: finding id {fid} is not F-0000")
        claim_id = str(finding.get("claim_id") or "")
        if claim_id and not CLAIM_ID_RE.match(claim_id):
            errors.append(f"{item.name}: {fid} claim_id {claim_id} is malformed")
        status = finding.get("status")
        response = finding.get("response")
        if status in {"addressed", "accepted", "reopened"} and not isinstance(response, dict):
            errors.append(f"{item.name}: {fid} status {status} needs a response")
        if isinstance(response, dict):
            action = response.get("action")
            if action in {"rebut", "dispute"} and not response.get("evidence"):
                errors.append(f"{item.name}: {fid} action {action} needs new evidence")
            if action == "fix" and not response.get("changelog_ref"):
                errors.append(f"{item.name}: {fid} fix needs changelog_ref")
            ref = response.get("changelog_ref")
            if ref and ref not in changelog:
                errors.append(f"{item.name}: {fid} changelog_ref {ref} is not in CHANGELOG.md")
        if int(finding.get("round") or 0) > 1 and finding.get("severity") in {"major", "minor"} and not finding.get("caused_by_edit"):
            errors.append(f"{item.name}: {fid} is a new non-blocker after round 1 without caused_by_edit")
    return errors


def bump_version(version: str) -> str:
    match = re.match(r"^v(\d+)\.(\d+)$", version or "")
    if not match:
        return "v1.1"
    return f"v{match.group(1)}.{int(match.group(2)) + 1}"
