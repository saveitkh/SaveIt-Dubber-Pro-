import { getToken } from "./api";

export interface JobEvent {
  stage: string;
  status: "running" | "done" | "error";
  progress: number;
  message?: string | null;
  error?: string | null;
}

/**
 * EventSource can't send an Authorization header, so the token rides in the
 * query string. SSE connections for jobs only ever carry progress text, never
 * secrets, so this is an acceptable trade-off for M1.
 */
export function subscribeToJob(jobId: string, onEvent: (event: JobEvent) => void): () => void {
  const token = getToken();
  const url = `/api/jobs/${jobId}/events${token ? `?access_token=${encodeURIComponent(token)}` : ""}`;
  const source = new EventSource(url, { withCredentials: true });

  source.addEventListener("progress", (ev) => {
    const data = JSON.parse((ev as MessageEvent).data) as JobEvent;
    onEvent(data);
    if (data.status === "done" || data.status === "error") {
      source.close();
    }
  });

  source.onerror = () => {
    // Browser EventSource auto-retries; nothing to do here for M1.
  };

  return () => source.close();
}
