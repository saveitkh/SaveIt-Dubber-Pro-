import { X } from "lucide-react";
import { useState } from "react";

import { api } from "../../lib/api";
import type { CharacterDetail } from "../../lib/types";

const EMOTIONS = ["neutral", "happy", "sad", "angry", "fearful", "excited"];
const EMOTION_LABELS: Record<string, string> = {
  neutral: "ធម្មតា",
  happy: "រីករាយ",
  sad: "សោកសៅ",
  angry: "ខឹង",
  fearful: "ភ័យខ្លាច",
  excited: "រំភើប",
};

interface CharacterSheetProps {
  character: CharacterDetail;
  onClose: () => void;
  onSaved: (updated: CharacterDetail) => void;
}

export function CharacterSheet({ character, onClose, onSaved }: CharacterSheetProps) {
  const [name, setName] = useState(character.name);
  const [gender, setGender] = useState(character.gender ?? "");
  const [emotionDefault, setEmotionDefault] = useState(character.emotionDefault);
  const [speed, setSpeed] = useState(character.speed);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/api/characters/${character.id}`, {
        name,
        gender: gender || null,
        emotionDefault,
        speed,
      });
      onSaved({ ...character, name, gender: gender || null, emotionDefault, speed });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 md:items-center" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-t-2xl bg-slate-900 p-5 md:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="h-8 w-8 rounded-full" style={{ backgroundColor: character.color }} />
            <h2 className="text-lg font-semibold text-slate-100">តួអង្គ</h2>
          </div>
          <button onClick={onClose} className="text-slate-400">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-slate-500">ឈ្មោះ</label>
            <input
              className="w-full rounded-xl bg-slate-800 px-4 py-3 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-brand-500"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-500">ភេទ</label>
            <div className="flex gap-2">
              {[
                { value: "male", label: "ប្រុស" },
                { value: "female", label: "ស្រី" },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setGender(opt.value)}
                  className={`flex-1 rounded-xl py-2.5 text-sm font-medium ${
                    gender === opt.value ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-500">អារម្មណ៍លំនាំដើម</label>
            <div className="grid grid-cols-3 gap-2">
              {EMOTIONS.map((e) => (
                <button
                  key={e}
                  onClick={() => setEmotionDefault(e)}
                  className={`rounded-xl py-2 text-xs font-medium ${
                    emotionDefault === e ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-300"
                  }`}
                >
                  {EMOTION_LABELS[e]}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-500">ល្បឿន ({speed.toFixed(2)}x)</label>
            <input
              type="range"
              min={0.5}
              max={1.5}
              step={0.05}
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>
        </div>

        <button
          onClick={save}
          disabled={saving}
          className="mt-6 w-full rounded-xl bg-brand-600 py-3 text-sm font-medium text-white disabled:opacity-60"
        >
          រក្សាទុក
        </button>
      </div>
    </div>
  );
}
