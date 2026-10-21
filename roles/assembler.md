# Assembler

Read `AGENTS.md`, `REVIEW.md`, and `policy/citations.md`. Assemble only after `scripts/validate.py --gate` would pass, or after `scripts/assemble.py` reports no gate errors.

## Build the guide

`scripts/assemble.py` writes `final/guide.md` (reader), `final/guide-sources.md` (reader sources), `final/guide-full.md` (audit), and `final/guide-full-sources.md` (audit sources).

The reader opens with the ballot table, then one contest at a time, in ballot order, inside the per-contest word budget. Headings nest: level, contest. Comparison tables use the same rows for every candidate, with a short fact in each cell. Empty rows that are empty for the whole race are one gap sentence. A row that is filled for only some candidates keeps `Not found` in the empty cells. A race with four or more candidates is transposed so each candidate is a row. Tables with six or more columns are marked for a landscape page. Per-candidate prose stays in the full edition. Profile links point at that edition, not at `draft.md`. The full edition adds the marker index and the changelog.

Works cited, source quotes, claim text, cell detail, and the search log are in the sources addendum for that edition. A marker in the body is a link to `#source-n`, and the addendum links back to `#cite-n`. The citation gate reads the body and the addendum together. It does not drop a claim check because the reader is short.

Both editions include:

- The not-an-official-ballot notice, and a fiction banner when `ballot.yaml` says `fiction: true`
- Official election office links from `logistics.md`, or from `ballot.yaml` logistics when that file is absent. A logistics URL is shown even when it has no marker. The citation gate exempts only that exact line, generated from the ballot label and URL.
- A precinct line from `ballot.yaml` when a precinct code or district list is stored there. That line restates the confirmed ballot. It is not a street address. The citation gate exempts only that exact generated sentence.
- The statement that the guide does not recommend a vote
- Methodology, disputed claims, and corrections in the body

Disputed and removed claims stay out of summaries. The appendix quotes the reviewer concern and the researcher position.

## Render

`scripts/build.sh --workspace <path>` writes HTML and PDF for the reader, the sources addendums, and the full edition. It copies versioned reader files under `versions/` and checks the banner. `scripts/check_pdf_layout.py` renders no opinion of the writing; it fails the build when text is outside the page box or below the minimum size. It runs `scripts/a11y_check.py`. Built-in HTML checks always run. When pa11y or axe is installed, that tool runs too, and errors fail the build. A missing external checker does not fail the build unless intake asked for pa11y or a screen reader. `./bootstrap.sh` installs pa11y under `.tools/a11y` and `.venv/bin`; `./bootstrap.sh --minimal` does not.

## Share

Stop after the build. The requester reviews the files. Record approval with `scripts/intake.py approve-sharing` before the files are sent to anyone else. Approval is not required before assembly. It is required before sharing.

## Offline archive

If `offline_archive` is true, run `scripts/archive_sources.py` after citations are stable and before you zip the guide. `pending` does not run the archive. The default `archive_tier` is `html-pdf` (HTTP body and PDF). `full` also saves a monolith mirror and a screenshot. The script prints a size estimate and captures each URL once. A failed fetch is `capture_failed` in the manifest and in `archive/failures.log`, with a Wayback copy when one exists. `./bootstrap.sh` installs monolith and a browser; `./bootstrap.sh --minimal` does not. The screenshot uses a temporary Chrome profile and skips the `/usr/local/bin/google-chrome` wrapper.
