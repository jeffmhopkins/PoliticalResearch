#!/usr/bin/env bash
# Idempotent environment check and install. Never commits, pushes, or contacts the git remote.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
MODE="install"

usage() {
  cat <<'EOF'
Usage: ./bootstrap.sh [--check | --install]

  --check    Report the environment and exit 2 unless the rating is Full.
  --install  Install missing tools where possible, create .venv, and report.
             This is the default.

The script does not commit, push, or talk to the upstream git remote.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check" ;;
    --install) MODE="install" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

need_apt=()
if [[ "$MODE" == "install" ]]; then
  command -v pandoc >/dev/null 2>&1 || need_apt+=(pandoc)
  command -v pdftotext >/dev/null 2>&1 || need_apt+=(poppler-utils)
  command -v curl >/dev/null 2>&1 || need_apt+=(curl)
  command -v jq >/dev/null 2>&1 || need_apt+=(jq)
  if ! command -v weasyprint >/dev/null 2>&1 && ! command -v wkhtmltopdf >/dev/null 2>&1; then
    need_apt+=(weasyprint)
  fi
  if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    need_apt+=(python3-venv)
  fi
  if [[ ${#need_apt[@]} -gt 0 ]]; then
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
      sudo apt-get update -qq || true
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${need_apt[@]}" || echo "apt install failed; continuing with a lower rating."
    elif [[ "$(id -u)" -eq 0 ]] && command -v apt-get >/dev/null 2>&1; then
      apt-get update -qq || true
      DEBIAN_FRONTEND=noninteractive apt-get install -y "${need_apt[@]}" || echo "apt install failed; continuing with a lower rating."
    else
      echo "Cannot install system packages without sudo: ${need_apt[*]}"
    fi
  fi
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Copied .env.example to .env. Fill in optional keys locally. Never commit .env."
  fi
  mkdir -p output
fi

mkdir -p output
python3 scripts/env_report.py --root "$ROOT" --mode "$MODE"
