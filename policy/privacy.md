# Privacy

## Requester

- A street address, ballot photo, email, and phone number go only in `output/<election-id>/private/`.
- `intake.yaml` stores a label, jurisdiction words such as county and city, and `address_location: private/address.txt`. It does not store the address.
- Delete ballot images after the contest list is extracted. `scripts/intake.py confirm` deletes files in `private/` whose names start with `ballot` and whose suffix is a photo or PDF.
- Do not commit `output/` or `private/`. Do not paste requester data into issues, commits, or the guide.

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

Identity anchors are photo-free. Do not add a portrait to the guide.
