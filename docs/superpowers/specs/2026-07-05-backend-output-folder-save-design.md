# Backend Save-to-Output-Folder — Design

## Purpose

Add a robust, backend-driven way to save each finished job's result zip to a
folder on the host machine — independent of the browser. The Celery worker
writes the zip to a mounted output directory the moment a job reaches `done`,
so saving no longer depends on keeping a browser tab open, staying on a
particular page, or using Chrome/Edge.

This exists **alongside** the existing browser File System Access auto-save
(kept as-is); the two are independent opt-ins.

## Motivation

The browser auto-save writes files from the home page's in-memory state. Its
engine (pending-jobs map, poll loop, folder handle) lives inside the home page
component, so navigating away (e.g. opening a job to watch it finish) unmounts
it and stops all further writes — observed in practice as "only the first jobs
saved." Moving the save into the worker removes every one of those fragilities.

## Constraint that shapes the design

The backend runs in Docker with a named volume (`videodata:/data`). A container
can only write to host folders that are **bind-mounted** into it, and mounts are
fixed at `docker compose up` time (not choosable per request). Therefore the
destination is a **pre-configured mounted base directory** plus an optional
**per-batch subfolder** created at runtime — not an arbitrary absolute host path
typed per submission.

## Architecture & path model

- **Mount:** `docker-compose.yml` bind-mounts a host folder into the **worker**
  service: `${OUTPUT_DIR:-./output}:/data/output`. `OUTPUT_DIR` is set in the
  project-root `.env` (e.g. `/Users/lorenzo/Desktop/FrameExports`) and defaults
  to `./output`. Docker Compose interpolates `${OUTPUT_DIR}` from `.env` at
  startup. (The `api` service does not need this mount — only the worker writes.)
- **Config:** `backend/app/config.py` gains `output_dir: str = "/data/output"`
  (the in-container path), so the worker code references a setting, not a
  literal.
- **Who writes:** the Celery worker, inside `process_job`, after the job's
  frames (and transcript, if any) are complete and status is `done`.
- **What it writes:** the same zip the `GET /jobs/{id}/zip` endpoint produces
  (frames + per-frame captions + `transcript.txt`). The zip-building logic
  currently inline in that endpoint is refactored into a shared helper used by
  both the endpoint and the worker (DRY).
- **Where:** `<output_dir>/<subfolder>/video_<index>.zip` in the container,
  which maps to `<OUTPUT_DIR>/<subfolder>/video_<index>.zip` on the host. A blank
  subfolder writes directly into `<output_dir>`.

## Form / UX

- A new, independent checkbox on `JobForm`: **"Also save finished results to the
  server output folder."** Separate from the existing browser folder-picker
  checkbox; either, both, or neither may be used.
- When checked, it reveals an optional text input **"Subfolder (optional)"**
  (e.g. `my-project`). Blank → write into the base `output_dir`.
- Applies to the whole batch. The submit request carries `save_to_output: bool`
  and `output_subdir: string | null`.
- The checkbox is always available (not feature-detected) — it does not depend
  on any browser API.

## Schema

Add three nullable/defaulted columns to `Job` (Alembic migration `0005`):

- `save_to_output: bool` — default `False`. Whether this job should be written
  to the output folder on completion.
- `output_subdir: str | None` — the sanitized subfolder name (None/empty →
  base dir).
- `output_index: int | None` — the job's 1-based position in its submission
  batch, used for the `video_<index>.zip` name.

## Data flow

1. **Submit** (`POST /jobs`): request adds `save_to_output` (bool, default
   False) and `output_subdir` (optional string). The subfolder is sanitized
   (below); an invalid value → **422**.
2. **Bulk create** (`routers/jobs.py`): if `save_to_output` is true, each created
   job gets `save_to_output=True`, `output_subdir=<sanitized>`, and
   `output_index` = its 1-based index in the batch (link #1 → 1). If false, all
   three keep their defaults (False / None / None).
3. **Worker** (`process_job`): after the job reaches `done`, if
   `save_to_output` and `output_index` are set:
   - Build the zip bytes via the shared helper.
   - Compute `target_dir = os.path.join(settings.output_dir, output_subdir or "")`
     and `os.makedirs(target_dir, exist_ok=True)`.
   - Resolve a non-colliding filename: `video_<index>.zip`, else
     `video_<index> (2).zip`, `video_<index> (3).zip`, … (never overwrite).
   - Write the file.
   - The whole save block is wrapped in `try/except`: any failure is logged and
     swallowed — it never changes the job's `done` status or crashes the worker.

## Naming & numbering

- `video_<index>.zip`, where `<index>` is the job's 1-based position in the
  submitted batch (`output_index`). Numbering is **per-batch** (each batch starts
  at 1).
- **Failed jobs** never reach the save step (only `done` jobs save), so a failed
  link's number is simply absent — a natural gap, matching the browser version.
- **Collisions never overwrite:** an existing `video_1.zip` yields
  `video_1 (2).zip`, then `video_1 (3).zip`, etc.

## Subfolder sanitization

A dedicated `sanitize_output_subdir(raw: str | None) -> str` helper:

- `None`/empty/whitespace → `""` (base dir).
- Rejects path traversal: any input containing `..`, a leading `/` or `\`, a
  drive-letter/absolute form, or a null byte → raises a validation error (→ 422).
- Allows a single path segment of safe characters only: letters, digits, space,
  `-`, `_`, `.`. Anything else → 422.
- Rejects the whole-name values `.` and `..` (any name consisting only of dots)
  → 422, so the segment can never mean "current"/"parent" directory.
- The result is always a single segment that stays within `output_dir`.

## Error handling

- Invalid subfolder → 422 at submit (nothing created).
- Worker write failure (permission, disk full, unexpected) → caught, logged,
  job stays `done`. Best-effort; never crashes the batch or worker.
- `/data/output` is always mounted, so `makedirs` of the subfolder under it
  succeeds on a normal run even if the host `OUTPUT_DIR` was freshly created.

## Testing

Fully unit-testable with the existing backend pytest suite (this closes the
verification gap the browser-only feature had):

- `sanitize_output_subdir`: empty/None → `""`; `..`, `../x`, `/abs`, `a/b`,
  backslashes, null bytes → rejected; `my-project`, `Batch_01` → kept.
- Shared zip helper: builds a valid zip containing the frames and
  `transcript.txt` for a job (reusing existing zip fixtures/coverage).
- Collision-safe write helper: writes `video_2.zip`; a second call →
  `video_2 (2).zip`; a third → `video_2 (3).zip` (using a tmp dir).
- Bulk create: with `save_to_output=True`, jobs get `output_index` 1..N and the
  sanitized `output_subdir`; with it false/omitted, all three fields stay at
  defaults; invalid subfolder → 422.
- Worker save path: a `done` job with `save_to_output` writes the expected file
  into a tmp `output_dir`; a `failed` job writes nothing.
- **Manual:** set `OUTPUT_DIR`, submit a batch with the server-save box + a
  subfolder, and confirm `video_1.zip`… appear on the host. Because real
  YouTube downloads fail from this datacenter IP, the worker save path is also
  exercised directly against a job that already has frames (e.g. a seeded `done`
  job) to prove real files land on the host.

## Out of scope

- Changing or removing the existing browser File System Access auto-save (kept
  as-is; independent).
- Choosing an arbitrary absolute host path per request (Docker mounts are fixed
  at startup; the base dir is configured once).
- Running the worker outside Docker.
- Surfacing per-job save success/failure in the API or UI (worker logs only).
- A continuous cross-batch counter (numbering is per-batch by position).
- Saving jobs that finished before this feature, or re-saving past jobs.
