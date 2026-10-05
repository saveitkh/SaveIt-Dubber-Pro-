import { FolderClosed, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { StatusChip } from "../components/StatusChip";
import { useT } from "../i18n";
import { api, type ProjectSummary } from "../lib/api";

function formatDuration(sec: number | null): string {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function Projects() {
  const t = useT();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.get<{ projects: ProjectSummary[] }>("/api/projects").then((res) => setProjects(res.projects));
  }, []);

  const filtered = projects.filter((p) => p.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-slate-100">{t.nav.projects}</h1>

      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          className="w-full rounded-xl bg-slate-900 py-3 pl-9 pr-4 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
          placeholder={t.common.search}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-slate-900 px-6 py-10 text-center">
          <FolderClosed size={28} className="text-slate-600" />
          <p className="text-sm text-slate-500">{t.home.empty}</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {filtered.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => navigate(`/projects/${p.id}`)}
                className="flex w-full items-center justify-between rounded-xl bg-slate-900 px-4 py-3.5 text-left transition active:bg-slate-800"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100">{p.name}</p>
                  <p className="mt-0.5 text-xs text-slate-500">{formatDuration(p.durationSec)}</p>
                </div>
                <StatusChip status={p.status} progress={p.latestJob?.progress} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
