# Bulk Submission & Per-User Job Queue — Design

## Purpose

Let a user paste multiple YouTube links (one per line) and have the app queue them,
processing that user's jobs **one at a time** (while different users still run in
parallel). Introduces a `waiting` status for queued jobs and the ability to cancel a
job that hasn't started yet.

## Statuses & lifecycle

- New `JobStatus.waiting` value (added via Alembic migration `0004`, same
  `ALTER TYPE ... ADD VALUE` pattern as `transcribing`).
- Job lifecycle:
  `waiting` (queued, not yet dispatched) → `pending` (claimed/enqueued, about to start)
  → `downloading` → `extracting` → [`transcribing`] → `done` / `failed`.
- Jobs are now **created as `waiting`** (previously `pending`). `pending` now means
  "claimed by the dispatcher and put on the Celery queue".
- **Cancel = delete**: `DELETE /jobs/{id}` is allowed only when the job is `waiting`
  (owner-scoped). A waiting job was never processed (no frames/files), so the row is
  simply deleted. No separate `canceled` status.

## Dispatcher (per-user serialization)

Celery stays at `--concurrency=2` so different users run in parallel; per-user
serialization is enforced in the application.

`dispatch_next(user_id)` (new, in `app/dispatch.py`) — opens its **own** `Session(engine)`
internally (so the advisory lock scopes to a single self-contained transaction) and does
NOT borrow the caller's session:
1. Acquire a **per-user Postgres advisory lock** (`pg_advisory_xact_lock(user_id)`) to
   serialize concurrent callers. Only issued when the bound dialect is `postgresql`; on
   SQLite (tests) it is skipped (tests are single-threaded, no race).
2. Check whether the user already has a job in an **active/claimed** status
   (`pending`, `downloading`, `extracting`, `transcribing`). If yes → do nothing (the
   running job will dispatch the next one when it finishes).
3. Otherwise → take the **oldest `waiting`** job for that user (ordered by `created_at`,
   then `id`), set it to `pending`, commit (releasing the advisory xact lock), and call
   `process_job.delay(job_id)` **after the commit**.

Invariant: at most one job per user is ever in an active/claimed status.

Callers just call `dispatch_next(user_id)` (no session argument):
- **Bulk create endpoint**: after creating and committing N `waiting` jobs in its request
  session, calls `dispatch_next(user.id)`.
- **`process_job`**: in a `finally` block (after the job reaches `done`/`failed` and its
  own `Session` block has done its work), calls `dispatch_next(job_user_id)` to promote
  that user's next `waiting` job. This call is itself wrapped so a dispatch failure is
  logged but does not crash the worker or change the just-finished job's outcome. Capture
  `job.user_id` into a local before the session work so it's available in `finally`.

Race safety: with `--concurrency=2`, two jobs for the same user could finish
simultaneously and both call `dispatch_next`. The advisory lock serializes them so only
one promotes the next waiting job; the second sees an active job (the one just promoted)
or no waiting jobs and does nothing.

## API

- **`POST /jobs`** now accepts a list:
  `{ youtube_urls: string[], interval_seconds?: float, manual_timestamps?: float[] }`.
  - Trims each URL, drops blank/whitespace-only lines.
  - If the resulting list is empty → **422**.
  - If more than **50** URLs → **422** (explicit refusal, no truncation).
  - Requires at least one of `interval_seconds` / `manual_timestamps` (same rule as today),
    applied to every job in the batch.
  - Creates one `waiting` `Job` per URL (same settings for all), calls
    `dispatch_next(session, user.id)`, and returns the list of created `JobResponse`.
  - The previous single `youtube_url` field is replaced by `youtube_urls`; the frontend
    always sends a list, even for one link.
- **`DELETE /jobs/{id}`** (new): owner-scoped (404 for another user's job or missing job).
  Allowed only when `status == waiting`; otherwise **409**. Deletes the row.
- All other endpoints (`GET /jobs`, `GET /jobs/{id}`, `/frames`, `/transcript`, `/zip`,
  `/stream`) are unchanged.

## Frontend

- **`JobForm`**: the URL `<input>` becomes a multi-line `<textarea>` ("one link per
  line"). On submit, split on newlines, trim, drop empties, and send
  `youtube_urls: string[]` to `POST /jobs`. Interval, manual timestamps, and the
  rights-acknowledgment checkbox apply to the whole batch. After submit → **redirect to
  the home job list** (not a single job detail).
- **`lib/jobs.ts`**: `createJob` becomes `createJobs(input)` sending
  `{ youtube_urls, interval_seconds?, manual_timestamps? }` and returning `Job[]`. Add
  `cancelJob(jobId)` → `DELETE /jobs/{id}`.
- **`StatusBadge`**: new `waiting` pill — neutral gray (`bg-chip text-muted`), distinct
  from the blue "in progress" states.
- **Home job list**: each `waiting` job shows a **"Cancel"** button (calls
  `cancelJob`, then removes it from the list). Non-`waiting` jobs show no cancel button.
- **Light polling**: the home page polls `GET /jobs` every ~3 s (`setInterval`, cleared
  on unmount) so statuses advance (waiting → in progress → done) without a manual reload.
  The job list is a plain list, so this keeps the queue from looking frozen.

## Error handling

- Empty batch (all blank lines) → 422; more than 50 URLs → 422.
- `DELETE` on a non-`waiting` job → 409; on another user's or a missing job → 404.
- Owner-scoping enforced on delete via the existing `_get_owned_job` helper.
- A `dispatch_next` failure inside the worker's `finally` is caught and logged; it must
  not crash the worker or change the just-finished job's outcome.

## Testing

- **Backend unit tests**:
  - `dispatch_next`: promotes the oldest `waiting` job when the user has no active job;
    does nothing when the user already has an active job; does nothing when there are no
    waiting jobs. (SQLite — advisory lock skipped.)
  - Bulk create: N `waiting` jobs created, exactly one promoted to `pending`, and
    `process_job.delay` called once with that job's id.
  - Chaining: simulate a job finishing (call the worker's post-processing dispatch) and
    assert the next `waiting` job is promoted.
  - `DELETE`: waiting → 200 + row gone; non-waiting → 409; non-owner/missing → 404.
  - Validation: empty list → 422; > 50 → 422; missing interval & timestamps → 422.
- **Frontend**: multi-line parsing (splits/trims/drops empties), `waiting` badge, cancel
  button calls `DELETE` and removes the row.
- **Manual verification**: paste 3 links, observe 1 in progress + 2 `waiting`, watch them
  chain one after another, and cancel a `waiting` job.

## Out of scope

- Canceling a job that is already in progress (only `waiting` jobs are cancelable).
- Reordering the queue / priorities.
- A per-batch grouping entity (jobs are individual; the "batch" is just the set created
  in one request).
- Global (whole-app) serialization — this design is per-user (different users run in
  parallel).
