"""Fictional fixtures for the identity gate, portal adapters, and record rules.

These tests do not contact the network. Portal HTTP is a stand-in object.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from check_links import live_statuses
from identity_gate import identity_gate_errors
from lib.api_clients import collect_fec_imports, fec_donations_from_schedule
from lib.archive import _collect_jobs
from lib.quality import structured_symmetry_errors
from lib.records import (
    adult_year,
    court_gate,
    names_party,
    surname,
)
from lib.schema import instance_errors, load_schema
from lib.util import dump_yaml, repo_root
from lib.workflow import fresh_loop_state, record_unchecked, review_queue, signoff
from portals import search_portal
from portals.fetch import PortalFetchError, SafePortalFetcher
from portals.fl_dfs import DfsPortal
from portals.fl_sunbiz import SunbizPortal

ROOT = repo_root()
EXAMPLE = ROOT / "examples" / "sample-election"


def _category(status: str, note: str = "") -> dict:
    row = {"status": status}
    if note:
        row["note"] = note
    return row


def _sweep(status: str = "checked_nothing_found") -> dict:
    sweep = {key: _category(status) for key in (
        "criminal",
        "civil",
        "financial",
        "ethics_campaign_finance",
        "professional_discipline",
        "labor_consumer",
        "misuse_of_office",
        "prior_statements",
    )}
    sweep["aliases_searched"] = ["Avery Hale"]
    return sweep


def _source(**overrides):
    data = {
        "url": "https://fictional.example/docket",
        "archive_failed": True,
        "archive_failed_reason": "fixture",
        "publisher": "Fixture Court",
        "title": "Fixture docket",
        "doc_type": "Court record",
        "published": "2010-04-01",
        "retrieved": "2026-10-20 09:00 ET",
        "tier": "T1",
        "locator": "caption",
        "quote": "State v. Hale.",
        "confidence": "verified",
        "marker": 1,
    }
    data.update(overrides)
    return data


def _claim(**overrides):
    data = {
        "id": "cand-fixture.legal.001",
        "section": "legal",
        "text": "A fixture sentence.",
        "marker": 1,
        "sources": [_source()],
        "confidence": "verified",
        "drives_summary": False,
        "polarity": "neutral",
        "about_person": True,
    }
    data.update(overrides)
    return data


def _write_item(root: Path, draft: str, claims: list[dict], identity: dict, profile: dict | None = None) -> None:
    item = root / "items" / "cand-fixture"
    item.mkdir(parents=True, exist_ok=True)
    (item / "draft.md").write_text(draft, encoding="utf-8")
    dump_yaml(
        item / "claims.yaml",
        {"item_id": "cand-fixture", "item_type": "candidate", "claims": claims},
    )
    dump_yaml(item / "identity.yaml", identity)
    if profile is not None:
        dump_yaml(item / "profile.yaml", profile)


def _identity(**overrides):
    data = {
        "item_id": "cand-fixture",
        "full_legal_name": "Avery Jordan Quinn",
        "ballot_name": "Avery Quinn",
        "office": "Mayor",
        "photo_included": False,
        "aliases": [{"name": "Avery Hale", "source": "https://fictional.example/filing", "kind": "former"}],
        "birth_year": 1990,
    }
    data.update(overrides)
    return data


def test_schema_keeps_birth_year_internal_and_requires_alias_sources():
    schema = load_schema("identity.schema.yaml")
    ok = _identity()
    assert instance_errors(ok, schema) == []
    dated = dict(ok)
    dated["birth_date"] = "1990-05-02"
    assert instance_errors(dated, schema)
    nameless = dict(ok)
    nameless["aliases"] = [{"name": "Avery Hale"}]
    assert instance_errors(nameless, schema)


def test_party_and_era_gates_use_aliases_and_drop_pre_adult_cases():
    assert surname("Alex Rivera Jr") == "rivera"
    assert surname("O'Brien") == "o'brien"
    names = ["Avery Quinn", "Avery Hale"]
    assert names_party("State v. Hale", {surname(name) for name in names})
    assert not names_party("State v. Okonkwo", {surname(name) for name in names})
    assert not names_party("Hale's appeal", {surname(name) for name in names})
    assert adult_year(1990) == 2008
    assert court_gate("State v. Hale", "1983-04-01", names, 1990)
    assert court_gate("State v. Okonkwo", "2010-04-01", names, 1990)
    assert court_gate("State v. Hale", "2010-04-01", names, 1990) == []
    assert court_gate("State v. Hale", "1983-04-01", names, None) == []


def test_identity_gate_rejects_misattributed_and_pre_adult_court_records(tmp_path: Path):
    draft = "# Avery\n\n## Legal issues\n\nNot found (searched: fictional docket under Avery Quinn and Avery Hale).\n"
    wrong = _claim(
        text="State v. Okonkwo names a different person.",
        record_kind="court",
        court_caption="State v. Okonkwo",
        record_date="2010-04-01",
        legal_category="criminal",
        legal_status="pending",
    )
    _write_item(tmp_path, draft, [wrong], _identity())
    errors = identity_gate_errors(tmp_path)
    assert any("does not name the candidate" in error for error in errors)

    early = _claim(
        text="State v. Hale was filed in 1983. Response requested, not found.",
        record_kind="court",
        court_caption="State v. Hale",
        record_date="1983-04-01",
        legal_category="criminal",
        legal_status="pending",
    )
    _write_item(tmp_path, draft, [early], _identity())
    errors = identity_gate_errors(tmp_path)
    assert any("turned 18" in error for error in errors)

    kept = _claim(
        text="State v. Hale, filed in 2010, is pending. Response requested, not found.",
        record_kind="court",
        court_caption="State v. Hale",
        record_date="2010-04-01",
        legal_category="criminal",
        legal_status="pending",
    )
    _write_item(tmp_path, draft, [kept], _identity())
    assert identity_gate_errors(tmp_path) == []


def test_birth_year_is_not_rendered_and_aliases_are_searched(tmp_path: Path):
    draft = "# Avery\n\nAvery Quinn was born in 1990.\n\n## Legal issues\n\nNot found (searched: fictional docket).\n"
    _write_item(tmp_path, draft, [], _identity())
    errors = identity_gate_errors(tmp_path)
    assert any("must not be rendered" in error for error in errors)
    assert any("omits alias search" in error for error in errors)


def test_legal_sweep_dismissal_settlement_and_symmetry(tmp_path: Path):
    draft = "# Avery\n\n## Legal issues\n\nchecked, nothing found under Avery Hale.\n"
    dismissed = _claim(
        legal_status="dismissal",
        legal_category="civil",
        accusation="a contract dispute",
        text="The contract dispute ended in a dismissal. Response requested, not found.",
    )
    _write_item(tmp_path, draft, [dismissed], _identity(), {"item_id": "cand-fixture", "legal_sweep": _sweep("record_found")})
    errors = identity_gate_errors(tmp_path)
    assert any("no claim uses that category" in error for error in errors)

    settled = _claim(
        id="cand-fixture.legal.002",
        legal_status="settlement_without_admission",
        legal_category="civil",
        text="Avery Quinn admitted liability in the settlement.",
    )
    assert any("not an admission" in error for error in identity_gate_errors_for(tmp_path, draft, [settled]))

    clean = _claim(
        legal_status="settlement_without_admission",
        legal_category="civil",
        record_kind="court",
        court_caption="State v. Hale",
        record_date="2010-04-01",
        text="The civil case ended in a settlement without admission. Response requested, not found.",
    )
    sweep = _sweep("record_found")
    for key in list(sweep):
        if key != "aliases_searched":
            sweep[key] = _category("checked_nothing_found" if key != "civil" else "record_found")
    _write_item(tmp_path, draft, [clean], _identity(), {"item_id": "cand-fixture", "legal_sweep": sweep})
    assert identity_gate_errors(tmp_path) == []

    dump_yaml(
        tmp_path / "ballot.yaml",
        {
            "contests": [
                {
                    "id": "race-1",
                    "type": "race",
                    "candidates": [
                        {"id": "cand-a", "item_id": "cand-a"},
                        {"id": "cand-b", "item_id": "cand-b"},
                    ],
                }
            ]
        },
    )
    for item_id, include in (("cand-a", True), ("cand-b", False)):
        folder = tmp_path / "items" / item_id
        folder.mkdir(parents=True)
        profile = {"item_id": item_id, "issues": {"parks": "A parks note[^1]."}}
        if include:
            profile["legal_sweep"] = _sweep()
        dump_yaml(folder / "profile.yaml", profile)
    symmetry = structured_symmetry_errors(tmp_path)
    assert any("legal_sweep is missing" in error for error in symmetry)


def identity_gate_errors_for(root: Path, draft: str, claims: list[dict]) -> list[str]:
    _write_item(root, draft, claims, _identity(), {"item_id": "cand-fixture", "legal_sweep": _sweep("record_found")})
    return identity_gate_errors(root)


def test_rhetoric_occupation_shift_and_entity_license(tmp_path: Path):
    draft = (
        "# Avery\n\n## Record vs rhetoric\n\nCONTRADICTION[^1].\n\n"
        "## Legal issues\n\nNot found (searched: fictional docket under Avery Quinn and Avery Hale).\n"
    )
    occupation = _claim(
        id="cand-fixture.record.001",
        section="record vs rhetoric",
        rhetoric_label="CONTRADICTION",
        rhetoric_basis="occupation",
        text="CONTRADICTION because the occupation is teaching.",
        sources=[_source(quote="classroom teacher")],
    )
    _write_item(tmp_path, draft, [occupation], _identity())
    errors = identity_gate_errors(tmp_path)
    assert any("occupation is not a contradiction" in error for error in errors)

    shift = _claim(
        id="cand-fixture.record.001",
        section="record vs rhetoric",
        rhetoric_label="NO RECORD",
        shift=True,
        text="NO RECORD. The position shifted.",
        sources=[_source(quote="levy")],
    )
    _write_item(tmp_path, draft.replace("CONTRADICTION", "NO RECORD"), [shift], _identity())
    assert any("both endpoints" in error for error in identity_gate_errors(tmp_path))

    dated = _claim(
        id="cand-fixture.record.001",
        section="record vs rhetoric",
        rhetoric_label="MATCH",
        shift=True,
        shift_from="2020-01-01",
        shift_to="2024-06-01",
        text="MATCH. The statement shifted from 2020-01-01 to 2024-06-01.",
        sources=[_source(marker=1, quote="2020 text"), _source(marker=2, quote="2024 text")],
    )
    _write_item(tmp_path, draft.replace("CONTRADICTION", "MATCH"), [dated], _identity())
    assert identity_gate_errors(tmp_path) == []

    license_claim = _claim(
        id="cand-fixture.occupation.001",
        section="occupation",
        record_kind="license_entity",
        license_holder="entity",
        text="The candidate holds license number W999 for Hale Consulting LLC.",
        sources=[_source(quote="Hale Consulting LLC holds license number W999")],
    )
    _write_item(
        tmp_path,
        "# Avery\n\n## Legal issues\n\nNot found (searched: fictional docket under Avery Quinn and Avery Hale).\n",
        [license_claim],
        _identity(),
    )
    assert any("entity's record" in error for error in identity_gate_errors(tmp_path))


def test_overspecific_degree_and_search_form_are_rejected(tmp_path: Path):
    draft = "# Avery\n\n## Legal issues\n\nNot found (searched: fictional docket under Avery Quinn and Avery Hale).\n"
    degree = _claim(
        section="education",
        text="Avery Quinn earned a B.S. in Business.",
        sources=[_source(quote="Avery Quinn earned a bachelor's degree.")],
    )
    _write_item(tmp_path, draft, [degree], _identity())
    errors = identity_gate_errors(tmp_path)
    assert any("B.S." in error for error in errors)
    assert any("Business" in error for error in errors)

    form = _claim(
        text="Not found on the Sunbiz form.",
        sources=[_source(url="https://search.sunbiz.org/Inquiry/CorporationSearch/ByName")],
    )
    _write_item(tmp_path, draft, [form], _identity())
    assert any("search form" in error for error in identity_gate_errors(tmp_path))


def test_sample_election_passes_the_identity_gate():
    assert identity_gate_errors(EXAMPLE) == []


class _FakePortal:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[tuple] = []
        self.body = ""

    def fetch_html(self, url, **kwargs):
        self.calls.append(("GET", url))
        if url not in self.pages:
            raise PortalFetchError("missing fixture", status_code=404)
        return url, self.pages[url]

    def submit_form(self, page_url, post_url, build_body):
        self.calls.append(("FORM", page_url))
        self.body = build_body(self.pages[page_url])
        return post_url, self.pages["POST"]


def test_sunbiz_distinguishes_hits_empty_form_and_outage():
    detail = (
        "<table><tr><td><a href=\"/Inquiry/CorporationSearch/SearchResultDetail?aggregateId=domp-1\">"
        "HALE EXAMPLE LLC</a></td><td>L100</td><td>Active</td></tr></table>"
    )
    portal = SunbizPortal("https://portal.test")
    probe = _FakePortal({})
    portal.search(probe, "Hale Example")
    url = probe.calls[0][1]
    assert "SearchResults" in url
    assert "ByName" not in url
    found = portal.search(_FakePortal({url: detail}), "Hale Example")
    assert found.status == "hits"
    assert found.citations
    assert "SearchResultDetail" in found.citations[0]
    assert found.counts_as_searched_empty() is False

    empty = portal.search(_FakePortal({url: "<table><tr><th>Entity Name</th></tr></table>"}), "Hale Example")
    assert empty.status == "searched-none" and empty.executed is True
    assert empty.counts_as_searched_empty() is True
    assert empty.citations == ()

    form = portal.search(_FakePortal({url: "<form action=\"/Inquiry/CorporationSearch/ByName\"></form>"}), "Hale Example")
    assert form.status == "search-form-only" and form.executed is False
    assert "not evidence" in form.note

    class Down:
        def fetch_html(self, requested, **kwargs):
            raise PortalFetchError("HTTP 403", status_code=403)

    outage = portal.search(Down(), "Hale Example")
    assert outage.status == "portal-down" and outage.executed is False


def test_dfs_cites_licensee_detail_and_does_not_treat_a_short_name_as_a_search():
    form = (
        "<form id=\"frmMainSearch\">"
        "<input name=\"csrf_token\" value=\"abc\">"
        "<input name=\"IndividualLNameFilter\" value=\"\">"
        "<input name=\"IndividualFNameFilter\" value=\"\">"
        "</form>"
    )
    rows = (
        "<table><tr data-licensee-id=\"42\" data-licensee-name=\"HALE, AVERY\" "
        "data-license-num=\"W123456\"></tr></table>"
    )
    portal = DfsPortal("https://portal.test")
    fake = _FakePortal({"https://portal.test/": form, "POST": rows})
    result = portal.search(fake, "Avery Hale")
    assert result.status == "hits"
    assert result.citations == ("https://portal.test/Licensee/42",)
    assert "csrf_token=abc" in fake.body
    assert "IndividualLNameFilter=Hale" in fake.body
    short = portal.search(fake, "Li")
    assert short.executed is False
    assert short.counts_as_searched_empty() is False
    form_only = portal.search(_FakePortal({"https://portal.test/": form, "POST": form}), "Avery Hale")
    assert form_only.status == "search-form-only"
    other = search_portal("business", "Hale", state="ZZ", fetcher=fake)
    assert other.status == "portal-down"
    assert other.status != "searched-none"


def test_portal_fetcher_blocks_loopback_and_does_not_retry_403(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("loopback was requested")

    fetcher = SafePortalFetcher(request=refuse)
    with pytest.raises(PortalFetchError):
        fetcher.fetch_html("http://127.0.0.1/secret")

    monkeypatch.setattr("portals.fetch.unsafe_fetch_target", lambda url: None)
    calls = []

    class Response:
        status_code = 403
        text = "blocked"
        url = "https://portal.test/search"
        cookies = {}

    def request(method, url, **kwargs):
        calls.append((method, url))
        return Response()

    guarded = SafePortalFetcher(request=request)
    with pytest.raises(PortalFetchError):
        guarded.fetch_html("https://portal.test/search")
    with pytest.raises(PortalFetchError):
        guarded.fetch_html("https://portal.test/search")
    assert calls == [("GET", "https://portal.test/search")]


def test_link_check_does_not_retry_403():
    calls = []

    class Response:
        def __init__(self, code):
            self.status_code = code

    def request(method, url, timeout=15):
        calls.append(method)
        return Response(403 if method == "HEAD" else 200)

    found = live_statuses(["https://fictional.example/blocked"], request)
    assert calls == ["HEAD"]
    assert found["https://fictional.example/blocked"][0] == 403


def test_fec_import_lists_aliases_and_donations_without_addresses():
    calls = []

    def getter(url, params):
        calls.append(url)
        if url.endswith("/totals/"):
            return {"results": [{"receipts": 10, "coverage_end_date": "2026-09-30"}]}
        if url.endswith("/P00000000/"):
            return {"results": [{"candidate_id": "P00000000", "name": "QUINN, AVERY JORDAN"}]}
        if url.endswith("/committees/"):
            return {"results": [{"committee_id": "C001", "name": "QUINN FOR EXAMPLE"}]}
        if url.endswith("/committee/C001/"):
            return {"results": [{"committee_id": "C001", "treasurer_name": "HALE, AVERY"}]}
        if "schedule_a" in url:
            assert params["contributor_name"] == "QUINN, AVERY JORDAN"
            return {
                "results": [
                    {
                        "contributor_name": "QUINN, AVERY JORDAN",
                        "contributor_street_1": "1 Secret Street",
                        "committee_id": "C009",
                        "committee": {"name": "FRIENDS OF EXAMPLE", "committee_id": "C009"},
                        "contribution_receipt_amount": 25,
                        "contribution_receipt_date": "2024-03-01T00:00:00",
                        "image_number": "2024030199",
                    }
                ]
            }
        raise AssertionError(url)

    totals, identity, payload = collect_fec_imports("P00000000", "2026", getter)
    assert totals["receipts"] == 10
    assert payload["results"][0]["receipts"] == 10
    names = [row["name"] for row in identity["aliases"]]
    assert "QUINN, AVERY JORDAN" in names
    assert "HALE, AVERY" in names
    assert identity["donations_made"][0]["recipient"] == "FRIENDS OF EXAMPLE"
    assert identity["donations_made"][0]["amount"] == 25
    assert identity["donations_made"][0]["date"] == "2024-03-01"
    blob = json.dumps(identity)
    assert "Secret Street" not in blob
    assert set(identity["donations_made"][0]) == {
        "recipient",
        "amount",
        "date",
        "filing_url",
        "contributor_name",
    }
    assert "recipient, amount, and date" in identity["note"]
    assert fec_donations_from_schedule({"results": []}) == []
    assert calls


def test_wayback_snapshot_is_an_extra_archive_job(tmp_path: Path):
    item = tmp_path / "items" / "cand-fixture"
    item.mkdir(parents=True)
    snapshot = "https://web.archive.org/web/20200101000000/https://fictional.example/doc"
    dump_yaml(
        item / "claims.yaml",
        {
            "item_id": "cand-fixture",
            "item_type": "candidate",
            "claims": [_claim(wayback_url=snapshot, sources=[_source()])],
        },
    )
    jobs = _collect_jobs(tmp_path)
    urls = [job[5] for job in jobs]
    assert "https://fictional.example/docket" in urls
    assert snapshot in urls
    assert jobs[0][3].get("_snapshot") is not True
    assert jobs[1][3].get("_snapshot") is True


def test_review_queue_lists_negative_claims_first_and_signoff_needs_the_list(tmp_path: Path):
    item = tmp_path / "items" / "cand-fixture"
    item.mkdir(parents=True)
    dump_yaml(
        item / "claims.yaml",
        {
            "claims": [
                _claim(id="cand-fixture.identity.001", section="identity", polarity="neutral", text="Avery Quinn filed."),
                _claim(id="cand-fixture.legal.002", section="legal", polarity="negative", text="No record was asserted."),
            ]
        },
    )
    queue = review_queue(item)
    assert queue.index("cand-fixture.legal.002 polarity=negative") < queue.index("cand-fixture.identity.001 polarity=neutral")
    from lib.util import dump_json

    dump_json(item / "loop-state.json", fresh_loop_state("cand-fixture", "2026-10-20 12:00 ET"))
    (item / "findings.yaml").write_text("[]\n", encoding="utf-8")
    assert signoff(item, "factcheck", "2026-10-20 12:00 ET")
    assert record_unchecked(item, "factcheck", "2026-10-20 12:00 ET", ["county image docket"]) == []
    assert signoff(item, "factcheck", "2026-10-20 12:00 ET") == []
    state = json.loads((item / "loop-state.json").read_text(encoding="utf-8"))
    assert state["not_checked"][0]["items"] == ["county image docket"]


def test_profile_schema_accepts_a_complete_legal_sweep():
    schema = load_schema("profile.schema.yaml")
    profile = {"item_id": "cand-fixture", "legal_sweep": _sweep(), "money": {"donations_made": [
        {"recipient": "Friends of Example", "amount": "25", "date": "2024-03-01"}
    ]}}
    assert instance_errors(profile, schema) == []
    partial = {"item_id": "cand-fixture", "legal_sweep": {"criminal": _category("not_checked")}}
    assert instance_errors(partial, schema)
