# Fictional sample election

**This entire folder is fiction.** Cedar Hollow, Oak County, and the State of Westland are invented. Avery Quinn and Blake Okonkwo are not real people. Every URL under `fictional.example` is a placeholder. Do not use this guide to vote. Do not cite it as a source about any real election.

It shows the file shape a real run keeps in git-ignored `output/`: intake, a confirmed ballot, item claims, a review finding that was fixed, a claim left disputed at the round cap, and `final/guide.md`.

Rebuild the guide after a script change:

```bash
.venv/bin/python examples/generate_sample_election.py
.venv/bin/python scripts/assemble.py --workspace examples/sample-election --today 2026-10-20 --now "2026-10-20 12:00 ET"
```

The generator already runs the assembler.
