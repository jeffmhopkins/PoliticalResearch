# Legal risk

This guide is research for one requester. It is not an official ballot and it is not legal advice.

## Allegations

- Attribute every allegation to the document that carries it.
- Label the status: convicted, pending, dismissed, settled, or allegation only.
- Include the date and the source.
- Include the candidate's response, or "response requested, not found."
- An unconfirmed negative claim is removed or labeled. It is not written as fact.
- A dismissal, acquittal, or reversal is reported with the accusation. Dropping the accusation leaves the outcome unexplained.
- A settlement without admission is not an admission of guilt or liability.
- Court records count only when the caption names the candidate, or a documented alias, as a party. The surname match ignores case, stays on a word boundary, and is at least three characters. A function word is not a party name. A full-text mention is not that. A matter dated before the year the candidate turned 18 is dropped. `birth_year` in `identity.yaml` is the internal input for that cutoff. It is not printed.
- Search every documented alias before marking a category clear. An alias is a full name. Its `source` is a URL or the claim id of the evidence record, not a free-text note. It cannot be another candidate's name. An alias does not, by itself, satisfy the two identity anchors. `scripts/identity_gate.py` checks the caption, the year, and the alias list.

## Category sweep

Every candidate gets the same eight categories in `profile.yaml` `legal_sweep`. `scripts/symmetry_check.py` compares those keys and, for each category, whether it was checked. `checked_nothing_found` and `record_found` are checked. A category left `not_checked` while another candidate's same category was checked is a symmetry error.

| Key | What it covers |
| --- | --- |
| `criminal` | Criminal cases |
| `civil` | Civil litigation |
| `financial` | Bankruptcy, tax, liens |
| `ethics_campaign_finance` | Ethics findings and campaign-finance matters, including FEC MURs |
| `professional_discipline` | Licenses and professional discipline |
| `labor_consumer` | Labor and consumer matters |
| `misuse_of_office` | Misuse of office by an officeholder |
| `prior_statements` | Prior public statements that the legal-risk rules allow, with date and context |

Status is `checked_nothing_found`, `record_found`, `not_checked`, or `portal_unavailable`. The guide phrase for a checked empty category is `checked, nothing found`. `portal_unavailable` names the outage. It does not say that no record exists. `record_found` needs a claim in that category. Prior statements stay attributed. Do not apply a loaded label to them.
- Repeating a false allegation can still be defamatory. When a blocker finding says a sentence is false, unsupported, or a privacy violation, the coordinator removes the claim at the round cap and records a gap. Blockers are never left as "disputed."

## Official-ballot banner

Every Markdown, HTML, and PDF output says it is not an official ballot and not voting instructions. Logistics stay as links to the election office.

## Republication

Quote short excerpts with a locator. The offline archive, when the requester asked for one, is for that person's reference. The README states that archived pages can be copyrighted and are not for republication.

When monolith and headless Chromium or Chrome are installed, a capture also includes a single-file HTML copy and a screenshot, alongside the PDF print. `archive/manifest.csv` records a SHA-256 for each saved file. If the live fetch fails, the manifest says `capture_failed` and the script keeps a Wayback Machine copy when one exists. Do not capture pages that sit behind the requester's logins. `./bootstrap.sh` installs the capture tools. `./bootstrap.sh --minimal`, or a failed install, leaves archive capability reduced: the archive still saves the HTTP body and a PDF print.
