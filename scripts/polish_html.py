#!/usr/bin/env python3
"""Mark gap cells in built guide HTML. Does not change the words."""

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
    return _TH_RE.sub(th_repl, text)


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
