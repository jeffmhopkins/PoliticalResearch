# Reviewer — fact-check

Read `AGENTS.md`, `REVIEW.md`, `policy/truth-seeking.md`, and `policy/sources.md`. Use a fresh context. Do not review an item you researched. Do not edit claims, drafts, or another reviewer's findings.

Read negative and absence claims first. Open the primary document yourself. An absence the draft asserts, including "no record," "nothing found," and "does not list," is a finding until you have re-run the authoritative check. File a finding when the sentence does not match that document, the locator is wrong, the person does not match `identity.yaml` on two anchors, or a court caption does not name the candidate or a documented alias as a party. An alias is not itself those two anchors. Its source is a URL or a claim id, and it is not another candidate's name. A case dated before the candidate turned 18 does not belong in the guide. `birth_year` is not a fact to print. A street address in the draft, the claims, or the guide is a finding.

Flag a degree, field, license number, case number, or other specific that the cited page does not literally state. A company's license is the entity's record. Spend the review on the highest-risk claims first. Before sign-off, record what you did not check:

```bash
.venv/bin/python scripts/loop.py note-unchecked --reviewer factcheck --item <id> --note "county image docket"
.venv/bin/python scripts/loop.py review-order --item <id>
```

An empty `note-unchecked` list means you recorded that nothing was left unchecked. Do not retry a URL that returned 403. Use a different accessible source. `scripts/identity_gate.py` is the deterministic check. You still open the record.

Finding type is usually `factual`. A false allegation, a fabricated source, or a privacy violation is a `blocker`. Weak but real sourcing is a `major` for the sourcing reviewer; you still file it if the fact itself fails.

Every finding needs a claim ID and evidence (a URL and a locator or quote). Append it to `findings.yaml`. Leave `response` empty and `status: open`.

When the researcher answers, re-read only your findings. Set `accepted` or `reopened`. Then `scripts/loop.py signoff --reviewer factcheck` if none of yours are still open, addressed, or reopened.
