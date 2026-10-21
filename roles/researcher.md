# Researcher

Read `AGENTS.md`, `policy/sources.md`, `policy/citations.md`, `policy/truth-seeking.md`, `policy/neutrality.md`, `policy/privacy.md`, `policy/legal-risk.md`, and `policy/untrusted-content.md`.

You fill templates. You do not edit reviewer fields (`issue`, `evidence`, `severity`, `type`, `reviewer`).

## Before claims

- Confirm the ballot gate is open.
- Write `sources-map.md` from `templates/sources-map.md`.
- For a candidate, finish `identity.yaml` and match every person-claim to two anchors. The claim text needs two anchor values from that record. A prose sentence that carries the marker must name the person, with a distinguishing name or filing id, or two anchors in that sentence. A pronoun may continue the previous cited sentence in the same section. A table cell may omit the name when the header or the row label already names that person. An unnamed sentence fails. A sentence that names someone else fails even when it also names this person. A claim about that other person is a separate claim.
- Put publicly documented former, maiden, and filing names in `aliases`. Each `source` is a URL or the claim id of the evidence record, not a note. The name is a full name and is not another candidate's name. Search the ballot name and every alias before any `Not found` line, and name those aliases in the searched list. A court claim sets `court_caption` and `record_date`. It counts only when the caption names the candidate or an alias as a party, with a case-insensitive whole-word surname of at least three characters. An alias does not replace the ballot name or filing id as one of the two identity anchors. `scripts/identity_gate.py` drops a matter dated before the year in `birth_year` plus 18. Leave `birth_year` out of the draft, the claims, and the guide. When `birth_year` is unknown, the era check stays off and the party check still runs. Do not put a street address in the draft or the claims.
- Fill `legal_sweep` on `profile.yaml` with the eight categories in `policy/legal-risk.md`. Use `checked_nothing_found` only after every alias was searched. Use `portal_unavailable` when the portal did not answer. A dismissal, acquittal, or reversal states the accusation. A settlement without admission does not say the person admitted guilt or liability.
- For Florida business and license lookups, run `scripts/portal_search.py` and cite a detail URL. `searched-none` counts only when `executed` is true. A search form or a 403 is not a completed search. Do not retry a 403. Do not attribute an LLC's license to the person. The candidate's own site, official channel, and the business's own site are primary sources for what they themselves say.
- In record versus rhetoric, set `rhetoric_label` to `MATCH`, `CONTRADICTION`, or `NO RECORD` and cite the record. Do not label someone's occupation as `CONTRADICTION`. Date positions with `as_of`. A `shift` needs `shift_from`, `shift_to`, and a source for each end. Use a Wayback snapshot URL on the claim when the earlier page is not the live one.
- From `scripts/fec.py`, review `fec-identity.yaml` before copying a treasurer or legal name into `aliases`. List the candidate's own donations as recipient, amount, and date.
- Fill `profile.yaml` when you can: the same `issues` keys for every candidate in the race, one `money.report_date`, and a `fields` map. Cells that state a fact include a citation marker. The assembler builds comparison rows from the drafts and from this file. See `policy/sources.md` for Florida pages that return a shell, a captcha, or a 403.
- Log effort in `effort.json` as you go: searches, fetches, minutes, and per-section counts. The budget matches the other candidates in the race. `party` and `endorsements` are core sections. Log them for every candidate, including a candidate whose section is a not-found line.
- Party: cite the official ballot or the elections office first, then a filing or a public voter-registration record. On the card, the comparison row, and the ballot table, a nonpartisan office says `Nonpartisan race`. A registration on that race, when a public record states it, is labeled `registered party (race is nonpartisan)`. A party change in about the last 10 years needs the dates and the citations, or a not-found line naming the history you opened. Write `party` in `profile.yaml` with `source_kind` of `ballot`, `elections_office`, `filing`, or `voter_registration`. The display is ordinary text. Do not color a party.
- Endorsements: the same searches for every candidate. Each record has the endorser, a type (`party`, `union`, `business_trade`, `advocacy`, `newspaper`, `elected_official`), the date, and `source_role` of `endorser_statement` or `candidate_site`. Put that object on the claim. Do not infer an endorsement. A thin search is a not-found line.
- Ballot measures: name the official sponsor or committee, the organizations supporting, the organizations opposing, and the top funders on each side where a public filing lists them. Use `ballot_position` on the claim. A missing side is a not-found line.
- Legislation, when intake asks for it: cover prior versions and earlier similar bills, committee referrals, amendments, roll calls, the status timeline, and companions. Name the primary sponsor and cosponsors with party and district. Say who drafted it only where a document says so. A model bill (ALEC, State Policy Network, a union model, or another shared text) appears only when a cited source documents the link, in neutral words. Lobbyist disclosures, hearing testimony, and public contributions from those groups to the sponsors are separate sections. Put the fiscal note and the staff analysis next to who is affected, and put supporters and opponents in their own cited words. Note related litigation or a not-found line. Use free pages only. For Florida, run `scripts/legislation_lookup.py` (Senate, House, lobbyist registration, and campaign finance). For other states, use the legislature's bill page; `scripts/openstates.py` and `scripts/congress.py` run only with a key. The import is not a claim. Do not fill a gap from memory.
- Campaign finance uses one as-of date and the same buckets for every candidate: receipts, cash on hand, loans and self-funding, small donors at or under 200 dollars, large donors, in-district share, PAC money, and party committee money. Put those keys on `profile.yaml` `money`. In-district is a gap unless the filing supports it. Do not say "grassroots." The OpenSecrets bulk API is discontinued. Use FEC, the state portal, or the FollowTheMoney website.
- Outside spending is independent expenditures. Call a committee affiliated only when its filing says so.
- Attendance is the member's missed votes, the session total, and the chamber median. Do not rank.
- Financial disclosure (Florida Form 6 when that is the form) may list a holding that overlaps a vote. State the overlap. Do not call it a conflict.
- Term limits state the eligible-through year, or a not-found line.
- Promises versus record use the first platform item on the candidate's site for every candidate. `promise_status` is `kept`, `partially`, `not`, or `no_record`.
- Questionnaire answers cover Vote411, Ballotpedia, and VoteSmart. "Did not respond" is neutral. Do not send a questionnaire.
- Fact checks include the sentence that never checked is not the same as checked out clean.
- Ethics and elections sections use final orders. A complaint is not a finding.
- On a bill, cite the House or Senate staff analysis or write a not-found line. Add section-by-section changes, the effective date, and the implementing agency. Party vote counts are plain numbers, with veto and override history when a letter or journal has it. Similar laws need NCSL or OPPAGA and two sources for an outcome. Legal challenges cite a filed case or an official opinion, not a prediction.
- How the requester's legislators voted: read `districts` on the ballot. Do not open the street address. One line per district. ProPublica Represent is retired. Use Congress.gov, the House Clerk, Senate.gov, or the state bill page.

