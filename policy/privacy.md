# Privacy

## Requester

- A street address, ballot photo, email, and phone number go only in `output/<election-id>/private/`. That directory is `private/` inside the election workspace. `address_location: private/address.txt` is relative to the workspace. Do not put a voter's address in a `private/` folder at the repo root.
- `intake.yaml` stores a label, jurisdiction words such as county and city, and `address_location: private/address.txt`. It does not store the address.
- Delete ballot images after the contest list is extracted. `scripts/intake.py confirm` deletes files in the workspace `private/` whose names start with `ballot` and whose suffix is a photo or PDF. It leaves a file such as `sample-ballot-precinct-122.pdf` in place.
- Do not commit `output/` or `private/`. Do not paste requester data into issues, commits, the guide, `versions/`, or the source archive.

## Candidates and other people

Do not publish:

- home addresses
- personal phone numbers
- names of minors
- medical information
- sexual orientation
- immigration status

unless the person has publicly raised that fact and it is relevant to the office. When you include it, use their words and cite them.

Religion and family follow the same rule. A relative who is an officeholder, lobbyist, or donor, or a documented nepotism finding, can be included with a citation. Do not infer family political views.

Official biographies sometimes include family fields in the page data, including Florida court biographies, `myfloridalegal.com` attorney-general biographies, and Senate handbook pages. Do not copy a spouse, child, or other family field into the guide unless the person publicly raised that fact and it is relevant to the office. The field's presence on the page is not that public statement.

Identity anchors are photo-free. Do not add a portrait to the guide.
