"""Unreviewed bill imports. Florida adapters when the state is Florida, otherwise a fallback.

The fallback does not invent sponsors, votes, lobbyists, or model-bill origins.
Open States and Congress.gov stay in their own scripts and run only with a key.
"""

from __future__ import annotations

from portals.bill_parse import bill_chamber, title_chamber
from portals.fl_campaign_finance import FloridaCampaignFinance
from portals.fl_house import FloridaHouseBills
from portals.fl_lobbyists import FloridaLobbyistRegistration, lobbyists_for_bill
from portals.fl_senate import FloridaSenateBills


def empty_import(state: str, bill: str, session: str) -> dict:
    return {
        "status": "unreviewed_import",
        "state": state,
        "bill": bill,
        "session": session,
        "title": "",
        "sponsors": [],
        "actions": [],
        "companions": [],
        "lobbyists": [],
        "contributions": [],
        "notes": [],
        "sources": [],
    }


def generic_fallback(state: str, bill: str, session: str) -> dict:
    """No state adapter. Point at the official page and at the free clients. Invent nothing."""
    record = empty_import(state, bill, session)
    code = (state or "").strip().upper()
    if code in {"US", "USA", "FEDERAL", "CONGRESS"}:
        record["status"] = "use_congress_script"
        record["notes"].append(
            "Federal bills use scripts/congress.py and the bill page on congress.gov. "
            "No bill text, sponsor, or vote was invented."
        )
        return record
    record["status"] = "no_state_adapter"
    record["notes"].append(
        f"No free legislative adapter for {state or 'this state'}. "
        "Open the legislature's bill page and cite that text. "
        "If OPENSTATES_API_KEY is set, scripts/openstates.py can save an unreviewed JSON import. "
        "FollowTheMoney and OpenSecrets are free reference pages, not a paid client in this tool. "
        "No sponsors, votes, lobbyists, or contributions were filled in."
    )
    return record


def collect_legislation(state: str, bill: str, session: str, fetcher, *, base_urls: dict | None = None) -> dict:
    """One unreviewed import. Florida uses the four public adapters. Every other state uses the fallback."""
    code = (state or "").strip().upper()
    if code not in {"FL", "FLORIDA"}:
        return generic_fallback(state, bill, session)
    bases = base_urls or {}
    record = empty_import("FL", bill, session)
    record["status"] = "unreviewed_import"
    kind = bill_chamber(bill)
    senate, senate_result = FloridaSenateBills(bases.get("senate", "")).fetch_bill(fetcher, session, bill)
    house, house_result = FloridaHouseBills(bases.get("house", "")).fetch_bill(fetcher, session, bill)
    # HB comes from the House page and SB from the Senate page. A page whose
    # title names the other chamber is not stored, even when that page loaded.
    if kind == "HB":
        chosen = house
    elif kind == "SB":
        chosen = senate
    else:
        chosen = {}
        record["notes"].append(
            "The bill id needs an HB or SB prefix. Neither chamber's bill was stored."
        )
    found = title_chamber(str(chosen.get("title") or ""))
    if kind and found != kind:
        if chosen.get("title") or chosen.get("sponsors"):
            record["notes"].append(
                "The fetched page was the other chamber's bill and was not stored."
            )
        chosen = {}
    record["title"] = chosen.get("title") or ""
    record["sponsors"] = list(chosen.get("sponsors") or [])
    record["actions"] = list(chosen.get("actions") or [])
    record["companions"] = list(chosen.get("companions") or [])
    record["sources"].extend(
        [
            {"adapter": "flsenate.gov", "status": senate_result.status, "note": senate_result.note, "citations": list(senate_result.citations)},
            {"adapter": "myfloridahouse.gov", "status": house_result.status, "note": house_result.note, "citations": list(house_result.citations)},
        ]
    )
    record["notes"].extend(chosen.get("notes") or [])
    lobby, lobby_result = FloridaLobbyistRegistration(bases.get("lobbyists", "")).fetch_session(fetcher, session)
    record["lobbyists"] = lobbyists_for_bill(list(lobby.get("lobbyists") or []), bill)
    record["notes"].extend(lobby.get("notes") or [])
    record["sources"].append(
        {"adapter": "fl_lobbyists", "status": lobby_result.status, "note": lobby_result.note, "citations": list(lobby_result.citations)}
    )
    money, money_result = FloridaCampaignFinance(bases.get("finance", "")).fetch_contributions(fetcher)
    record["contributions"] = list(money.get("contributions") or [])
    record["notes"].extend(money.get("notes") or [])
    record["sources"].append(
        {
            "adapter": "fl_campaign_finance",
            "status": money_result.status,
            "note": money_result.note,
            "citations": list(money_result.citations),
        }
    )
    record["notes"].append(
        "Unreviewed import. Copy a field into claims.yaml only after you cite the legislature's page, "
        "the lobbyist disclosure, or the campaign filing. Do not treat this JSON as a claim."
    )
    return record
