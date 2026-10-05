import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import OUTPUTS_DIR, UPLOADS_DIR, VOICES_DIR
from app.db import init_db
from app.routers import auth, characters, health, jobs, lines, projects, settings, voices

app = FastAPI(title="SaveIt Dubber Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(lines.router)
app.include_router(characters.router)
app.include_router(voices.router)
app.include_router(settings.router)

app.mount("/media/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/media/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
app.mount("/media/voices", StaticFiles(directory=str(VOICES_DIR)), name="voices")

# In production the Docker image bundles the built frontend; served last so it
# never shadows the /api and /media routes above. In local dev this directory
# doesn't exist and the Vite dev server is used instead (see vite.config.ts proxy).
frontend_dist = Path(os.environ.get("STUDIO_FRONTEND_DIST", ""))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
