import { Mic2 } from "lucide-react";

import { t } from "../i18n";

export function Voices() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-slate-100">{t.nav.voices}</h1>
      <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-slate-700 bg-slate-900 px-6 py-10 text-center text-slate-400">
        <Mic2 size={32} className="text-brand-400" />
        <p className="text-sm">
          Voice Clip — ដាក់ឯកសារសំឡេង ឬវីដេអូ ដើម្បីញែក និងដាក់ឈ្មោះអ្នកនិយាយ (M3)
        </p>
      </div>
    </div>
  );
}
