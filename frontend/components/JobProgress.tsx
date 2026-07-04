"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

interface StreamEvent {
  status: string;
  frames_done: number;
  frames_total: number;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function JobProgress({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [event, setEvent] = useState<StreamEvent | null>(null);

  useEffect(() => {
    const token = getToken();
    const source = new EventSource(`${API_URL}/jobs/${jobId}/stream?token=${token}`);

    source.onmessage = (e) => {
      const data: StreamEvent = JSON.parse(e.data);
      setEvent(data);
      if (data.status === "done") {
        source.close();
        onDone();
      } else if (data.status === "failed") {
        source.close();
      }
    };

    return () => source.close();
  }, [jobId, onDone]);

  if (!event) {
    return <p className="text-sm text-gray-500">Connecting...</p>;
  }

  if (event.status === "failed") {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        <p className="font-semibold mb-1">Failed</p>
        <p>{event.error}</p>
      </div>
    );
  }

  const percent =
    event.frames_total > 0
      ? Math.min(100, Math.round((event.frames_done / event.frames_total) * 100))
      : 0;

  return (
    <div>
      <div className="flex justify-between items-center mb-2 text-sm text-gray-700">
        <span className="capitalize">{event.status}&hellip;</span>
        <span className="text-gray-500">
          {event.frames_done} / {event.frames_total}
        </span>
      </div>
      <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className="bg-indigo-600 h-full rounded-full transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
