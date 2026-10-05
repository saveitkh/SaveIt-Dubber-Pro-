import type { Dict } from "./km";

export const en: Dict = {
  appName: "SaveIt Dubber Pro",
  nav: { home: "Home", projects: "Projects", voices: "Voices", settings: "Settings" },
  home: {
    uploadTitle: "Upload video",
    uploadHint: "Drag & drop, or click to choose",
    linkPlaceholder: "or paste a video link",
    recent: "Recent projects",
    empty: "No projects yet — start by uploading a video",
  },
  status: { new: "New", processing: "Processing", needsReview: "Needs review", done: "Done", error: "Error" },
  project: {
    needsReview: "Needs review",
    characters: "Characters",
    playDub: "Play dub",
    regenerate: "Regenerate",
    export: "Export",
    timeline: "Timeline",
  },
  auth: {
    signingInTelegram: "Signing in with Telegram…",
    loginWithTelegram: "Log in with Telegram",
    username: "Username",
    password: "Password",
    login: "Log in",
    register: "Register",
    reopenFromBot: "Please reopen this app from the bot",
  },
  settings: {
    providers: "Providers",
    automation: "Automation level",
    account: "Account",
    outputDefaults: "Output defaults",
  },
  common: { save: "Save", cancel: "Cancel", loading: "Loading…", retry: "Retry" },
};
