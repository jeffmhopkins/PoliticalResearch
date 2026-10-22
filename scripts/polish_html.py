#!/usr/bin/env python3
"""Mark gap cells in built guide HTML and keep headings with the block that follows.

Does not change the words.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TD_RE = re.compile(r"<td(\s[^>]*)?>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_P_RE = re.compile(r"<p(\s[^>]*)?>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TH_RE = re.compile(r"<th(\s[^>]*)?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_CLASS_RE = re.compile(r"""class=(['"])(.*?)\1""", re.IGNORECASE)


def _plain(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _is_gap(text: str) -> bool:
    return text == "Not found" or text.lower().startswith("not found (searched:")


def _add_class(attrs: str, name: str) -> str:
    attrs = attrs or ""
    match = _CLASS_RE.search(attrs)
    if not match:
        return f'{attrs} class="{name}"'
    classes = match.group(2).split()
    if name in classes:
        return attrs
    classes.append(name)
    return attrs[: match.start(2)] + " ".join(classes) + attrs[match.end(2) :]


def _add_attr(attrs: str, key: str, value: str) -> str:
    attrs = attrs or ""
    if re.search(rf"\b{key}=", attrs, re.IGNORECASE):
        return attrs
    return f'{attrs} {key}="{value}"'


def _class_token(attrs: str, name: str) -> bool:
    match = _CLASS_RE.search(attrs or "")
    return bool(match) and name in match.group(2).split()


_DIV_RE = re.compile(r"<div\b([^>]*)>", re.IGNORECASE)
_H3_UL_RE = re.compile(
    r"(</h3>\s*)<ul(\s[^>]*)?>(.*?)</ul>",
    re.IGNORECASE | re.DOTALL,
)


def _tuck_pair_headings(html: str) -> str:
    """Move a heading into the card row it introduces.

    WeasyPrint leaves the heading on its own page when break-after:avoid
    meets a flex row taller than the space that remains. The heading is the
    first flex item, so it travels with the first cards. Only a heading with
    nothing but whitespace between it and the row moves.
    """
    pieces: list[str] = []
    cursor = 0
    for match in _DIV_RE.finditer(html):
        if not _class_token(match.group(1), "pair"):
            continue
        before = html[cursor:match.start()]
        heading = re.search(r"<h3\b([^>]*)>([^<]*)</h3>(\s*)$", before)
        if heading is None:
            continue
        h_attrs, inner, space = heading.groups()
        pieces.append(before[: heading.start()])
        pieces.append(
            f"<div{match.group(1)}>{space}<h3{_add_class(h_attrs, 'pair-label')}>{inner}</h3>"
        )
        cursor = match.end()
    pieces.append(html[cursor:])
    return "".join(pieces)


def _keep_short_lists(html: str) -> str:
    """Stop a four-line sign-off list from leaving its last bullet alone."""

    def repl(match: re.Match) -> str:
        pre, attrs, inner = match.groups()
        if len(re.findall(r"<li\b", inner, re.IGNORECASE)) > 6:
            return match.group(0)
        return f"{pre}<ul{_add_class(attrs, 'keep-together')}>{inner}</ul>"

    return _H3_UL_RE.sub(repl, html)


_UL_BEFORE_HEADING_RE = re.compile(
    r"<ul(\s[^>]*)?>(.*?)</ul>(\s*)(?=<h[12]\b)",
    re.IGNORECASE | re.DOTALL,
)


def _keep_list_tails(html: str) -> str:
    """Keep the last entries of a long list on one page before the next heading."""

    def mark(chunk: str) -> str:
        return re.sub(
            r"<li\b([^>]*)>",
            lambda item: f"<li{_add_class(item.group(1), 'keep-tail')}>",
            chunk,
            count=1,
            flags=re.IGNORECASE,
        )

    def repl(match: re.Match) -> str:
        attrs, inner, space = match.groups()
        pieces = re.split(r"(?=<li\b)", inner, flags=re.IGNORECASE)
        indexes = [i for i, piece in enumerate(pieces) if piece.lstrip().lower().startswith("<li")]
        if len(indexes) < 2:
            return match.group(0)
        for index in indexes[-min(8, len(indexes)) :]:
            pieces[index] = mark(pieces[index])
        return f"<ul{attrs or ''}>{''.join(pieces)}</ul>{space or ''}"

    return _UL_BEFORE_HEADING_RE.sub(repl, html)


_BILL_CLOSE_RE = re.compile(
    r"<h3\b[^>]*\bid=(['\"])who-sponsored-it.*?\1[^>]*>.*?<div class=\"tail\">.*?</div>",
    re.IGNORECASE | re.DOTALL,
)


def _keep_bill_closing(html: str) -> str:
    """Keep the sponsor lines with the roll call so the last bill page is not a short tail."""

    def repl(match: re.Match) -> str:
        return f'<div class="bill-close">{match.group(0)}</div>'

    return _BILL_CLOSE_RE.sub(repl, html)


_PROFILE_RE = re.compile(
    r'<section\b[^>]*\bclass="[^"]*\bprofile\b[^"]*"[^>]*>.*?</section>',
    re.IGNORECASE | re.DOTALL,
)
_BACK_LINK_RE = re.compile(
    r'<p(?:\s+class="back-link")?><a href="#your-ballot-at-a-glance">Back to ballot</a></p>',
    re.IGNORECASE,
)
_BACK_LINK_HTML = '<p class="back-link"><a href="#your-ballot-at-a-glance">Back to ballot</a></p>'


def _plain_len(html: str) -> int:
    text = _TAG_RE.sub(" ", html or "")
    return len(re.sub(r"\s+", " ", text).strip())


def _pair_short_profiles(html: str) -> str:
    """Keep a short final profile with the short profile before it."""
    pieces: list[str] = []
    cursor = 0
    for link in _BACK_LINK_RE.finditer(html):
        before = html[cursor:link.start()]
        profiles = list(_PROFILE_RE.finditer(before))
        if len(profiles) < 2:
            continue
        previous, last = profiles[-2], profiles[-1]
        if before[previous.end():last.start()].strip():
            continue
        if before[last.end():].strip():
            continue
        if "profile-pair" in before[max(0, previous.start() - 40):previous.start()]:
            continue
        if _plain_len(previous.group(0)) > 700 or _plain_len(last.group(0)) > 700:
            continue
        start = cursor + previous.start()
        pieces.append(html[cursor:start])
        pieces.append(f'<div class="profile-pair">{previous.group(0)}{last.group(0)}</div>')
        cursor = cursor + last.end()
    pieces.append(html[cursor:])
    return "".join(pieces)


_KEEP_WITH_LINK_RE = re.compile(
    r"(<div class=\"profile-pair\">.*?</div>|<section\b[^>]*\bclass=\"[^\"]*\bprofile\b[^\"]*\"[^>]*>.*?</section>)"
    r"\s*(<p(?:\s+class=\"back-link\")?><a href=\"#your-ballot-at-a-glance\">Back to ballot</a></p>)",
    re.IGNORECASE | re.DOTALL,
)


def _keep_back_link(html: str) -> str:
    """Keep the ballot link with a short profile. A long profile may split."""

    def repl(match: re.Match) -> str:
        if "link-keep" in html[max(0, match.start() - 80) : match.start()]:
            return match.group(0)
        block = match.group(1)
        # A long biography has to be able to start on the page before it.
        if _plain_len(block) > 900:
            return block + _BACK_LINK_HTML
        return f'<div class="link-keep">{block}{_BACK_LINK_HTML}</div>'

    return _KEEP_WITH_LINK_RE.sub(repl, html)


def polish_html(html: str) -> str:
    """Add not-found styling hooks and column scope. The visible text stays."""

    def td_repl(match: re.Match) -> str:
        attrs, inner = match.group(1), match.group(2)
        if _is_gap(_plain(inner)):
            attrs = _add_class(attrs, "not-found")
        return f"<td{attrs or ''}>{inner}</td>"

    def p_repl(match: re.Match) -> str:
        attrs, inner = match.group(1), match.group(2)
        if _is_gap(_plain(inner)):
            attrs = _add_class(attrs, "not-found")
        return f"<p{attrs or ''}>{inner}</p>"

    def th_repl(match: re.Match) -> str:
        return f"<th{_add_attr(match.group(1), 'scope', 'col')}>"

    text = _TD_RE.sub(td_repl, html)
    text = _P_RE.sub(p_repl, text)
    text = _TH_RE.sub(th_repl, text)
    text = _tuck_pair_headings(text)
    text = _keep_short_lists(text)
    text = _keep_list_tails(text)
    text = _keep_bill_closing(text)
    text = _pair_short_profiles(text)
    text = _BACK_LINK_RE.sub(_BACK_LINK_HTML, text)
    return _keep_back_link(text)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: scripts/polish_html.py FILE.html", file=sys.stderr)
        return 2
    path = Path(args[0])
    path.write_text(polish_html(path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
