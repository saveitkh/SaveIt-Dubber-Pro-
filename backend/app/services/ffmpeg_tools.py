"""Thin ffmpeg/ffprobe wrappers used by the pipeline stages.

Ported from the reference repo's `services/audio_processor.py` (`get_media_duration`,
`extract_audio`, `merge_video_audio`) but trimmed to what M2 needs; the overlay/
commercial-overlay and effects paths from that file are dropped per docs/PLAN.md.
"""

import asyncio
import json
import re
import subprocess


async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}\n{stderr.decode(errors='ignore')[-2000:]}")


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


async def extract_audio(src_path: str, out_wav_path: str, sample_rate: int = 16000) -> None:
    await _run([
        "ffmpeg", "-y", "-i", src_path, "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-acodec", "pcm_s16le", out_wav_path,
    ])


async def make_proxy(src_path: str, out_mp4_path: str, height: int = 720) -> None:
    await _run([
        "ffmpeg", "-y", "-i", src_path,
        "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "26", "-c:a", "aac", "-b:a", "128k", out_mp4_path,
    ])


def has_video_stream(path: str) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return bool(json.loads(out.stdout).get("streams"))


async def mux_video_audio(video_path: str, audio_path: str, out_path: str) -> None:
    """Replace a video's audio track; audio-only sources are passed through untouched."""
    if not has_video_stream(video_path):
        await _run(["ffmpeg", "-y", "-i", audio_path, "-c:a", "libmp3lame", "-q:a", "2", out_path])
        return
    await _run([
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", out_path,
    ])


async def to_mp3(src_audio_path: str, out_mp3_path: str) -> None:
    await _run(["ffmpeg", "-y", "-i", src_audio_path, "-c:a", "libmp3lame", "-q:a", "2", out_mp3_path])


async def measure_segment_mean_volume(path: str, start: float, end: float) -> float | None:
    """Mean loudness (dBFS) of a time span in an audio file, via ffmpeg's `volumedetect`.
    Used to nudge the Khmer TTS line's volume/energy toward how loud the original
    performance was at that moment — a cheap stand-in for real prosody transfer until
    VoxCPM2 cloning (M3) carries the original performance directly."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-y", "-ss", str(max(0.0, start)), "-to", str(max(0.0, end)),
        "-i", path, "-af", "volumedetect", "-f", "null", "-",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", stderr.decode(errors="ignore"))
    return float(match.group(1)) if match else None


async def concat_audio(clip_paths: list[str], out_path: str) -> None:
    """Concatenate audio clips (re-encoding via filter_complex, safe across mismatched
    source formats — unlike the concat demuxer's `-c copy`, which is picky about
    identical codec params across inputs)."""
    if len(clip_paths) == 1:
        await _run(["ffmpeg", "-y", "-i", clip_paths[0], "-ar", "44100", "-ac", "2", out_path])
        return
    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", p]
    concat_inputs = "".join(f"[{i}:a]" for i in range(len(clip_paths)))
    filter_complex = f"{concat_inputs}concat=n={len(clip_paths)}:v=0:a=1[out]"
    await _run(["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[out]", out_path])


async def silence_clip(out_path: str, duration_sec: float) -> None:
    await _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"anullsrc=channel_layout=stereo:sample_rate=44100:d={max(duration_sec, 0.01):.3f}",
        out_path,
    ])


async def atempo(src_path: str, out_path: str, factor: float) -> None:
    """Speed up/slow down audio without changing pitch. ffmpeg's atempo filter is limited
    to 0.5-2.0 per instance, so chain two filters for more extreme factors."""
    factor = max(0.4, min(2.5, factor))
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    await _run(["ffmpeg", "-y", "-i", src_path, "-filter:a", ",".join(filters), out_path])
