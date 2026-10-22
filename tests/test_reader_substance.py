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


def test_a_percent_does_not_take_a_dollar_sign_and_a_source_lead_becomes_the_fact():
    from lib.reader_substance import ballot_box_problem, substance_errors

    percent = fact_sentence(
        "Official results list Jennifer Jenkins with 14,764 votes, 54.60 percent of 27,041[^9]."
    )
    assert "$" not in percent
    assert "54.60 percent" in percent
    assert "received 14,764 votes" in percent
    job = fact_sentence(
        "The campaign site for Daniel Lewis Cicirelli, calls him a small business owner and handyman[^4]."
    )
    assert job.startswith("Daniel Lewis Cicirelli is a small business owner")
    assert "campaign site" not in job.lower()
    degree = fact_sentence(
        "The Florida Senate handbook lists a bachelor of arts from Stetson University in 1992 "
        "for Mike Haridopolos[^8]."
    )
    assert degree.startswith("Mike Haridopolos earned a bachelor of arts")
    assert "handbook" not in degree.lower()
    salary = fact_sentence(
        "As of January 21, 2026, the base salary for all members of Congress is $174,000[^8]."
    )
    assert salary.startswith("As of January 21, 2026")
    assert "$174,000" in salary
    bio = fact_sentence(
        "A 2019 appointment release and the official biography say Carlos G. Muñiz, "
        "a Justice of the Supreme Court, had served as general counsel[^9]."
    )
    assert bio.startswith("Carlos G. Muñiz had served as general counsel")
    assert "biography" not in bio.lower()
    school = fact_sentence("He graduated from harvard law school in 2006[^2].")
    assert "Harvard Law School" in school
    mixed = fact_sentence("He attended St. johns river state college[^2].")
    assert "St. Johns River State College" in mixed
    appointed = fact_sentence(
        "On January 22, 2019, Ron DeSantis appointed Carlos G. Muñiz, as a Justice of the Supreme Court[^1]."
    )
    assert "appointed Carlos G. Muñiz as a Justice of the Supreme Court" in appointed
    assert ", as a Justice" not in appointed
    withdrawn = fact_sentence(
        'Ballotpedia lists Moliere "Moe" Dimanche, Division of Elections, under withdrawn or '
        "disqualified candidates for the November 7, 2023, Mayor of Orlando election[^1]."
    )
    assert withdrawn.startswith('Moliere "Moe" Dimanche was listed as a withdrawn or disqualified candidate')
    assert "under withdrawn" not in withdrawn.lower()
    died = fact_sentence(
        "The Florida house lists Angie Nixon as a first named sponsor of the house bill, "
        "and the last event is Died in criminal justice subcommittee[^3]."
    )
    assert "last event" not in died.lower()
    assert "died in the criminal justice subcommittee" in died.lower()
    guide = (
        "## Race {#contest-race-one .contest-title}\n\n"
        "### Exact words on your ballot\n\n"
        "Muñiz of the Supreme Court be retained in office?\n\n"
        "### Background\n\n"
        "Listed next to NRAYS LLC: $104,696.\n"
    )
    problems = " ".join(substance_errors(guide, {"contests": [{"candidates": [{"item_id": "cand-a", "name": "Ada"}]}]}))
    assert "dollar sign" not in problems
    assert "does not start as a full question" in problems or "capital" in problems
    money = (
        "## Race {#contest-race-one .contest-title}\n\n"
        "She won with $54.60 percent of the vote[^1].\n\n"
        "### Background\n\n"
        "She served on the board in 2020[^1].\n"
    )
    assert any("percent is printed with a dollar sign" in error for error in substance_errors(money, {"contests": []}))
    assert ballot_box_problem("Shall Justice Carlos G. Muñiz of the Supreme Court be retained in office?") == ""
    assert ballot_box_problem("Of the Fifth District Court of Appeal be retained in office?")
    assert ballot_box_problem("shall this school tax be renewed for the stated purpose?") == (
        "ballot box does not start with a capital letter"
    )
    assert ballot_box_problem("Shall this pass", "Shall this pass") == "ballot box is only the title"
    titled = (
        "## Race {#contest-race-one .contest-title}\n\n"
        "### Exact words on your ballot\n\n"
        "Amendment 2\n\n"
        "The full ballot wording was not captured.\n"
    )
    assert any("only the title" in error for error in substance_errors(titled, {"contests": []}))
    bare_heading = (
        "## Race {#contest-race-one .contest-title}\n\n"
        "### Recorded votes\n\n"
        "### Background\n\n"
        "She served on the board in 2020.\n"
    )
    assert any("empty heading" in error for error in substance_errors(bare_heading, {"contests": []}))
    empty = drop_heading = (
        "## Race {#contest-race-one .contest-title}\n\n### Status timeline\n\n### What is this about?\n\nIt raises the cap[^1].\n"
    )
    from lib.reader_substance import drop_empty_headings

    dropped = drop_empty_headings(empty)
    assert "Status timeline" not in dropped
    assert "What is this about?" in dropped
    staff = drop_empty_headings(
        "## Race {#contest-race-one .contest-title}\n\n### Staff analysis\n\n"
        "[Back to ballot](#your-ballot-at-a-glance)\n"
    )
    assert "Staff analysis" not in staff
    assert "Back to ballot" in staff
    same_quarter = fact_sentence(
        "No on H reported 18000 dollars in receipts for that same quarter[^28]."
    )
    assert same_quarter.startswith("No on H reported 18000 dollars")
    assert "Same quarter" not in same_quarter
    told = fact_sentence(
        "Florida Today reported in 2022, when this millage was first proposed, "
        "that parent Katie Delaney told the School Board the public had lost trust[^7]."
    )
    assert told.startswith("Parent Katie Delaney told")
    assert "Florida Today" not in told
    article = fact_sentence(
        "In that 2022 article, then-state representative Randy Fine wrote that the district was running a failing system[^8]."
    )
    assert article.startswith("Then-state representative Randy Fine wrote")
    nixon = fact_sentence(
        "The 2026 House directory and the House roster list Angie Nixon as Democrat for District 13, "
        "with roster dates November 6, 2024 through November 3, 2026[^41]."
    )
    assert nixon.startswith("Angie Nixon is the Democrat")
    assert "directory" not in nixon.lower()
    assert "November 6, 2024" in nixon
    moody = fact_sentence(
        "The Senate new-senators table and the office biography both record that Ashley Moody "
        "was appointed and sworn in on January 21, 2025[^36]."
    )
    assert moody.startswith("Ashley Moody was appointed")
    assert "biography" not in moody.lower()
    jenkins = fact_sentence(
        "Brevard County official results for the election dated August 18, 2020, list Jennifer Jenkins "
        "with 14,764 votes, 54.60 percent of 27,041, for School Board Member, District 3, "
        "and her campaign site says she served on the Brevard County School Board[^82]."
    )
    assert jenkins.startswith("In 2020, Jennifer Jenkins received 14,764 votes")
    assert "54.60 percent" in jenkins
    assert "$" not in jenkins
    assert "campaign site" not in jenkins.lower()
    assert "she served" in jenkins.lower()
    tally = fact_sentence(
        "The 2022 Brevard results page lists 146,334 yes votes, 58.21 percent, and 105,059 no votes, "
        "41.79 percent, for that millage[^14]."
    )
    assert tally.startswith("In 2022, the yes vote was 146,334")
    assert "results page" not in tally.lower()
    chief = fact_sentence(
        "The chief justice list says Carlos G. Muñiz served as chief justice from 2022 to 2024[^1]."
    )
    assert chief.startswith("Carlos G. Muñiz served as chief justice")
    professor = fact_sentence(
        "the senate handbook identifies Mike Haridopolos as a college professor and author, "
        "and his House biography says he taught U.S. history at Brevard Community College[^9]."
    )
    assert professor.startswith("Mike Haridopolos is a college professor and author, and he taught")
    assert "handbook" not in professor.lower()
    assert "As ," not in professor
    home = fact_sentence(
        "Wilton Simpson, Commissioner of Agriculture, lives in Pasco County, Florida[^2].",
        "background",
    )
    assert home.startswith("Wilton Simpson lives in Pasco County, Florida")
    lives = fact_sentence(
        "Division of Elections lists Ashley Moody, U.S. Senator from Florida, as Republican, "
        "and the filing city is Tampa[^4].",
        "background",
    )
    assert lives.startswith("Ashley Moody lives in Tampa, Florida")
    work = fact_sentence(
        "The office biography says Ashley Moody began at Holland & Knight and later joined the "
        "U.S. Attorney's Office, where the biography says she prosecuted drug offenses, "
        "and this work history is a single source[^5]."
    )
    assert "where she prosecuted" in work
    assert "biography" not in work.lower()
    assert "single source" not in work.lower()


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
