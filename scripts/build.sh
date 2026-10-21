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

if [[ ! -d "$WORKSPACE" ]]; then
  echo "Workspace not found: $WORKSPACE" >&2
  exit 1
fi
WORKSPACE="$(cd "$WORKSPACE" && pwd)"

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

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi
if ! "$PY" "$ROOT/scripts/validate.py" --workspace "$WORKSPACE" --gate; then
  echo "Assembly gate failed." >&2
  exit 1
fi
if ! "$PY" "$ROOT/scripts/check_citations.py" --workspace "$WORKSPACE"; then
  echo "Citation check failed." >&2
  exit 1
fi

cp "$ROOT/assets/guide.css" "$WORKSPACE/final/guide.css"
cp "$ROOT/assets/guide-narrow.css" "$WORKSPACE/final/guide-narrow.css"

build_one() {
  local source_md="$1"
  local html_out="$2"
  local pdf_out="$3"
  local hash
  hash="$(sha256sum "$source_md" | awk '{print $1}')"
  (
    cd "$WORKSPACE/final"
    pandoc "$source_md" \
      --from markdown+footnotes+header_attributes \
      --to html5 \
      --standalone \
      --template "$ROOT/assets/guide.html.tmpl" \
      --css guide.css \
      --toc --toc-depth=2 \
      --metadata lang=en \
      --variable version="$VERSION" \
      --variable content-hash="$hash" \
      -o "$html_out"
  )
  "$PY" "$ROOT/scripts/a11y_check.py" "$html_out"
  if command -v weasyprint >/dev/null 2>&1; then
    timeout -k 15 120 weasyprint "$html_out" "$pdf_out"
  elif command -v wkhtmltopdf >/dev/null 2>&1; then
    timeout -k 15 120 wkhtmltopdf "$html_out" "$pdf_out"
  else
    echo "No PDF engine found. HTML is at $html_out" >&2
  fi
  if [[ -f "$pdf_out" ]]; then
    local pdf_text
    pdf_text="$(pdftotext "$pdf_out" - || true)"
    if [[ "$pdf_text" != *"Not an official ballot"* ]]; then
      echo "PDF is missing the not-an-official-ballot banner: $pdf_out" >&2
      exit 1
    fi
    "$PY" "$ROOT/scripts/check_pdf_layout.py" "$pdf_out"
  fi
  echo "Built $html_out"
  if [[ -f "$pdf_out" ]]; then
    echo "Built $pdf_out"
  fi
  echo "Content hash: $hash"
}

build_one "$GUIDE" "$WORKSPACE/final/guide.html" "$WORKSPACE/final/guide.pdf"
if [[ -f "$WORKSPACE/final/guide.pdf" ]] && command -v pdfinfo >/dev/null 2>&1; then
  pdfinfo "$WORKSPACE/final/guide.pdf" | awk '/^Pages:/ { print "Reader pages: " $2 }'
fi
if [[ -f "$WORKSPACE/final/guide-sources.md" ]]; then
  build_one "$WORKSPACE/final/guide-sources.md" "$WORKSPACE/final/guide-sources.html" "$WORKSPACE/final/guide-sources.pdf"
fi
if [[ -f "$WORKSPACE/final/guide-full.md" ]]; then
  build_one "$WORKSPACE/final/guide-full.md" "$WORKSPACE/final/guide-full.html" "$WORKSPACE/final/guide-full.pdf"
fi
if [[ -f "$WORKSPACE/final/guide-full-sources.md" ]]; then
  build_one "$WORKSPACE/final/guide-full-sources.md" "$WORKSPACE/final/guide-full-sources.html" "$WORKSPACE/final/guide-full-sources.pdf"
fi

mkdir -p "$WORKSPACE/versions"
cp "$WORKSPACE/final/guide.html" "$WORKSPACE/versions/guide-${VERSION}.html"
if [[ -f "$WORKSPACE/final/guide.pdf" ]]; then
  cp "$WORKSPACE/final/guide.pdf" "$WORKSPACE/versions/guide-${VERSION}.pdf"
fi
