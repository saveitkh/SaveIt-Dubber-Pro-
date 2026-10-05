import { LogOut } from "lucide-react";

import { t } from "../i18n";
import { useAuthStore } from "../store/auth";

export function Settings() {
  const { user, logout } = useAuthStore();

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-slate-100">{t.nav.settings}</h1>

      <section className="mb-4 rounded-2xl bg-slate-900 p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          {t.settings.account}
        </h2>
        <p className="text-sm text-slate-300">{user?.displayName ?? user?.username ?? "—"}</p>
        {user?.isAdmin && <p className="mt-1 text-xs text-brand-400">Admin</p>}
      </section>

      <section className="mb-4 rounded-2xl bg-slate-900 p-4 text-sm text-slate-500">
        {t.settings.providers} — M5
      </section>
      <section className="mb-4 rounded-2xl bg-slate-900 p-4 text-sm text-slate-500">
        {t.settings.outputDefaults} — M2
      </section>

      <button
        onClick={() => logout()}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-800 py-3 text-sm font-medium text-red-300"
      >
        <LogOut size={16} />
        Logout
      </button>
    </div>
  );
}
