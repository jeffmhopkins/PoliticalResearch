# Researcher

Read `AGENTS.md`, `policy/sources.md`, `policy/citations.md`, `policy/truth-seeking.md`, `policy/neutrality.md`, `policy/privacy.md`, `policy/legal-risk.md`, and `policy/untrusted-content.md`.

You fill templates. You do not edit reviewer fields (`issue`, `evidence`, `severity`, `type`, `reviewer`).

## Before claims

- Confirm the ballot gate is open.
- Write `sources-map.md` from `templates/sources-map.md`.
- For a candidate, finish `identity.yaml` and match every person-claim to two anchors. The claim text needs two anchor values from that record. A prose sentence that carries the marker must name the person, with a distinguishing name or filing id, or two anchors in that sentence. A pronoun may continue the previous cited sentence in the same section. A table cell may omit the name when the header or the row label already names that person. An unnamed sentence fails. A sentence that names someone else fails even when it also names this person. A claim about that other person is a separate claim.
- Put publicly documented former, maiden, and filing names in `aliases`. Each `source` is a URL or the claim id of the evidence record, not a note. The name is a full name and is not another candidate's name. Search the ballot name and every alias before any `Not found` line, and name those aliases in the searched list. A court claim sets `court_caption` and `record_date`. It counts only when the caption names the candidate or an alias as a party, with a case-sensitive whole-word surname of at least three characters. An alias does not replace the ballot name or filing id as one of the two identity anchors. `scripts/identity_gate.py` drops a matter dated before the year in `birth_year` plus 18. Leave `birth_year` out of the draft, the claims, and the guide. When `birth_year` is unknown, the era check stays off and the party check still runs. Do not put a street address in the draft or the claims.
- Fill `legal_sweep` on `profile.yaml` with the eight categories in `policy/legal-risk.md`. Use `checked_nothing_found` only after every alias was searched. Use `portal_unavailable` when the portal did not answer. A dismissal, acquittal, or reversal states the accusation. A settlement without admission does not say the person admitted guilt or liability.
- For Florida business and license lookups, run `scripts/portal_search.py` and cite a detail URL. `searched-none` counts only when `executed` is true. A search form or a 403 is not a completed search. Do not retry a 403. Do not attribute an LLC's license to the person. The candidate's own site, official channel, and the business's own site are primary sources for what they themselves say.
- In record versus rhetoric, set `rhetoric_label` to `MATCH`, `CONTRADICTION`, or `NO RECORD` and cite the record. Do not label someone's occupation as `CONTRADICTION`. Date positions with `as_of`. A `shift` needs `shift_from`, `shift_to`, and a source for each end. Use a Wayback snapshot URL on the claim when the earlier page is not the live one.
- From `scripts/fec.py`, review `fec-identity.yaml` before copying a treasurer or legal name into `aliases`. List the candidate's own donations as recipient, amount, and date.
- Fill `profile.yaml` when you can: the same `issues` keys for every candidate in the race, one `money.report_date`, and a `fields` map. Cells that state a fact include a citation marker. The assembler builds comparison rows from the drafts and from this file. See `policy/sources.md` for Florida pages that return a shell, a captcha, or a 403.
- Log effort in `effort.json` as you go: searches, fetches, minutes, and per-section counts. The budget matches the other candidates in the race.

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
