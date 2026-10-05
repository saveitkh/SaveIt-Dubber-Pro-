"""Stock Khmer TTS via edge-tts (free, no API key — Microsoft's public Khmer neural
voices). Used for unlicensed users and as the speak-stage default until voice cloning
(VoxCPM2/ElevenLabs, M3) is wired in, per spec §3/§8: "Unlicensed users get the same
pipeline with stock Khmer AI voices — never a blocked or half-finished job."

Beyond a flat read, each line is performed: Gemini's per-line `emotion` (spec §3 stage
3) drives rate/pitch/volume, the line is split into clauses at Khmer sentence/clause
punctuation so a short breath-pause falls between them (longer for sad/fearful,
shorter for angry/excited — a plain TTS read has none of this), and the original
vocal's loudness at that moment nudges the Khmer delivery's volume up or down so a
shouted line stays loud and a hushed line stays hushed, even though the language and
the voice itself are different (spec §8b's "Ultimate cloning" does real prosody
transfer from a reference clip; this is the stock-voice approximation of the same
idea using only rate/pitch/volume + pacing, until VoxCPM2 cloning lands in M3).
"""

import os
import re
import shutil
import tempfile

import edge_tts

from app.services import ffmpeg_tools

MALE_VOICE = "km-KH-PisethNeural"
FEMALE_VOICE = "km-KH-SreymomNeural"

_RATE_CLAMP = (-40, 60)
_VOLUME_CLAMP = (-40, 40)
_PITCH_CLAMP_HZ = (-40, 40)

# rate/volume/pitch are deltas from the voice's neutral delivery; pause_ms is the
# breath gap inserted between clauses of a line carrying that emotion.
_EMOTION_PROSODY: dict[str, dict[str, int]] = {
    "neutral": {"rate": 0, "volume": 0, "pitch": 0, "pause_ms": 220},
    "happy": {"rate": 8, "volume": 5, "pitch": 20, "pause_ms": 150},
    "sad": {"rate": -14, "volume": -6, "pitch": -15, "pause_ms": 420},
    "angry": {"rate": 10, "volume": 14, "pitch": 10, "pause_ms": 110},
    "fearful": {"rate": 6, "volume": -4, "pitch": 15, "pause_ms": 320},
    "excited": {"rate": 16, "volume": 9, "pitch": 25, "pause_ms": 100},
}

_CLAUSE_SPLIT = re.compile(r"(?<=[។៕!?…,])\s+")


def voice_for_gender(gender: str | None) -> str:
    return FEMALE_VOICE if (gender or "").lower() == "female" else MALE_VOICE


def _clamp(value: float, bounds: tuple[int, int]) -> int:
    return int(max(bounds[0], min(bounds[1], value)))


def _signed_percent(value: int) -> str:
    return f"{'+' if value >= 0 else ''}{value}%"


def _signed_hz(value: int) -> str:
    return f"{'+' if value >= 0 else ''}{value}Hz"


def _split_clauses(text: str) -> list[str]:
    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(text) if c.strip()]
    return clauses or [text.strip()]


async def _synth_clause(text: str, voice: str, out_path: str, rate: int, volume: int, pitch: int) -> None:
    communicate = edge_tts.Communicate(
        text, voice,
        rate=_signed_percent(rate), volume=_signed_percent(volume), pitch=_signed_hz(pitch),
    )
    await communicate.save(out_path)


async def synthesize_line(text: str, voice: str, out_path: str, rate_percent: int = 0) -> None:
    """Flat single-pass synthesis (no emotion/breath shaping) — kept for callers that
    just need a quick read, e.g. Voice Clip previews in M3."""
    await _synth_clause(text, voice, out_path, _clamp(rate_percent, _RATE_CLAMP), 0, 0)


async def synthesize_expressive(
    text: str, voice: str, out_path: str, emotion: str = "neutral", energy_db: float | None = None
) -> None:
    """Perform `text` instead of reading it flat: per-emotion rate/pitch/volume, a
    breath pause between clauses, and an optional volume nudge toward `energy_db`
    (the original line's measured loudness, from `ffmpeg_tools.measure_segment_mean_volume`
    on the separated vocals track)."""
    prosody = _EMOTION_PROSODY.get(emotion, _EMOTION_PROSODY["neutral"])
    volume = prosody["volume"]
    if energy_db is not None:
        # -20dB is a reasonable "average speech" baseline for the DSP/Demucs vocals
        # track; each dB above/below it nudges the Khmer line louder/softer.
        volume = _clamp(volume + (energy_db - (-20.0)) * 4, _VOLUME_CLAMP)
    rate = _clamp(prosody["rate"], _RATE_CLAMP)
    pitch = _clamp(prosody["pitch"], _PITCH_CLAMP_HZ)
    pause_sec = prosody["pause_ms"] / 1000.0

    clauses = _split_clauses(text)
    with tempfile.TemporaryDirectory(prefix="tts_expr_") as tmp_dir:
        clips: list[str] = []
        silence_path = os.path.join(tmp_dir, "pause.wav")
        if len(clauses) > 1:
            await ffmpeg_tools.silence_clip(silence_path, pause_sec)

        for i, clause in enumerate(clauses):
            clip_path = os.path.join(tmp_dir, f"clause_{i}.mp3")
            await _synth_clause(clause, voice, clip_path, rate, volume, pitch)
            clips.append(clip_path)
            if i < len(clauses) - 1:
                clips.append(silence_path)

        await ffmpeg_tools.concat_audio(clips, out_path)


async def synthesize_fit_to_slot(
    text: str,
    voice: str,
    out_path: str,
    slot_seconds: float,
    tmp_path: str,
    emotion: str = "neutral",
    energy_db: float | None = None,
) -> tuple[bool, float]:
    """Perform `text` (see `synthesize_expressive`) and squeeze/stretch it to fit
    `slot_seconds` if needed. Returns (fit_ok, final_duration) — fit_ok is False when
    even the atempo limit (0.5x-2.0x) can't make it fit, which the caller should flag
    as a slot_overflow review item (spec §6)."""
    await synthesize_expressive(text, voice, tmp_path, emotion=emotion, energy_db=energy_db)
    duration = ffmpeg_tools.probe_duration(tmp_path)

    if slot_seconds <= 0 or abs(duration - slot_seconds) < 0.15:
        if tmp_path != out_path:
            shutil.move(tmp_path, out_path)
        return True, duration

    factor = duration / slot_seconds
    await ffmpeg_tools.atempo(tmp_path, out_path, factor)
    final_duration = ffmpeg_tools.probe_duration(out_path)
    fit_ok = 0.5 <= factor <= 2.0
    return fit_ok, final_duration
