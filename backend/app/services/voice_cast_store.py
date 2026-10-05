"""Reference-clip selection for auto-cast (spec §3 stage 5 / §4.1): for a character,
pick its cleanest 8-20s of lines from the vocals track and stitch them into one
reference clip for cloning. Trimmed/adapted from the reference repo's
`services/voice_cast_store.py` concept — SQLite-backed here instead of JSON files.
"""

import os

from app.services import ffmpeg_tools

MIN_TOTAL_SECONDS = 1.5  # below this, cloning quality is too poor to attempt
TARGET_TOTAL_SECONDS = 15.0
MIN_CLIP_SECONDS = 0.8  # shorter lines are usually noise/interjections, not useful


async def build_reference_clip(
    vocals_path: str, line_spans: list[tuple[float, float]], out_path: str
) -> tuple[str | None, float]:
    """Returns (path, total_seconds); path is None when there isn't enough usable
    audio to clone from (caller should fall back to a stock voice and flag
    low_clone_quality, spec §6)."""
    usable = sorted(
        (span for span in line_spans if span[1] - span[0] >= MIN_CLIP_SECONDS),
        key=lambda s: s[1] - s[0],
        reverse=True,
    )
    if not usable:
        return None, 0.0

    picked: list[tuple[float, float]] = []
    total = 0.0
    for start, end in usable:
        if total >= TARGET_TOTAL_SECONDS:
            break
        picked.append((start, end))
        total += end - start

    if total < MIN_TOTAL_SECONDS:
        return None, total

    # Stitch in chronological order so phoneme transitions at clip boundaries stay
    # as natural as possible.
    picked.sort(key=lambda s: s[0])
    tmp_dir = os.path.dirname(out_path)
    os.makedirs(tmp_dir, exist_ok=True)
    clip_paths = []
    for i, (start, end) in enumerate(picked):
        clip_path = os.path.join(tmp_dir, f"_ref_clip_{i}.wav")
        await ffmpeg_tools.trim_clip(vocals_path, start, end, clip_path)
        clip_paths.append(clip_path)

    await ffmpeg_tools.concat_audio(clip_paths, out_path)
    for clip_path in clip_paths:
        if os.path.exists(clip_path):
            os.remove(clip_path)

    return out_path, total
