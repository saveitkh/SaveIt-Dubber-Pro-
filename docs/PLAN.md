# SaveIt Dubber Pro — Architecture & Reuse Plan

Source prompt: `SAVEIT_DUBBER_PRO_PROMPT.md` (product spec).
Reference repo read for this plan: `saveitkh/BarameyDabber` (cloned read-only, commit `53c08ba`).

## 1. What we are building vs. what we are not

Building: a focused app around one pipeline — upload → auto Khmer dub with cloned
voices → review queue → export. Mobile-first PWA + desktop editor, FastAPI backend,
SSE job progress, SQLite + optional Supabase sync.

Explicitly out of scope (present in the reference repo, dropped here): the 6-step
`WorkflowStepper` wizard, `ThumbnailGenerator`, `VideoEffectsPanel` / `effectsLibrary`,
`CommercialOverlayModal`, `StudioCustomizerModal` / `QuickThemeFloatingWidget`,
`KhmerOfflineBatchPanel` / offline batch pages, `VideoDownloaderModal`, Flutter/Android
app (`flutter_app/`, `android/`), desktop `.exe` build tooling (`build_exe*.bat`,
`animeclone.spec`, `desktop_app*.py`), the auto-updater (`auto_updater.py`,
`update_manager.py`, `checkpoint_manager.py`, `AUTO_UPDATE_README.md`), license-key
system, `AdminVoiceManagement` grant/toggle UI beyond a minimal providers page, and the
Node.js duplicate services (`server.js`, `khmerDubbingService.js`, `audioProcessor.js`,
`elevenlabsService.js`, `translationService.js`) — the Python stack is the single
source of truth going forward.

## 2. Reuse map — what comes from which reference file

| New module | Ported from (reference) | What's kept | What changes |
|---|---|---|---|
| `backend/app/services/vocal_separator.py` | `services/vocal_separator.py` | Demucs call, ffmpeg DSP fallback, cache-by-hash | Async-wrapped, job-aware progress callback |
| `backend/app/services/audio_mix.py` | `services/audio_processor.py` (`build_smart_bed`, `auto_mix_gains`, `measure_lufs`, subtitle burn, encoder probe) | Smart background bed math, LUFS auto-gain, SRT/ASS subtitle burn, encoder detection | Split one 750-line file into `audio_mix.py` (bed/gain/export) + `subtitles.py`; drop overlay-image/commercial-overlay code path |
| `backend/app/services/dubber.py` | `services/khmer_dubber.py` (`extract_dialogue_timeline`, `transcribe_chunk_with_gemini`, `assign_unique_voices_to_segments`, `assemble_timeline_audio`, `process_khmer_dubbing`) | Chunked (~90s/5s overlap) Gemini transcription+translation, timeline assembly, per-line TTS provider fallback chain | Replace legacy Edge-TTS/ElevenLabs-only paths with the provider order Gemini→VoxCPM2→ElevenLabs described in §8 of the spec; this becomes stage 3/6/7 of the job pipeline, not a single monolithic call |
| `backend/app/services/voice_engine.py` | `scripts/voice_split_offline.py` (`detect_speech_segments`, `extract_features` MFCC, `cluster_segments` Ward, `export_clusters`) | YIN-ish pitch + MFCC fingerprint, Ward clustering, auto character count, clip export | Add cross-episode profile matching against `series_voices` table (was file-based `voices.json`); add `overlap`/`unsure`/`missed` flagging as first-class review-item types instead of CLI flags |
| `backend/app/services/voice_cast_store.py` | `services/voice_cast_store.py` | Per-character reference clip selection/quality scoring | Backed by SQLite `voices`/`characters` tables instead of JSON files on disk |
| `backend/app/services/gemini_client.py` | `services/gemini_client.py` | Client wrapper, retry/backoff, model picker | Add text-shortening call (slot-overflow fix) and emotion-from-scene suggestion |
| `backend/app/services/elevenlabs_service.py` | `services/elevenlabs_service.py` | Clone + TTS calls | Wrapped behind the same `TTSProvider` interface as VoxCPM2 engine |
| `backend/voxcpm_engine/` (+ `backend/app/services/voxcpm_client.py`) | `VoxCPM2_Server.py`, `local_voxcpm_server.py`, `colab_voxcpm_api.py` | Request/response shape, Colab/Kaggle launcher pattern | Rewritten per spec §8b against the official `voxcpm` pip package and the `/v1/voices`, `/v1/speak`, `/v1/speak/stream`, `/v1/audio/speech` API; one `run.py` + `run.bat`/`run.sh` instead of three divergent server scripts; `/health` reports "not installed" cleanly instead of crashing when run without a GPU |
| `backend/app/auth/telegram.py` | `server.py` (`verify_telegram_init_data`, `/api/auth/telegram*` routes) | HMAC `WebAppData` verification, 24h max-age, admin-ID allowlist, cookie (`HttpOnly; Secure; SameSite=None`) + bearer token dual support | Pulled out of the 3,800-line `server.py` monolith into its own router module |
| `backend/app/auth/db.py` | `services/auth_db.py` | Token-session model, password hashing, admin flags | Trimmed: drop license-key activation, device-reset, premium-grant admin ops not in the new spec |
| `src/screens/*`, `src/components/timeline/*` | `src/components/session/*` (`CharacterCastBoard`, `DubbingStudioPanel`, `VoiceCloneSession`, `OutputSettingsCard`), `MultiTrackTimeline.tsx` | Character cards, clone-from-movie line picker, timeline drag/trim/waveform interactions, background card controls | Re-themed to the mobile-first screens in spec §5 (Home/Project/Character sheet/Review queue/Voices/Settings) instead of the old `App.tsx` shell |

