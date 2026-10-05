"""Chunked transcription+translation over a full audio track: splits into ~90s chunks
with 5s overlap, calls Gemini per chunk in parallel, offsets timestamps back to the full
track, and de-duplicates lines that both chunks saw in the overlap window. Ported
(trimmed) from the reference `khmer_dubber.extract_dialogue_timeline`.
"""

import asyncio
import os
import subprocess
from collections.abc import Callable

from app.services import gemini_client

CHUNK_SECONDS = 90.0
OVERLAP_SECONDS = 5.0


def _chunk_bounds(total_duration: float) -> list[tuple[float, float]]:
    bounds = []
    start = 0.0
    step = CHUNK_SECONDS - OVERLAP_SECONDS
    while start < total_duration:
        end = min(start + CHUNK_SECONDS, total_duration)
        bounds.append((start, end))
        if end >= total_duration:
            break
        start += step
    return bounds or [(0.0, total_duration)]


def _extract_chunk(audio_path: str, start: float, end: float, out_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-ss", str(start), "-to", str(end), "-i", audio_path,
         "-ar", "16000", "-ac", "1", out_path],
        check=True, capture_output=True,
    )


def _dedupe(lines: list[dict]) -> list[dict]:
    lines = sorted(lines, key=lambda line: line["start_time"])
    kept: list[dict] = []
    for line in lines:
        overlaps_prev = kept and line["start_time"] < kept[-1]["end_time"] - 0.5
        same_text = overlaps_prev and kept[-1]["source_text"].strip() == line["source_text"].strip()
        if same_text:
            continue
        kept.append(line)
    return kept


async def extract_dialogue_timeline(
    audio_path: str,
    total_duration: float,
    api_key: str,
    tmp_dir: str,
    on_progress: Callable[[float], None] | None = None,
) -> list[dict]:
    os.makedirs(tmp_dir, exist_ok=True)
    bounds = _chunk_bounds(total_duration)
    all_lines: list[dict] = []

    for idx, (start, end) in enumerate(bounds):
        chunk_path = os.path.join(tmp_dir, f"chunk_{idx}.wav")
        await asyncio.to_thread(_extract_chunk, audio_path, start, end, chunk_path)
        try:
            raw_lines = await gemini_client.transcribe_chunk(chunk_path, api_key, mime_type="audio/wav")
        finally:
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

        for line in raw_lines:
            try:
                line_start = start + float(line.get("start_time", 0))
                line_end = start + float(line.get("end_time", 0))
            except (TypeError, ValueError):
                continue
            if line_end <= line_start:
                continue
            all_lines.append({
                "speaker_id": str(line.get("speaker_id") or "speaker_1"),
                "speaker_name": line.get("speaker_name") or "",
                "gender": line.get("gender") or "unknown",
                "start_time": min(line_start, total_duration),
                "end_time": min(line_end, total_duration),
                "source_text": (line.get("source_text") or "").strip(),
                "khmer_translation": (line.get("khmer_translation") or "").strip(),
                "emotion": line.get("emotion") or "neutral",
            })

        if on_progress:
            on_progress((idx + 1) / len(bounds) * 100.0)

    return _dedupe(all_lines)
