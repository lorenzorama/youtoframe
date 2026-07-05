# Auto-Download Outputs to a Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user opt in (a checkbox under the URL textarea) to have each job's result zip written automatically into a folder they choose, named `video_1.zip`, `video_2.zip`, … by the link's position in the submitted batch.

**Architecture:** Frontend-only. Reuses the existing `GET /jobs/{id}/zip` endpoint; the `video_N` name is applied client-side at write time via the browser File System Access API. On submit, `JobForm` opens a folder picker (Chrome/Edge) and hands the created jobs + the chosen directory handle to the home page, which — in its existing 3-second poll loop — writes each job's zip into the folder as the job reaches `done`.

**Tech Stack:** Next.js (App Router, client components) + React + TypeScript, File System Access API (`window.showDirectoryPicker`).

## Global Constraints

- **Frontend-only.** No backend, database, Celery, or migration changes. Do not touch `backend/`.
- **Read `frontend/AGENTS.md` first.** This project uses a customized Next.js; consult `node_modules/next/dist/docs/` before writing code and heed deprecation notices.
- **Chrome/Edge only** via the File System Access API. The checkbox is feature-detected with `isAutoSaveSupported()`; where unsupported, render a short note instead — never a non-working checkbox.
- **Numbering is per-batch by link position:** the Nth pasted link → `video_N.zip` (`video_${index + 1}` from the ordered `createJobs` result), regardless of finish order. A **failed** job produces no file — its number is skipped.
- **No overwrite:** if `video_1.zip` exists in the folder, write `video_1 (2).zip`; if that exists too, `video_1 (3).zip`, and so on.
- **The tab must stay open** while a batch runs; the granted directory handle lives only in memory (a `useRef`). A page reload loses it — not-yet-finished jobs then won't auto-save (still downloadable manually from the gallery). This is an accepted limitation, not an error path to handle.
- **Verification (Node 20, no test runner):** `npm run build` (TypeScript type-check) + `npx eslint` clean + a manual walkthrough in Chrome. There is no automated unit test; keep helpers small and pure.

---

### Task 1: Auto-save helper module (`lib/autosave.ts`)

**Files:**
- Create: `frontend/lib/autosave.ts`

**Interfaces:**
- Consumes: `Job` from `frontend/lib/jobs.ts` (existing: `{ id: number; status: "waiting" | "pending" | "downloading" | "extracting" | "transcribing" | "done" | "failed"; ... }`).
- Produces:
  - `interface DirectoryHandle { getFileHandle(name: string, options?: { create?: boolean }): Promise<FileHandle> }`
  - `interface FileHandle { createWritable(): Promise<WritableFileStream> }`
  - `interface WritableFileStream { write(data: Blob): Promise<void>; close(): Promise<void> }`
  - `interface AutoSaveBatch { jobs: Job[]; dirHandle: DirectoryHandle | null }`
  - `isAutoSaveSupported(): boolean`
  - `pickDirectory(): Promise<DirectoryHandle | null>` (null when the user dismisses the dialog)
  - `resolveZipName(dir: DirectoryHandle, base: string): Promise<string>`
  - `writeZipToDir(dir: DirectoryHandle, name: string, blob: Blob): Promise<void>`

- [ ] **Step 1: Create the module**

Create `frontend/lib/autosave.ts` with exactly this content:

```ts
import { Job } from "@/lib/jobs";

// Minimal structural subset of the File System Access API we use. The project's
// TS lib config does not include these types, so we declare just what we call.
export interface WritableFileStream {
  write(data: Blob): Promise<void>;
  close(): Promise<void>;
}

export interface FileHandle {
  createWritable(): Promise<WritableFileStream>;
}

export interface DirectoryHandle {
  getFileHandle(name: string, options?: { create?: boolean }): Promise<FileHandle>;
}

declare global {
  interface Window {
    showDirectoryPicker?: (options?: { mode?: "read" | "readwrite" }) => Promise<DirectoryHandle>;
  }
}

// A batch of jobs created together, plus the folder chosen for auto-saving them
// (null when auto-save was off or unsupported).
export interface AutoSaveBatch {
  jobs: Job[];
  dirHandle: DirectoryHandle | null;
}

// True only where the File System Access API exists (Chrome/Edge).
export function isAutoSaveSupported(): boolean {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
}

// Opens the native folder chooser. Returns the granted handle, or null if the
// user dismissed the dialog (AbortError). Any other error propagates.
export async function pickDirectory(): Promise<DirectoryHandle | null> {
  if (!window.showDirectoryPicker) return null;
  try {
    return await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err && (err as { name?: string }).name === "AbortError") return null;
    throw err;
  }
}

async function fileExists(dir: DirectoryHandle, name: string): Promise<boolean> {
  try {
    await dir.getFileHandle(name);
    return true;
  } catch (err) {
    if (err && (err as { name?: string }).name === "NotFoundError") return false;
    throw err;
  }
}

// Resolves a non-colliding "<base>.zip" name in dir: "<base>.zip", else
// "<base> (2).zip", "<base> (3).zip", ... Probes with getFileHandle (no create),
// treating NotFoundError as "free".
export async function resolveZipName(dir: DirectoryHandle, base: string): Promise<string> {
  for (let i = 1; ; i++) {
    const name = i === 1 ? `${base}.zip` : `${base} (${i}).zip`;
    if (!(await fileExists(dir, name))) return name;
  }
}

// Writes blob into dir under name. The caller passes a name already resolved to
// be collision-free (see resolveZipName).
export async function writeZipToDir(dir: DirectoryHandle, name: string, blob: Blob): Promise<void> {
  const handle = await dir.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(blob);
  await writable.close();
}
```

