#!/usr/bin/env bash
# Build guide.md into HTML and PDF. Writes only inside the election workspace.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE=""
ELECTION=""

usage() {
  echo "Usage: scripts/build.sh --workspace PATH | --election-id ID" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WORKSPACE="${2:-}"; shift 2 ;;
    --election-id|--election) ELECTION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$WORKSPACE" ]]; then
  if [[ -z "$ELECTION" ]]; then
    usage
    exit 2
  fi
  WORKSPACE="$ROOT/output/$ELECTION"
fi

GUIDE="$WORKSPACE/final/guide.md"
if [[ ! -f "$GUIDE" ]]; then
  echo "Missing $GUIDE. Assemble the guide first." >&2
  exit 1
fi

HASH="$(sha256sum "$GUIDE" | awk '{print $1}')"
VERSION="$(python3 - "$GUIDE" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
match = re.search(r"^version:\s*(\S+)", text, re.M)
print(match.group(1) if match else "v0")
PY
)"

cp "$ROOT/assets/guide.css" "$WORKSPACE/final/guide.css"
HTML="$WORKSPACE/final/guide.html"
(
  cd "$WORKSPACE/final"
  pandoc "$GUIDE" \
    --from markdown+footnotes \
    --to html5 \
    --standalone \
    --template "$ROOT/assets/guide.html.tmpl" \
    --css guide.css \
    --toc --toc-depth=2 \
    --metadata lang=en \
    --variable version="$VERSION" \
    --variable content-hash="$HASH" \
    -o guide.html
)

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi
"$PY" "$ROOT/scripts/a11y_check.py" "$HTML"

PDF="$WORKSPACE/final/guide.pdf"
if command -v weasyprint >/dev/null 2>&1; then
  weasyprint "$HTML" "$PDF"
elif command -v wkhtmltopdf >/dev/null 2>&1; then
  wkhtmltopdf "$HTML" "$PDF"
else
  echo "No PDF engine found. HTML is at $HTML" >&2
fi

if [[ -f "$PDF" ]]; then
  pdf_text="$(pdftotext "$PDF" - || true)"
  if [[ "$pdf_text" != *"Not an official ballot"* ]]; then
    echo "PDF is missing the not-an-official-ballot banner." >&2
    exit 1
  fi
fi

mkdir -p "$WORKSPACE/versions"
cp "$HTML" "$WORKSPACE/versions/guide-${VERSION}.html"
if [[ -f "$PDF" ]]; then
  cp "$PDF" "$WORKSPACE/versions/guide-${VERSION}.pdf"
fi

echo "Built $HTML"
if [[ -f "$PDF" ]]; then
  echo "Built $PDF"
fi
echo "Content hash: $HASH"
