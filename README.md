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
**M3 Voices** — `voxcpm_engine/` (a standalone VoxCPM2 service per spec §8b: `/health`,
`/v1/voices`, `/v1/speak`, `/v1/speak/stream`, `/v1/audio/speech`; reports a clear
"model not installed" status rather than crashing when no GPU/model is present),
the acoustic voice engine (ported `scripts/voice_split_offline.py` as library code:
VAD, MFCC+pitch features, Ward clustering) cross-checking Gemini's speaker split and
flagging disagreements for review, auto-cast with cloning (VoxCPM2 → ElevenLabs →
stock, in that order) gated on a licensed/admin account, cross-episode series voice
memory by acoustic fingerprint similarity, and a working Voice Clip screen/endpoint
(drop any file with voices → separated, split by speaker, quality-scored clips ready
to name and save).

**M4 Editor** — server-computed, cached waveform peaks rendered on a timeline with
flagged-line markers and click-to-seek; a Review queue (spec §6) with play
original-vs-Khmer, Correct/Regenerate/Remove, and one-tap reassign-to-character for
`unsure` items; a Character sheet for name/gender/emotion/speed; and partial re-runs —
fixing one flagged line re-synthesizes only that line then rebuilds the mix/export
(not the whole project), measured at well under a second in testing against the
spec's <30s target. Providers settings UI and deploy polish land in M5.

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
