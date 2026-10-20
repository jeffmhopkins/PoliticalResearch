"""Re-run script entry points with the repo virtualenv when it exists."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def maybe(repo_root: Path) -> None:
    if os.environ.get("PR_NO_REEXEC") == "1":
        return
    venv = repo_root / ".venv" / "bin" / "python"
    if not venv.exists():
        return
    current = Path(sys.executable).resolve()
    if current == venv.resolve():
        return
    os.execv(str(venv), [str(venv), *sys.argv])
