"""Waveform peaks for the timeline (spec §5.1: "Real waveforms (server-computed
peaks, cached)"). Decodes audio to raw PCM via ffmpeg, downsamples to a fixed number
of min/max buckets the frontend can draw directly onto a canvas/SVG at any zoom
level, and caches the result as JSON next to the source file.
"""

import json
import os
import subprocess

import numpy as np

PEAK_BUCKETS = 1200
DECODE_SAMPLE_RATE = 8000


def _cache_path(audio_path: str) -> str:
    base, _ = os.path.splitext(audio_path)
    return f"{base}.peaks.json"


def compute_peaks(audio_path: str) -> dict:
    cache_path = _cache_path(audio_path)
    if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= os.path.getmtime(audio_path):
        with open(cache_path) as f:
            return json.load(f)

    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", audio_path, "-f", "s16le",
         "-ac", "1", "-ar", str(DECODE_SAMPLE_RATE), "-"],
        capture_output=True, check=True,
    )
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        result = {"buckets": PEAK_BUCKETS, "sampleRate": DECODE_SAMPLE_RATE, "min": [], "max": []}
    else:
        bucket_size = max(1, len(samples) // PEAK_BUCKETS)
        n_buckets = max(1, len(samples) // bucket_size)
        trimmed = samples[: n_buckets * bucket_size].reshape(n_buckets, bucket_size)
        mins = trimmed.min(axis=1)
        maxs = trimmed.max(axis=1)
        result = {
            "buckets": n_buckets,
            "sampleRate": DECODE_SAMPLE_RATE,
            "durationSec": len(samples) / DECODE_SAMPLE_RATE,
            "min": [round(float(v), 4) for v in mins],
            "max": [round(float(v), 4) for v in maxs],
        }

    with open(cache_path, "w") as f:
        json.dump(result, f)
    return result
