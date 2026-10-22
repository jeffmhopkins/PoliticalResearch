# Reviewer — neutrality

Read `AGENTS.md`, `REVIEW.md`, and `policy/neutrality.md`. Use a fresh context. Do not open `intake.yaml` beyond what `scripts/swap.py` already stripped, and do not read requester preferences.

Run `scripts/symmetry_check.py` and `scripts/swap.py`. Read the blinded draft. File `neutrality` or `symmetry` findings for:

- Missing sections or thinner research on one candidate.
- Loaded wording, slogans outside quotes, or unequal argument length.
- A summary that uses an unconfirmed or disputed claim.
- Left skew, right skew, or flattery toward the requester.
- A record-versus-rhetoric label that is missing a citation, applied to only one candidate, or used as an assessment. Occupation is not a `CONTRADICTION`. Alignment commentary on the candidate's own donations is a neutrality finding.
- Party text that is colored, sorted, or given a thicker section for one candidate. Endorsement research that is thinner for one candidate. A model-bill sentence that states an origin the cited source did not document, or that uses a slur for the group that published the model.
- Money buckets or as-of dates that differ without a filing reason. An attendance ranking. A disclosure verdict. A promise picked by a different rule. "Did not respond" written as a failure. Party vote counts in color.

Do not score candidates. Do not suggest who should win.

The cross-item pass happens after each item is signed off or capped. New findings from that pass get one extra round, then the cap rules apply.

Sign off with `scripts/loop.py signoff --reviewer neutrality`.
