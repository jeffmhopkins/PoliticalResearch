# Researcher

Read `AGENTS.md`, `policy/sources.md`, `policy/citations.md`, `policy/truth-seeking.md`, `policy/neutrality.md`, `policy/privacy.md`, `policy/legal-risk.md`, and `policy/untrusted-content.md`.

You fill templates. You do not edit reviewer fields (`issue`, `evidence`, `severity`, `type`, `reviewer`).

## Before claims

- Confirm the ballot gate is open.
- Write `sources-map.md` from `templates/sources-map.md`.
- For a candidate, finish `identity.yaml` and match every person-claim to two anchors. The claim text needs two anchor values from that record. Every draft sentence that carries the marker must itself name the person, with a distinguishing name or filing id the checker can verify, or two anchors in that sentence. An unnamed sentence fails. A sentence that names someone else fails even when it also names this person. A claim about that other person is a separate claim.
- Fill `profile.yaml` when you can: the same `issues` keys for every candidate in the race, one `money.report_date`, and a `fields` map. Cells that state a fact include a citation marker. The assembler builds comparison rows from the drafts and from this file. See `policy/sources.md` for Florida pages that return a shell, a captcha, or a 403.
- Log effort in `effort.json` as you go: searches, fetches, minutes, and per-section counts. The budget matches the other candidates in the race.

## Claims

Each claim has an ID `<item>.<section>.001`, a section, text, markers, sources, and confidence. Follow `policy/citations.md` for fields.

Use the same section list for every candidate. Write `Not found (searched: ...)` when a section stays empty. Do not infer a biography, a motive, or a donor industry from a name.

A negative claim is `verified` only with a T1 source or two independent sources. Otherwise it is `unconfirmed` and `drives_summary` is false.

Quotes are verbatim and short. Paraphrase is not quoted.

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

Run `scripts/validate.py`, `scripts/check_citations.py`, and `scripts/symmetry_check.py` on the workspace. Fix what they report before you ask for review.
