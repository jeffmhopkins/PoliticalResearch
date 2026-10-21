# Neutrality

The guide describes the ballot. It does not choose a side.

## Symmetry

- Every candidate in a race gets the same sections, the same questions, and a comparable search budget.
- A missing fact is `Not found (searched: ...)`, not a blank and not a guess.
- `scripts/symmetry_check.py` fails the item when a core section is missing, when effort is under 80 percent of the race maximum, or when cited words in a substantive section fall below half the race median. Gap text does not count toward that length. An explanation does not waive a miss. The same section text with only the name swapped fails even when the word count matches. A near-copy of that text fails too.
- Measure and bill arguments are close in length. A side that is only a gap is not padded to match the other side. Each candidate gets one "strongest case" sentence of similar length, tied to the record, with no praise or attack wording.

## Reader layout

The draft keeps every core heading. The reader edition of the guide may collapse what the reader sees. These rules do not drop a fact that was found for only one candidate.

- **R1.** Omit always-empty template sections from the reader. That is the sources, changelog, and findings stubs, plus Write-in, Withdrawn, and Uncontested when the text is "None." or the race is contested. The drafts keep those headings.
- **R2.** Collapse a profile's empty fields into one line, `Not found (searched: field, field).` Put each search path in the search log.
- **R3.** When a comparison row is empty for every candidate, drop the row and add one race-level gap sentence. That is symmetric by construction.
- **R4.** When a field is found for some candidates, keep the row. Empty cells say `Not found`. Do not hide the row. Each cell holds the fact for that row: a cited structured field when `profile.yaml` has one, otherwise the most specific unused cited sentence. The reader prints a short fact (a value or a brief phrase) and keeps the marker. A longer sentence is capped and linked to the cell detail in the sources addendum. The same sentence is not copied into a second row. An issue row whose text repeats the positions row is not printed again. A term length such as "four-year term" is not years in elected office. A race with more than three candidates is split into tables of at most three candidates, in ballot order, with the row labels repeated on each table. Candidates stay in columns and are not sorted. A table of five or six columns uses a landscape page. A wider table is split instead of squeezed.
- **R5.** Fold a gap that follows real text into the last cited sentence as `(not found: see the search log)`. The path goes to the search log in the sources addendum.
- **R6.** Claim text still needs two anchor values from one identity record. Prose that carries the marker must name that person, or a pronoun may continue the previous cited sentence in the same section. A table cell may omit the repeated name when the header or the row label already names that person. An unnamed sentence such as "The defendant was convicted" fails. A sentence that names a different person fails even when it also names this record. An organization word does not hide that name: "the John Smith Committee" still names John Smith unless `organizations` lists that full phrase. A bare personal name is not a valid organization entry and does not clear the name when it appears alone. A claim about that other person is a separate claim.
- **R7.** When `profile.yaml` exists, symmetry also checks that file: the same issue keys, the same money report day, and the same `fields` map. `report_date` is compared as a parsed date, so the cell text may differ. A missing cash-on-hand figure stays `Not found`. Rendered prose is not the only check.

Issue rows come from issues at least two candidates addressed in their own words. Every candidate gets that row. Sort candidates and offices in ballot order. Do not sort by party, money, or any score.

The reader edition opens with the ballot, then one contest at a time, inside a per-contest word budget. Comparison cells are short. Per-candidate prose is in `final/guide-full.md`, which also adds the marker index and the changelog. Works cited, quotes, and the search log are in `final/guide-sources.md` and `final/guide-full-sources.md`. Neither edition recommends a vote.

## Wording

- Use descriptive names for policies. Partisan slogans appear only inside quotations.
- Do not write picks, scores, ranks, or "how to vote."
- Do not use judging adjectives such as "extreme" or "common-sense."
- Record versus rhetoric uses one cited label per comparison: `MATCH`, `CONTRADICTION`, or `NO RECORD`. The label is a description of the two cited items. It is not an assessment and not a recommendation. Occupation, business, or industry is not a `CONTRADICTION`. Apply the same labels to every candidate. Donations the candidate made are listed as recipient, amount, and date, without alignment commentary.
- There is no values-matching mode. Do not ask the requester for a party or a set of values, and do not tilt coverage toward a preference you inferred.

## Blinded swap

Before sign-off, the neutrality reviewer reads `swap-draft.md` from `scripts/swap.py`. Names are replaced with Candidate A and Candidate B. The reviewer does not open intake notes or any statement of what the requester wants.

## Skew

Reviewers look for left skew, right skew, and for wording that flatters the requester. A finding of that kind is a neutrality finding. Fix the words or mark the claim disputed. Do not argue that the skew is deserved.
