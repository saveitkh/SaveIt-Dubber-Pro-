import { type ReactNode, useEffect, useState } from "react";

import { t } from "../i18n";
import { isInsideTelegram } from "../lib/telegram";
import { useAuthStore } from "../store/auth";

export function AuthGate({ children }: { children: ReactNode }) {
  const { status, error, checkSession, loginWithPassword, register } = useAuthStore();
  const insideTelegram = isInsideTelegram();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  if (status === "idle" || status === "checking") {
    return <SplashScreen label={insideTelegram ? t.auth.signingInTelegram : t.common.loading} />;
  }

  if (status === "error" && insideTelegram) {
    return (
      <SplashScreen label={error ?? t.auth.signingInTelegram} isError>
        <p className="mt-2 text-sm text-slate-400">{t.auth.reopenFromBot}</p>
      </SplashScreen>
    );
  }

  if (status === "authenticated") {
    return <>{children}</>;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      if (mode === "login") await loginWithPassword(username, password);
      else await register(username, password);
    } catch (err) {
      setFormError((err as Error).message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-slate-900 p-6 shadow-xl">
        <h1 className="text-center text-xl font-semibold text-slate-100">{t.appName}</h1>
        <input
          className="w-full rounded-xl bg-slate-800 px-4 py-3 text-base text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
          placeholder={t.auth.username}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <input
          className="w-full rounded-xl bg-slate-800 px-4 py-3 text-base text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
          placeholder={t.auth.password}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
        {formError && <p className="text-sm text-red-400">{formError}</p>}
        <button
          type="submit"
          className="w-full rounded-xl bg-brand-600 py-3 text-base font-medium text-white active:bg-brand-700"
        >
          {mode === "login" ? t.auth.login : t.auth.register}
        </button>
        <button
          type="button"
          className="w-full text-sm text-slate-400"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? t.auth.register : t.auth.login}
        </button>
      </form>
    </div>
  );
}

function SplashScreen({
  label,
  isError,
  children,
}: {
  label: string;
  isError?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center">
      {!isError && (
        <div className="mb-4 h-10 w-10 animate-spin rounded-full border-2 border-slate-700 border-t-brand-500" />
      )}
      <p className={isError ? "text-red-400" : "text-slate-300"}>{label}</p>
      {children}
    </div>
  );
}
