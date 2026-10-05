# SaveIt Dubber Pro

Upload a video → get it back dubbed in Khmer, automatically, with every character
speaking in their own cloned voice and the original background music kept. Then only
listen and fix what is wrong.

See `docs/PLAN.md` for the architecture, the reuse map from the reference repo
(`saveitkh/BarameyDabber`), and the milestone plan this build follows.

## Status

**M1 Skeleton** — auth (Telegram + password), projects, upload, job runner with SSE,
mobile + desktop shells.

**M2 Auto pipeline** — all 8 stages run for real: ffmpeg prepare/mux/export, Demucs
(with an ffmpeg DSP fallback when Demucs isn't installed) for vocal/background
separation, chunked Gemini transcription+translation, stock Khmer TTS (edge-tts,
free/no key) fit to each line's time slot, and a smart background bed mix (full
volume where nobody speaks, ducked under dialogue). Without `GEMINI_API_KEY`
configured, a project still finishes end-to-end as a clean passthrough of the
original audio with a review item explaining why — never a blocked job (spec §3/§8).
Voice cloning (VoxCPM2/ElevenLabs) and the acoustic diarization/review-queue
refinements land in M3/M4.

## Local development

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in keys as you get them
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api and /media to :8000
```

## Docker

```bash
cp .env.example .env
docker compose up -d studio
curl http://localhost:3000/api/health
```

To join an existing VPS proxy network instead of the bundled Caddy profile, see the
comment at the bottom of `docker-compose.yml`.

## Repo layout

```
backend/    FastAPI app (auth, projects, job runner, pipeline stages, services)
frontend/   React + TypeScript + Vite + Tailwind (mobile-first, Khmer UI)
docs/       PLAN.md — architecture and reuse map
data/       SQLite database (gitignored)
uploads/ outputs/ voices/   Runtime media volumes (gitignored)
```
