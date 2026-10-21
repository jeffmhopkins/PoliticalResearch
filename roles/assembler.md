# Assembler

Read `AGENTS.md`, `REVIEW.md`, and `policy/citations.md`. Assemble only after `scripts/validate.py --gate` would pass, or after `scripts/assemble.py` reports no gate errors.

## Build the guide

`scripts/assemble.py` writes `final/guide.md` (reader) and `final/guide-full.md` (audit).

The reader opens with the ballot table, then one contest at a time, in ballot order. Headings nest: level, contest, candidate. Comparison tables use the same rows for every candidate. Empty rows that are empty for the whole race are one gap sentence. A row that is filled for only some candidates keeps `Not found` in the empty cells. Profile links are anchors, not `draft.md` paths. Works cited lists only markers the edition uses. The full edition adds the marker index and the changelog.

Both editions include:

- The not-an-official-ballot notice, and a fiction banner when `ballot.yaml` says `fiction: true`
- Official election office links from `logistics.md`, or from `ballot.yaml` logistics when that file is absent
- The statement that the guide does not recommend a vote
- Methodology, disputed claims, corrections, the search log, and works cited
- Pandoc footnote definitions for markers the edition cites

Disputed and removed claims stay out of summaries. The appendix quotes the reviewer concern and the researcher position.

## Render

`scripts/build.sh --workspace <path>` writes HTML and PDF for the reader and, when `guide-full.md` exists, for the full edition. It copies versioned reader files under `versions/` and checks the banner. It runs `scripts/a11y_check.py`. Built-in HTML checks always run. When pa11y or axe is installed, that tool runs too, and errors fail the build. A missing external checker does not fail the build unless intake asked for pa11y or a screen reader. `./bootstrap.sh` installs pa11y under `.tools/a11y` and `.venv/bin`; `./bootstrap.sh --minimal` does not.

## Share

Stop after the build. The requester reviews the files. Record approval with `scripts/intake.py approve-sharing` before the files are sent to anyone else. Approval is not required before assembly. It is required before sharing.

## Offline archive

If `offline_archive` is true, run `scripts/archive_sources.py` after citations are stable and before you zip the guide. `pending` does not run the archive. The default `archive_tier` is `html-pdf` (HTTP body and PDF). `full` also saves a monolith mirror and a screenshot. The script prints a size estimate and captures each URL once. A failed fetch is `capture_failed` in the manifest and in `archive/failures.log`, with a Wayback copy when one exists. `./bootstrap.sh` installs monolith and a browser; `./bootstrap.sh --minimal` does not. The screenshot uses a temporary Chrome profile and skips the `/usr/local/bin/google-chrome` wrapper.
