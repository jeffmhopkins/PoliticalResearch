# Are you a human? Start here

PoliticalResearch is a reusable kit an AI coding agent follows to research **your** upcoming ballot and write a **nonpartisan, cited** guide. It covers candidates, ballot measures, and, if you ask, specific bills. It does not tell you how to vote.

**What it will do**

- Ask a short intake (election, place, how deep, whether you want an offline copy of sources).
- Build a contest list from your sample ballot or from official pages, then ask you to confirm it before research starts.
- Write the same sections for every candidate, with sources, dates, and visible gaps where a fact was not found.
- Run a review loop that can mark a claim disputed instead of dropping it.
- Save a reader edition and a full audit edition as Markdown, HTML, and PDF under `output/`. Those files are git-ignored and are not uploaded by this repo. The reader opens with what is on the ballot.

**What it will not do**

- Endorse, rank, score, or recommend a vote.
- Act as an official ballot or as the source for registration deadlines and polling places. Those stay as links to your election office.
- Ask your party or your values. There is no "match my views" mode.
- Store your street address or ballot photo in git.

**Run it**

```bash
./bootstrap.sh
```

Then tell your agent: "Read AGENTS.md and start a guide for this election." Give it the election date and your county, or a sample ballot. Reports land in `output/<election-id>/`. Your address, if you provide one, stays in `output/<election-id>/private/`.

You can practice on the fictional fixture without touching a real ballot:

```bash
./bootstrap.sh
.venv/bin/python -m pytest
./scripts/build.sh --workspace examples/sample-election
```

Open `examples/sample-election/final/guide.md`. It is fiction. Cedar Hollow, Westland, Avery Quinn, and Blake Okonkwo are not real.

**Privacy.** Do not commit `output/` or `private/`. An offline source bundle, if you asked for one, is for your own reference. Pages in that bundle can be copyrighted. Do not republish them.

**Not an official ballot. Not voting instructions.**

Prior art that shaped the workflow is credited below. The license is MIT, copyright Jeffrey Hopkins.

# Are you an AI agent? Start here

Stop. Read [AGENTS.md](AGENTS.md) and follow it. The checklist at the top of that file is mandatory before you research a ballot. Then read [REVIEW.md](REVIEW.md) and the files in `policy/` that match the role you are playing.

Do not recommend a vote. Do not invent ballot contents. Do not commit `output/`, `private/`, or `.env`.

# What this repository is

Instructions, policies, templates, schemas, and small scripts. The agent does the research. The scripts keep the files valid: schemas, citation markers, symmetry, the review cap, resume, and the HTML/PDF build.

```bash
./bootstrap.sh                      # core tools plus yt-dlp, monolith, Chromium, and pa11y
./bootstrap.sh --with-transcription # also faster-whisper and the Whisper model
./bootstrap.sh --minimal            # core tools only; skip ffmpeg, yt-dlp, monolith, Chromium, and pa11y
./bootstrap.sh --check              # report only; exit 2 unless the rating is Full
```

`--check` never installs. Whisper stays off unless you pass `--with-transcription` or set `whisper_transcription: true` in `config.yaml`. `whisper_model` (default `base`) is what that opt-in downloads. `--minimal` skips ffmpeg, yt-dlp, monolith, Chromium, and pa11y, and does not cancel `--with-transcription`. A heavy install that fails is reported and bootstrap continues. The tooling rating can stay **Full** while a sandbox capability is **reduced**. `scripts/transcribe.py` tells you how to turn Whisper on when it is not installed.

Ratings:

- **Full** — Python, pandoc, a PDF engine, poppler, jq, and the virtualenv packages are present.
- **Reduced** — you can still draft Markdown, but build or schema tools are missing.
- **Minimal** — the sandbox cannot run the scripts reliably.

API keys are optional. The environment report lists them as set or unset and never prints the values. Missing keys do not lower a Full tooling rating; they are disclosed separately because live finance and ballot lookups will be skipped.

# First test session

1. `./bootstrap.sh`
2. `git check-ignore -v output/private-test private/address.txt` should show those paths ignored. Do not create them in git.
3. Run the fixture checks:

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

`output/demo-session/` stays uncommitted.

# Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Agent contract, phases, hard rules |
| `CLAUDE.md` | Pointer for Claude Code |
| `REVIEW.md` | Correction loop |
| `policy/` | Sources, citations, neutrality, privacy, legal risk, untrusted content |
| `roles/` | Who may write which files |
| `templates/` | Section outlines and JSON Schemas |
| `scripts/` | Deterministic helpers |
| `examples/sample-election/` | Fictional worked example |
| `output/` | Git-ignored run directory |

# Defaults for open choices

These match `config.yaml`.

| Topic | Choice |
| --- | --- |
| License | MIT, copyright Jeffrey Hopkins |
| Review rounds | 3, then the cap. A refresh uses 1 round |
| Agent runtimes | Any Linux agent via `AGENTS.md`. Claude Code has extra notes in `CLAUDE.md` |
| Paid data APIs | Optional keys only. No Ballotpedia or BallotReady client. Democracy Works is called only if you set its URL |
| Legislation | Off unless intake says `include_legislation: true` and lists topics |
| PDF engine | weasyprint, then wkhtmltopdf |
| Transcripts | Opt-in via `--with-transcription` or `whisper_transcription: true`. Model is `whisper_model` (default `base`) |
| Offline captures | HTTP body and PDF always. Monolith and a screenshot install by default; `--minimal` skips them |
| Accessibility | Built-in HTML checks always. pa11y installs by default; `--minimal` skips it |
| Languages | English in v1 |
| Human sign-off | Required before sharing, not before assembly |
| Strongest case | One cited sentence per candidate, plus equal-length arguments on measures and bills |
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
