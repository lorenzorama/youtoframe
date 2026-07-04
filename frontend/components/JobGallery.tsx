"use client";

import { useEffect, useState } from "react";
import { listFrames, getTranscript, Frame, Transcript } from "@/lib/jobs";
import { getToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTime(seconds: number): string {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type Tab = "storyboard" | "transcript";

export default function JobGallery({ jobId }: { jobId: number }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("storyboard");
  const [transcript, setTranscript] = useState<Transcript | null>(null);

  useEffect(() => {
    listFrames(jobId).then(setFrames).catch(() => {});
    getTranscript(jobId).then(setTranscript).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    const token = getToken();
    let cancelled = false;
    const urls: Record<number, string> = {};

    Promise.all(
      frames.map(async (frame) => {
        const res = await fetch(`${API_URL}/frames/${frame.id}/image`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const blob = await res.blob();
        urls[frame.id] = URL.createObjectURL(blob);
      })
    ).then(() => {
      if (!cancelled) setImageUrls(urls);
    });

    return () => {
      cancelled = true;
      Object.values(urls).forEach(URL.revokeObjectURL);
    };
  }, [frames]);

  useEffect(() => {
    if (selectedIndex === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setSelectedIndex(null);
      else if (e.key === "ArrowLeft") setSelectedIndex((i) => (i !== null && i > 0 ? i - 1 : i));
      else if (e.key === "ArrowRight")
        setSelectedIndex((i) => (i !== null && i < frames.length - 1 ? i + 1 : i));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIndex, frames.length]);

  async function downloadZip() {
    const token = getToken();
    const res = await fetch(`${API_URL}/jobs/${jobId}/zip`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job_${jobId}_frames.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadFrame(frame: Frame) {
    const url = imageUrls[frame.id];
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${frame.timestamp_seconds}.jpg`;
    a.click();
  }

  // Open the frame whose timestamp is closest to a transcript cue's start.
  function openNearestFrame(startSeconds: number) {
    if (frames.length === 0) return;
    let best = 0;
    let bestDist = Infinity;
    frames.forEach((f, i) => {
      const d = Math.abs(f.timestamp_seconds - startSeconds);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setSelectedIndex(best);
  }

  const selectedFrame = selectedIndex !== null ? frames[selectedIndex] : null;
  const hasTranscript = !!transcript && transcript.cues.length > 0;

  function tabButton(value: Tab, label: string) {
    const active = tab === value;
    return (
      <button
        onClick={() => setTab(value)}
        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
          active ? "bg-ink text-white" : "text-muted hover:bg-chip"
        }`}
      >
        {label}
      </button>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2">
          {tabButton("storyboard", "Storyboard")}
          {tabButton("transcript", "Transcript")}
        </div>
        <button
          onClick={downloadZip}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
        >
          Download all as ZIP
        </button>
      </div>

      {tab === "storyboard" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {frames.map((frame, index) => (
            <div key={frame.id} className="flex flex-col gap-1.5">
              <button
                onClick={() => setSelectedIndex(index)}
                className="group relative overflow-hidden rounded-xl border border-line bg-chip"
              >
                {imageUrls[frame.id] ? (
                  <img
                    src={imageUrls[frame.id]}
                    alt={`Frame at ${frame.timestamp_seconds}s`}
                    className="aspect-video w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
                  />
                ) : (
                  <div className="aspect-video w-full animate-pulse bg-chip" />
                )}
                <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium text-white">
                  {formatTime(frame.timestamp_seconds)}
                </span>
              </button>
              {frame.caption && (
                <p className="line-clamp-2 text-xs leading-snug text-muted">{frame.caption}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "transcript" && (
        <div>
          {!hasTranscript ? (
            <div className="rounded-xl border border-dashed border-line px-4 py-10 text-center">
              <p className="text-sm text-muted">No transcript available for this video.</p>
            </div>
          ) : (
            <div>
              {transcript!.source === "whisper" && (
                <p className="mb-2 text-xs text-muted">Auto-transcribed</p>
              )}
              <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
                {transcript!.cues.map((cue, i) => (
                  <li key={i}>
                    <button
                      onClick={() => openNearestFrame(cue.start_seconds)}
                      className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface"
                    >
                      <span className="mt-0.5 shrink-0 font-mono text-xs text-muted">
                        {formatTime(cue.start_seconds)}
                      </span>
                      <span className="text-sm text-ink">{cue.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {selectedFrame && selectedIndex !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
          onClick={() => setSelectedIndex(null)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedIndex(null);
            }}
            className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-2xl leading-none text-white transition-colors hover:bg-white/20"
            aria-label="Close"
          >
            &times;
          </button>

          {selectedIndex > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex - 1);
              }}
              className="absolute left-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Previous frame"
            >
              &#8249;
            </button>
          )}

          <div className="flex max-w-[85vw] flex-col items-center gap-4" onClick={(e) => e.stopPropagation()}>
            <img
              src={imageUrls[selectedFrame.id]}
              alt={`Frame at ${selectedFrame.timestamp_seconds}s`}
              className="max-h-[70vh] max-w-full rounded-lg"
            />
            {selectedFrame.caption && (
              <p className="max-w-2xl text-center text-sm text-white/90">{selectedFrame.caption}</p>
            )}
            <div className="flex items-center gap-4">
              <span className="text-sm text-white/70">
                {formatTime(selectedFrame.timestamp_seconds)} · {selectedFrame.timestamp_seconds}s
              </span>
              <button
                onClick={() => downloadFrame(selectedFrame)}
                className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
              >
                Download
              </button>
            </div>
          </div>

          {selectedIndex < frames.length - 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIndex(selectedIndex + 1);
              }}
              className="absolute right-4 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-3xl leading-none text-white transition-colors hover:bg-white/20"
              aria-label="Next frame"
            >
              &#8250;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
