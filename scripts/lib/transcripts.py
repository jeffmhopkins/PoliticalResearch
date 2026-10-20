"""Optional forum and debate transcripts.

yt-dlp can be installed by a normal bootstrap. faster-whisper and its model are
opt-in (`./bootstrap.sh --with-transcription`, or `whisper_transcription: true`).
A missing Whisper install exits with a message and does not write a claim.
Output is an unreviewed import. It is not merged into claims.yaml.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from lib.quality import SENTENCE_SPLIT_RE
from lib.util import dump_yaml, load_config, repo_root, resolve_bin, slugify, unsafe_fetch_target

SKIP_MESSAGE = (
    "Whisper transcription is not available. It is opt-in: set whisper_transcription: true "
    "in config.yaml or run ./bootstrap.sh --with-transcription. That installs faster-whisper "
    "and downloads the whisper_model (default base). yt-dlp still comes from a normal bootstrap; "
    "./bootstrap.sh --minimal skips yt-dlp, monolith, Chromium, and pa11y. "
    "Cite the recording page until transcription is enabled."
)
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
DEFAULT_WHISPER_MODEL = "base"


def faster_whisper_available(root: Path | None = None) -> bool:
    root = root or repo_root()
    venv = root / ".venv" / "bin" / "python"
    python = str(venv) if venv.exists() else None
    if python is None:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True
    result = subprocess.run([python, "-c", "import faster_whisper"], capture_output=True)
    return result.returncode == 0


def tool_status(root: Path | None = None) -> dict[str, bool]:
    root = root or repo_root()
    return {
        "yt-dlp": resolve_bin("yt-dlp", root) is not None,
        "ffmpeg": resolve_bin("ffmpeg", root) is not None,
        "whisper": resolve_bin("whisper", root) is not None,
        "faster-whisper": faster_whisper_available(root),
    }


def whisper_transcription_enabled(root: Path | None = None) -> bool:
    """True when config.yaml opts in. The bootstrap flag installs the package."""
    return load_config(root).get("whisper_transcription") is True


def whisper_model_name(root: Path | None = None) -> str:
    """Model from config.yaml. Anything unexpected falls back to base."""
    raw = str(load_config(root).get("whisper_model") or "").strip()
    if _MODEL_RE.match(raw):
        return raw
    return DEFAULT_WHISPER_MODEL


def transcripts_ready(root: Path | None = None) -> bool:
    status = tool_status(root)
    engine = status["whisper"] or status["faster-whisper"]
    return bool(status["yt-dlp"] and status["ffmpeg"] and engine)


def format_timestamp(seconds: float) -> str:
    total = max(0, int(float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def normalize_segments(raw) -> list[dict]:
    segments = []
    for item in raw or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            start = item.get("start", 0)
            end = item.get("end", start)
        else:
            text = str(getattr(item, "text", "") or "").strip()
            start = getattr(item, "start", 0)
            end = getattr(item, "end", start)
        if not text:
            continue
        segments.append({"start": float(start), "end": float(end), "text": text})
    return segments


def quote_from_segments(segments: list[dict]) -> tuple[str, str]:
    """At most two sentences, with a Timestamp locator a researcher can copy."""
    chosen: list[str] = []
    start_at = None
    end_at = None
    for segment in segments:
        parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(segment["text"]) if part.strip()]
        if not parts:
            continue
        if start_at is None:
            start_at = segment["start"]
        for part in parts:
            chosen.append(part)
            end_at = segment["end"]
            if len(chosen) >= 2:
                break
        if len(chosen) >= 2:
            break
    quote = " ".join(chosen).strip()
    if start_at is None:
        return "", "Timestamp 00:00:00"
    start = format_timestamp(start_at)
    end = format_timestamp(end_at if end_at is not None else start_at)
    locator = f"Timestamp {start}" if start == end else f"Timestamp {start}-{end}"
    return quote, locator


def render_timestamped_text(segments: list[dict]) -> str:
    lines = [f"[{format_timestamp(segment['start'])}] {segment['text']}" for segment in segments]
    return "\n".join(lines) + ("\n" if lines else "")


def transcribe_item(
    workspace: Path,
    item_id: str,
    url: str,
    *,
    title: str,
    publisher: str,
    clock: str,
    keep_media: bool = False,
    download=None,
    transcribe=None,
) -> tuple[int, str]:
    if download is None or transcribe is None:
        if not transcripts_ready():
            return 1, SKIP_MESSAGE
        download = download or live_download
        transcribe = transcribe or live_transcribe
    dest = workspace / "items" / item_id / "imports" / "transcripts"
    media = dest / "media"
    dest.mkdir(parents=True, exist_ok=True)
    media.mkdir(parents=True, exist_ok=True)
    try:
        audio = download(url, media)
    except Exception as exc:  # noqa: BLE001 - surface the tool error and stop this import
        return 1, f"Transcript download failed: {exc}"
    if audio is None:
        return 1, SKIP_MESSAGE
    try:
        raw = transcribe(Path(audio))
    except Exception as exc:  # noqa: BLE001
        return 1, f"Transcription failed: {exc}"
    if raw is None:
        return 1, SKIP_MESSAGE
    segments = normalize_segments(raw)
    if not segments:
        return 1, "Transcript was empty."
    slug = slugify(title or url)
    text_path = dest / f"{slug}.txt"
    json_path = dest / f"{slug}.json"
    stub_path = dest / f"{slug}.citation.yaml"
    text_path.write_text(render_timestamped_text(segments), encoding="utf-8")
    json_path.write_text(
        json.dumps({"url": url, "title": title, "segments": segments}, indent=2) + "\n",
        encoding="utf-8",
    )
    quote, locator = quote_from_segments(segments)
    relative_text = text_path.relative_to(workspace).as_posix()
    relative_json = json_path.relative_to(workspace).as_posix()
    dump_yaml(
        stub_path,
        {
            "status": "unreviewed_import",
            "note": (
                "Machine transcript. Not a finished claim. Check the quote against the recording "
                "before copying suggested_source into claims.yaml. Replace marker 9001 with a number "
                "that is unique in this election. Confirm the tier: a campaign "
                "video is not T1 by default."
            ),
            "url": url,
            "title": title,
            "publisher": publisher,
            "doc_type": "Forum transcript",
            "retrieved": clock,
            "text_path": relative_text,
            "segments_path": relative_json,
            "suggested_source": {
                "url": url,
                "publisher": publisher,
                "title": title,
                "doc_type": "Forum transcript",
                "published": "undated",
                "retrieved": clock,
                "tier": "T3",
                "locator": locator,
                "quote": quote,
                "confidence": "unconfirmed",
                "archive_failed": True,
                "archive_failed_reason": "Transcript import is unreviewed. Archive the recording before publication.",
                "marker": 9001,
            },
        },
    )
    if not keep_media:
        shutil.rmtree(media, ignore_errors=True)
    return 0, (
        f"Wrote an unreviewed transcript stub at {stub_path.relative_to(workspace).as_posix()}. "
        f"Locator: {locator}. It was not added to claims.yaml."
    )


def live_download(url: str, media_dir: Path) -> Path | None:
    reason = unsafe_fetch_target(url)
    if reason:
        raise RuntimeError(f"Refusing fetch: {reason}")
    binary = resolve_bin("yt-dlp")
    if not binary or resolve_bin("ffmpeg") is None:
        return None
    media_dir.mkdir(parents=True, exist_ok=True)
    template = str(media_dir / "audio.%(ext)s")
    result = subprocess.run(
        [
            binary,
            "-x",
            "--audio-format",
            "wav",
            "--no-playlist",
            "--no-write-thumbnail",
            "--no-write-info-json",
            "-o",
            template,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "yt-dlp failed").strip()
        raise RuntimeError(detail[-500:])
    files = sorted(media_dir.glob("audio.*"))
    if not files:
        raise RuntimeError("yt-dlp produced no audio file")
    return files[0]


def live_transcribe(audio: Path) -> list[dict] | None:
    if faster_whisper_available():
        from faster_whisper import WhisperModel

        model = WhisperModel(whisper_model_name(), device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio))
        return normalize_segments(segments)
    binary = resolve_bin("whisper")
    if not binary:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [binary, str(audio), "--model", whisper_model_name(), "--output_format", "json", "--output_dir", tmp],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "whisper failed").strip()
            raise RuntimeError(detail[-500:])
        files = list(Path(tmp).glob("*.json"))
        if not files:
            raise RuntimeError("whisper produced no JSON")
        payload = json.loads(files[0].read_text(encoding="utf-8"))
    return normalize_segments(payload.get("segments") or [])
