# Legal risk

This guide is research for one requester. It is not an official ballot and it is not legal advice.

## Allegations

- Attribute every allegation to the document that carries it.
- Label the status: convicted, pending, dismissed, settled, or allegation only.
- Include the date and the source.
- Include the candidate's response, or "response requested, not found."
- An unconfirmed negative claim is removed or labeled. It is not written as fact.
- Repeating a false allegation can still be defamatory. When a blocker finding says a sentence is false, unsupported, or a privacy violation, the coordinator removes the claim at the round cap and records a gap. Blockers are never left as "disputed."

## Official-ballot banner

Every Markdown, HTML, and PDF output says it is not an official ballot and not voting instructions. Logistics stay as links to the election office.

## Republication

Quote short excerpts with a locator. The offline archive, when the requester asked for one, is for that person's reference. The README states that archived pages can be copyrighted and are not for republication.

When monolith and headless Chromium or Chrome are installed, a capture also includes a single-file HTML copy and a screenshot, alongside the PDF print. `archive/manifest.csv` records a SHA-256 for each saved file. If the live fetch fails, the manifest says `capture_failed` and the script keeps a Wayback Machine copy when one exists. Do not capture pages that sit behind the requester's logins. `./bootstrap.sh` installs the capture tools. `./bootstrap.sh --minimal`, or a failed install, leaves archive capability reduced: the archive still saves the HTTP body and a PDF print.
