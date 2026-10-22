"""Reader substance gates, including candidate privacy."""

from lib.reader_substance import (
    _family_or_none,
    _residence_clause,
    background_lines,
    draft_street_errors,
    fact_sentence,
    street_spans,
    substance_errors,
)


def test_street_gate_skips_court_names_and_flags_a_home_address():
    from lib.util import looks_like_street_address

    assert street_spans("The case was filed in the 26 Supreme Court.") == []
    assert street_spans("District Court of Appeal heard the case.") == []
    assert street_spans("35 of 35 precincts reporting") == []
    assert street_spans("In 2006 Ashley Moody was elected circuit court judge.") == []
    assert looks_like_street_address("In 2006 Ashley Moody was elected circuit court judge.") is False
    found = street_spans("The filing lists 6070 Chapman Rd, Cocoa.")
    assert found
    assert "Chapman" in found[0]
    assert looks_like_street_address("6070 Chapman Rd") is True


def test_residence_is_city_and_state_when_the_sentence_has_a_street():
    shown = fact_sentence(
        "She lives at 100 Main Street, Cocoa, Florida[^4].",
        "background",
    )
    assert shown == "Lives in Cocoa, Florida[^4]."
    assert "Main" not in shown
    assert _residence_clause("He is a resident of Miami, Florida.") == "Lives in Miami, Florida"


def test_minor_children_are_a_count_only():
    assert (
        _family_or_none("She and her husband have two children, Maya, 8, and Leo, 11, both minors.")
        == "Two children, both minors"
    )
    assert _family_or_none("His son Alex attends West Orange High School.") == "One child, a minor"
    shown = fact_sentence("His son Alex attends West Orange High School[^2].", "background")
    assert shown == "One child, a minor[^2]."
    assert "Alex" not in shown
    assert "Orange" not in shown
    assert fact_sentence("Her son Noah is 6 and attends a local elementary school[^8].", "background") == (
        "One child, a minor[^8]."
    )
    kept = fact_sentence(
        "She has said her adult daughter Maria works on the campaign[^3].",
        "background",
    )
    assert "Maria" in kept
    assert "adult" in kept.lower()
    dropped = fact_sentence("Her adult son John lives in Tampa[^9].", "background")
    assert dropped == ""


def test_background_section_is_required_and_a_street_fails_the_guide():
    missing = (
        "## Race {#contest-mayor}\n\n"
        "## Ada {#profile-cand-ada .profile-title}\n\n"
        "### Education\n\nA degree[^1].\n"
    )
    ballot = {"contests": [{"candidates": [{"item_id": "cand-ada", "name": "Ada"}]}]}
    assert any("Background" in error for error in substance_errors(missing, ballot))
    street = (
        "## Race {#contest-mayor}\n\n"
        "## Ada {#profile-cand-ada .profile-title}\n\n"
        "### Background\n\nLives at 100 Main Street, Cocoa[^1].\n"
    )
    assert any("street address" in error for error in substance_errors(street, ballot))
    limited = {"contests": [{"candidates": [{"item_id": "cand-ada", "limited_public_record": True}]}]}
    notice = (
        "## Race {#contest-mayor}\n\n"
        "## Ada {#profile-cand-ada}\n\n"
        "### Background\n\nLimited public record.\n"
    )
    assert substance_errors(notice, limited) == []


def test_background_lines_keep_a_gap_when_nothing_is_cited():
    lines = background_lines({"education": "Not found (searched: a degree)."})
    assert "### Background" in lines
    assert any(line.startswith("No public record found") for line in lines)


def test_a_timeline_year_stays_a_year_when_a_marker_uses_the_same_number():
    from lib.guide_layout import _renumber_markers

    body = "Elected in 2014[^2014].\n\n| When | What happened |\n| --- | --- |\n| 2014 | Elected in 2014[^2014]. |\n"
    rewritten, _addendum, _mapping = _renumber_markers(body, "")
    assert "| 2014 |" in rewritten
    assert "[^1]" in rewritten


def test_listed_as_fragments_become_facts():
    assert (
        fact_sentence("The 2025 House final bill analysis lists the sponsor as McClure[^5].")
        == "The sponsor is McClure[^5]."
    )
    house = fact_sentence(
        "The Division of Elections lists the sponsor as the Florida Legislature/House[^6]."
    )
    assert house == "The Florida House is the sponsor[^6]."
    assert "Legislature/House" not in house
    lives = fact_sentence(
        "The Florida house biography lists the occupation of Blaise Ingoglia, as homebuilder "
        "and his city of residence as Spring Hill[^7].",
        "background",
    )
    assert lives == "Blaise Ingoglia is a homebuilder and lives in Spring Hill, Florida[^7]."
    assert "occupation of" not in lives.lower()
    officer = fact_sentence(
        "Sunbiz lists Hartland homes, Inc., document P02000026766, filed in 2002, as active, "
        "with Blaise Ingoglia, on the officer line as INGOGLIA, BLAISE, title DP, in Spring Hill[^8]."
    )
    assert officer.startswith("Blaise Ingoglia is an officer of Hartland homes, Inc.")
    assert "INGOGLIA" not in officer
    assert "P02000026766" not in officer
    assert fact_sentence("Officers signed HJR 5019 and filed it with the Secretary of State[^9].") == ""
    kept = fact_sentence("That section limits withdrawals to revenue shortfalls[^10].")
    assert kept.startswith("That section limits withdrawals")


def test_candidate_draft_street_gate(tmp_path):
    item = tmp_path / "items" / "cand-ada"
    item.mkdir(parents=True)
    (item / "draft.md").write_text("She lives at 12 Oak Lane, Tampa.\n", encoding="utf-8")
    race = tmp_path / "items" / "race-mayor"
    race.mkdir()
    (race / "draft.md").write_text("The office is on 1 Court Street in the fictional city.\n", encoding="utf-8")
    errors = draft_street_errors(tmp_path)
    assert any("cand-ada" in error for error in errors)
    assert all("race-mayor" not in error for error in errors)
