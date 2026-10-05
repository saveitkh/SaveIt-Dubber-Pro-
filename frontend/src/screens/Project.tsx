import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { StatusChip } from "../components/StatusChip";
import { t } from "../i18n";
import { api } from "../lib/api";
import { subscribeToJob, type JobEvent } from "../lib/sse";

interface ProjectDetail {
  project: {
    id: string;
    name: string;
    status: string;
    outputVideoPath: string | null;
  };
  lines: Array<{ id: string; startSec: number; endSec: number; khmerText: string; flags: string[] }>;
  characters: Array<{ id: string; name: string; color: string }>;
  reviewItems: Array<{ id: string; kind: string }>;
  jobs: Array<{ id: string; stage: string; status: string; progress: number; message: string | null }>;
}

const STAGE_LABELS: Record<string, string> = {
  prepare: "រៀបចំ",
  separate: "ញែកសំឡេង",
  transcribe: "សម្រាយ+បកប្រែ",
  diarize: "កំណត់អ្នកនិយាយ",
  cast: "ជ្រើសសំឡេង",
  speak: "និយាយខ្មែរ",
  mix: "លាយសំឡេង",
  export: "នាំចេញ",
};
const STAGE_ORDER = Object.keys(STAGE_LABELS);

export function ProjectScreen() {
  const { projectId } = useParams<{ projectId: string }>();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [live, setLive] = useState<JobEvent | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.get<ProjectDetail>(`/api/projects/${projectId}`).then(setDetail);
  }, [projectId]);

  useEffect(() => {
    const jobId = detail?.jobs[0]?.id;
    if (!jobId || detail?.jobs[0]?.status === "done") return;
    return subscribeToJob(jobId, (event) => {
      setLive(event);
      if (event.status === "done" && projectId) {
        api.get<ProjectDetail>(`/api/projects/${projectId}`).then(setDetail);
      }
    });
  }, [detail?.jobs, projectId]);

  if (!detail) return <div className="p-6 text-slate-400">{t.common.loading}</div>;

  const { project, characters, reviewItems } = detail;
  const stageIdx = live ? STAGE_ORDER.indexOf(live.stage) : -1;

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="truncate text-lg font-semibold text-slate-100">{project.name}</h1>
        <StatusChip status={project.status} progress={live?.progress} />
      </div>

      {live && live.status !== "done" && (
        <div className="mb-6 rounded-2xl bg-slate-900 p-4">
          <ol className="flex flex-wrap gap-2 text-xs">
            {STAGE_ORDER.map((stage, idx) => (
              <li
                key={stage}
                className={`rounded-full px-3 py-1 ${
                  idx < stageIdx
                    ? "bg-emerald-500/20 text-emerald-300"
                    : idx === stageIdx
                      ? "bg-brand-600 text-white"
                      : "bg-slate-800 text-slate-500"
                }`}
              >
                {STAGE_LABELS[stage]}
              </li>
            ))}
          </ol>
          {live.message && <p className="mt-3 text-sm text-slate-400">{live.message}</p>}
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div className="h-full bg-brand-500 transition-all" style={{ width: `${live.progress}%` }} />
          </div>
        </div>
      )}

      {live?.status === "error" && (
        <div className="mb-6 rounded-xl bg-red-500/10 p-4 text-sm text-red-300">{live.error}</div>
      )}

      {reviewItems.length > 0 && (
        <div className="mb-6 rounded-xl bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-300">
          {t.project.needsReview}: {reviewItems.length}
        </div>
      )}

      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {t.project.characters}
      </h2>
      <div className="mb-6 flex gap-3 overflow-x-auto pb-2">
        {characters.length === 0 ? (
          <p className="text-sm text-slate-500">—</p>
        ) : (
          characters.map((c) => (
            <div
              key={c.id}
              className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-full text-xs font-medium text-white"
              style={{ backgroundColor: c.color }}
            >
              {c.name || "?"}
            </div>
          ))
        )}
      </div>

      <div className="sticky bottom-20 flex gap-2 md:bottom-4">
        <button className="flex-1 rounded-xl bg-brand-600 py-3 text-sm font-medium text-white">
          {t.project.playDub}
        </button>
        <button className="rounded-xl bg-slate-800 px-4 py-3 text-sm font-medium text-slate-200">
          {t.project.regenerate}
        </button>
        <button className="rounded-xl bg-slate-800 px-4 py-3 text-sm font-medium text-slate-200">
          {t.project.export}
        </button>
      </div>
    </div>
  );
}
