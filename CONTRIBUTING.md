# Contributing

This repository is the tool: policies, templates, schemas, and scripts. Voter guides produced with it stay in git-ignored `output/` and are not pull requests.

## Change a template or policy

Open a pull request that explains the rule you want to change and why. Keep the guide nonpartisan. Do not add endorsements, scores, or a values-matching mode. Update the matching schema, script, and test when a field changes.

`config.yaml` holds the defaults for rounds, staleness, effort parity, and the choices listed in the README. Change those in the same pull request as the docs that mention them.

## Report a wrong fact in the tool

The worked example under `examples/sample-election/` is fiction. If a script, schema, or policy states a real-world procedure incorrectly, open an issue or a pull request that names the file and the official documentation that contradicts it.

A wrong fact in a guide someone built with this tool is handled inside that guide's review loop and corrections section, not by editing `output/` in this repo. Guides are not stored here.

## Do not commit

- `output/`
- `private/`
- `.env`
- A real address, ballot image, or API key
- A report about real candidates, even as a fixture
