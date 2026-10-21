"""Read an official sample-ballot PDF without the layout mode that splits columns.

`pdftotext -layout` pulls a bilingual ballot and its watermark into overlapping
columns. `-raw -nodiag` keeps the reading order. A token such as "Shallll Judge"
is an extraction error, not a contest name. Compare the text to the election-office copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_ballot_text(pdf: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-raw", "-nodiag", str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or "pdftotext failed").strip()
        raise RuntimeError(detail)
    return result.stdout or ""
