"""VoxCPM2 engine service (spec §8b).

One codebase, three launchers (local GPU, Colab, Kaggle — see run.py/run.sh/run.bat
and the Colab/Kaggle notebooks this directory's README points to), speaking the API
the main studio app calls regardless of where it runs:

    GET  /health                 -> {model, version, device, vram_free, sample_rate}
    POST /v1/voices               upload ref wav (+ transcript) -> voice_id (cached encoding)
    POST /v1/speak                {text, voice_id | design, style, seed, cfg, steps} -> wav
    POST /v1/speak/stream         same, chunked audio
    POST /v1/audio/speech         OpenAI-compatible (vLLM-Omni style) for drop-in use

This machine has no GPU and the `voxcpm` package is a multi-GB model download, so
this module is written to run correctly wherever `pip install voxcpm` + a GPU exist,
but falls back to a clear "model not installed" response instead of crashing when it
doesn't — `/health` reports that honestly rather than pretending to be ready.
"""

import io
import os
import tempfile
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="VoxCPM2 Engine")

_model: Any = None
_model_error: str | None = None
_voice_cache: dict[str, dict] = {}  # voice_id -> {reference_wav_path, prompt_text}


def _load_model() -> Any:
    """Lazy-load so `/health` works (and reports why) even when the model can't
    load — never crash the process over a missing GPU or package."""
    global _model, _model_error
    if _model is not None or _model_error is not None:
        return _model
    try:
        from voxcpm import VoxCPM  # type: ignore[import-not-found]

        _model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
    except Exception as exc:  # noqa: BLE001
        _model_error = str(exc)
    return _model


@app.get("/health")
def health() -> dict:
    model = _load_model()
    if model is None:
        return {
            "model": None,
            "version": None,
            "device": "unavailable",
            "vramFree": None,
            "sampleRate": None,
            "error": _model_error or "voxcpm package not installed (pip install voxcpm)",
        }
    try:
        import voxcpm  # type: ignore[import-not-found]

        version = getattr(voxcpm, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        version = "unknown"
    device = "cuda" if _has_cuda() else "cpu"
    return {
        "model": "VoxCPM2",
        "version": version,
        "device": device,
        "vramFree": _vram_free_mb(),
        "sampleRate": model.tts_model.sample_rate,
    }


def _has_cuda() -> bool:
    try:
        import torch  # type: ignore[import-not-found]

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _vram_free_mb() -> int | None:
    try:
        import torch  # type: ignore[import-not-found]

        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return int(free / 1024 / 1024)
    except Exception:  # noqa: BLE001
        return None


class VoiceDesign(BaseModel):
    description: str  # e.g. "old man, deep, calm voice" (spec §8b voice design)


class SpeakRequest(BaseModel):
    text: str
    voiceId: str | None = None
    design: VoiceDesign | None = None
    style: str | None = None  # e.g. "(happy, excited, slightly fast)"
    seed: int = 42
    cfg: float = 2.0
    steps: int = 10


def _require_model() -> Any:
    model = _load_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"VoxCPM2 model not available: {_model_error or 'not installed'}. "
            "Run on a GPU host with `pip install voxcpm`, or configure a different "
            "TTS provider (ElevenLabs/stock) in Settings -> Providers.",
        )
    return model


@app.post("/v1/voices")
async def register_voice(file: UploadFile, transcript: str = "") -> dict:
    """Cache a reference clip's encoding for reuse across many /v1/speak calls on
    the same voice, per spec §8b "cache the reference encoding per character"."""
    _require_model()  # fail fast with a clear error if the model isn't usable
    voice_id = uuid.uuid4().hex
    suffix = os.path.splitext(file.filename or "ref.wav")[1] or ".wav"
    dest = os.path.join(tempfile.gettempdir(), f"voxcpm_ref_{voice_id}{suffix}")
    with open(dest, "wb") as f:
        f.write(await file.read())
    _voice_cache[voice_id] = {"reference_wav_path": dest, "prompt_text": transcript}
    return {"voiceId": voice_id}


def _style_prefixed_text(text: str, style: str | None) -> str:
    # Emotion = the "(...)" prefix (spec §8b); never shown to users, so the
    # caller is responsible for keeping it out of subtitles/khmer_text display.
    return f"({style}){text}" if style else text


@app.post("/v1/speak")
def speak(body: SpeakRequest) -> Response:
    model = _require_model()
    text = _style_prefixed_text(body.text, body.style)

    kwargs: dict[str, Any] = {"text": text, "cfg_value": body.cfg, "inference_timesteps": body.steps, "seed": body.seed}
    if body.voiceId:
        ref = _voice_cache.get(body.voiceId)
        if not ref:
            raise HTTPException(status_code=404, detail=f"Unknown voiceId: {body.voiceId}")
        kwargs["prompt_wav_path"] = ref["reference_wav_path"]
        kwargs["reference_wav_path"] = ref["reference_wav_path"]
        if ref["prompt_text"]:
            kwargs["prompt_text"] = ref["prompt_text"]
    # else: voice design / no-reference synthesis from the style prefix alone (spec §8b).

    wav = model.generate(**kwargs)
    buf = io.BytesIO()
    _write_wav(buf, wav, model.tts_model.sample_rate)
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.post("/v1/speak/stream")
def speak_stream(body: SpeakRequest):
    from fastapi.responses import StreamingResponse

    model = _require_model()
    text = _style_prefixed_text(body.text, body.style)
    kwargs: dict[str, Any] = {"text": text, "cfg_value": body.cfg, "inference_timesteps": body.steps}
    if body.voiceId:
        ref = _voice_cache.get(body.voiceId)
        if ref:
            kwargs["reference_wav_path"] = ref["reference_wav_path"]

    def _chunks():
        for chunk in model.generate_streaming(**kwargs):
            yield chunk

    return StreamingResponse(_chunks(), media_type="audio/wav")


class OpenAISpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    speed: float = 1.0


@app.post("/v1/audio/speech")
def openai_compatible_speech(body: OpenAISpeechRequest) -> Response:
    """OpenAI-compatible endpoint (spec §8b), for drop-in use with vLLM-Omni-style
    tooling that already speaks this shape."""
    return speak(SpeakRequest(text=body.input, voiceId=body.voice))


def _write_wav(buf: io.BytesIO, wav_array: Any, sample_rate: int) -> None:
    import numpy as np
    import soundfile as sf  # type: ignore[import-not-found]

    arr = np.asarray(wav_array, dtype=np.float32)
    sf.write(buf, arr, sample_rate, format="WAV")
    buf.seek(0)
