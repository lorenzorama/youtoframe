# Auto-Download Outputs to a Folder — Design

## Purpose

Let a user opt in — via a checkbox under the URL textarea — to have each job's
result zip written **automatically into a folder they choose**, as each job in
the batch finishes. Zips are named `video_1.zip`, `video_2.zip`, … by the
position of the link in the submitted batch.

This removes the manual "open each finished job → click Download ZIP" step for
bulk submissions.

## Scope

**Frontend-only.** No backend, database, Celery, or migration changes. The
existing `GET /jobs/{id}/zip` endpoint already returns the finished job's zip
(frames + captions + `transcript.txt`). The `video_N` naming is applied
client-side at write time (we control the filename we write; the endpoint's
`Content-Disposition` is irrelevant here). Nothing server-side changes.

## Mechanism: File System Access API (Chrome/Edge)

The destination-folder capability uses the browser
[File System Access API](https://developer.mozilla.org/docs/Web/API/File_System_API):

- On form submit (a user gesture), if auto-save is checked, call
  `window.showDirectoryPicker({ mode: "readwrite" })`. The browser shows a
  native folder chooser and grants the page read/write access to that folder.
- As each job finishes, the app fetches its zip and writes it directly into the
  chosen folder handle — no per-file "Save As" prompt.

**Constraints (accepted):**
- Chrome/Edge only. The API is absent in Firefox/Safari. The checkbox is
  feature-detected (`"showDirectoryPicker" in window`) and only rendered where
  supported; elsewhere a one-line note explains it needs Chrome/Edge.
- The tab must stay open while the batch runs — the browser does the writing.
- The granted directory handle lives only in memory (handles are not trivially
  persistable). If the user reloads mid-batch, auto-save for not-yet-finished
  jobs is lost; those remain downloadable manually from the gallery as today.

## Naming & numbering

- Numbers map to **link position in the submitted batch**: the Nth link pasted
  becomes `video_N.zip`, regardless of the order jobs finish. Numbering is
  per-batch (resets each submission).
- **Failed job → no file; its number is skipped.** If link #2 fails, the folder
  gets `video_1.zip`, `video_3.zip`. The number always equals the link's
  position, so there is never ambiguity about which video a file came from.
- **Collision → no overwrite.** If `video_1.zip` already exists in the folder,
  write `video_1 (2).zip`; if that also exists, `video_1 (3).zip`, and so on.

## Flow

1. **Submit (`JobForm`):** if the auto-save checkbox is checked, first call
   `showDirectoryPicker({ mode: "readwrite" })`.
   - If the user cancels the picker (`AbortError`) → abort the submit with an
     inline message; **create no jobs**; leave the checkbox checked.
   - Otherwise proceed: `createJobs(...)` returns the created jobs **in
     submitted order**. Each job's index gives its position → `video_{index+1}`.
2. **Hand-off:** `JobForm` passes the created jobs plus the directory handle up
   to the home page via a callback. (Today `onCreated: () => void` just triggers
   `reload`; it becomes `onCreated(batch)` where `batch` carries the ordered
   jobs and the optional directory handle.)
3. **Home page tracks the batch:** stores an in-memory map (a `useRef`, since
   handles are not serializable) of `jobId → { position, dirHandle }` for the
   active auto-save batch, then calls `reload()` as before.
4. **The existing 3s poll loop** (already on the home page) watches these jobs:
   - When a tracked job's status becomes `done`: fetch `GET /jobs/{id}/zip` with
     the auth bearer token (as `JobGallery.downloadZip` does today), resolve a
     free filename via `resolveZipName`, write it with `writeZipToDir`, then
     remove the job from the map.
   - When a tracked job's status becomes `failed`: remove it from the map with
     no file written (number skipped).
   - A job is processed once: it is removed from the map as soon as it is
     handled, so the next poll will not re-download it.

## Components (frontend)

New helpers (small, isolated, pure-ish — the only nontrivial logic):

- `resolveZipName(dirHandle, base): Promise<string>` — returns `${base}.zip`
  if free, else `${base} (2).zip`, `${base} (3).zip`, … Probes existence with
  `dirHandle.getFileHandle(name)` (no `create`), treating a thrown
  `NotFoundError` as "free". Lives in a new `frontend/lib/autosave.ts`.
- `writeZipToDir(dirHandle, name, blob): Promise<void>` — `getFileHandle(name,
  { create: true })` → `createWritable()` → `write(blob)` → `close()`. Also in
  `frontend/lib/autosave.ts`.
- A minimal TypeScript type for the directory handle (structural: the subset of
  `FileSystemDirectoryHandle` we use), to avoid depending on lib DOM typings
  that may not include it.

Modified files:

- `frontend/components/JobForm.tsx` — add the feature-detected checkbox; on
  submit, open the picker when checked; pass the batch (jobs + handle) up.
- `frontend/app/page.tsx` — accept the batch, keep the `useRef` map, and extend
  the existing poll loop to write finished jobs' zips. Manages per-job
  in-flight guarding so a slow write isn't started twice by overlapping polls.
- `frontend/lib/jobs.ts` — a helper to fetch a job's zip as a `Blob`
  (`fetchJobZip(jobId): Promise<Blob>`), reused from the gallery's inline logic
  if convenient (optional refactor, only if it stays clean).

## Error handling

- **Picker cancelled** (`AbortError`): abort submit, create nothing, inline
  message ("Folder selection cancelled — nothing was queued"), checkbox stays
  checked.
- **Unsupported browser:** checkbox not rendered; a note says auto-save needs
  Chrome or Edge. Everything else works unchanged.
- **Per-job fetch or write failure** (network, permission revoked, disk):
  caught per job; log + a small non-blocking inline error; **continue** with the
  remaining jobs in the batch. One bad zip never stops the others.
- **Reload mid-batch:** in-memory handle lost; remaining jobs won't auto-save;
  manual gallery download still available. (Documented limitation, not an error
  path to handle.)

## Testing

Consistent with the project's established frontend verification (no test runner
is present, and this machine runs Node 20, which cannot execute TypeScript
directly; every prior frontend feature was verified by build + lint + manual
walkthrough):

- **`resolveZipName` collision logic** — verified in the manual walkthrough
  rather than an automated test (Node 20 can't run a TS assertion script without
  adding a dependency, which was declined). The walkthrough explicitly exercises:
  pre-place `video_1.zip` → next save becomes `video_1 (2).zip`; place both
  `video_1.zip` and `video_1 (2).zip` → next becomes `video_1 (3).zip`. The
  helper is kept small and pure so the behavior is easy to reason about.
- **`next build`** passes (TypeScript type-check).
- **`eslint`** clean.
- **Manual walkthrough in Chrome:** check the box, submit 3 URLs, pick a folder,
  confirm `video_1.zip`/`video_2.zip`/`video_3.zip` land in it; confirm a failed
  job skips its number (e.g. `video_1.zip`, `video_3.zip`); confirm a
  pre-existing `video_1.zip` yields `video_1 (2).zip`; confirm the checkbox is
  absent in Firefox/Safari.

## Out of scope

- Persisting the folder choice across reloads/sessions (would need IndexedDB
  handle storage + re-permission prompts).
- Auto-download in Firefox/Safari or a plain-Downloads fallback (explicitly not
  chosen; Chrome/Edge folder picker only).
- Auto-saving jobs created outside the checked batch, or re-downloading past
  jobs into the folder.
- Any change to zip contents, the `/zip` endpoint, or numbering that is global
  across batches.
- A continuous cross-batch counter (numbering is per-batch by position).
