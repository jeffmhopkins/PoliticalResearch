# Assembler

Read `AGENTS.md`, `REVIEW.md`, and `policy/citations.md`. Assemble only after `scripts/validate.py --gate` would pass, or after `scripts/assemble.py` reports no gate errors.

## Build the guide

`scripts/assemble.py` writes `final/guide.md` with:

- The not-an-official-ballot notice, and a fiction banner when `ballot.yaml` says `fiction: true`
- How to use the guide, including the statement that it does not recommend a vote
- Logistics from `logistics.md` when that file exists
- Race drafts, then each candidate, then measures and other contests, in ballot order
- Methodology: version, date, environment file, subagent note, finding and dispute counts, effort table, gaps
- Disputed-claims appendix
- Corrections, works cited, marker index, glossary, changelog
- Pandoc footnote definitions

Disputed and removed claims stay out of summaries. The appendix quotes the reviewer concern and the researcher position.

## Render

`scripts/build.sh --workspace <path>` writes HTML and PDF, copies versioned files under `versions/`, checks the banner, and runs the built-in accessibility checks.

## Share

Stop after the build. The requester reviews the files. Record approval with `scripts/intake.py approve-sharing` before the files are sent to anyone else. Approval is not required before assembly. It is required before sharing.

## Offline archive

If `offline_archive` is true, run `scripts/archive_sources.py` after citations are stable and before you zip the guide. The methodology should mention how many sources were captured. The script prints that count.
