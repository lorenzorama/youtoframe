import json
import re
import subprocess
from typing import NamedTuple

# ffmpeg cannot reliably decode a frame exactly at (or past) a video's
# reported duration -- no frame exists there, and its fallback path for
# "no filtered frames" fails to initialize the encoder without real frame
# data. Cap sampling this far short of the reported duration.
SAFE_END_BUFFER_SECONDS = 0.5


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"Command {args!r} failed with exit code {exc.returncode}: {stderr or '(no stderr output)'}"
        ) from exc


def compute_timestamps(
    duration: float,
    interval_seconds: float | None,
    manual_timestamps: list[float] | None,
) -> list[float]:
    if interval_seconds is None and not manual_timestamps:
        raise ValueError("Must provide interval_seconds and/or manual_timestamps")

    safe_end = max(0.0, duration - SAFE_END_BUFFER_SECONDS)

    timestamps: set[float] = set()

    if interval_seconds is not None:
        t = 0.0
        while t < safe_end:
            timestamps.add(round(t, 3))
            t += interval_seconds
        timestamps.add(round(safe_end, 3))

    for t in manual_timestamps or []:
        if t < 0 or t > duration:
            raise ValueError(f"Timestamp {t} is outside video duration {duration}")
        timestamps.add(round(min(t, safe_end), 3))

    return sorted(timestamps)


class Cue(NamedTuple):
    start: float
    end: float
    text: str


def get_video_info(url: str) -> dict:
    result = _run(["yt-dlp", "--no-warnings", "--no-playlist", "-j", url])
    return json.loads(result.stdout)


def get_video_duration(url: str) -> float:
    return float(get_video_info(url)["duration"])


def pick_caption_language(info: dict) -> str | None:
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    available = list(subs.keys()) + list(autos.keys())
    if not available:
        return None
    for lang in available:
        if lang == "en":
            return lang
    for lang in available:
        if lang.startswith("en"):
            return lang
    return available[0]


def download_captions(url: str, lang: str, dest_stem: str) -> str:
    # Best-effort: yt-dlp writes "<dest_stem>.<lang>.vtt". The caller checks the
    # file exists before parsing.
    _run(
        [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", lang,
            "--sub-format", "vtt",
            "-o", dest_stem,
            url,
        ]
    )
    return f"{dest_stem}.{lang}.vtt"


def _parse_ts(token: str) -> float:
    token = token.strip().replace(",", ".")
    parts = [float(p) for p in token.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0.0, parts[0], parts[1]
    else:
        raise ValueError(f"bad timestamp {token}")
    return h * 3600 + m * 60 + s


def parse_vtt(path: str) -> list[Cue]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        timing_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_idx is None:
            continue  # WEBVTT header, NOTE block, or id-only block
        left, _, right = lines[timing_idx].partition("-->")
        try:
            start = _parse_ts(left.strip().split()[0])
            end = _parse_ts(right.strip().split()[0])
        except (ValueError, IndexError):
            continue
        text = " ".join(lines[timing_idx + 1:])
        text = re.sub(r"<[^>]+>", "", text)      # strip inline tags
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if cues and cues[-1].text == text:       # collapse consecutive duplicates
            continue
        cues.append(Cue(start, end, text))
    return cues


def caption_for_timestamp(cues: list[Cue], t: float) -> str | None:
    covering = [c for c in cues if c.start <= t <= c.end]
    if covering:
        return covering[0].text
    preceding = [c for c in cues if c.start <= t]
    if preceding:
        return max(preceding, key=lambda c: c.start).text
    return None


def download_video(url: str, dest_path: str) -> None:
    _run(
        [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", dest_path,
            url,
        ]
    )


def extract_frame(video_path: str, timestamp: float, dest_path: str) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            dest_path,
        ]
    )
