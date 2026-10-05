"""HTTP client for the VoxCPM2 engine (spec §8b) — the main studio app's half of
the `voxcpm_engine/` API. First-priority TTS provider in the fallback chain
(VoxCPM2 -> ElevenLabs -> stock, spec §8); unreachable/misconfigured raises
VoxCPMError so the caller falls through to the next provider rather than failing
the job (spec §3: "never a blocked or half-finished job").
"""

import httpx


class VoxCPMError(RuntimeError):
    pass


# Emotion -> the "(...)" English style prefix VoxCPM2 reads as a performance
# direction (spec §8b) — never shown to the user; the Khmer text itself stays clean.
EMOTION_STYLE = {
    "neutral": "calm, conversational",
    "happy": "happy, warm, cheerful",
    "sad": "sad, slow, breathy",
    "angry": "angry, forceful, shouting",
    "fearful": "scared, shaky, nervous",
    "excited": "excited, energetic, slightly fast",
}


async def register_voice(base_url: str, reference_wav_path: str, transcript: str = "") -> str:
    """Upload a reference clip once per character; the engine caches its encoding
    (spec §8b "cache the reference encoding per character") and returns a voice_id
    reused across every line's /v1/speak call."""
    async with httpx.AsyncClient(timeout=60) as client:
        with open(reference_wav_path, "rb") as f:
            resp = await client.post(
                f"{base_url.rstrip('/')}/v1/voices",
                files={"file": (reference_wav_path.split("/")[-1], f, "audio/wav")},
                data={"transcript": transcript},
            )
    if resp.status_code != 200:
        raise VoxCPMError(f"VoxCPM2 /v1/voices HTTP {resp.status_code}: {resp.text[:300]}")
    voice_id = resp.json().get("voiceId")
    if not voice_id:
        raise VoxCPMError("VoxCPM2 /v1/voices response had no voiceId")
    return voice_id


async def speak(
    base_url: str, text: str, out_path: str, voice_id: str | None = None,
    style: str | None = None, seed: int = 42,
) -> None:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/v1/speak",
            json={"text": text, "voiceId": voice_id, "style": style, "seed": seed},
        )
    if resp.status_code != 200:
        raise VoxCPMError(f"VoxCPM2 /v1/speak HTTP {resp.status_code}: {resp.text[:300]}")
    with open(out_path, "wb") as f:
        f.write(resp.content)


async def check_status(base_url: str) -> dict:
    if not base_url:
        return {"ok": False, "reason": "no engine URL configured"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{base_url.rstrip('/')}/health")
        except httpx.HTTPError as exc:
            return {"ok": False, "reason": str(exc)}
    if resp.status_code != 200:
        return {"ok": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    if not data.get("model"):
        return {"ok": False, "reason": data.get("error", "model not loaded")}
    return {"ok": True, **data}
