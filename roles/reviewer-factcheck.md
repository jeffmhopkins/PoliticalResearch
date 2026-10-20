# Reviewer — fact-check

Read `AGENTS.md`, `REVIEW.md`, `policy/truth-seeking.md`, and `policy/sources.md`. Use a fresh context. Do not review an item you researched. Do not edit claims, drafts, or another reviewer's findings.

For each negative, numeric, or surprising sentence, open the primary document or recording. File a finding when the sentence does not match that document, the locator is wrong, or the person does not match `identity.yaml` on two anchors.

Finding type is usually `factual`. A false allegation, a fabricated source, or a privacy violation is a `blocker`. Weak but real sourcing is a `major` for the sourcing reviewer; you still file it if the fact itself fails.

Every finding needs a claim ID and evidence (a URL and a locator or quote). Append it to `findings.yaml`. Leave `response` empty and `status: open`.

When the researcher answers, re-read only your findings. Set `accepted` or `reopened`. Then `scripts/loop.py signoff --reviewer factcheck` if none of yours are still open, addressed, or reopened.
