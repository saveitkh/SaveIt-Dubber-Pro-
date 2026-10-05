import { Mic2, Pause, Play, Save, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useT } from "../i18n";
import { api } from "../lib/api";
import type { VoiceGroup, VoiceItem } from "../lib/types";

const QUALITY_STYLES: Record<string, string> = {
  best: "bg-emerald-500/20 text-emerald-300",
  ok: "bg-amber-500/20 text-amber-300",
  too_short: "bg-red-500/20 text-red-300",
};

export function Voices() {
  const t = useT();
  const fileInput = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [groups, setGroups] = useState<VoiceGroup[]>([]);
  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [names, setNames] = useState<Record<number, string>>({});

  const loadVoices = () => {
    api.get<{ voices: VoiceItem[] }>("/api/voices").then((res) => setVoices(res.voices));
  };

  useEffect(() => {
    loadVoices();
  }, []);

  const handleUpload = async (file: File | null) => {
    if (!file) return;
    setProcessing(true);
    setError(null);
    setGroups([]);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.postForm<{ groups: VoiceGroup[]; workDir: string }>("/api/voices/clip", form);
      setGroups(res.groups);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProcessing(false);
    }
  };

  const togglePlay = (url: string) => {
    const el = audioRef.current;
    if (!el) return;
    if (playingUrl === url) {
      el.pause();
      setPlayingUrl(null);
    } else {
      el.src = url;
      el.play();
      setPlayingUrl(url);
      el.onended = () => setPlayingUrl(null);
    }
  };

  const saveVoice = async (group: VoiceGroup) => {
    const name = names[group.groupId]?.trim();
    if (!name || !group.previewPath) return;
    setSavingId(group.groupId);
    try {
      const form = new FormData();
      form.append("name", name);
      form.append("reference_path", group.previewPath);
      await api.postForm("/api/voices", form);
      setNames((prev) => ({ ...prev, [group.groupId]: "" }));
      loadVoices();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <audio ref={audioRef} />

      <h1 className="mb-4 text-lg font-semibold text-slate-100">{t.nav.voices}</h1>

      <button
        type="button"
        onClick={() => fileInput.current?.click()}
        disabled={processing}
        className="flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-900 px-6 py-10 text-center transition hover:border-slate-600 active:border-brand-500 disabled:opacity-60"
      >
        <UploadCloud size={36} className="text-brand-400" />
        <span className="text-lg font-medium text-slate-100">{t.voices.uploadTitle}</span>
        <span className="text-sm text-slate-400">
          {processing ? t.voices.processing : t.voices.uploadHint}
        </span>
        {processing && (
          <div className="mt-2 h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-brand-500" />
        )}
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="audio/*,video/*"
        className="hidden"
        onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
      />

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      {groups.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            {t.voices.uploadHint}
          </h2>
          <div className="space-y-3">
            {groups.map((group) => (
              <div key={group.groupId} className="rounded-2xl bg-slate-900 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        group.gender === "female"
                          ? "bg-pink-500/20 text-pink-300"
                          : "bg-blue-500/20 text-blue-300"
                      }`}
                    >
                      {group.gender === "female" ? t.voices.female : t.voices.male}
                    </span>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${QUALITY_STYLES[group.quality] ?? ""}`}>
                      {group.quality === "best"
                        ? t.voices.qualityBest
                        : group.quality === "ok"
                          ? t.voices.qualityOk
                          : t.voices.qualityShort}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {group.totalSeconds}s · {group.clipCount} {t.voices.clips}
                  </span>
                </div>

                {group.previewPath && (
                  <button
                    onClick={() => togglePlay(group.previewPath!)}
                    className="mb-3 flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-200"
                  >
                    {playingUrl === group.previewPath ? <Pause size={16} /> : <Play size={16} />}
                    {t.voices.preview}
                  </button>
                )}

                <div className="flex gap-2">
                  <input
                    className="flex-1 rounded-xl bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
                    placeholder={t.voices.namePlaceholder}
                    value={names[group.groupId] ?? ""}
                    onChange={(e) => setNames((prev) => ({ ...prev, [group.groupId]: e.target.value }))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") saveVoice(group);
                    }}
                  />
                  <button
                    onClick={() => saveVoice(group)}
                    disabled={!names[group.groupId]?.trim() || savingId === group.groupId}
                    className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    <Save size={16} />
                    {savingId === group.groupId ? t.voices.saving : t.voices.save}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {t.voices.library}
      </h2>
      {voices.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-slate-900 px-6 py-8 text-center">
          <Mic2 size={28} className="text-slate-600" />
          <p className="text-sm text-slate-500">{t.voices.empty}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {voices.map((voice) => {
            const previewUrl = voice.referencePath?.startsWith("/media/") ? voice.referencePath : null;
            return (
              <div key={voice.id} className="flex items-center justify-between rounded-xl bg-slate-900 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-600/20">
                    <Mic2 size={18} className="text-brand-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-100">{voice.name}</p>
                    {voice.providerIds && Object.keys(voice.providerIds).length > 0 && (
                      <div className="mt-0.5 flex gap-1">
                        {Object.entries(voice.providerIds).map(([provider]) => (
                          <span key={provider} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">
                            {provider}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {previewUrl && (
                  <button
                    onClick={() => togglePlay(previewUrl)}
                    className="rounded-lg bg-slate-800 p-2 text-slate-300"
                  >
                    {playingUrl === previewUrl ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
