import { Home as HomeIcon, Mic2, Settings as SettingsIcon, FolderClosed } from "lucide-react";
import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useT } from "../../i18n";

export function AppShell({ children }: { children: ReactNode }) {
  const t = useT();
  const TABS = [
    { to: "/", label: t.nav.home, icon: HomeIcon },
    { to: "/projects", label: t.nav.projects, icon: FolderClosed },
    { to: "/voices", label: t.nav.voices, icon: Mic2 },
    { to: "/settings", label: t.nav.settings, icon: SettingsIcon },
  ];
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 md:flex-row">
      <aside className="hidden w-56 flex-col border-r border-slate-800 p-4 md:flex">
        <h1 className="mb-6 px-2 text-lg font-semibold text-slate-100">{t.appName}</h1>
        <nav className="flex flex-col gap-1">
          {TABS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  isActive ? "bg-brand-600 text-white" : "text-slate-300 hover:bg-slate-800"
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1 overflow-y-auto pb-20 md:pb-0">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 flex border-t border-slate-800 bg-slate-950/95 backdrop-blur md:hidden">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-xs ${
                isActive ? "text-brand-400" : "text-slate-500"
              }`
            }
          >
            <Icon size={22} />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
