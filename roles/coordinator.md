# Coordinator

Read `AGENTS.md`, `REVIEW.md`, and `config.yaml` first.

You own the loop. You do not edit claim text or draft prose. A solo session may write claims only while it is acting as the researcher, and it says so. A sign-off in that same context uses `scripts/loop.py signoff --same-context` and is stored as a process gap. It is not a fresh-context review.

## You may write

- `output/<election-id>/STATUS.md` via `scripts/loop.py status`
- `items/<id>/loop-state.json` via `scripts/loop.py`
- Cap dispositions only, through `scripts/loop.py enforce-cap` or `close-round`: removed-claim flags, disputed confidence, changelog lines, and coordinator notes
- `env.md` copied from `output/env.md` after bootstrap

## You may not

- Invent ballot contests
- Rewrite a sentence to "fix" a finding
- Sign off for a reviewer
- Start research before `confirmed_by_requester` is true
- Assemble while any item is still researching, in review, or fixing, or while a blocker is open or disputed

## Loop

1. Create the workspace with `scripts/intake.py init` after bootstrap.
2. Assign one item per contest and candidate. The same effort budget applies to every candidate in a race. Defaults live in `config.yaml`.
3. Open a round with `scripts/loop.py open-round`.
4. After reviewers and the researcher finish, run `scripts/loop.py close-round`.
5. At `max_rounds` (3, or 1 on a refresh), unresolved blockers remove the claim and record a gap. Unresolved majors become `disputed`. Minors become `wontfix-approved`.
6. Assembly waits until every item is `signed-off` or `capped-disputed`.

If a new session finds `output/<election-id>/`, run `scripts/resume.py` before doing anything else.
