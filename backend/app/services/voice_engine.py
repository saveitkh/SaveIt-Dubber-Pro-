"""Acoustic speaker-identity engine, ported from the reference repo's
`scripts/voice_split_offline.py` (VAD by rolling-noise-floor RMS, 13-MFCC +
median-pitch + voiced-ratio features, Ward agglomerative clustering with
silhouette-scored auto-k). Kept as library functions operating on in-memory
numpy arrays (the original was a CLI that read/wrote wav files) so it composes
with the job pipeline: stage 4 (diarize) cross-checks Gemini's speaker labels
against this, stage 5 (cast) picks reference clips with it, and the Voice Clip
screen (spec §4.1) uses it directly on an arbitrary upload.

CAVEAT (unchanged from the reference): acoustic-feature clustering, not true
speaker recognition. Works best when speakers differ in pitch/timbre and
dialogue is louder than background music.
"""

import os
import subprocess
import tempfile
import wave

import numpy as np
from scipy.fftpack import dct
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

FRAME_LEN = 400  # 25ms @ 16kHz
HOP_LEN = 160  # 10ms @ 16kHz
SAMPLE_RATE = 16000


def decode_to_wav(src_path: str, wav_path: str, sr: int = SAMPLE_RATE) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", src_path, "-ac", "1", "-ar", str(sr), wav_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def load_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return data, sr


