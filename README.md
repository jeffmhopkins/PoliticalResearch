<div align="center">

# PoliticalResearch

A reusable kit an AI coding agent follows to research one voter's upcoming ballot and write a nonpartisan, cited guide.

[![CI](https://github.com/jeffmhopkins/PoliticalResearch/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml) [![Tests](https://img.shields.io/badge/tests-pytest-blue)](tests) [![Nonpartisan](https://img.shields.io/badge/guide-nonpartisan-blue)](policy/neutrality.md)

</div>

The kit covers candidates (including judicial retention, primaries, and local offices), ballot measures, and, when you ask, specific bills. Finished guides are Markdown, HTML, and PDF under git-ignored `output/`. This repository does not upload them.

# Are you a human? Start here

> [!TIP]
> Tell your agent: "Read AGENTS.md and start a guide for this election." Give it the election date and your county, or a sample ballot. Reports land in `output/<election-id>/`.

**What it will do**

- Ask a short intake: election, place, depth (`quick`, `standard`, or `deep`), formats, and whether you want an offline copy of cited sources.
- Build a contest list from your sample ballot or from official pages, then ask you to confirm it before research starts.
- Write the same sections for every candidate, with sources, dates, and visible gaps where a fact was not found.
- Run a review loop that can mark a claim disputed and leave both positions in the guide.
- Save a short reader edition and a full audit edition as Markdown, HTML, and PDF under `output/`. Those files are git-ignored and are not uploaded by this repo. The reader opens with what is on the ballot and keeps one short contest section. Citations, quotes, and the search log are in the sources addendums, `guide-sources.md` and `guide-full-sources.md`.

> [!CAUTION]
> **This is not an official ballot and not voting instructions.** Confirm contests, deadlines, and polling places with the election office linked in the guide. The guide does not endorse, rank, score, or recommend a vote. It does not ask your party or your values. There is no values-matching mode.

> [!WARNING]
> **Addresses and reports stay off git.** A street address, if you provide one, is stored only with `scripts/intake.py set-address` in `output/<election-id>/private/address.txt`. `intake.yaml` keeps a label and the path, and does not store the address. `scripts/intake.py confirm` deletes ballot images and PDFs under that `private/` directory after the contest list is extracted. Do not commit `output/`, `private/`, or `.env`. Do not paste a home address, a ballot photo, or a finished guide into a commit, an issue, or a pull request. An offline source bundle, when you asked for one, is for your own reference. Pages in that bundle can be copyrighted. Do not republish them.

**Run it**

```bash
./bootstrap.sh
```

You can practice on the fictional fixture without touching a real ballot:

```bash
./bootstrap.sh
.venv/bin/python -m pytest
./scripts/build.sh --workspace examples/sample-election
```

Open [examples/sample-election/final/guide.md](examples/sample-election/final/guide.md). It is fiction. Cedar Hollow, Westland, Avery Quinn, and Blake Okonkwo are not real. See [examples/sample-election/README.md](examples/sample-election/README.md).

# Are you an AI agent? Start here

> [!IMPORTANT]
> Stop. Read [AGENTS.md](AGENTS.md) and follow it. The checklist at the top of that file is mandatory before you research a ballot. Then read [REVIEW.md](REVIEW.md) and the files in [policy/](policy/) for the role you are playing. [CLAUDE.md](CLAUDE.md) only adds notes for Claude Code. Do not recommend a vote, a ranking, or a score. Do not invent ballot contents, dates, deadlines, or polling places. Do not commit or push `output/`, `private/`, or `.env`. Do not write to this upstream repository as part of a voter-guide run.

## Requirements

Verify this before research. `./bootstrap.sh` writes the tooling rating to `output/env.md` as **Full**, **Reduced**, or **Minimal**.

- **Environment.** You are in a Linux sandbox with a shell. You can install packages, or they are already installed.
- **Required capabilities.** You can search the web and fetch pages, read and write local files, run shell commands and Python 3, and read PDFs (`pdftotext` from poppler-utils).
- **Separate contexts.** Spawn parallel subagents so researchers and reviewers work separately. If you cannot, run each role one at a time in a fresh context and say that in the methodology. A sign-off in the same context that drafted the claims is a process gap (`scripts/loop.py signoff --same-context`).
- **Bootstrap.** Run `./bootstrap.sh` (see the flags below). If an install fails, continue. The environment report keeps the tooling rating and marks that sandbox capability reduced.
- **Optional API keys.** Copy [.env.example](.env.example) to `.env` if bootstrap did not. Keys: OpenFEC, Google Civic, Democracy Works (key plus URL), Open States, Congress.gov, and LegiScan. Missing keys are disclosed in `output/env.md` and do not lower a Full rating. Scripts exit successfully and tell you to use official pages. Do not invent the data the API would have returned. LegiScan has no client script in v1. Democracy Works is called only when both its key and its URL are set.
- **Behavior.** Ask the intake questions in [roles/intake.md](roles/intake.md). Get ballot confirmation before research. Cite every factual claim using [policy/citations.md](policy/citations.md). Apply the same template and effort to every candidate. There is no values-matching mode.
- **Gaps.** If something is missing, tell the requester what the report will lack. Continue only if they say to continue. Record the rating and the gaps in the methodology.
- **Resume.** If `output/<election-id>/` already exists, run `python3 scripts/resume.py --election-id <election-id>` before any other step.

Policies in `policy/` are binding. If `AGENTS.md` and a policy disagree, the stricter citation, privacy, or neutrality rule wins. The twelve hard rules, the phase gates, and who may write which file are in [AGENTS.md](AGENTS.md). The correction loop is in [REVIEW.md](REVIEW.md).

> [!IMPORTANT]
> **Neutrality.** The guide describes the ballot. It does not choose a side. Every candidate in a race gets the same sections, the same questions, and a comparable search. A missing fact stays `Not found (searched: ...)`. `scripts/symmetry_check.py` rejects a missing core section, thin effort, and prose that only swaps a name. Each candidate gets one strongest-case sentence tied to the record. Measure and bill arguments stay close in length. Interest-group ratings appear only as a pair from opposite sides, or they are omitted. The neutrality reviewer reads a blinded draft from `scripts/swap.py` and does not open intake notes. Do not ask what the requester believes. Details: [policy/neutrality.md](policy/neutrality.md).

> [!IMPORTANT]
> **Citations.** Every factual sentence, number, quote, date, vote, dollar figure, legal status, and characterization of a position carries a marker such as `[^12]`. The marker resolves to one source on one claim in `claims.yaml`. The assembler renders it as a link to the sources addendum (`guide-sources.md` for the reader, `guide-full-sources.md` for the full edition), which holds the works-cited line, the quote, and the claim text. A missing addendum entry fails the guide check. A `verified` claim needs a T1 source or two independent sources. `single-source` is labeled. `unconfirmed` and `disputed` claims stay out of summaries. Uncited factual text fails the build. `scripts/check_citations.py` enforces [policy/citations.md](policy/citations.md).

> [!NOTE]
> **Record checks.** `identity.yaml` can list documented aliases and a `birth_year`. An alias source is a URL or a claim id, the name is a full name, and it cannot be another candidate's name. The year is an internal court-record check and is not printed. `scripts/identity_gate.py` keeps a court record only when the caption names the candidate or an alias as a party, drops matters from before the candidate turned 18, and rejects a birth-year phrase or a street address in a draft, a claim, or the assembled guide. Every candidate's `legal_sweep` uses the same eight categories, and `scripts/symmetry_check.py` compares those keys and whether each category was checked. Record versus rhetoric is a cited `MATCH`, `CONTRADICTION`, or `NO RECORD` label. Occupation is not a contradiction. `scripts/portal_search.py` runs the Florida Sunbiz and DFS lookups. `searched-none` is a recognized results page that says nothing was found, even if the search form remains. Detail rows are hits even if the page mentions recaptcha. A bare search form or a challenge page with no result rows was not executed. A 403 is not retried. `scripts/fec.py` writes filing names and the candidate's own donations for review, without alignment commentary. Fact-check and sourcing record a not-checked list with `scripts/loop.py note-unchecked` before they sign off. Details: [policy/legal-risk.md](policy/legal-risk.md), [policy/sources.md](policy/sources.md), [policy/neutrality.md](policy/neutrality.md), [policy/privacy.md](policy/privacy.md).

> [!NOTE]
> **Short reader, full edition, and the sources addendums.** `scripts/assemble.py` writes `final/guide.md` (reader), `final/guide-sources.md` (reader sources), `final/guide-full.md` (audit), and `final/guide-full-sources.md` (audit sources). The fictional copies are [examples/sample-election/final/guide-sources.md](examples/sample-election/final/guide-sources.md) and [examples/sample-election/final/guide-full-sources.md](examples/sample-election/final/guide-full-sources.md). The reader opens with the ballot table, then one short contest section at a time, inside a per-contest word budget. Comparison cells are short facts. Empty rows that are empty for every candidate become one gap sentence. Per-candidate prose stays in the full edition, which also adds the marker index and the changelog. Works cited, quotes, cell detail, and the search log are in that edition's sources addendum. A marker in the body links to the addendum, and the addendum links back.
>
> `scripts/build.sh` writes HTML and PDF for the reader, both addendums, and the full edition. [scripts/check_pdf_layout.py](scripts/check_pdf_layout.py) fails the build when text is outside the page box, below the minimum size, or in columns narrower than 1.5 inches. It also fails when a comparison table has more than three candidates. It does not judge the writing. The check reads Poppler `pdftotext -bbox` output and the built HTML. The default design is Docket: IBM Plex Sans and IBM Plex Serif, with Liberation and DejaVu as fallbacks. Optional themes in `assets/themes/` load after that default and do not replace it: `./scripts/build.sh --workspace PATH --theme charter` (or `folio`). Omitting `--theme` keeps Docket.
>
> An offline copy of cited pages is a separate bundle. Intake records `offline_archive` (default no). `pending` does not capture anything. When it is `true`, `scripts/archive_sources.py` writes `archive/` and `final/guide-with-sources.zip` (the guide files plus the local copies and `archive/manifest.csv`). The default `archive_tier` is `html-pdf` (HTTP body and a PDF print). `full` also saves a monolith mirror and a screenshot when those tools are installed. A failed fetch is `capture_failed`, with a Wayback copy when one exists.

> [!TIP]
> **Bootstrap flags.** `./bootstrap.sh` installs pandoc, a PDF engine (weasyprint, then wkhtmltopdf), poppler-utils, fonts-liberation when Liberation Serif is missing, a virtualenv, the packages in [requirements.txt](requirements.txt), and the sandbox tools: ffmpeg, yt-dlp, monolith, headless Chromium or Chrome, and pa11y. It does not install Whisper.
>
> - `./bootstrap.sh --with-transcription` also installs faster-whisper and downloads the model named by `whisper_model` in [config.yaml](config.yaml) (default `base`). The same opt-in is `whisper_transcription: true`. `scripts/transcribe.py` exits with a short message when Whisper is not installed.
> - `./bootstrap.sh --minimal` skips ffmpeg, yt-dlp, monolith, Chromium, and pa11y. Core build tools still install. `--minimal` does not cancel `--with-transcription`. Built-in HTML checks, HTTP archive copies, and PDF prints still run.
> - `./bootstrap.sh --check` reports only and exits 2 unless the rating is Full. It never installs.
>
> A heavy install that fails is reported and bootstrap continues. The tooling rating can stay **Full** while a sandbox capability is **reduced**.

**Ratings**

`scripts/env_report.py` sets the rating:

- **Full** — bash, git, Python 3.10 or newer, curl, jq, pandoc, poppler (`pdftotext`), a PDF engine, the virtualenv packages, and a `.gitignore` that ignores `output/` and `private/`.
- **Reduced** — bash, git, Python, and curl are present, and jq, pandoc, pdftotext, a PDF engine, the virtualenv packages, or the `.gitignore` check for `output/` and `private/` is missing.
- **Minimal** — bash, git, Python, or curl is missing.

# First test session

1. `./bootstrap.sh`
2. `git check-ignore -v output/private-test private/address.txt` should show those paths ignored. Do not create them in git.
3. Run the fixture checks. Continuous integration runs the same pytest suite and the fixture gate on every pull request ([.github/workflows/ci.yml](.github/workflows/ci.yml)). The gate date is pinned to the fixture.

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/validate.py --workspace examples/sample-election --gate --today 2026-10-20
./scripts/build.sh --workspace examples/sample-election
```

4. For a throwaway workspace that does not use a real address:

```bash
.venv/bin/python scripts/intake.py init --election-id demo-session --label household --now "2026-10-20 12:00 ET"
.venv/bin/python scripts/intake.py set --election-id demo-session --field election_date --value 2026-11-03
.venv/bin/python scripts/intake.py set --election-id demo-session --field jurisdiction_label --value "Oak County, Westland"
.venv/bin/python scripts/ballot_lookup.py --election-id demo-session
```

Without `GOOGLE_CIVIC_API_KEY`, lookup writes `skipped_no_api_key` and does not invent contests. Add contests to `output/demo-session/ballot.yaml` only from an official sample ballot, then:

```bash
.venv/bin/python scripts/intake.py confirm --election-id demo-session --now "2026-10-20 12:00 ET"
.venv/bin/python scripts/resume.py --election-id demo-session
```

`output/demo-session/` stays uncommitted. Record sharing approval with `scripts/intake.py approve-sharing` before a guide is sent to anyone else. Approval is required before sharing, and it is not required before assembly.

# Layout

| Path | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Agent contract, phases, hard rules |
| [CLAUDE.md](CLAUDE.md) | Pointer for Claude Code |
| [REVIEW.md](REVIEW.md) | Correction loop |
| [policy/](policy/) | Sources, citations, neutrality, privacy, legal risk, truth-seeking, untrusted content |
| [roles/](roles/) | Who may write which files |
| [templates/](templates/) | Section outlines and JSON Schemas |
| [scripts/](scripts/) | Deterministic helpers |
| [examples/sample-election/](examples/sample-election/) | Fictional worked example |
| [config.yaml](config.yaml) | Defaults for rounds, staleness, effort parity, and the choices below |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change the tool. Guides are not pull requests |
| `output/` | Git-ignored run directory |

# Defaults for open choices

These match [config.yaml](config.yaml). Python 3.10 or newer ([pyproject.toml](pyproject.toml)).

| Topic | Choice |
| --- | --- |
| License | MIT, copyright Jeffrey Hopkins |
| Review rounds | 3, then the cap. A refresh uses 1 round |
| Agent runtimes | Any Linux agent via `AGENTS.md`. Claude Code has extra notes in `CLAUDE.md` |
| Paid data APIs | Optional keys only. No Ballotpedia or BallotReady client. Democracy Works is called only if you set its URL |
| Legislation | Off unless intake says `include_legislation: true` and lists topics |
| PDF engine | weasyprint, then wkhtmltopdf. `scripts/check_pdf_layout.py` fails the build when text is outside the page, below the minimum size, or in columns narrower than 1.5 inches, and when a comparison table has more than three candidates |
| Transcripts | Opt-in via `--with-transcription` or `whisper_transcription: true`. Model is `whisper_model` (default `base`) |
| Offline captures | HTTP body and PDF always when `offline_archive` is true. Monolith and a screenshot install by default; `--minimal` skips them |
| Accessibility | Built-in HTML checks always. pa11y installs by default; `--minimal` skips it. An installed checker that reports errors fails the build |
| Languages | English in v1 |
| Human sign-off | Required before sharing, not before assembly |
| Strongest case | One cited sentence per candidate. Measure and bill arguments stay close in length |
| Interest-group ratings | A pair from opposite sides, or omit |

# Credits

The workflow borrows ideas, not code, from:

- [little-ballot-helper](https://github.com/arcataroger/little-ballot-helper) (CC0) — phased research, symmetric evidence, blinded swap, environment rating, staleness
- [STORM](https://github.com/stanford-oval/storm) — outline, then cite
- [gpt-researcher](https://github.com/assafelovic/gpt-researcher) — plan, parallel research, write
- [VOTE411](https://www.vote411.org/) and [LWVC Pros & Cons](https://www.lwvc.org/vote/pros-cons)
- [California Voter Information Guide](https://vigarchive.sos.ca.gov/2024/general/) and [LAO ballot analyses](https://lao.ca.gov/BallotAnalysis)
- [Oregon Voters' Pamphlet](https://sos.oregon.gov/elections/Pages/Voters-Pamphlet.aspx)
- [CalMatters voter guide](https://calmatters.org/california-voter-guide-2024/)
- [OpenSecrets](https://www.opensecrets.org/)
- [Wikipedia infobox officeholder](https://en.wikipedia.org/wiki/Template:Infobox_officeholder)
- [Google Civic Information API](https://developers.google.com/civic-information/docs/v2), [Democracy Works Elections API](https://www.democracy.works/elections-api), [OpenFEC](https://github.com/fecgov/openFEC), [Open States](https://openstates.org/)
- [We Vote](https://github.com/wevote/WebApp) — a reference for how endorsements can be modeled, not a source of ratings here

# License

MIT. Copyright (c) 2026 Jeffrey Hopkins. See [LICENSE](LICENSE).
