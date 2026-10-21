# Intake

Read `AGENTS.md`, `policy/privacy.md`, and this file. Write intake answers with `scripts/intake.py`. Do not store the requester's address, email, phone, or ballot photo in `intake.yaml`.

## Ask

- Election date and type (primary, general, special).
- Jurisdiction: state, county, city, and districts. Or a residential address, which you store only with `scripts/intake.py set-address`.
- Scope: the whole ballot, or a list of contests.
- Whether to include legislation. Default is no. If yes, ask for a topic list. Record `include_legislation` and `legislation_topics`.
- Depth: quick, standard, or deep.
- Output: Markdown, HTML, PDF.
- Language. v1 produces English. If they need another language, say so and record it as a gap. Do not pretend the guide is translated.
- Accessibility needs (large type, plain language, screen-reader HTML).
- Offline archive: "Do you want an offline copy of every cited source bundled with the report?" Default no. Record `offline_archive`.
- A short requester label such as "household". Do not ask for a legal name.

## Do not ask

Party, ideology, religion, or "what you care about." This guide does not match values and does not recommend a vote.

## Ballot finder

Use sources in this order. Every contest needs an official source URL. Flag conflicts. Do not invent a contest to fill a gap.

1. A sample ballot or photo the requester supplies. Keep the file in the workspace `private/` directory (`output/<election-id>/private/`). This is the preferred source. Do not copy that directory into artifacts or git.
2. The county or state sample ballot and voter pamphlet.
3. `scripts/ballot_lookup.py` when `GOOGLE_CIVIC_API_KEY` is set (`officialOnly=true`). Democracy Works runs only when both `DEMOCRACY_WORKS_API_KEY` and `DEMOCRACY_WORKS_API_URL` are set.
4. Ballotpedia or VOTE411 as a cross-check, never as the only official URL.

If no key is set, the lookup script exits 0, writes `lookup_status: skipped_no_api_key`, and leaves contests empty. Fill them from the official ballot.

## Confirmation

Show the offices, candidates, measures, and districts. Ask the requester to correct the list. Then run `scripts/intake.py confirm`, which sets `confirmed_by_requester: true`, records the timestamp, and deletes ballot images.

Do not scaffold research items or fetch finance before that flag is true. `scripts/intake.py gate` exits 1 until it is.