def write_wav(path: str, data: np.ndarray, sr: int) -> None:
    data = np.clip(data, -1, 1)
    pcm = (data * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def load_audio_16k_mono(path: str) -> tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable file to 16kHz mono for feature extraction,
    regardless of its actual sample rate/channel layout (e.g. the 44.1kHz
    stereo tracks `services/vocal_separator.py` produces)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        decode_to_wav(path, tmp_path, sr=SAMPLE_RATE)
        return load_wav(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def detect_speech_segments(
    audio: np.ndarray, sr: int, margin_db: float = 6.0, min_dur: float = 0.35,
    merge_gap: float = 0.25, max_dur: float = 6.0,
) -> list[tuple[float, float]]:
    frame_len = int(0.025 * sr)
    hop_len = int(0.010 * sr)
    n_frames = 1 + (len(audio) - frame_len) // hop_len
    if n_frames < 1:
        return []
    idx = np.arange(frame_len)[None, :] + hop_len * np.arange(n_frames)[:, None]
    frames = audio[idx]

    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    rms_db = 20 * np.log10(rms + 1e-9)

    win_frames = int(3.0 / 0.010)
    half = win_frames // 2
    pad = np.pad(rms_db, (half, half), mode="edge")
    floor = np.array([np.percentile(pad[i : i + win_frames], 25) for i in range(len(rms_db))])

    mask = rms_db > (floor + margin_db)

    segs: list[list[int]] = []
    in_seg, start = False, 0
    for i, m in enumerate(mask):
        if m and not in_seg:
            in_seg, start = True, i
        elif not m and in_seg:
            in_seg = False
            segs.append([start, i])
    if in_seg:
        segs.append([start, len(mask)])

    gap_frames = int(merge_gap / 0.010)
    merged: list[list[int]] = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= gap_frames:
            merged[-1][1] = s[1]
        else:
            merged.append(s)

    min_frames = int(min_dur / 0.010)
    max_frames = int(max_dur / 0.010)
    out: list[tuple[int, int]] = []
    for s, e in merged:
        if e - s < min_frames:
            continue
        while e - s > max_frames:
            out.append((s, s + max_frames))
            s += max_frames
        out.append((s, e))

    return [(s * hop_len / sr, e * hop_len / sr) for s, e in out]


def _mel_filterbank(sr: int, n_fft: int = 512, n_mels: int = 26, low: float = 50) -> np.ndarray:
    def hz2mel(f: float) -> float:
        return 2595 * np.log10(1 + f / 700)

    def mel2hz(m: np.ndarray) -> np.ndarray:
        return 700 * (10 ** (m / 2595) - 1)

    pts = np.linspace(hz2mel(low), hz2mel(sr / 2), n_mels + 2)
    hz = mel2hz(pts)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, b):
            if b > a:
                fb[m - 1, k] = (k - a) / (b - a)
        for k in range(b, c):
            if c > b:
                fb[m - 1, k] = (c - k) / (c - b)
    return fb


def _mfcc(sig: np.ndarray, fbank: np.ndarray, n_fft: int = 512, n_mfcc: int = 13) -> np.ndarray:
    window = np.hamming(FRAME_LEN)
    n = len(sig)
    if n < FRAME_LEN:
        sig = np.pad(sig, (0, FRAME_LEN - n))
        n = len(sig)
    n_fr = 1 + (n - FRAME_LEN) // HOP_LEN
    if n_fr < 1:
        return np.zeros((1, n_mfcc))
    idx = np.arange(FRAME_LEN)[None, :] + HOP_LEN * np.arange(n_fr)[:, None]
    fr = sig[idx] * window
    mag = np.abs(np.fft.rfft(fr, n=n_fft, axis=1))
    power = (mag**2) / n_fft
    mel = np.maximum(power @ fbank.T, np.finfo(float).eps)
    return dct(np.log(mel), type=2, axis=1, norm="ortho")[:, :n_mfcc]


def _pitch(sig: np.ndarray, sr: int, fmin: float = 70, fmax: float = 400) -> tuple[float, float]:
    window = np.hamming(FRAME_LEN)
    n_fr = 1 + (len(sig) - FRAME_LEN) // HOP_LEN
    if n_fr < 1:
        return 0.0, 0.0
    lag_min, lag_max = int(sr / fmax), int(sr / fmin)
    pitches = []
    for i in range(n_fr):
        fr = sig[i * HOP_LEN : i * HOP_LEN + FRAME_LEN] * window
        fr = fr - fr.mean()
        if np.max(np.abs(fr)) < 1e-4:
            continue
        ac = np.correlate(fr, fr, mode="full")[len(fr) - 1 :]
        if lag_max >= len(ac) or ac[0] <= 0:
            continue
        seg = ac[lag_min:lag_max]
        if len(seg) == 0:
            continue
        p = np.argmax(seg)
        if seg[p] / ac[0] > 0.3:
            lag = lag_min + p
            if lag > 0:
                pitches.append(sr / lag)
    if not pitches:
        return 0.0, 0.0
    return float(np.median(pitches)), float(len(pitches) / n_fr)


def segment_fingerprint(audio: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    """28-dim feature vector for one time span: 13 MFCC means, 13 MFCC stds,
    median pitch (Hz), voiced-frame ratio. The same vector space Character/Voice
    fingerprints live in, so cosine similarity across projects (series memory,
    spec §4.3) and within a project (cluster assignment) both just work."""
    fbank = _mel_filterbank(sr)
    sig = audio[int(start * sr) : int(end * sr)]
    m = _mfcc(sig, fbank)
    p_med, v_ratio = _pitch(sig, sr)
    return np.concatenate([m.mean(0), m.std(0), [p_med, v_ratio]])


def extract_features(
    audio: np.ndarray, sr: int, segments: list[tuple[float, float]]
) -> np.ndarray:
    return np.array([segment_fingerprint(audio, sr, s, e) for s, e in segments])


def cluster_segments(
    feats: np.ndarray, k: int | None = None, k_range: tuple[int, int] = (2, 6)
) -> tuple[np.ndarray, int, float | None]:
    """Ward-linkage agglomerative clustering; auto-picks k in k_range by best
    silhouette score unless k is forced."""
    x = StandardScaler().fit_transform(feats)
    n_samples = len(feats)
    if k:
        k = min(k, n_samples)
        return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(x), k, None

    hi = min(k_range[1], n_samples - 1)
    if hi < k_range[0]:
        return np.zeros(n_samples, dtype=int), 1, None

    best_labels, best_score, best_k = None, -2.0, k_range[0]
    for kk in range(k_range[0], hi + 1):
        labels = AgglomerativeClustering(n_clusters=kk, linkage="ward").fit_predict(x)
        try:
            score = silhouette_score(x, labels)
        except ValueError:
            score = -2.0
        if score > best_score:
            best_labels, best_score, best_k = labels, score, kk
    return best_labels, best_k, best_score


# Per-dimension scale for fingerprint_similarity: the raw vector is [13 MFCC
# means, 13 MFCC stds, pitch Hz, voiced ratio]. Pitch sits in the 70-400 range
# while MFCCs are typically single digits, so an unscaled cosine similarity is
# dominated by pitch almost alone — two acoustically different voices at a
# similar pitch would wrongly score as near-identical. Dividing each block by
# its typical magnitude brings them to comparable scale before comparing.
_FINGERPRINT_SCALE = np.concatenate([np.full(13, 15.0), np.full(13, 8.0), [150.0], [1.0]])


def fingerprint_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity on scale-normalized fingerprints, used for series voice
    memory (spec §4.3): does this project's new character sound like a voice
    already in the series library?"""
    a, b = a / _FINGERPRINT_SCALE, b / _FINGERPRINT_SCALE
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
