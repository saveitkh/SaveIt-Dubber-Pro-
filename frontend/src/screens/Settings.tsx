import { Check, LogOut, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import { localeStore, useT, type Locale } from "../i18n";
import { api } from "../lib/api";
import { useAuthStore } from "../store/auth";
import type { HealthStatus, ProviderStatus } from "../lib/types";

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  elevenlabs: "ElevenLabs",
  voxcpm: "VoxCPM",
};

export function Settings() {
  const t = useT();
  const { user, logout } = useAuthStore();
  const locale = localeStore((s) => s.locale);
  const setLocale = localeStore((s) => s.setLocale);

  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [providerConfig, setProviderConfig] = useState<ProviderStatus | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; reason: string }>>({});

  useEffect(() => {
    api.get<HealthStatus>("/api/health").then(setHealth).catch(() => {});
    if (user?.isAdmin) {
      api
        .get<{ status: ProviderStatus; config: Record<string, unknown> }>("/api/settings/providers")
        .then((res) => setProviderConfig(res.status))
        .catch(() => {});
    }
  }, [user?.isAdmin]);

  const testProvider = async (name: string) => {
    setTesting(name);
    try {
      const result = await api.post<{ ok: boolean; reason: string }>(`/api/settings/providers/${name}/test`);
      setTestResults((prev) => ({ ...prev, [name]: result }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [name]: { ok: false, reason: (err as Error).message } }));
    } finally {
      setTesting(null);
    }
  };

  const providerStatus: ProviderStatus | null = providerConfig ?? (health
    ? {
        gemini: { configured: health.providers.gemini, model: "" },
        elevenlabs: { configured: health.providers.elevenlabs },
        voxcpm: { configured: health.providers.voxcpm, url: "", mode: "" },
      }
    : null);

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-slate-100">{t.nav.settings}</h1>

      <section className="mb-4 rounded-2xl bg-slate-900 p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{t.settings.language}</h2>
        <div className="flex gap-2">
          {(["km", "en"] as Locale[]).map((l) => (
            <button
              key={l}
              onClick={() => setLocale(l)}
              className={`flex-1 rounded-xl py-2.5 text-sm font-medium transition ${
                locale === l ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-300"
              }`}
            >
              {l === "km" ? "ខ្មែរ" : "English"}
            </button>
          ))}
        </div>
      </section>

      <section className="mb-4 rounded-2xl bg-slate-900 p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{t.settings.account}</h2>
        <p className="text-sm text-slate-300">{user?.displayName ?? user?.username ?? "—"}</p>
        {user?.isAdmin && <p className="mt-1 text-xs text-brand-400">Admin</p>}
      </section>

      {providerStatus && (
        <section className="mb-4 rounded-2xl bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{t.settings.providers}</h2>
          <div className="space-y-3">
            {Object.entries(providerStatus).map(([key, status]) => (
              <div key={key} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-slate-200">{PROVIDER_LABELS[key] ?? key}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      status.configured ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-700 text-slate-400"
                    }`}
                  >
                    {status.configured ? t.settings.configured : t.settings.notConfigured}
                  </span>
                </div>
                {user?.isAdmin && status.configured && (
                  <button
                    onClick={() => testProvider(key)}
                    disabled={testing === key}
                    className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200 disabled:opacity-50"
                  >
                    <Zap size={12} />
                    {testing === key ? t.settings.testing : t.settings.testProvider}
                  </button>
                )}
              </div>
            ))}
            {Object.entries(testResults).map(([key, result]) => (
              <div
                key={`result-${key}`}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
                  result.ok ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"
                }`}
              >
                {result.ok ? <Check size={14} /> : <X size={14} />}
                {PROVIDER_LABELS[key] ?? key}: {result.reason}
              </div>
            ))}
          </div>
        </section>
      )}

      {health && (
        <section className="mb-4 rounded-2xl bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{t.settings.systemHealth}</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              { label: "FFmpeg", ok: health.ffmpeg },
              { label: "Demucs", ok: health.demucs },
              { label: "GPU", ok: health.gpu },
              { label: "Telegram", ok: health.telegram },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${item.ok ? "bg-emerald-400" : "bg-slate-600"}`} />
                <span className="text-slate-300">{item.label}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <button
        onClick={() => logout()}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-800 py-3 text-sm font-medium text-red-300 transition active:bg-slate-700"
      >
        <LogOut size={16} />
        Logout
      </button>
    </div>
  );
}
