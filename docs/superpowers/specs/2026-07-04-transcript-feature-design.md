# Transcript Feature — Design

## Purpose

Add the video's transcript (captions) to the frame-extraction flow so each extracted
frame can be paired with what was being said at that moment, and the full transcript
can be browsed alongside the frames. The transcript is a best-effort enhancement — it
never blocks or fails the core frame-extraction feature.

## Source & language

- Captions come from **YouTube's own subtitle tracks via yt-dlp** (manual or
  auto-generated). No new heavy dependency — yt-dlp already downloads the video.
- Language selection: **prefer English; otherwise the first available track.** One
  transcript per job.
- The available-caption info is read from the **existing `yt-dlp -j` metadata call**
  (which already runs per job to get duration), so picking the language adds no extra
  network round-trip. The actual caption file is then downloaded with a separate
  best-effort `yt-dlp` call.

## Backend: data & extraction

### Schema additions (one Alembic migration)

- **`TranscriptCue`** table: `id`, `job_id` (FK, indexed), `start_seconds` (float),
  `end_seconds` (float), `text` (str). Ordered by `start_seconds`. Powers the
  full-transcript tab.
- **`Frame.caption`** — new nullable `str` column: the transcript text spoken at that
  frame's timestamp, computed at extraction time (denormalized so the storyboard needs
  no join/pairing on the client).
- **`Job.transcript_language`** — new nullable `str`: the language code of the fetched
  transcript; `null` means no transcript was available.

### Worker flow (`process_job`)

Extends the existing pipeline. After the video downloads and before/around frame
extraction:

1. From the `yt-dlp -j` metadata (already fetched for duration), determine the caption
   language via `pick_caption_language(info)` — English if present in `subtitles` or
   `automatic_captions`, else the first available key, else `None`.
2. If a language was found, download that caption track as `.vtt` with a best-effort
   `yt-dlp` call into the job directory, parse it into cues, insert `TranscriptCue`
   rows, and set `Job.transcript_language`.
3. When extracting each frame at timestamp `T`, compute its caption via
   `caption_for_timestamp(cues, T)` and store it on `Frame.caption`.
4. **All transcript work is wrapped in try/except** — any caption download/parse failure
   is logged and swallowed; the job proceeds and completes with frames regardless. A
   transcript failure must never change the job's success/failure outcome.

### Video module functions (`app/video.py`)

- `get_video_info(url) -> dict` — runs `yt-dlp -j` once and returns the parsed metadata
  dict. `get_video_duration` becomes a thin wrapper (`float(get_video_info(url)["duration"])`)
  so its existing behavior/tests are unchanged and the worker fetches metadata only once.
- `pick_caption_language(info: dict) -> str | None` — English-first, else first available
  track from `subtitles`/`automatic_captions`, else `None`.
- `download_captions(url, lang, dest_path) -> None` — best-effort `yt-dlp` call writing
  the chosen language's `.vtt` (skip video download; `--sub-langs <lang>`,
  `--write-subs --write-auto-subs`, `--sub-format vtt`).
- `parse_vtt(path) -> list[Cue]` — parse a WebVTT file into cues `(start, end, text)`.
  Defensive: skips malformed cue blocks, strips inline tags (e.g. `<c>`, `<00:00:01.000>`),
  and collapses consecutive duplicate text lines (common in auto-captions).
- `caption_for_timestamp(cues, t) -> str | None` — the text of the cue whose
  `[start, end]` contains `t`; if none, the nearest preceding cue's text; else `None`.

## Backend: API

- **`FrameResponse`** gains `caption: str | None`. Storyboard captions ride along on the
  existing `GET /jobs/{id}/frames` — no new call needed for the storyboard.
- **`GET /jobs/{id}/transcript`** (new) → `{ "language": str | None, "cues": [{ "start_seconds": float, "end_seconds": float, "text": str }] }`.
  Owner-scoped exactly like the other job endpoints (404 for a job the requester doesn't
  own, consistent with `_get_owned_job`).
- **`GET /jobs/{id}/zip`** also includes a `transcript.txt` (plain text, one line per cue
  prefixed with its timestamp) when a transcript exists — so a single download yields both
  the frames and the words.

## Frontend

Once a job's frames are ready, the job page shows a **two-tab view**: **Storyboard**
(default) and **Transcript**.

- **Storyboard tab** — the existing gallery grid, but each thumbnail shows its
  `caption` beneath it, truncated to ~2 lines. Frames with a `null` caption show just the
  timestamp badge as today.
- **Lightbox** — gains a subtitle line: the current frame's caption displayed under the
  image, alongside the existing timestamp label and download button.
- **Transcript tab** — a scrollable panel of the full transcript from
  `GET /jobs/{id}/transcript`, each line prefixed with its timestamp (`0:12`). **Clicking a
  line opens the nearest frame in the lightbox** (transcript → frame sync); "nearest" =
  the frame whose timestamp is closest to the cue's start.
- **No-transcript case** — the Transcript tab shows a subtle "No transcript available for
  this video" note; the Storyboard omits captions; everything else works normally. The tab
  is always shown (with the empty note when applicable) for a consistent UI.
- Styling follows the current neutral "Frame Extractor" palette and component patterns.

## Error handling

- Caption download/parse failures are logged and swallowed; the job still succeeds with
  frames (transcript is strictly best-effort).
- `parse_vtt` skips malformed cues rather than raising.
- `caption_for_timestamp` falls back to the nearest preceding cue when no cue exactly
  covers a frame's timestamp; returns `None` if there are no cues at or before it.

## Testing

- **Backend unit tests:** `parse_vtt` (well-formed and messy auto-caption input with tags
  and duplicate lines), `caption_for_timestamp` (exact-cover, nearest-preceding, and
  no-cue cases), and `pick_caption_language` (English-preferred, first-available fallback,
  none-available).
- **Backend API tests:** `GET /jobs/{id}/transcript` (owner scoping → 404 for non-owner;
  the no-transcript / empty-cues case), and the new `caption` field appearing on
  `GET /jobs/{id}/frames`.
- **Frontend:** verified via `npm run build` / `npm run lint` plus a live browser
  walkthrough — storyboard captions render, the Transcript tab lists cues, the lightbox
  shows the caption subtitle, clicking a transcript line opens the nearest frame, and the
  no-transcript note appears for a caption-less video.

## Out of scope

- Whisper / local speech-to-text transcription (captions only for this iteration).
- Multiple simultaneous transcript languages or a per-job language picker.
- Editing/correcting transcript text.
