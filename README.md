# SaveIt Dubber Pro

Upload a video → get it back dubbed in Khmer, automatically, with every character
speaking in their own cloned voice and the original background music kept. Then only
listen and fix what is wrong.

See `docs/PLAN.md` for the architecture, the reuse map from the reference repo
(`saveitkh/BarameyDabber`), and the milestone plan this build follows.

## Status

**M1 Skeleton** — auth (Telegram + password), projects, upload, job runner with SSE,
mobile + desktop shells. Pipeline stages are stubbed (real timing/progress, no-op
processing) until M2 wires in ffmpeg/Demucs/Gemini/TTS.

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