- [ ] **Step 2: Type-check with the build**

Run: `cd frontend && npm run build`
Expected: build succeeds (compiles `lib/autosave.ts` with no type errors).

- [ ] **Step 3: Lint**

Run: `cd frontend && npx eslint lib/autosave.ts`
Expected: no errors, no warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/autosave.ts
git commit -m "feat: add File System Access auto-save helpers"
```

---

### Task 2: Folder checkbox + picker in the submit form (`JobForm.tsx`)

**Files:**
- Modify: `frontend/components/JobForm.tsx`

**Interfaces:**
- Consumes: `createJobs` from `@/lib/jobs`; `isAutoSaveSupported`, `pickDirectory`, `AutoSaveBatch` from `@/lib/autosave`.
- Produces: `JobForm`'s prop becomes `onCreated: (batch: AutoSaveBatch) => void`. On a successful submit, `JobForm` calls `onCreated({ jobs, dirHandle })` where `jobs` is the ordered `createJobs` result and `dirHandle` is the chosen folder (or null). (A no-arg `() => void` callback remains assignable to this prop, so `app/page.tsx` still compiles until Task 3 wires it.)

**Context:** The current `JobForm` takes `onCreated: () => void`, has a URL textarea, interval/timestamps inputs, and a required rights-acknowledgment checkbox. The whole file is replaced below.

- [ ] **Step 1: Replace the component**

Replace the entire contents of `frontend/components/JobForm.tsx` with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { createJobs } from "@/lib/jobs";
import { isAutoSaveSupported, pickDirectory, AutoSaveBatch } from "@/lib/autosave";

const fieldClass =
  "w-full rounded-lg border border-line px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-ink";

export default function JobForm({ onCreated }: { onCreated: (batch: AutoSaveBatch) => void }) {
  const [urls, setUrls] = useState("");
  const [interval, setInterval_] = useState("5");
  const [timestamps, setTimestamps] = useState("");
  const [autoSave, setAutoSave] = useState(false);
  const [supported, setSupported] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Feature-detect on the client only (avoids SSR/CSR hydration mismatch).
  useEffect(() => {
    setSupported(isAutoSaveSupported());
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const urlList = urls
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const manual = timestamps
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map(Number)
        .filter((n) => !Number.isNaN(n));

      // If auto-save is on, obtain the folder from the submit gesture BEFORE
      // creating jobs. A cancelled picker aborts the whole submit.
      let dirHandle = null;
      if (autoSave && supported) {
        dirHandle = await pickDirectory();
        if (!dirHandle) {
          setError("Folder selection cancelled — nothing was queued.");
          return;
        }
      }

      const jobs = await createJobs({
        youtube_urls: urlList,
        interval_seconds: interval ? Number(interval) : undefined,
        manual_timestamps: manual.length ? manual : undefined,
      });
      setUrls("");
      onCreated({ jobs, dirHandle });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create jobs");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-muted">YouTube URLs (one per line)</label>
        <textarea
          placeholder={"https://youtube.com/watch?v=…\nhttps://youtube.com/watch?v=…"}
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={4}
          className={`${fieldClass} resize-y`}
          required
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Interval (seconds)</label>
          <input placeholder="5" value={interval} onChange={(e) => setInterval_(e.target.value)} className={fieldClass} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Manual timestamps</label>
          <input
            placeholder="e.g. 12.5, 30, 90"
            value={timestamps}
            onChange={(e) => setTimestamps(e.target.value)}
            className={fieldClass}
          />
        </div>
      </div>

      {supported ? (
        <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
          <input
            type="checkbox"
            checked={autoSave}
            onChange={(e) => setAutoSave(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-ink"
          />
          <span>
            Auto-save each result to a folder — you&apos;ll pick the folder when you submit. Keep
            this tab open while the jobs run.
          </span>
        </label>
      ) : (
        <p className="text-xs text-muted">
          Tip: auto-saving results straight to a folder is available in Chrome or Edge.
        </p>
      )}

      <label className="flex items-start gap-2.5 text-xs leading-relaxed text-muted">
        <input type="checkbox" required className="mt-0.5 h-4 w-4 shrink-0 accent-ink" />
        <span>
          I confirm I own these videos or am otherwise authorized to extract frames from them, and
          that doing so complies with the source platform&apos;s Terms of Service and applicable
          copyright law.
        </span>
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
      >
        {submitting ? "Queuing…" : "Queue extraction"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Type-check with the build**

Run: `cd frontend && npm run build`
Expected: build succeeds. (`app/page.tsx` still passes its no-arg `reload` as `onCreated` — assignable — so it compiles.)

- [ ] **Step 3: Lint**

Run: `cd frontend && npx eslint components/JobForm.tsx`
Expected: no errors, no warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/JobForm.tsx
git commit -m "feat: folder-picker auto-save checkbox in job form"
```

