"""Vocal/background separation: Demucs (htdemucs, GPU if available) with an ffmpeg DSP
fallback. Ported from the reference repo's `services/vocal_separator.py`; the DSP recipe
(keep the stereo centre but cut the speech band there, so effects/music under dialogue
survive while the original voices drop ~20dB) is unchanged.
"""

import asyncio
import os
import shutil
import subprocess
import sys

DSP_VERSION = "dsp2"


def has_demucs() -> bool:
    try:
        import demucs  # noqa: F401

        return True
    except ImportError:
        return False


async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{stderr.decode(errors='ignore')[-2000:]}")


async def separate_with_demucs(audio_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]

    await _run([
        sys.executable, "-m", "demucs.separate", "-n", "htdemucs", "--two-stems=vocals",
        "-o", output_dir, audio_path,
    ])

    demucs_dir = os.path.join(output_dir, "htdemucs", base_name)
    vocals_wav = os.path.join(demucs_dir, "vocals.wav")
    bgm_wav = os.path.join(demucs_dir, "no_vocals.wav")
    dest_vocals = os.path.join(output_dir, f"{base_name}_ai_vocals.wav")
    dest_bgm = os.path.join(output_dir, f"{base_name}_ai_bgm.wav")

    if os.path.exists(vocals_wav) and os.path.exists(bgm_wav):
        shutil.copyfile(vocals_wav, dest_vocals)
        shutil.copyfile(bgm_wav, dest_bgm)
        return {"engine": "meta-demucs-ai", "vocalsPath": dest_vocals, "bgmPath": dest_bgm}
    raise RuntimeError("Demucs outputs not found in expected folder")


async def separate_with_ffmpeg_fallback(audio_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    dest_vocals = os.path.join(output_dir, f"{base_name}_{DSP_VERSION}_vocals.wav")
    dest_bgm = os.path.join(output_dir, f"{base_name}_{DSP_VERSION}_bgm.wav")

    bgm_filter = (
        "[0:a]asplit=3[a1][a2][a3];"
        "[a1]lowpass=f=240[bass];"
        "[a2]stereotools=mlev=0.015625:slev=1.25,highpass=f=220,equalizer=f=1100:width_type=o:w=2.2:g=-10[sides];"
        "[a3]stereotools=mlev=1:slev=0.015625,highpass=f=220,"
        "equalizer=f=450:width_type=o:w=1.4:g=-16,"
        "equalizer=f=1100:width_type=o:w=1.4:g=-22,"
        "equalizer=f=2600:width_type=o:w=1.4:g=-18,volume=0.8[centre];"
        "[bass][sides][centre]amix=inputs=3:dropout_transition=0:normalize=0,alimiter=limit=0.95"
    )
    await _run([
        "ffmpeg", "-nostdin", "-y", "-i", audio_path, "-filter_complex", bgm_filter,
        "-ar", "44100", "-ac", "2", dest_bgm,
    ])

    vocal_filter = "stereotools=slev=0.015625:mlev=1.35,highpass=f=240,lowpass=f=3800"
    await _run([
        "ffmpeg", "-nostdin", "-y", "-i", audio_path, "-af", vocal_filter,
        "-ar", "44100", "-ac", "2", dest_vocals,
    ])

    return {"engine": "ffmpeg-dsp", "vocalsPath": dest_vocals, "bgmPath": dest_bgm}


async def separate_vocals_and_bgm(audio_path: str, output_dir: str, prefer_ai: bool = True) -> dict:
    if prefer_ai and has_demucs():
        try:
            return await separate_with_demucs(audio_path, output_dir)
        except Exception:  # noqa: BLE001 — fall through to the DSP recipe
            return await separate_with_ffmpeg_fallback(audio_path, output_dir)
    return await separate_with_ffmpeg_fallback(audio_path, output_dir)
