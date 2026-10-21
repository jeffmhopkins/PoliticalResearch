# Citations

`scripts/check_citations.py` and the sourcing reviewer enforce this file.

## What needs a citation

Every factual sentence, number, quote, date, vote, dollar figure, legal status, and characterization of a position.

These do not need a source marker: headings, "not found" notes, the how-to-use section, methodology, the glossary, the changelog, and the marker index.

A paragraph that mixes a not-found note with any other sentence must cite the other sentence.

Uncited factual text fails the build.

## Inline markers

Put a marker immediately after the claim: `[^12]`. Use one marker per source. Two sources look like `[^12][^15]`.

Each marker number maps to one source on one claim in `claims.yaml`. Markers are unique across the election. The marker index in the guide lists `[^12]` next to the claim ID.

## Works-cited line

```
[n] Publisher/Author. "Title." Document type, published YYYY-MM-DD. URL — Archived: archive URL. Retrieved YYYY-MM-DD HH:MM ET. Tier T1. Locator: page, section, timestamp, or table row.
```

If no archive exists, write `Archived: capture failed (reason).` A local copy, when one was saved, is added as `Local copy: archive/<n>-<slug>.<ext>.`

Example:

```
[12] Federal Election Commission. "Form 3 Quarterly Report, Q3 2026." Campaign filing, filed 2026-10-15. https://example.test/filing — Archived: https://web.archive.org/web/example. Retrieved 2026-10-20 10:14 ET. Tier T1. Locator: Summary page, line 6.
```

Drafts keep the `[^12]` marker. The assembler renders that marker as a small link to the sources addendum (`guide-sources.md` for the reader, `guide-full-sources.md` for the full edition) and writes the works-cited line, the quote, and the claim text there. The addendum entry links back to the first use of the marker. Per-contest sections in the addendum hold that contest's sources, cell detail, and search log. `scripts/check_citations.py` still resolves markers from the drafts and from the body plus the addendum together. A missing addendum entry fails the guide check.

## Required source fields

`url`, `archive_url` or `archive_failed` plus `archive_failed_reason`, `publisher`, `title`, `doc_type`, `published` (a date or `undated`), `retrieved` (`YYYY-MM-DD HH:MM ET`), `tier`, `locator`, `quote` (at most two sentences), and source `confidence`.

## Quotes

Quotes are verbatim, with a locator and a link to the original recording or document. Do not put a paraphrase in quotation marks. Label a translation with the translator. When a source has `local_copy`, the quote must appear in that saved file. Do not append tokens to a quote so a number from somewhere else on the page will match. A figure in a sentence must appear in the quote or in the text of that local copy. The filename does not count.

A forum or debate transcript from `scripts/transcribe.py` is an unreviewed import under `items/<id>/imports/transcripts/`. It is not a claim until you check it against the recording and copy `suggested_source` into `claims.yaml`. Use a verbatim excerpt of at most two sentences. The locator looks like `Timestamp HH:MM:SS` or `Timestamp HH:MM:SS-HH:MM:SS`. Link the original recording. Whisper is opt-in. If it is not installed, the script exits with a message to run `./bootstrap.sh --with-transcription`, and you cite the recording page yourself.

## Numbers

Every figure has an as-of date and, for filings, the filing period. A sum or percentage lists its inputs and cites each one.

## Confidence shown to readers

- `verified` — a T1 source, or two independent sources. Summaries may use these.
- `single-source` — label it in the text.
- `unconfirmed` — label it. It cannot appear in a summary.
- `disputed` — the review loop left both positions in place. It cannot appear in a summary.
- `identity-unconfirmed` — do not publish the sentence.

## Checks that block the phase

Before review and again before assembly:

- Every factual paragraph has a marker.
- Every marker resolves to a source.
- Every guide marker has a works-cited line.
- Required fields are present.
- A T4 source does not support a fact (`attribution_only` is required when every source is T4, and that claim cannot be `verified` or drive a summary).
- No disallowed host appears.
- A URL that errors needs an archive fallback (`archive_url`, or `archive_failed` with a reason). `scripts/check_links.py` performs the live check. The citation checker treats a recorded archive failure as the fallback so a fixture with no live web still validates.

## Recency

Label a source older than the election year with that year. `scripts/staleness.py` flags anything retrieved more than 7 days before assembly. Re-fetch T1 sources before assembly and before a refresh. A dead link falls back to the archive copy and is flagged.