Everything under `backend/app/` is new Python package layout (FastAPI routers +
services + SQLAlchemy models) — the reference `server.py` is a single 3,800-line file
with 90+ routes; we are not porting that structure, only the logic above.

## 3. Pipeline → job stages (spec §3)

One `jobs` row per run, `stage` enum = `prepare | separate | transcribe | diarize |
cast | speak | mix | export`, each stage's output cached by content hash so a
`PATCH /api/lines/{id}` only invalidates `speak` for that line and `mix`/`export`
downstream. Progress streamed via `GET /api/jobs/{id}/events` (SSE); job state
persisted in SQLite so a reload resumes from `jobs.stage`/`jobs.progress` instead of
restarting.

## 4. Backend layout

```
backend/
  app/
    main.py                 # FastAPI app, router mounts, CORS, static mounts
    db.py                   # SQLAlchemy engine/session, SQLite file in data/
    models.py                # users, series, projects, jobs, lines, characters, voices, review_items, settings
    deps.py                  # get_current_user, require_admin, require_license
    auth/
      telegram.py            # verify_telegram_init_data, /api/auth/telegram*
      password.py            # /api/auth/login, /api/auth/me
    routers/
      projects.py             # POST /api/projects, GET /api/projects/{id}, /run
      jobs.py                 # SSE /api/jobs/{id}/events
      lines.py                 # PATCH /api/lines/{id}, /regenerate
      characters.py           # PATCH/POST /api/characters/*
      voices.py                 # /api/voices/clip, /api/voices, /api/series/{id}/voices
      settings.py               # /api/settings/providers, /test
      health.py                  # /api/health
    services/
      vocal_separator.py
      audio_mix.py
      subtitles.py
      dubber.py
      voice_engine.py
      voice_cast_store.py
      gemini_client.py
      elevenlabs_service.py
      tts_provider.py          # common interface VoxCPM2 / ElevenLabs / Gemini TTS fallback chain
    jobs/
      runner.py                 # background job executor + SSE broadcaster
      pipeline.py                # stage functions wired to services above
  voxcpm_engine/
    engine.py                    # FastAPI app implementing /health /v1/voices /v1/speak /v1/speak/stream /v1/audio/speech
    run.py / run.bat / run.sh
    colab_launcher.ipynb
  requirements.txt
  pyproject.toml (ruff + mypy config)
  tests/
```

## 5. Frontend layout

```
frontend/
  src/
    main.tsx, App.tsx          # route shell: mobile bottom-tabs vs desktop three-pane (media query)
    store/                      # Zustand: auth, project, player, jobProgress
    i18n/km.ts, en.ts
    lib/api.ts, sse.ts, telegram.ts
    screens/
      Home.tsx
      Project.tsx
      CharacterSheet.tsx
      ReviewQueue.tsx
      Voices.tsx
      Settings.tsx
    components/
      timeline/ (ported from session/MultiTrackTimeline)
      characters/ (ported from session/CharacterCastBoard)
      player/
      ui/
  tailwind.config.ts            # Kantumruy Pro / Noto Sans Khmer
  vite.config.ts
```

## 6. Milestones (spec §13) — tracked in this build

- **M1 Skeleton** (this change): auth (Telegram + password), projects, upload, job
  runner with SSE (stages stubbed/no-op where providers aren't wired yet), mobile +
  desktop shells.
- **M2 Auto pipeline**: real stages 1–8 end-to-end with stock voices.
- **M3 Voices**: `voxcpm_engine/`, voice engine (split/clips/profiles), auto-cast,
  Voice Clip screen, series memory.
- **M4 Editor**: timeline, character sheet, review queue, partial re-runs.
- **M5 Providers & deploy**: providers page, `deploy.sh`, health endpoint, external
  network compose.

## 7. Deployment

`docker-compose.yml` with `studio` service (container `dubbing-studio`), optional
`caddy` service, and a `default` network that can be swapped to `external: true`
joining an existing VPS network per spec §11. `.env.example` lists every variable from
the spec. `/api/health` reports ffmpeg/Demucs/GPU/providers/Telegram status.