---

### Task 3: Write finished jobs' zips from the home poll loop (`page.tsx` + `jobs.ts`)

**Files:**
- Modify: `frontend/lib/jobs.ts` (add `fetchJobZip`)
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `fetchJobZip` (new, below); `resolveZipName`, `writeZipToDir`, `DirectoryHandle`, `AutoSaveBatch` from `@/lib/autosave`; existing `listJobs`, `cancelJob`, `Job`.
- Produces: nothing consumed by later tasks (final task).

**Context:** `app/page.tsx` renders `<JobForm onCreated={reload} />`, keeps a `jobs` list, and already polls `listJobs()` every 3 seconds via `setInterval(reload, 3000)`. This task adds an in-memory map of the active auto-save batch and writes each job's zip when it reaches `done`.

- [ ] **Step 1: Add `fetchJobZip` to `lib/jobs.ts`**

In `frontend/lib/jobs.ts`, add this function immediately after the existing `listJobs` function (it uses the already-imported `apiFetch`):

```ts
export async function fetchJobZip(jobId: number): Promise<Blob> {
  const res = await apiFetch(`/jobs/${jobId}/zip`);
  if (!res.ok) throw new Error("Failed to fetch zip");
  return res.blob();
}
```

- [ ] **Step 2: Replace `app/page.tsx`**

