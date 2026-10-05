interface TelegramWebApp {
  initData: string;
  ready: () => void;
  expand: () => void;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  BackButton: { show: () => void; hide: () => void; onClick: (cb: () => void) => void };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function isInsideTelegram(): boolean {
  const webApp = getTelegramWebApp();
  return !!webApp && webApp.initData.length > 0;
}

export function initTelegram(): void {
  const webApp = getTelegramWebApp();
  if (!webApp) return;
  webApp.ready();
  webApp.expand();
}
