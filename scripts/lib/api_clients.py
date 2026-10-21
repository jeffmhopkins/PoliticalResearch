"""Optional data-source clients. They never invent records when a key or network call is missing."""

from __future__ import annotations

from lib.util import redact, safe_request


class ApiError(RuntimeError):
    pass


_CIVIC_DROP = {
    "normalizedinput",
    "mailonly",
    "pollinglocations",
    "earlyvotesites",
    "dropofflocations",
    "address",
    # precinctId stays. It is a precinct code, not a street address.
}


def scrub_civic_payload(payload: dict) -> dict:
    def walk(value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                if str(key).lower() in _CIVIC_DROP:
                    continue
                cleaned[key] = walk(item)
            return cleaned
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    walked = walk(payload)
    return walked if isinstance(walked, dict) else {}


def _http_url(value: str | None) -> str | None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return value
    return None


def contests_from_civic(payload: dict) -> tuple[list[dict], list[str]]:
    """Map a Civic voterInfo response into draft contests. Returns contests and notes."""
    notes: list[str] = []
    official_urls: list[str] = []
    for state in payload.get("state") or []:
        if not isinstance(state, dict):
            continue
        for source in state.get("sources") or []:
            if isinstance(source, dict):
                url = _http_url(source.get("name")) or _http_url(source.get("officialUrl"))
                if url:
                    official_urls.append(url)
    fallback = official_urls[0] if official_urls else None
    if fallback is None:
        notes.append("Google Civic did not return an official URL. Attach the county sample-ballot URL before confirmation.")
    contests = []
    for index, contest in enumerate(payload.get("contests") or [], start=1):
        if not isinstance(contest, dict):
            continue
        referendum = contest.get("referendumTitle") or contest.get("referendumSubtitle")
        if referendum:
            url = _http_url(contest.get("referendumUrl")) or fallback
            contests.append(
                {
                    "id": f"measure-{index}",
                    "type": "measure",
                    "title": referendum,
                    "item_id": f"measure-{index}",
                    "official_source_url": url,
                    "district": (contest.get("district") or {}).get("name") if isinstance(contest.get("district"), dict) else "",
                    "candidates": [],
                }
            )
            if not url:
                notes.append(f"measure-{index} has no official URL yet.")
            continue
        office = contest.get("office") or contest.get("ballotTitle") or f"Contest {index}"
        candidates = []
        for cand_index, candidate in enumerate(contest.get("candidates") or [], start=1):
            if not isinstance(candidate, dict) or not candidate.get("name"):
                continue
            slug = f"cand-{index}-{cand_index}"
            row = {
                "id": slug,
                "item_id": slug,
                "name": candidate.get("name"),
                "withdrawn": False,
                "write_in": False,
                "limited_public_record": False,
            }
            if candidate.get("party"):
                row["party"] = candidate.get("party")
            if candidate.get("incumbent") is True:
                row["incumbent"] = True
            campaign = _http_url(candidate.get("candidateUrl"))
            if campaign:
                row["campaign_url"] = campaign
            candidates.append(row)
        url = fallback
        contests.append(
            {
                "id": f"race-{index}",
                "type": "race",
                "title": office,
                "item_id": f"race-{index}",
                "official_source_url": url,
                "district": (contest.get("district") or {}).get("name") if isinstance(contest.get("district"), dict) else "",
                "candidates": candidates,
            }
        )
        if not url:
            notes.append(f"race-{index} has no official URL yet.")
    return contests, notes


def _fec_results(payload: dict) -> list[dict]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    return [row for row in results if isinstance(row, dict)]


def fec_aliases_from_payloads(candidate_id: str, candidate_payload: dict, committees: list[dict]) -> list[dict]:
    """Names from the candidate record and committee treasurer fields. Unreviewed."""
    aliases = []
    seen: set[str] = set()

    def add(name: str, source: str) -> None:
        text = " ".join(str(name or "").split())
        key = text.casefold()
        if not text or key in seen:
            return
        seen.add(key)
        aliases.append({"name": text, "source": source, "kind": "filing"})

    for row in _fec_results(candidate_payload):
        add(str(row.get("name") or ""), f"OpenFEC candidate {candidate_id} name field")
    for row in committees:
        if not isinstance(row, dict):
            continue
        committee_id = str(row.get("committee_id") or "").strip()
        source = f"OpenFEC committee {committee_id} treasurer_name" if committee_id else "OpenFEC committee treasurer_name"
        add(str(row.get("treasurer_name") or ""), source)
    return aliases


def fec_donations_from_schedule(payload: dict) -> list[dict]:
    """Recipient, amount, and date. Street addresses and alignment notes are not copied."""
    donations = []
    for row in _fec_results(payload):
        committee = row.get("committee") if isinstance(row.get("committee"), dict) else {}
        committee_id = str(row.get("committee_id") or committee.get("committee_id") or "").strip()
        recipient = str(committee.get("name") or row.get("committee_name") or committee_id).strip()
        amount = row.get("contribution_receipt_amount")
        date = str(row.get("contribution_receipt_date") or "")[:10]
        image = str(row.get("image_number") or "").strip()
        if image:
            filing_url = f"https://docquery.fec.gov/cgi-bin/fecimg/?{image}"
        elif committee_id:
            filing_url = f"https://www.fec.gov/data/committee/{committee_id}/"
        else:
            filing_url = "https://www.fec.gov/data/receipts/"
        if not recipient or amount is None or not date:
            continue
        donations.append(
            {
                "recipient": recipient,
                "amount": amount,
                "date": date,
                "filing_url": filing_url,
                "contributor_name": str(row.get("contributor_name") or ""),
            }
        )
    return donations


def fec_identity_stub(candidate_id: str, cycle: str, aliases: list[dict], donations: list[dict], notes: list[str] | None = None) -> dict:
    return {
        "status": "unreviewed_import",
        "source": "OpenFEC",
        "candidate_id": candidate_id,
        "cycle": cycle,
        "aliases": aliases,
        "donations_made": donations,
        "lookup_notes": list(notes or []),
        "note": (
            "Unreviewed import. Copy a documented alias into identity.yaml only after you cite the filing. "
            "List the candidate's own donations as recipient, amount, and date. "
            "Do not add alignment commentary. Do not treat this stub as a claim."
        ),
    }


def collect_fec_imports(candidate_id: str, cycle: str, getter) -> tuple[dict, dict, dict]:
    """Totals plus alias and donation stubs. getter(url, params) returns JSON or raises ApiError."""
    totals_payload = getter(
        f"https://api.open.fec.gov/v1/candidate/{candidate_id}/totals/",
        {"cycle": cycle},
    )
    totals = fec_stub(candidate_id, cycle, totals_payload)
    notes: list[str] = []
    try:
        candidate_payload = getter(f"https://api.open.fec.gov/v1/candidate/{candidate_id}/", {})
    except ApiError as exc:
        candidate_payload = {}
        notes.append(f"Candidate name lookup failed ({exc}). No alias was invented.")
    try:
        committee_payload = getter(
            f"https://api.open.fec.gov/v1/candidate/{candidate_id}/committees/",
            {},
        )
        committees = _fec_results(committee_payload)
    except ApiError as exc:
        committees = []
        notes.append(f"Committee lookup failed ({exc}). No treasurer name was invented.")
    filled = []
    for row in committees[:5]:
        if row.get("treasurer_name") or not row.get("committee_id"):
            filled.append(row)
            continue
        try:
            detail = getter(f"https://api.open.fec.gov/v1/committee/{row.get('committee_id')}/", {})
        except ApiError as exc:
            notes.append(f"Committee {row.get('committee_id')} lookup failed ({exc}).")
            filled.append(row)
            continue
        detail_row = _fec_results(detail)
        merged = dict(row)
        if detail_row and detail_row[0].get("treasurer_name"):
            merged["treasurer_name"] = detail_row[0].get("treasurer_name")
        filled.append(merged)
    aliases = fec_aliases_from_payloads(candidate_id, candidate_payload, filled)
    donations: list[dict] = []
    candidate_name = ""
    for row in _fec_results(candidate_payload):
        candidate_name = str(row.get("name") or "").strip()
        if candidate_name:
            break
    if not candidate_name:
        notes.append("Candidate name was not in the FEC payload, so donations by the candidate were not searched.")
    else:
        try:
            schedule = getter(
                "https://api.open.fec.gov/v1/schedules/schedule_a/",
                {"contributor_name": candidate_name, "per_page": 20, "sort": "-contribution_receipt_date"},
            )
            donations = fec_donations_from_schedule(schedule)
        except ApiError as exc:
            notes.append(f"Donation lookup failed ({exc}). No donation was invented.")
    return totals, fec_identity_stub(candidate_id, cycle, aliases, donations, notes), totals_payload


def fec_stub(candidate_id: str, cycle: str, payload: dict) -> dict:
    results = payload.get("results") or []
    latest = results[0] if results and isinstance(results[0], dict) else {}
    return {
        "status": "unreviewed_import",
        "source": "OpenFEC",
        "candidate_id": candidate_id,
        "cycle": cycle,
        "filing_url": f"https://www.fec.gov/data/candidate/{candidate_id}/",
        "coverage_end_date": latest.get("coverage_end_date"),
        "receipts": latest.get("receipts"),
        "disbursements": latest.get("disbursements"),
        "cash_on_hand_end_period": latest.get("cash_on_hand_end_period"),
        "debts": latest.get("debts_owed_by_committee"),
        "note": "Draft import only. Open the filing, quote the line, and only then add a claim. Do not treat this stub as a finished citation.",
    }


def get_json(url: str, *, headers: dict | None = None, params: dict | None = None, secrets: list[str] | None = None, timeout: int = 30) -> dict:
    import requests

    try:
        response = safe_request("GET", url, headers=headers or {}, params=params or {}, timeout=timeout)
    except RuntimeError as exc:
        raise ApiError(redact(str(exc), secrets or [])) from exc
    except requests.RequestException as exc:
        raise ApiError(redact(str(exc), secrets or [])) from exc
    if response.status_code >= 400:
        raise ApiError(redact(f"HTTP {response.status_code} from {url}", secrets or []))
    try:
        data = response.json()
    except ValueError as exc:
        raise ApiError("Response was not JSON") from exc
    if not isinstance(data, dict):
        raise ApiError("Response JSON was not an object")
    return data
