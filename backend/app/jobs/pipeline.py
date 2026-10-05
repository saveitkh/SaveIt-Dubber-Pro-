"""Pipeline stage functions (spec §3).

M1 ships these as working stubs (real timing, real progress events, real DB writes)
so the job runner, SSE wire format and resumable-job behaviour are all exercised
end-to-end without any provider keys configured. Each stage is replaced with real
logic as its milestone lands:

  prepare     -> ffmpeg extract audio + 720p proxy                         (M2)
  separate    -> services/vocal_separator.py (Demucs -> DSP fallback)      (M2)
  transcribe  -> services/dubber.py (chunked Gemini transcribe+translate)  (M2)
  diarize     -> services/voice_engine.py (acoustic speaker clustering)    (M3)
  cast        -> services/voice_cast_store.py (auto-cast reference clips)  (M3)
  speak       -> voxcpm_engine / elevenlabs_service / gemini TTS fallback  (M3)
  mix         -> services/audio_mix.py (smart background bed, LUFS)       (M2)
  export      -> services/subtitles.py + ffmpeg mux                       (M2)
"""

import asyncio
from collections.abc import Callable

from sqlalchemy.orm import Session

STAGES = ["prepare", "separate", "transcribe", "diarize", "cast", "speak", "mix", "export"]

ProgressFn = Callable[[float, str | None], None]


async def _stub_stage(label: str, project_id: str, db: Session, on_progress: ProgressFn) -> None:
    for pct in (0, 25, 50, 75, 100):
        on_progress(float(pct), label)
        await asyncio.sleep(0.15)


async def run_stage(stage: str, project_id: str, db: Session, on_progress: ProgressFn) -> None:
    labels = {
        "prepare": "កំពុងរៀបចំវីដេអូ…",
        "separate": "កំពុងញែកសំឡេង និងតន្ត្រី…",
        "transcribe": "កំពុងសម្រាយ និងបកប្រែជាខ្មែរ…",
        "diarize": "កំពុងកំណត់អ្នកនិយាយ…",
        "cast": "កំពុងជ្រើសសំឡេងសម្រាប់តួអង្គ…",
        "speak": "កំពុងបង្កើតសំឡេងខ្មែរ…",
        "mix": "កំពុងលាយសំឡេង…",
        "export": "កំពុងនាំចេញវីដេអូ…",
    }
    await _stub_stage(labels.get(stage, stage), project_id, db, on_progress)
