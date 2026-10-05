"""Smart background bed + final mix, ported (trimmed) from the reference repo's
`services/audio_processor.py` (`build_smart_bed`, `auto_mix_gains`, `mix_vocals_with_original`).

Rule from spec §3/§7: original soundtrack 100% where nobody speaks, separated
background under dialogue, automatic loudness gain so dialogue always reads clearly.
"""

import asyncio
import subprocess


async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mix failed: {' '.join(cmd)}\n{stderr.decode(errors='ignore')[-2000:]}")


def _duck_expr(line_spans: list[tuple[float, float]], duck_level: float) -> str:
    """ffmpeg `volume` filter with per-span gain, chained via `enable=between(t,s,e)`."""
    if not line_spans:
        return "volume=1.0"
    parts = [f"volume={duck_level}:enable='between(t,{s:.3f},{e:.3f})'" for s, e in line_spans]
    return ",".join(parts)


async def build_background_bed(
    background_or_original_path: str,
    line_spans: list[tuple[float, float]],
    out_path: str,
    duck_level: float = 0.22,
) -> None:
    """Background track at full volume except under dialogue spans, where it ducks."""
    await _run([
        "ffmpeg", "-y", "-i", background_or_original_path,
        "-af", _duck_expr(line_spans, duck_level),
        "-ar", "44100", "-ac", "2", out_path,
    ])


async def build_dialogue_track(
    line_audio_paths: list[tuple[float, str]], total_duration: float, out_path: str
) -> None:
    """Overlay each line's synthesized clip at its start time onto a silent base track
    the length of the whole project, via ffmpeg adelay+amix."""
    if not line_audio_paths:
        await _run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=44100:d={max(total_duration, 0.1):.3f}",
            out_path,
        ])
        return

    inputs: list[str] = []
    filters: list[str] = []
    for i, (start_sec, path) in enumerate(line_audio_paths):
        inputs += ["-i", path]
        delay_ms = max(0, int(start_sec * 1000))
        filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},apad[a{i}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(line_audio_paths)))
    filter_complex = ";".join(filters) + f";{mix_inputs}amix=inputs={len(line_audio_paths)}:normalize=0[out]"

    await _run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex, "-map", "[out]",
        "-t", f"{max(total_duration, 0.1):.3f}",
        "-ar", "44100", "-ac", "2", out_path,
    ])


async def mix_dialogue_and_background(dialogue_path: str, background_path: str, out_path: str) -> None:
    """Combine the two beds and auto-normalize loudness (single-pass loudnorm —
    the reference repo's two-pass `measure_lufs` + target-gain approach is deferred
    to M5 when real-world mixes need the extra precision)."""
    await _run([
        "ffmpeg", "-y", "-i", dialogue_path, "-i", background_path,
        "-filter_complex",
        "[0:a]volume=1.6[dlg];[dlg][1:a]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[out]",
        "-map", "[out]", "-ar", "44100", "-ac", "2", out_path,
    ])
