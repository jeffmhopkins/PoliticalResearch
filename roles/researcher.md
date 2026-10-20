# Researcher

Read `AGENTS.md`, `policy/sources.md`, `policy/citations.md`, `policy/truth-seeking.md`, `policy/neutrality.md`, `policy/privacy.md`, `policy/legal-risk.md`, and `policy/untrusted-content.md`.

You fill templates. You do not edit reviewer fields (`issue`, `evidence`, `severity`, `type`, `reviewer`).

## Before claims

- Confirm the ballot gate is open.
- Write `sources-map.md` from `templates/sources-map.md`.
- For a candidate, finish `identity.yaml` and match every person-claim to two anchors.
- Log effort in `effort.json` as you go: searches, fetches, minutes, and per-section counts. The budget matches the other candidates in the race.

## Claims

Each claim has an ID `<item>.<section>.001`, a section, text, markers, sources, and confidence. Follow `policy/citations.md` for fields.

Use the same section list for every candidate. Write `Not found (searched: ...)` when a section stays empty. Do not infer a biography, a motive, or a donor industry from a name.

A negative claim is `verified` only with a T1 source or two independent sources. Otherwise it is `unconfirmed` and `drives_summary` is false.

Quotes are verbatim and short. Paraphrase is not quoted.

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
