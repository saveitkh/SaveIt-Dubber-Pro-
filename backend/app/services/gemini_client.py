"""Gemini transcription + translation, ported (and trimmed) from the reference repo's
`services/gemini_client.py` + `services/khmer_dubber.py` (`transcribe_chunk_with_gemini`).

Sends an audio chunk inline and asks for diarized, translated, emotion-tagged lines as
JSON. Model auto-discovery (`candidate_models`/`ListModels`) from the reference is
dropped for M2 in favour of one configurable model name — add it back in M5 if a given
key can't use `gemini-flash-latest`.
"""

import asyncio
import base64
import json
import re

import httpx

# Gemini returns 429 (quota) and 503 (transient overload) under normal load; a
# single retry-with-backoff absorbs most of these rather than failing the whole
# chunk (and, upstream, the whole transcribe stage).
_TRANSIENT_STATUS = {429, 503}
_RETRY_DELAYS = (2, 6, 15)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-flash-latest"

PROMPT = """You are a professional film dubbing director and translator specialized in \
Cambodian Khmer theatrical dubbing. Listen to this audio clip carefully — even over \
background music or sound effects — and extract every spoken dialogue line.

CRITICAL LANGUAGE RULE: 'khmer_translation' must be 100% authentic Khmer script \
(ភាសាខ្មែរ). Never include Thai, Vietnamese, or Chinese characters.

For each line, identify:
- speaker_id: a stable short id for this speaker within the clip (e.g. "speaker_1")
- speaker_name: a short descriptive name if inferable, else the speaker_id
- gender: "male" | "female" | "unknown"
- start_time / end_time: seconds relative to the start of this clip, decimal precision
- source_text: the original spoken line, transcribed in its source language/script
- khmer_translation: a natural, theatrical Khmer translation matching the original \
line's length and rhythm closely enough to fit the same time slot
- emotion: one of neutral, happy, sad, angry, fearful, excited

Return ONLY a JSON array in a ```json code block, no other text:
```json
[
  {"speaker_id": "speaker_1", "speaker_name": "", "gender": "male",
   "start_time": 1.25, "end_time": 4.10, "source_text": "...",
   "khmer_translation": "...", "emotion": "neutral"}
]
```
If there is no speech in this clip, return an empty array `[]`.
"""


class GeminiError(RuntimeError):
    pass


async def transcribe_chunk(
    chunk_path: str, api_key: str, model: str = DEFAULT_MODEL, mime_type: str = "audio/wav"
) -> list[dict]:
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not configured")

    with open(chunk_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    url = f"{API_ROOT}/models/{model}:generateContent"
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
            ]
        }]
    }

    resp = None
    async with httpx.AsyncClient(timeout=90) as client:
        for delay in (*_RETRY_DELAYS, None):
            resp = await client.post(url, headers={"x-goog-api-key": api_key}, json=payload)
            if resp.status_code == 200 or resp.status_code not in _TRANSIENT_STATUS or delay is None:
                break
            await asyncio.sleep(delay)

    if resp.status_code != 200:
        raise GeminiError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return []

    match = re.search(r"```json\s*([\s\S]*?)\s*```", raw)
    json_str = match.group(1) if match else raw
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
