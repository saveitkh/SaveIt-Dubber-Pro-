import { ArrowLeft, Check, Pause, Play, Trash2, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../lib/api";
import type { ProjectDetail } from "../lib/types";

const KIND_LABELS: Record<string, string> = {
  overlap: "សំឡេងត្រួតគ្នា",
  unsure: "មិនប្រាកដអ្នកនិយាយ",
  missed: "បាត់បន្ទាត់",
  slot_overflow: "សំឡេងវែងពេក",
  low_clone_quality: "គំរូសំឡេងមិនល្អ",
  tts_failed: "បង្កើតសំឡេងបរាជ័យ",
};

export function ReviewQueue() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const originalAudioRef = useRef<HTMLAudioElement>(null);
  const khmerAudioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState<{ itemId: string; which: "original" | "khmer" } | null>(null);

  const load = () => {
    if (!projectId) return;
    api.get<ProjectDetail>(`/api/projects/${projectId}`).then(setDetail);
  };

  useEffect(load, [projectId]);

  if (!detail) return <div className="p-6 text-slate-400">កំពុងផ្ទុក…</div>;

  const { reviewItems, lines, characters, project } = detail;
  const lineById = new Map(lines.map((l) => [l.id, l]));
  const charById = new Map(characters.map((c) => [c.id, c]));

  const playOriginal = (itemId: string, startSec: number, endSec: number) => {
    const el = originalAudioRef.current;
    if (!el) return;
    el.currentTime = startSec;
    el.play();
    setPlaying({ itemId, which: "original" });
    const onTime = () => {
      if (el.currentTime >= endSec) {
        el.pause();
        setPlaying(null);
        el.removeEventListener("timeupdate", onTime);
      }
    };
    el.addEventListener("timeupdate", onTime);
  };

  const playKhmer = (itemId: string, url: string) => {
    const el = khmerAudioRef.current;
    if (!el) return;
    el.src = url;
    el.play();
    setPlaying({ itemId, which: "khmer" });
    el.onended = () => setPlaying(null);
  };

  const resolve = async (itemId: string) => {
    setBusyId(itemId);
    try {
      await api.post(`/api/review-items/${itemId}/resolve`);
      load();
    } finally {
      setBusyId(null);
    }
  };

  const regenerate = async (lineId: string, itemId: string) => {
    setBusyId(itemId);
    try {
      await api.post(`/api/lines/${lineId}/regenerate`);
      load();
    } finally {
      setBusyId(null);
    }
  };

  const removeLine = async (lineId: string, itemId: string) => {
    setBusyId(itemId);
    try {
      await api.delete_(`/api/lines/${lineId}`);
      load();
    } finally {
      setBusyId(null);
    }
  };

  const changeCharacter = async (lineId: string, characterId: string, itemId: string) => {
    setBusyId(itemId);
    try {
      await api.patch(`/api/lines/${lineId}`, { characterId });
      await api.post(`/api/lines/${lineId}/regenerate`);
      load();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <audio ref={originalAudioRef} src={project.originalAudioUrl ?? undefined} />
      <audio ref={khmerAudioRef} />

      <div className="mb-4 flex items-center gap-3">
        <button onClick={() => navigate(`/projects/${projectId}`)} className="text-slate-400">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-lg font-semibold text-slate-100">ត្រូវការពិនិត្យ ({reviewItems.length})</h1>
      </div>

      {reviewItems.length === 0 ? (
        <p className="text-sm text-slate-500">គ្មានអ្វីត្រូវពិនិត្យទេ — អ្វីៗគ្រប់យ៉ាងរួចរាល់!</p>
      ) : (
        <div className="space-y-3">
          {reviewItems.map((item) => {
            const line = item.lineId ? lineById.get(item.lineId) : undefined;
            const character = line?.characterId ? charById.get(line.characterId) : undefined;
            const isBusy = busyId === item.id;
            const reason =
              (item.payload?.reason as string | undefined) ?? (item.payload?.error as string | undefined);

            return (
              <div key={item.id} className="rounded-2xl bg-slate-900 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="rounded-full bg-amber-500/20 px-2.5 py-1 text-xs font-medium text-amber-300">
                    {KIND_LABELS[item.kind] ?? item.kind}
                  </span>
                  {character && (
                    <span className="flex items-center gap-1.5 text-xs text-slate-400">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: character.color }} />
                      {character.name}
                    </span>
                  )}
                </div>

                {line ? (
                  <>
                    <p className="mb-1 text-sm text-slate-300">{line.sourceText || "—"}</p>
                    <p className="mb-3 text-sm text-slate-100">{line.khmerText || "—"}</p>

                    <div className="mb-3 flex gap-2">
                      <button
                        onClick={() => playOriginal(item.id, line.startSec, line.endSec)}
                        className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
                      >
                        {playing?.itemId === item.id && playing.which === "original" ? (
                          <Pause size={14} />
                        ) : (
                          <Play size={14} />
                        )}
                        ដើម
                      </button>
                      {line.audioUrl && (
                        <button
                          onClick={() => playKhmer(item.id, line.audioUrl!)}
                          className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
                        >
                          {playing?.itemId === item.id && playing.which === "khmer" ? (
                            <Pause size={14} />
                          ) : (
                            <Play size={14} />
                          )}
                          ខ្មែរ
                        </button>
                      )}
                    </div>

                    {item.kind === "unsure" && characters.length > 1 && (
                      <div className="mb-3 flex flex-wrap gap-1.5">
                        <span className="flex items-center gap-1 text-xs text-slate-500">
                          <Users size={12} /> ប្តូរទៅ៖
                        </span>
                        {characters
                          .filter((c) => c.id !== line.characterId)
                          .map((c) => (
                            <button
                              key={c.id}
                              disabled={isBusy}
                              onClick={() => changeCharacter(line.id, c.id, item.id)}
                              className="rounded-full px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                              style={{ backgroundColor: c.color }}
                            >
                              {c.name}
                            </button>
                          ))}
                      </div>
                    )}

                    <div className="flex gap-2">
                      <button
                        disabled={isBusy}
                        onClick={() => resolve(item.id)}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-600/20 px-3 py-2 text-xs font-medium text-emerald-300 disabled:opacity-50"
                      >
                        <Check size={14} /> ត្រឹមត្រូវ
                      </button>
                      <button
                        disabled={isBusy}
                        onClick={() => regenerate(line.id, item.id)}
                        className="rounded-lg bg-brand-600/20 px-3 py-2 text-xs font-medium text-brand-300 disabled:opacity-50"
                      >
                        បង្កើតឡើងវិញ
                      </button>
                      <button
                        disabled={isBusy}
                        onClick={() => removeLine(line.id, item.id)}
                        className="flex items-center gap-1.5 rounded-lg bg-red-600/20 px-3 py-2 text-xs font-medium text-red-300 disabled:opacity-50"
                      >
                        <Trash2 size={14} /> លុប
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="mb-3 text-sm text-slate-400">{reason ?? "—"}</p>
                    <button
                      disabled={isBusy}
                      onClick={() => resolve(item.id)}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-600/20 px-3 py-2 text-xs font-medium text-emerald-300 disabled:opacity-50"
                    >
                      <Check size={14} /> បានដឹង
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
