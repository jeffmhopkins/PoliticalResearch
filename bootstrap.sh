#!/usr/bin/env bash
# Idempotent environment check and install. Never commits, pushes, or contacts the git remote.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
MODE="install"
MINIMAL=0
WITH_TRANSCRIPTION=0

usage() {
  cat <<'EOF'
Usage: ./bootstrap.sh [--check | --install] [--minimal] [--with-transcription]

  --check               Report the environment and exit 2 unless the rating is Full.
  --install             Install tools, create .venv, and report. This is the default.
  --minimal             Skip the heavy defaults: ffmpeg, yt-dlp, monolith,
                        headless Chromium, and pa11y. Core build tools still install.
  --with-transcription  Also install faster-whisper and download the Whisper
                        model named by whisper_model in config.yaml (default base).
                        Off unless you pass this flag or set whisper_transcription: true.

A normal install fetches ffmpeg, yt-dlp, monolith, a headless browser, and pa11y.
It does not install Whisper. If one of the installs that did run fails, bootstrap
continues and the environment report lists that sandbox capability as reduced.
The Full / Reduced / Minimal tooling rating is unchanged by those failures.
--check never installs. --minimal does not cancel --with-transcription.

The script does not commit, push, or talk to the upstream git remote.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check" ;;
    --install) MODE="install" ;;
    --minimal) MINIMAL=1 ;;
    --with-transcription) WITH_TRANSCRIPTION=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

apt_install() {
  local pkgs=("$@")
  if [[ ${#pkgs[@]} -eq 0 ]]; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}" || echo "apt install failed (${pkgs[*]}); continuing."
  elif [[ "$(id -u)" -eq 0 ]] && command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}" || echo "apt install failed (${pkgs[*]}); continuing."
  else
    echo "Cannot install system packages without sudo: ${pkgs[*]}"
  fi
}

browser_present() {
  command -v chromium >/dev/null 2>&1 \
    || command -v chromium-browser >/dev/null 2>&1 \
    || command -v google-chrome >/dev/null 2>&1 \
    || command -v google-chrome-stable >/dev/null 2>&1
}

install_monolith() {
  if command -v monolith >/dev/null 2>&1 || [[ -x "$ROOT/.venv/bin/monolith" ]]; then
    return 0
  fi
  apt_install monolith
  if command -v monolith >/dev/null 2>&1; then
    return 0
  fi
  local asset dest url
  dest="$ROOT/.venv/bin/monolith"
  mkdir -p "$ROOT/.venv/bin"
  case "$(uname -m)" in
    x86_64) asset="monolith-cli-linux-x86_64" ;;
    aarch64|arm64) asset="monolith-cli-linux-aarch64" ;;
    armv7l|armhf) asset="monolith-cli-linux-armhf" ;;
    *)
      echo "No monolith package or release for $(uname -m). Archive capture stays reduced and will save the HTTP body and a PDF print."
      return 0
      ;;
  esac
  url="https://github.com/Y2Z/monolith/releases/latest/download/${asset}"
  if curl -fL --retry 3 -o "$dest" "$url"; then
    chmod +x "$dest"
    echo "Installed monolith to $dest"
  else
    rm -f "$dest"
    echo "Could not download monolith. Offline archive will save the HTTP body and a PDF print."
  fi
}

install_browser() {
  if browser_present; then
    return 0
  fi
  apt_install chromium
  if browser_present; then
    return 0
  fi
  apt_install chromium-browser
  if ! browser_present; then
    echo "Headless Chromium was not installed. Screenshot capture will be skipped."
  fi
}

config_wants_transcription() {
  grep -Eq '^whisper_transcription:[[:space:]]*true[[:space:]]*(#.*)?$' "$ROOT/config.yaml"
}

install_ytdlp() {
  if ! command -v ffmpeg >/dev/null 2>&1; then
    apt_install ffmpeg
  fi
  .venv/bin/python -m pip install "yt-dlp" \
    || echo "yt-dlp failed to install. Audio download stays reduced. Continuing."
}

install_whisper() {
  .venv/bin/python -m pip install "faster-whisper" \
    || echo "faster-whisper failed to install. Whisper transcription stays unavailable. Continuing."
  prefetch_whisper_model
}

prefetch_whisper_model() {
  if ! .venv/bin/python -c "import faster_whisper" >/dev/null 2>&1; then
    echo "faster-whisper is not importable. Transcript capability stays reduced."
    return 0
  fi
  local model
  model="$(PYTHONPATH="$ROOT/scripts" .venv/bin/python -c 'from lib.transcripts import whisper_model_name; print(whisper_model_name())' 2>/dev/null || echo base)"
  echo "Prefetching Whisper model ${model} from config.yaml (whisper_model)."
  PYTHONPATH="$ROOT/scripts" .venv/bin/python -c 'from faster_whisper import WhisperModel; from lib.transcripts import whisper_model_name; WhisperModel(whisper_model_name(), device="cpu", compute_type="int8")' \
    || echo "Whisper model prefetch failed. The first transcription will try again. Continuing with reduced transcript capability until then."
}

install_a11y() {
  if command -v pa11y >/dev/null 2>&1 || [[ -x "$ROOT/.venv/bin/pa11y" ]]; then
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    apt_install nodejs npm
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is not available. Accessibility capability stays reduced. Built-in HTML checks still run."
    return 0
  fi
  mkdir -p "$ROOT/.tools"
  if npm install --prefix "$ROOT/.tools/a11y" pa11y; then
    ln -sfn "$ROOT/.tools/a11y/node_modules/.bin/pa11y" "$ROOT/.venv/bin/pa11y"
    echo "Installed pa11y into .venv/bin."
  else
    echo "pa11y install failed. Accessibility capability stays reduced. Built-in HTML checks still run."
  fi
}

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
    apt_install "${need_apt[@]}"
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
  if [[ "$MINIMAL" -eq 0 ]]; then
    install_ytdlp
    install_monolith
    install_browser
    install_a11y
  else
    echo "Minimal install: skipping ffmpeg, yt-dlp, monolith, Chromium, and pa11y."
  fi
  if [[ "$WITH_TRANSCRIPTION" -eq 1 ]] || config_wants_transcription; then
    install_whisper
  else
    echo "Whisper transcription is opt-in. Run ./bootstrap.sh --with-transcription to install faster-whisper and the model in config.yaml."
  fi
fi

if [[ -d "$ROOT/.venv/bin" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi
mkdir -p output
python3 scripts/env_report.py --root "$ROOT" --mode "$MODE"
