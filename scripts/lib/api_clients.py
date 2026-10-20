"""Optional data-source clients. They never invent records when a key or network call is missing."""

from __future__ import annotations

from lib.util import redact


class ApiError(RuntimeError):
    pass


_CIVIC_DROP = {
    "normalizedinput",
    "mailonly",
    "pollinglocations",
    "earlyvotesites",
    "dropofflocations",
    "precinctid",
    "address",
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
            candidates.append(row)
        url = None
        for candidate in contest.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            found = _http_url(candidate.get("candidateUrl"))
            if found:
                url = found
                break
        if url is None:
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

    from lib.util import unsafe_fetch_target

    reason = unsafe_fetch_target(url)
    if reason:
        raise ApiError(f"Refusing fetch: {reason}")
    try:
        response = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    except requests.RequestException as exc:
        raise ApiError(redact(str(exc), secrets or [])) from exc
    redirected = unsafe_fetch_target(response.url)
    if redirected:
        raise ApiError(f"Refusing redirect: {redirected}")
    if response.status_code >= 400:
        raise ApiError(redact(f"HTTP {response.status_code} from {url}", secrets or []))
    try:
        data = response.json()
    except ValueError as exc:
        raise ApiError("Response was not JSON") from exc
    if not isinstance(data, dict):
        raise ApiError("Response JSON was not an object")
    return data
