# Privacy

## Requester

- A street address, ballot photo, email, and phone number go only in `output/<election-id>/private/`. That directory is `private/` inside the election workspace. `address_location: private/address.txt` is relative to the workspace. Do not put a voter's address in a `private/` folder at the repo root.
- `intake.yaml` stores a label, jurisdiction words such as county and city, and `address_location: private/address.txt`. It does not store the address.
- Delete ballot images after the contest list is extracted. `scripts/intake.py confirm` deletes every image and PDF under the workspace `private/`, whatever the file name. A phone photo such as `IMG_2044.jpg` and a sample-ballot PDF are both removed. `address.txt` and other non-image files stay. `ballot_photo_deleted` is set only when every image and PDF is gone. A symlink that points outside `private/` blocks confirmation and leaves that flag unset.
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

`identity.yaml` may store `birth_year` when a public record supports it. That year is an internal input to the court-record era check. Do not print it, a full date of birth, or an age that exists only because the year was stored. `scripts/identity_gate.py` rejects a draft, a claim, or an assembled guide that renders it, including `year of birth`, `birthdate`, `b.`, and `born` next to a year across a line break. Aliases are full names a public filing, court caption, or the candidate's own words document. Each alias's `source` is the URL or the claim id of that evidence record. A free-text note is not a source, and an alias cannot repeat another candidate's name. Do not put a street address in a draft, a claim, or the guide. The same gate rejects one.
