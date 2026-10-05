import { en } from "./en";
import { km } from "./km";

export const dictionaries = { km, en };
export type Locale = keyof typeof dictionaries;
export const t = dictionaries.km;
