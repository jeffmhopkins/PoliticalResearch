#!/usr/bin/env python3
"""Draft ballot.yaml from Google Civic or a configured Democracy Works URL."""

from __future__ import annotations

import sys

import _boot  # noqa: F401
from lib.api_clients import ApiError, contests_from_civic, get_json, scrub_civic_payload
from lib.cli import base_parser, workspace_from
from lib.util import dump_json, dump_yaml, load_dotenv, load_yaml, redact


def _remember_precinct(ballot: dict, payload: dict) -> None:
    """Keep a precinct code. Drop anything that looks like a street address."""
    from lib.util import looks_like_street_address

    raw = payload.get("precinctId") or payload.get("precinct_id") or payload.get("precinct")
    if raw is None:
        return
    text = str(raw).strip()
    if not text or looks_like_street_address(text):
        return
    ballot["precinct"] = text


def _address(workspace, explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    path = workspace / "private" / "address.txt"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Look up a draft ballot. Never invent contests when no API data is available.")
    parser.add_argument("--address", help="Optional address. Prefer private/address.txt so it is not stored in the shell history of a report.")
    args = parser.parse_args(argv)
    workspace = workspace_from(args)
    ballot_path = workspace / "ballot.yaml"
    ballot = load_yaml(ballot_path)
    if not isinstance(ballot, dict):
        print("ballot.yaml is missing. Run intake.py init first.", file=sys.stderr)
        return 1
    keys = load_dotenv()
    address = _address(workspace, args.address)
    if not address:
        ballot["lookup_status"] = "missing_address"
        ballot["lookup_error"] = "No address file. Store one with intake.py set-address or pass an official sample ballot yourself."
        dump_yaml(ballot_path, ballot)
        print("No address on file. Ballot lookup skipped. Fill contests from an official sample ballot and keep the address out of git.")
        return 0
    civic = keys.get("GOOGLE_CIVIC_API_KEY", "").strip()
    democracy_url = keys.get("DEMOCRACY_WORKS_API_URL", "").strip()
    democracy_key = keys.get("DEMOCRACY_WORKS_API_KEY", "").strip()
    if not civic and not (democracy_url and democracy_key):
        ballot["lookup_status"] = "skipped_no_api_key"
        ballot["lookup_source"] = None
        ballot["notes"] = list(ballot.get("notes") or [])
        note = (
            "Ballot lookup skipped: GOOGLE_CIVIC_API_KEY is unset and Democracy Works is not configured. "
            "Use the county Supervisor of Elections finder (for example VoterFocus Find My Precinct and the sample-ballot PDF) "
            "or a sample ballot the requester supplied. Record the precinct code, not the street address, and put an official URL on every contest. "
            "Read a bilingual sample ballot with scripts/lib/ballot_text.py (pdftotext -raw -nodiag) and compare it to the election-office copy. "
            "A token such as Shallll Judge is an extraction error, not a contest name."
        )
        if note not in ballot["notes"]:
            ballot["notes"].append(note)
        dump_yaml(ballot_path, ballot)
        print(note)
        if democracy_key and not democracy_url:
            print("DEMOCRACY_WORKS_API_KEY is set but DEMOCRACY_WORKS_API_URL is empty. Set the URL from your partner docs. No call was made.")
        return 0
    private = workspace / "private"
    private.mkdir(parents=True, exist_ok=True)
    if civic:
        try:
            payload = get_json(
                "https://www.googleapis.com/civicinfo/v2/voterinfo",
                params={"address": address, "officialOnly": "true", "key": civic},
                secrets=[civic, address],
            )
        except ApiError as exc:
            ballot["lookup_status"] = "error"
            ballot["lookup_source"] = "google_civic"
            ballot["lookup_error"] = redact(str(exc), [civic, address])
            dump_yaml(ballot_path, ballot)
            print(f"Google Civic lookup failed ({ballot['lookup_error']}). Existing contests were left unchanged.")
            return 0
        payload = scrub_civic_payload(payload)
        _remember_precinct(ballot, payload)
        dump_json(private / "google-civic.json", payload)
        if ballot.get("contests"):
            ballot["lookup_status"] = "fetched_not_applied"
            ballot["lookup_source"] = "google_civic"
            ballot["notes"] = list(ballot.get("notes") or []) + [
                "Civic response saved to private/google-civic.json. Contests already present were not overwritten."
            ]
            dump_yaml(ballot_path, ballot)
            print("Saved Civic response. Did not overwrite existing contests.")
            return 0
        contests, notes = contests_from_civic(payload)
        election = payload.get("election") or {}
        ballot["contests"] = contests
        ballot["lookup_status"] = "draft"
        ballot["lookup_source"] = "google_civic"
        ballot["confirmed_by_requester"] = False
        ballot["confirmed_at"] = None
        if isinstance(ballot.get("election"), dict):
            ballot["election"]["name"] = election.get("name") or ballot["election"].get("name") or ""
            ballot["election"]["date"] = election.get("electionDay") or ballot["election"].get("date") or ""
        ballot["notes"] = list(ballot.get("notes") or []) + notes + [
            "Draft only. Ask the requester to confirm this contest list before research."
        ]
        dump_yaml(ballot_path, ballot)
        print(f"Drafted {len(contests)} contests from Google Civic with officialOnly=true. Not confirmed.")
        return 0
    try:
        payload = get_json(
            democracy_url,
            headers={"Authorization": f"Bearer {democracy_key}"},
            params={"address": address},
            secrets=[democracy_key, address],
        )
    except ApiError as exc:
        ballot["lookup_status"] = "error"
        ballot["lookup_source"] = "democracy_works"
        ballot["lookup_error"] = redact(str(exc), [democracy_key, address])
        dump_yaml(ballot_path, ballot)
        print(f"Democracy Works lookup failed ({ballot['lookup_error']}). No contests were invented.")
        return 0
    payload = scrub_civic_payload(payload)
    dump_json(private / "democracy-works.json", payload)
    ballot["lookup_status"] = "fetched_unparsed"
    ballot["lookup_source"] = "democracy_works"
    dump_yaml(ballot_path, ballot)
    print("Saved Democracy Works JSON to private/democracy-works.json. Map contests by hand into ballot.yaml and confirm with the requester.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
