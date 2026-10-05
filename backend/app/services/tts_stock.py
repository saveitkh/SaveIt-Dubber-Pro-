"""Stock Khmer TTS via edge-tts (free, no API key — Microsoft's public Khmer neural
voices). Used for unlicensed users and as the speak-stage default until voice cloning
(VoxCPM2/ElevenLabs, M3) is wired in, per spec §3/§8: "Unlicensed users get the same
pipeline with stock Khmer AI voices — never a blocked or half-finished job."
"""

import edge_tts

from app.services import ffmpeg_tools

MALE_VOICE = "km-KH-PisethNeural"
FEMALE_VOICE = "km-KH-SreymomNeural"

# edge-tts accepts a percentage rate adjustment directly, which avoids an extra
# ffmpeg atempo pass for the common case; atempo is still used to correct any
# residual slot mismatch after synthesis (TTS duration isn't fully predictable).
_RATE_CLAMP = (-40, 60)


def voice_for_gender(gender: str | None) -> str:
    return FEMALE_VOICE if (gender or "").lower() == "female" else MALE_VOICE


async def synthesize_line(
    text: str, voice: str, out_path: str, rate_percent: int = 0
) -> None:
    rate_percent = max(_RATE_CLAMP[0], min(_RATE_CLAMP[1], rate_percent))
    rate = f"{'+' if rate_percent >= 0 else ''}{rate_percent}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_path)


async def synthesize_fit_to_slot(
    text: str, voice: str, out_path: str, slot_seconds: float, tmp_path: str
) -> tuple[bool, float]:
    """Synthesize `text` and squeeze/stretch it to fit `slot_seconds` if needed.
    Returns (fit_ok, final_duration) — fit_ok is False when even the atempo limit
    (0.5x-2.0x) can't make it fit, which the caller should flag as a slot_overflow
    review item (spec §6)."""
    await synthesize_line(text, voice, tmp_path)
    duration = ffmpeg_tools.probe_duration(tmp_path)

    if slot_seconds <= 0 or abs(duration - slot_seconds) < 0.15:
        if tmp_path != out_path:
            import shutil

            shutil.move(tmp_path, out_path)
        return True, duration

    factor = duration / slot_seconds
    await ffmpeg_tools.atempo(tmp_path, out_path, factor)
    final_duration = ffmpeg_tools.probe_duration(out_path)
    fit_ok = 0.5 <= factor <= 2.0
    return fit_ok, final_duration
