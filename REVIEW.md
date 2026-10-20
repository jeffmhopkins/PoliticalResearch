# Review and correction loop

This file is the protocol for phases 7 through 10. Schemas live in `templates/findings.schema.yaml` and `templates/loop-state.schema.json`. `scripts/loop.py` enforces the cap and writes `STATUS.md`.

## Finding

Append one object to `items/<id>/findings.yaml`. Do not rewrite older objects except to set `status` on re-review or to fill `response` as the researcher.

```yaml
- id: F-0007
  round: 1
  reviewer: neutrality
  claim_id: cand-smith.funding.003
  type: factual
  severity: major
  issue: "Totals cite the Q2 filing. The Q3 filing is dated 2026-10-15."
  evidence:
    - "https://example.test/filing"
    - "Summary page, line 6"
  status: open
  response:
    action: fix
    rationale: "Replaced the totals with the Q3 lines."
    evidence: []
    changelog_ref: CL-0012
```

`type` is `factual`, `sourcing`, `neutrality`, `symmetry`, `stale`, `privacy`, or `legal-risk`.

`severity` is:

- `blocker` — false statement, defamation risk, fabricated source, or privacy violation. Never left disputed. At the cap the claim is removed and the gap is noted.
- `major` — weak sourcing, asymmetry, or loaded framing. At the cap the claim is `disputed` and stays out of summaries.
- `minor` — style or a missing date that does not change the meaning. At the cap it may be `wontfix-approved` with a reason.

`status` is `open`, `addressed`, `accepted`, `reopened`, `disputed`, or `wontfix-approved`.

## Responses

The researcher sets `response.action` to `fix`, `rebut`, or `dispute` and sets `status` to `addressed`.

- `fix` needs `changelog_ref`, and that id must appear in `CHANGELOG.md`.
- `rebut` and `dispute` need new `response.evidence`.

The reviewer who filed the finding then sets `accepted` or `reopened`. A reopened finding is unresolved.

## Rounds

1. Reviewers file findings tied to claim IDs.
2. The researcher answers every open finding.
3. Reviewers re-review only the responses to their own findings.
4. Repeat until every reviewer has signed off, or until `max_rounds` from `config.yaml` (default 3).
5. At the cap, `scripts/loop.py close-round` converts leftovers: blockers remove the claim, majors become disputed, minors become `wontfix-approved`.
6. Do not add a new major or minor after round 1 unless the finding sets `caused_by_edit: true` because a fix in that round created it. `scripts/validate.py` rejects other late non-blockers. A new blocker is always allowed.

`scripts/loop.py signoff --reviewer <name>` refuses to sign while that reviewer still has a finding that is not `accepted`, `disputed`, or `wontfix-approved`.

## Loop state

`loop-state.json` stores the round, open counts by severity, a sign-off per reviewer, and `status`: `researching`, `in-review`, `fixing`, `signed-off`, or `capped-disputed`.

`scripts/loop.py status` rewrites `STATUS.md` from those files.

## Changelog line

```
CL-id | round | finding id | claim id | before -> after | reason | timestamp ET
```

## Disputed text in the guide

The assembler prints the reviewer concern and the researcher position in the Disputed claims section. The draft may also say, next to the sentence, that it is disputed. Disputed claims do not drive summaries. Methodology reports the round and the counts.

## Sign-off checklist

A reviewer signs off only when all of these are true for their own findings:

- No finding of theirs is `open`, `addressed`, or `reopened`.
- Their blockers are `accepted` only because the sentence was fixed or the claim was removed.
- Changelog lines exist for every `fix`.

The coordinator allows assembly only when:

- No blocker remains `open`, `reopened`, `addressed`, or `disputed`.
- Every major is `accepted` or `disputed`.
- The changelog covers each fix and each cap disposition.
- `scripts/symmetry_check.py` passes.
- `scripts/check_links.py` has been run, and dead links have an archive URL or `archive_failed`.
- T1 retrieval dates are under 7 days old at assembly (`scripts/staleness.py`).
- `scripts/edge_cases.py` passes for withdrawn, write-in, thin-record, and uncontested contests.
- Summary grade is within the configured limit.

## Audit trail

Keep findings, changelog lines, and loop state. Do not squash them away to make the draft look untouched. A later reader should be able to see what changed, who objected, and how the cap resolved it.

## Fairness pass

After items are signed off or capped, the neutrality reviewer runs the blinded swap and the symmetry check across the whole ballot. Findings from that pass get one round, then the same cap. They do not restart the counter at zero for unrelated items.

## Refresh

`scripts/refresh.py` lists stale sources, can set `mode: refresh` and `max_rounds` to 1, and can bump `report_version` while copying the previous guide into `versions/`. A correction section lists what changed, why, and when. Corrected claims set `corrected: true` and `correction_note`.
