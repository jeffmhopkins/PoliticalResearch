# Neutrality

The guide describes the ballot. It does not choose a side.

## Symmetry

- Every candidate in a race gets the same sections, the same questions, and a comparable search budget.
- A missing fact is `Not found (searched: ...)`, not a blank and not a guess.
- `scripts/symmetry_check.py` fails the item when a core section is missing, when effort is under 80 percent of the race maximum without an explanation, or when a substantive section is under half the length of the same section for another candidate.
- Measure and bill arguments are close in length. Each candidate gets one "strongest case" sentence of similar length, tied to the record, with no praise or attack wording.

## Wording

- Use descriptive names for policies. Partisan slogans appear only inside quotations.
- Do not write picks, scores, ranks, or "how to vote."
- Do not use judging adjectives such as "extreme" or "common-sense."
- There is no values-matching mode. Do not ask the requester for a party or a set of values, and do not tilt coverage toward a preference you inferred.

## Blinded swap

Before sign-off, the neutrality reviewer reads `swap-draft.md` from `scripts/swap.py`. Names are replaced with Candidate A and Candidate B. The reviewer does not open intake notes or any statement of what the requester wants.

## Skew

Reviewers look for left skew, right skew, and for wording that flatters the requester. A finding of that kind is a neutrality finding. Fix the words or mark the claim disputed. Do not argue that the skew is deserved.