Replace the entire contents of `frontend/app/page.tsx` with:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import JobForm from "@/components/JobForm";
import StatusBadge from "@/components/StatusBadge";
import { listJobs, cancelJob, fetchJobZip, Job } from "@/lib/jobs";
import { resolveZipName, writeZipToDir, DirectoryHandle, AutoSaveBatch } from "@/lib/autosave";
import { getToken } from "@/lib/api";

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoSaveError, setAutoSaveError] = useState<string | null>(null);
  const router = useRouter();

  // jobId -> where/which name to save when it finishes. In a ref because handles
  // are not serializable and this must survive re-renders without triggering them.
  const pendingSaves = useRef<Map<number, { position: number; dir: DirectoryHandle }>>(new Map());
  // Jobs whose write is in flight, so overlapping polls don't start it twice.
  const savingIds = useRef<Set<number>>(new Set());

  const processAutoSaves = useCallback(async (current: Job[]) => {
    for (const job of current) {
      const entry = pendingSaves.current.get(job.id);
      if (!entry) continue;
      if (job.status === "failed") {
        pendingSaves.current.delete(job.id); // no file; its number is skipped
        continue;
      }
      if (job.status !== "done") continue;
      if (savingIds.current.has(job.id)) continue;
      savingIds.current.add(job.id);
      try {
        const blob = await fetchJobZip(job.id);
        const name = await resolveZipName(entry.dir, `video_${entry.position}`);
        await writeZipToDir(entry.dir, name, blob);
        pendingSaves.current.delete(job.id);
      } catch (err) {
        // Give up on this one, keep saving the rest of the batch.
        pendingSaves.current.delete(job.id);
        setAutoSaveError(
          `Couldn't save video_${entry.position}.zip — ${err instanceof Error ? err.message : "write failed"}`
        );
      } finally {
        savingIds.current.delete(job.id);
      }
    }
  }, []);

  const reload = useCallback(() => {
    listJobs()
      .then((current) => {
        setJobs(current);
        void processAutoSaves(current);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [processAutoSaves]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    reload();
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [router, reload]);

  function handleCreated(batch: AutoSaveBatch) {
    const dir = batch.dirHandle;
    if (dir) {
      batch.jobs.forEach((job, i) => {
        pendingSaves.current.set(job.id, { position: i + 1, dir });
      });
    }
    reload();
  }

  async function handleCancel(jobId: number) {
    try {
      await cancelJob(jobId);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      pendingSaves.current.delete(jobId);
    } catch {
      // ignore; next poll will reconcile
    }
  }

  return (
    <>
      <Nav />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Extract frames from YouTube videos
          </h1>
          <p className="mt-1 text-sm text-muted">
            Paste one or more links (one per line). They&apos;re queued and processed one at a time.
          </p>
        </header>

        <section className="rounded-2xl border border-line bg-white p-6">
          <JobForm onCreated={handleCreated} />
        </section>

        {autoSaveError && (
          <p className="mt-4 text-sm text-red-600">{autoSaveError}</p>
        )}

        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Your jobs</h2>

          {loading && (
            <div className="flex flex-col gap-2">
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
              <div className="h-14 animate-pulse rounded-xl bg-chip" />
            </div>
          )}

          {!loading && jobs.length === 0 && (
            <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center">
              <p className="text-sm text-muted">No jobs yet — paste a YouTube URL above to get started.</p>
            </div>
          )}

          {!loading && jobs.length > 0 && (
            <ul className="flex flex-col gap-2">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white px-4 py-3"
                >
                  <Link href={`/jobs/${job.id}`} className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{job.youtube_url}</p>
                    <p className="mt-0.5 text-xs text-muted">Job #{job.id}</p>
                  </Link>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge status={job.status} />
                    {job.status === "waiting" && (
                      <button
                        onClick={() => handleCancel(job.id)}
                        className="rounded-full border border-line px-3 py-1 text-xs font-medium text-muted transition-colors hover:bg-chip"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}
```

- [ ] **Step 3: Type-check with the build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 4: Lint**

Run: `cd frontend && npx eslint app/page.tsx lib/jobs.ts`
Expected: no errors, no warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx frontend/lib/jobs.ts
git commit -m "feat: auto-save finished job zips into the chosen folder"
```

---

### Task 4: Manual walkthrough in Chrome

**Files:** none (verification only).

**Context:** Real YouTube downloads fail from this environment's datacenter IP (bot detection), so jobs typically end in `failed`. To exercise the `done` path, you may need a job that actually produces frames. Two options: (a) if any previously-completed `done` job with frames exists for the test user, reuse it; or (b) inject a `done` job with frames directly in the DB / reuse an existing one, then trigger the save path. The collision and failure behaviors below do not depend on a real download.

- [ ] **Step 1: Start the stack and open the app in Chrome**

Run: `docker compose up -d` (from repo root), then open `http://localhost:3000` in Chrome or Edge. Log in (or sign up) as a test user.
Expected: the home page shows the job form with the **"Auto-save each result to a folder"** checkbox visible (because Chrome supports the API).

- [ ] **Step 2: Verify the unsupported-browser note**

Open the same URL in Firefox or Safari.
Expected: no checkbox; instead the note "auto-saving results straight to a folder is available in Chrome or Edge."

- [ ] **Step 3: Verify cancel aborts the submit**

Back in Chrome: paste one URL, check the auto-save box, click **Queue extraction**, and **dismiss** the folder picker.
Expected: inline message "Folder selection cancelled — nothing was queued."; no new job appears in the list.

- [ ] **Step 4: Verify a batch auto-saves with correct numbering**

Paste 3 URLs, check the box, submit, and pick an empty folder. Let the batch run (keep the tab open). For any job that reaches `done`, confirm a `video_<position>.zip` appears in the chosen folder, where position matches the link's line order. For a job that ends `failed`, confirm no file is written for it and its number is skipped (e.g. `video_1.zip`, `video_3.zip` when link 2 failed).
Expected: files land in the folder named by position; failed jobs leave a gap; the page shows a per-job error only if a write/fetch actually failed.

- [ ] **Step 5: Verify no-overwrite collision naming**

Pre-place a file named `video_1.zip` in the target folder. Submit a batch of 1 (auto-save on) whose job reaches `done`, choosing that same folder.
Expected: the new file is written as `video_1 (2).zip`; the pre-existing `video_1.zip` is untouched. Repeat with both `video_1.zip` and `video_1 (2).zip` present → next is `video_1 (3).zip`.

- [ ] **Step 6: Confirm manual gallery download still works**

Open a finished job's gallery and click **Download ZIP**.
Expected: `job_<id>_frames.zip` downloads to the browser's default Downloads folder as before (unchanged behavior).

- [ ] **Step 7: Record the walkthrough result**

No commit. Note pass/fail for each step in the progress ledger.