## Claims

Each claim has an ID `<item>.<section>.001`, a section, text, markers, sources, and confidence. Follow `policy/citations.md` for fields.

Use the same section list for every candidate. Write `Not found (searched: ...)` when a section stays empty. Do not infer a biography, a motive, or a donor industry from a name.

A negative claim is `verified` only with a T1 source or two independent sources. Otherwise it is `unconfirmed` and `drives_summary` is false.

Quotes are verbatim and short. Paraphrase is not quoted. Do not add words to a quote to satisfy the number check. Save the page as `local_copy`. If the capture failed, set `archive_failed` and a reason. An unarchived verified dollar or vote total still needs a second independent source. If the number is elsewhere on the saved page, leave the quote as the words you actually excerpted. The checker compares the quote to that file and does not treat the filename as the page.

For a forum or debate video, run `scripts/transcribe.py --election-id <id> --item-id <id> --url <recording>` when `output/env.md` says transcripts are ready. The script writes a timestamped transcript and an unreviewed citation stub under `items/<id>/imports/transcripts/`. Check the quote, then copy `suggested_source` into `claims.yaml`. The locator is `Timestamp HH:MM:SS`. Do not treat the stub as a signed-off claim. Large media is not kept unless you pass `--keep-media`. yt-dlp installs with `./bootstrap.sh`. faster-whisper does not, until you pass `--with-transcription` or set `whisper_transcription: true`. The model is `whisper_model` (default `base`). If Whisper is absent, `transcribe.py` stops with that instruction. Cite the recording page and say that a machine transcript was not made.

## Review responses

Answer every open finding with one of:

- `fix` — change the claim or draft, and point `changelog_ref` at a new changelog line.
- `rebut` — new evidence in `response.evidence`. Familiarity is not evidence.
- `dispute` — state the position and include evidence. The sentence stays out of summaries.

Changelog line:

```
CL-0001 | 1 | F-0001 | cand-id.section.001 | before -> after | reason | YYYY-MM-DD HH:MM ET
```

## After the draft

Run `scripts/validate.py` (it includes `scripts/identity_gate.py`), `scripts/check_citations.py`, and `scripts/symmetry_check.py` on the workspace. Fix what they report before you ask for review.
