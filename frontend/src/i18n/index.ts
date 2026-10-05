import { create } from "zustand";

import { en } from "./en";
import { km } from "./km";

const dictionaries = { km, en };
export type Locale = keyof typeof dictionaries;

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const localeStore = create<LocaleState>((set) => ({
  locale: (localStorage.getItem("saveit_locale") as Locale) || "km",
  setLocale: (locale) => {
    localStorage.setItem("saveit_locale", locale);
    set({ locale });
  },
}));

export function useT() {
  return localeStore((s) => dictionaries[s.locale]);
}

export const t = dictionaries.km;
