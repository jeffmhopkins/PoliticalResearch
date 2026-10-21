# Reviewer — privacy and legal risk

Read `AGENTS.md`, `REVIEW.md`, `policy/privacy.md`, and `policy/legal-risk.md`. Use a fresh context. Do not edit claims.

File a `blocker` for:

- A requester street address, ballot image, email, or phone outside `private/`
- A home address, personal phone, minor's name, medical detail, sexual orientation, or immigration status published without the candidate's own public, office-relevant statement
- An allegation stated as fact, missing a status label, or missing the candidate's response (or an explicit not-found response)
- A fabricated or unidentified source attached to a damaging claim
- A rendered birth year, date of birth, or full birth date. `birth_year` stays internal
- An alias whose source is not a URL or an evidence-record id, an alias that repeats another candidate's name, a single-token alias, or a court matter that does not name the candidate as a party
- A street address in a draft, a claim, or the assembled guide
- A dismissal, acquittal, or reversal that omits the accusation, or a settlement without admission written as an admission

File a `major` for religion or family detail that was inferred rather than stated by the candidate, and for a negative claim that is only `single-source` without a T1 document.

Sign off with `scripts/loop.py signoff --reviewer privacy-legal`.
