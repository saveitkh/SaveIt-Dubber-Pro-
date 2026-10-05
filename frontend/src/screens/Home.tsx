import { UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { StatusChip } from "../components/StatusChip";
import { useT } from "../i18n";
import { api, type ProjectSummary } from "../lib/api";

export function Home() {
  const t = useT();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [link, setLink] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = () => {
    api.get<{ projects: ProjectSummary[] }>("/api/projects").then((res) => setProjects(res.projects));
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const startUpload = async (file: File | null, url: string) => {
    if (!file && !url) return;
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      if (url) form.append("url", url);
      form.append("name", file?.name ?? url);
      const res = await api.postForm<{ project: ProjectSummary }>("/api/projects", form);
      navigate(`/projects/${res.project.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <button
        type="button"
        onClick={() => fileInput.current?.click()}
        disabled={uploading}
        className="flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-900 px-6 py-10 text-center active:border-brand-500 disabled:opacity-60"
      >
        <UploadCloud size={36} className="text-brand-400" />
        <span className="text-lg font-medium text-slate-100">{t.home.uploadTitle}</span>
        <span className="text-sm text-slate-400">{uploading ? t.common.loading : t.home.uploadHint}</span>
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="video/*,audio/*"
        className="hidden"
        onChange={(e) => startUpload(e.target.files?.[0] ?? null, "")}
      />

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          startUpload(null, link);
        }}
      >
        <input
          className="flex-1 rounded-xl bg-slate-900 px-4 py-3 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
          placeholder={t.home.linkPlaceholder}
          value={link}
          onChange={(e) => setLink(e.target.value)}
        />
        <button
          type="submit"
          disabled={!link || uploading}
          className="rounded-xl bg-brand-600 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"
        >
          OK
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {t.home.recent}
      </h2>
      {projects.length === 0 ? (
        <p className="text-sm text-slate-500">{t.home.empty}</p>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => navigate(`/projects/${p.id}`)}
                className="flex w-full items-center justify-between rounded-xl bg-slate-900 px-4 py-3 text-left active:bg-slate-800"
              >
                <span className="truncate text-sm font-medium text-slate-100">{p.name}</span>
                <StatusChip status={p.status} progress={p.latestJob?.progress} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
