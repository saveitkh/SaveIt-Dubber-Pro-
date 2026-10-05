import { create } from "zustand";

import { api, getToken, setToken, type UserPublic } from "../lib/api";
import { getTelegramWebApp, isInsideTelegram } from "../lib/telegram";

interface AuthState {
  user: UserPublic | null;
  status: "idle" | "checking" | "authenticated" | "unauthenticated" | "error";
  error: string | null;
  checkSession: () => Promise<void>;
  loginWithTelegram: () => Promise<void>;
  loginWithPassword: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "idle",
  error: null,

  checkSession: async () => {
    set({ status: "checking" });
    if (isInsideTelegram() && !getToken()) {
      try {
        await useAuthStore.getState().loginWithTelegram();
        return;
      } catch (err) {
        set({ status: "error", error: (err as Error).message });
        return;
      }
    }
    if (!getToken()) {
      set({ status: "unauthenticated" });
      return;
    }
    try {
      const user = await api.get<UserPublic>("/api/auth/me");
      set({ user, status: "authenticated" });
    } catch {
      setToken(null);
      set({ status: "unauthenticated" });
    }
  },

  loginWithTelegram: async () => {
    const webApp = getTelegramWebApp();
    if (!webApp) throw new Error("Telegram WebApp is not available");
    const { token, user } = await api.post<{ token: string; user: UserPublic }>("/api/auth/telegram", {
      initData: webApp.initData,
    });
    setToken(token);
    set({ user, status: "authenticated" });
  },

  loginWithPassword: async (username, password) => {
    const { token, user } = await api.post<{ token: string; user: UserPublic }>("/api/auth/login", {
      username,
      password,
    });
    setToken(token);
    set({ user, status: "authenticated" });
  },

  register: async (username, password) => {
    const { token, user } = await api.post<{ token: string; user: UserPublic }>("/api/auth/register", {
      username,
      password,
    });
    setToken(token);
    set({ user, status: "authenticated" });
  },

  logout: async () => {
    await api.post("/api/auth/logout");
    setToken(null);
    set({ user: null, status: "unauthenticated" });
  },
}));
