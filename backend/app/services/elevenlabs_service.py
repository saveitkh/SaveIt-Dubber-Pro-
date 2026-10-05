"""ElevenLabs instant voice cloning + multilingual TTS, ported (trimmed) from the
reference repo's `services/elevenlabs_service.py`. One of the TTS providers in the
fallback chain (spec §8): VoxCPM2 (primary) -> ElevenLabs -> stock/Gemini TTS.

Network note: this talks to api.elevenlabs.io directly (httpx, async) — code-complete
and type-correct, but this development sandbox's egress policy blocks that host, so
the live calls below are unverified here; they follow the same request/response shape
the reference implementation already uses in production.
"""

import httpx

BASE_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsError(RuntimeError):
    pass


async def clone_voice(api_key: str, name: str, reference_audio_path: str, description: str = "") -> str:
    """Instant Voice Clone from a reference clip. Returns the new voice_id."""
    with open(reference_audio_path, "rb") as f:
        audio_bytes = f.read()

    files = {"files": (reference_audio_path.split("/")[-1], audio_bytes, "audio/mpeg")}
    data = {"name": name, "description": description or "SaveIt Dubber Pro cloned voice"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{BASE_URL}/voices/add", headers={"xi-api-key": api_key}, data=data, files=files)

    if resp.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs clone HTTP {resp.status_code}: {resp.text[:300]}")

    voice_id = resp.json().get("voice_id")
    if not voice_id:
        raise ElevenLabsError("ElevenLabs clone response had no voice_id")
    return voice_id


# emotion -> voice_settings; higher `style` leans into expressive delivery, lower
# `stability` allows more variation (closer to an excited/angry performance).
_EMOTION_SETTINGS: dict[str, dict[str, float]] = {
    "neutral": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.15},
    "happy": {"stability": 0.45, "similarity_boost": 0.85, "style": 0.35},
    "sad": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.25},
    "angry": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.5},
    "fearful": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.4},
    "excited": {"stability": 0.3, "similarity_boost": 0.85, "style": 0.5},
}


async def text_to_speech(
    api_key: str, voice_id: str, text: str, out_path: str, emotion: str = "neutral"
) -> None:
    settings = _EMOTION_SETTINGS.get(emotion, _EMOTION_SETTINGS["neutral"])
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {**settings, "use_speaker_boost": True},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE_URL}/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )

    if resp.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs TTS HTTP {resp.status_code}: {resp.text[:300]}")

    with open(out_path, "wb") as f:
        f.write(resp.content)


async def check_status(api_key: str) -> dict:
    """Used by the Providers page's Test button and /api/health."""
    if not api_key:
        return {"ok": False, "reason": "no API key configured"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{BASE_URL}/user/subscription", headers={"xi-api-key": api_key})
        except httpx.HTTPError as exc:
            return {"ok": False, "reason": str(exc)}
    if resp.status_code != 200:
        return {"ok": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    return {
        "ok": True,
        "tier": data.get("tier"),
        "characterCount": data.get("character_count"),
        "characterLimit": data.get("character_limit"),
    }
