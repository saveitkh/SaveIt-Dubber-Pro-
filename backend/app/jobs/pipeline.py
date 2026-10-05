"""Pipeline stage functions (spec §3).

Each stage caches its output on the `Project` row so re-running only redoes what
changed (spec rule: editing one line re-generates one line and re-mixes, nothing
else — partial re-runs land in M4). Without a Gemini key configured, `transcribe`
degrades to zero lines and a review item instead of failing the job, so a project
without providers still finishes as a straight passthrough of the original audio —
"never a blocked or half-finished job" (spec §3/§8).
"""

import asyncio
import os
import shutil
from collections import Counter
from collections.abc import Callable

import numpy as np
from sqlalchemy.orm import Session

from app.config import OUTPUTS_DIR, settings
from app.models import Character, Line, Project, ReviewItem, User, Voice
from app.services import (
    audio_mix,
    dubber,
    elevenlabs_service,
    ffmpeg_tools,
    subtitles,
    tts_stock,
    vocal_separator,
    voice_cast_store,
    voice_engine,
    voxcpm_client,
)

STAGES = ["prepare", "separate", "transcribe", "diarize", "cast", "speak", "mix", "export"]

ProgressFn = Callable[[float, str | None], None]

STAGE_LABELS = {
    "prepare": "កំពុងរៀបចំវីដេអូ…",
    "separate": "កំពុងញែកសំឡេង និងតន្ត្រី…",
    "transcribe": "កំពុងសម្រាយ និងបកប្រែជាខ្មែរ…",
    "diarize": "កំពុងកំណត់អ្នកនិយាយ…",
    "cast": "កំពុងជ្រើសសំឡេងសម្រាប់តួអង្គ…",
    "speak": "កំពុងបង្កើតសំឡេងខ្មែរ…",
    "mix": "កំពុងលាយសំឡេង…",
    "export": "កំពុងនាំចេញវីដេអូ…",
}


def _project_dir(project_id: str) -> str:
    d = os.path.join(OUTPUTS_DIR, project_id)
    os.makedirs(d, exist_ok=True)
    return d


async def stage_prepare(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["prepare"])
    pdir = _project_dir(project.id)
    project.duration_sec = ffmpeg_tools.probe_duration(project.source_path)
    on_progress(30, STAGE_LABELS["prepare"])

    audio_path = os.path.join(pdir, "audio.wav")
    await ffmpeg_tools.extract_audio(project.source_path, audio_path)
    project.audio_path = audio_path
    on_progress(70, STAGE_LABELS["prepare"])

    if ffmpeg_tools.has_video_stream(project.source_path):
        proxy_path = os.path.join(pdir, "proxy.mp4")
        await ffmpeg_tools.make_proxy(project.source_path, proxy_path)
        project.proxy_video_path = proxy_path
    db.commit()
    on_progress(100, STAGE_LABELS["prepare"])


async def stage_separate(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["separate"])
    pdir = os.path.join(_project_dir(project.id), "separated")
    result = await vocal_separator.separate_vocals_and_bgm(project.audio_path, pdir)
    project.vocals_path = result["vocalsPath"]
    project.background_path = result["bgmPath"]
    db.commit()
    on_progress(100, STAGE_LABELS["separate"])


async def stage_transcribe(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["transcribe"])
    api_key = settings.gemini_api_key

    # Clear any previous run's auto-generated lines/characters so a re-run from this
    # stage doesn't duplicate them (manual edits downstream are out of scope for M2's
    # full-pipeline run; partial re-runs that preserve edits land in M4).
    db.query(Line).filter(Line.project_id == project.id).delete()
    db.query(Character).filter(Character.project_id == project.id).delete()
    db.query(ReviewItem).filter(ReviewItem.project_id == project.id, ReviewItem.kind == "missed").delete()
    db.commit()

    if not api_key:
        db.add(ReviewItem(
            project_id=project.id, kind="missed",
            payload={"reason": "GEMINI_API_KEY is not configured — dub skipped, original audio kept"},
        ))
        db.commit()
        on_progress(100, STAGE_LABELS["transcribe"])
        return

    tmp_dir = os.path.join(_project_dir(project.id), "tmp_chunks")
    source_audio = project.vocals_path or project.audio_path
    try:
        raw_lines, failed_chunks = await dubber.extract_dialogue_timeline(
            source_audio, project.duration_sec or 0, api_key, tmp_dir,
            on_progress=lambda pct: on_progress(pct * 0.9, STAGE_LABELS["transcribe"]),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # A chunk Gemini couldn't transcribe (quota, transient 5xx after retries, …)
    # loses only its own time span, not the rest of the project (spec §3/§8: never
    # a blocked or half-finished job) — surfaced as a review item for that span.
    for start, end, error in failed_chunks:
        db.add(ReviewItem(
            project_id=project.id, kind="missed",
            payload={"reason": f"Gemini call failed for {start:.0f}s-{end:.0f}s: {error}"},
        ))

    characters: dict[str, Character] = {}
    palette = ["#f87171", "#fb923c", "#facc15", "#4ade80", "#38bdf8", "#818cf8", "#f472b6", "#a78bfa"]
    for line in raw_lines:
        speaker_id = line["speaker_id"]
        if speaker_id not in characters:
            character = Character(
                project_id=project.id,
                name=line["speaker_name"] or f"អ្នកនិយាយ {len(characters) + 1}",
                gender=line["gender"] if line["gender"] in ("male", "female") else None,
                color=palette[len(characters) % len(palette)],
            )
            db.add(character)
            db.flush()
            characters[speaker_id] = character
        character = characters[speaker_id]

        db_line = Line(
            project_id=project.id,
            character_id=character.id,
            start_sec=line["start_time"],
            end_sec=line["end_time"],
            source_text=line["source_text"],
            khmer_text=line["khmer_translation"],
            emotion=line["emotion"],
            flags=[],
        )
        if not line["khmer_translation"]:
            db_line.flags = ["missed"]
            db.add(ReviewItem(project_id=project.id, kind="missed", payload={"lineStart": line["start_time"]}))
        db.add(db_line)

    db.commit()
    on_progress(100, STAGE_LABELS["transcribe"])


async def stage_diarize(project: Project, db: Session, on_progress: ProgressFn) -> None:
    """Cross-checks Gemini's speaker split (stage 3) against the acoustic voice
    engine: cluster every line's audio span by MFCC+pitch, and flag any line whose
    acoustic cluster disagrees with the majority cluster of the character Gemini
    assigned it to as `unsure` (spec §6) — Gemini is good at *who said this* from
    context but can mislabel an unfamiliar voice; the acoustic signal catches that.
    Also computes each character's fingerprint (mean feature vector of its lines),
    used for cross-episode voice reuse in stage_cast (spec §4.3)."""
    on_progress(0, STAGE_LABELS["diarize"])
    lines = db.query(Line).filter(Line.project_id == project.id).order_by(Line.start_sec).all()
    characters = {c.id: c for c in db.query(Character).filter(Character.project_id == project.id).all()}
    source = project.vocals_path or project.audio_path

    if len(lines) < 2 or not source:
        on_progress(100, STAGE_LABELS["diarize"])
        return

    def _analyze() -> tuple[np.ndarray, np.ndarray]:
        audio, sr = voice_engine.load_audio_16k_mono(source)
        spans = [(line.start_sec, line.end_sec) for line in lines]
        feats = voice_engine.extract_features(audio, sr, spans)
        k_hint = len(characters) or None
        k_hi = min(8, len(lines))
        labels, _, _ = voice_engine.cluster_segments(feats, k=k_hint, k_range=(2, max(2, k_hi)))
        return feats, labels

    feats, labels = await asyncio.to_thread(_analyze)
    on_progress(60, STAGE_LABELS["diarize"])

    votes: dict[str, Counter] = {}
    for line, label in zip(lines, labels, strict=True):
        if line.character_id:
            votes.setdefault(line.character_id, Counter())[int(label)] += 1
    majority_cluster = {cid: c.most_common(1)[0][0] for cid, c in votes.items()}

    for line, label in zip(lines, labels, strict=True):
        if line.character_id and majority_cluster.get(line.character_id) != int(label) and "unsure" not in line.flags:
            line.flags = [*line.flags, "unsure"]
            db.add(ReviewItem(project_id=project.id, line_id=line.id, kind="unsure"))

    for cid, character in characters.items():
        idxs = [i for i, line in enumerate(lines) if line.character_id == cid]
        if idxs:
            character.fingerprint = np.mean(feats[idxs], axis=0).tolist()

    db.commit()
    on_progress(100, STAGE_LABELS["diarize"])


async def _find_series_voice_reuse(project: Project, character: Character, db: Session) -> Voice | None:
    """Series memory (spec §4.3): does this character sound like a voice already in
    the series library? Cross-episode, so episode 2's cast reuses episode 1's clones
    instead of cloning the same actor twice."""
    if not project.series_id or not character.fingerprint:
        return None
    candidates = (
        db.query(Voice)
        .filter(Voice.series_id == project.series_id, Voice.fingerprint.isnot(None))
        .all()
    )
    char_fp = np.array(character.fingerprint)
    best: tuple[Voice, float] | None = None
    for voice in candidates:
        sim = voice_engine.fingerprint_similarity(char_fp, np.array(voice.fingerprint))
        if sim > 0.985 and (best is None or sim > best[1]):
            best = (voice, sim)
    return best[0] if best else None


async def _try_clone(
    project: Project, character: Character, built_path: str, label: str
) -> Voice | None:
    """Provider fallback order for cloning itself (spec §8): VoxCPM2 first when an
    engine URL is configured, then ElevenLabs. Either failure is non-fatal — the
    caller falls back further to a stock voice."""
    if settings.voxcpm_url:
        try:
            voice_id = await voxcpm_client.register_voice(settings.voxcpm_url, built_path)
            voice = Voice(
                series_id=project.series_id, name=label, reference_path=built_path,
                fingerprint=character.fingerprint, provider_ids={"voxcpm": voice_id},
            )
            return voice
        except voxcpm_client.VoxCPMError:
            pass  # fall through to ElevenLabs

    if settings.elevenlabs_api_key:
        try:
            voice_id = await elevenlabs_service.clone_voice(settings.elevenlabs_api_key, label, built_path)
            return Voice(
                series_id=project.series_id, name=label, reference_path=built_path,
                fingerprint=character.fingerprint, provider_ids={"elevenlabs": voice_id},
            )
        except elevenlabs_service.ElevenLabsError:
            pass

    return None


async def stage_cast(project: Project, db: Session, on_progress: ProgressFn) -> None:
    """Auto-cast (spec §3 stage 5): reuse a series voice when this character's
    fingerprint matches one already cast; otherwise clone from its own lines
    (VoxCPM2 -> ElevenLabs, spec §8) when cloning is available and the project
    owner is licensed/admin; otherwise fall back to a stock voice — unlicensed
    users always get a working dub, never a blocked job (spec §3)."""
    on_progress(0, STAGE_LABELS["cast"])
    characters = db.query(Character).filter(Character.project_id == project.id).all()
    owner = db.get(User, project.owner_id)
    can_clone = (
        bool(settings.voxcpm_url or settings.elevenlabs_api_key)
        and owner is not None
        and (owner.is_licensed or owner.is_admin)
    )
    voices_dir = os.path.join(_project_dir(project.id), "voices")

    for i, character in enumerate(characters):
        if character.voice_id:
            continue

        reused = await _find_series_voice_reuse(project, character, db)
        if reused:
            character.voice_id = reused.id
            db.commit()
            on_progress((i + 1) / max(len(characters), 1) * 100.0, STAGE_LABELS["cast"])
            continue

        cloned = False
        if can_clone and project.vocals_path:
            lines = db.query(Line).filter(Line.character_id == character.id).all()
            spans = [(line.start_sec, line.end_sec) for line in lines]
            ref_path = os.path.join(voices_dir, f"{character.id}_ref.wav")
            built_path, total_sec = await voice_cast_store.build_reference_clip(project.vocals_path, spans, ref_path)
            if built_path:
                label = character.name or f"Character {i + 1}"
                voice = await _try_clone(project, character, built_path, label)
                if voice:
                    db.add(voice)
                    db.flush()
                    character.voice_id = voice.id
                    cloned = True
                else:
                    db.add(ReviewItem(
                        project_id=project.id, kind="low_clone_quality",
                        payload={"character": character.name, "reason": "cloning failed on every configured provider"},
                    ))
            else:
                db.add(ReviewItem(
                    project_id=project.id, kind="low_clone_quality",
                    payload={"character": character.name, "reason": f"only {total_sec:.1f}s of usable audio"},
                ))

        if not cloned and not character.stock_voice:
            character.stock_voice = tts_stock.voice_for_gender(character.gender)

        db.commit()
        on_progress((i + 1) / max(len(characters), 1) * 100.0, STAGE_LABELS["cast"])

    on_progress(100, STAGE_LABELS["cast"])


async def _fit_to_slot(tmp_path: str, out_path: str, slot_seconds: float) -> tuple[bool, float]:
    """Shared slot-fit step (spec §3 stage 6: "fitted to the line's time slot, speed-
    adjust, never overlap the next line") for whichever provider produced tmp_path."""
    duration = ffmpeg_tools.probe_duration(tmp_path)
    if slot_seconds <= 0 or abs(duration - slot_seconds) < 0.15:
        if tmp_path != out_path:
            import shutil as _shutil

            _shutil.move(tmp_path, out_path)
        return True, duration
    factor = duration / slot_seconds
    await ffmpeg_tools.atempo(tmp_path, out_path, factor)
    return 0.5 <= factor <= 2.0, ffmpeg_tools.probe_duration(out_path)


async def stage_speak(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["speak"])
    lines_dir = os.path.join(_project_dir(project.id), "lines")
    os.makedirs(lines_dir, exist_ok=True)

    lines = (
        db.query(Line)
        .filter(Line.project_id == project.id, Line.khmer_text != "")
        .order_by(Line.start_sec)
        .all()
    )
    for i, line in enumerate(lines):
        character = line.character
        out_path = os.path.join(lines_dir, f"{line.id}.mp3")
        tmp_path = os.path.join(lines_dir, f"{line.id}.raw.mp3")
        slot = max(0.0, line.end_sec - line.start_sec)

        provider_ids = (character.voice.provider_ids if character and character.voice else None) or {}
        voxcpm_voice_id = provider_ids.get("voxcpm")
        elevenlabs_voice_id = provider_ids.get("elevenlabs")

        energy_db = None
        vocals_source = project.vocals_path or project.audio_path
        if vocals_source:
            energy_db = await ffmpeg_tools.measure_segment_mean_volume(vocals_source, line.start_sec, line.end_sec)

        try:
            if voxcpm_voice_id and settings.voxcpm_url:
                # Cloned voice (M3, primary provider): the character's own performance,
                # in Khmer, with emotion carried as a style prefix (spec §8b).
                await voxcpm_client.speak(
                    settings.voxcpm_url, line.khmer_text, tmp_path, voice_id=voxcpm_voice_id,
                    style=voxcpm_client.EMOTION_STYLE.get(line.emotion),
                )
                fit_ok, _ = await _fit_to_slot(tmp_path, out_path, slot)
            elif elevenlabs_voice_id:
                # Cloned voice (M3, fallback provider).
                await elevenlabs_service.text_to_speech(
                    settings.elevenlabs_api_key, elevenlabs_voice_id, line.khmer_text, tmp_path, emotion=line.emotion,
                )
                fit_ok, _ = await _fit_to_slot(tmp_path, out_path, slot)
            else:
                # Stock voice fallback (spec §3/§8): always available, no license needed.
                stock_voice = (character.stock_voice if character else None) or tts_stock.voice_for_gender(
                    character.gender if character else None
                )
                fit_ok, _ = await tts_stock.synthesize_fit_to_slot(
                    line.khmer_text, stock_voice, out_path, slot, tmp_path,
                    emotion=line.emotion, energy_db=energy_db,
                )
            line.audio_path = out_path
            if not fit_ok and "slot_overflow" not in line.flags:
                line.flags = [*line.flags, "slot_overflow"]
                db.add(ReviewItem(project_id=project.id, line_id=line.id, kind="slot_overflow"))
        except Exception as exc:  # noqa: BLE001
            if "tts_failed" not in line.flags:
                line.flags = [*line.flags, "tts_failed"]
                db.add(ReviewItem(project_id=project.id, line_id=line.id, kind="tts_failed", payload={"error": str(exc)}))
        line.dirty = False
        db.commit()
        on_progress((i + 1) / max(len(lines), 1) * 100.0, STAGE_LABELS["speak"])

    on_progress(100, STAGE_LABELS["speak"])


async def stage_mix(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["mix"])
    pdir = _project_dir(project.id)
    mix_path = os.path.join(pdir, "mix.wav")

    lines_with_audio = (
        db.query(Line)
        .filter(Line.project_id == project.id, Line.audio_path.isnot(None))
        .order_by(Line.start_sec)
        .all()
    )

    if not lines_with_audio:
        # No dub was generated for this project (no provider configured, or nothing to
        # say) — keep the original soundtrack untouched rather than ship a silent video.
        shutil.copyfile(project.audio_path, mix_path)
        project.dialogue_mix_path = mix_path
        db.commit()
        on_progress(100, STAGE_LABELS["mix"])
        return

    dialogue_path = os.path.join(pdir, "dialogue.wav")
    await audio_mix.build_dialogue_track(
        [(line.start_sec, line.audio_path) for line in lines_with_audio],
        project.duration_sec or 0,
        dialogue_path,
    )
    on_progress(40, STAGE_LABELS["mix"])

    background_source = project.background_path or project.audio_path
    background_bed_path = os.path.join(pdir, "background_bed.wav")
    line_spans = [(line.start_sec, line.end_sec) for line in lines_with_audio]
    await audio_mix.build_background_bed(background_source, line_spans, background_bed_path)
    on_progress(75, STAGE_LABELS["mix"])

    await audio_mix.mix_dialogue_and_background(dialogue_path, background_bed_path, mix_path)
    project.dialogue_mix_path = mix_path
    db.commit()
    on_progress(100, STAGE_LABELS["mix"])


async def stage_export(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["export"])
    pdir = _project_dir(project.id)

    final_video = os.path.join(pdir, "final.mp4")
    await ffmpeg_tools.mux_video_audio(project.source_path, project.dialogue_mix_path, final_video)
    project.output_video_path = final_video
    on_progress(50, STAGE_LABELS["export"])

    final_mp3 = os.path.join(pdir, "final.mp3")
    await ffmpeg_tools.to_mp3(project.dialogue_mix_path, final_mp3)
    project.output_audio_path = final_mp3
    on_progress(75, STAGE_LABELS["export"])

    lines = db.query(Line).filter(Line.project_id == project.id).all()
    srt_content = subtitles.build_srt([
        {"start_sec": line.start_sec, "end_sec": line.end_sec, "khmer_text": line.khmer_text} for line in lines
    ])
    if srt_content:
        final_srt = os.path.join(pdir, "final.srt")
        with open(final_srt, "w", encoding="utf-8") as f:
            f.write(srt_content)
        project.output_srt_path = final_srt

    unresolved = db.query(ReviewItem).filter(
        ReviewItem.project_id == project.id, ReviewItem.resolved.is_(False)
    ).count()
    project.status = "needs_review" if unresolved else "done"
    db.commit()
    on_progress(100, STAGE_LABELS["export"])


_STAGE_FUNCS: dict[str, Callable] = {
    "prepare": stage_prepare,
    "separate": stage_separate,
    "transcribe": stage_transcribe,
    "diarize": stage_diarize,
    "cast": stage_cast,
    "speak": stage_speak,
    "mix": stage_mix,
    "export": stage_export,
}


async def run_stage(stage: str, project_id: str, db: Session, on_progress: ProgressFn) -> None:
    project = db.get(Project, project_id)
    if not project:
        raise RuntimeError(f"Project not found: {project_id}")
    await _STAGE_FUNCS[stage](project, db, on_progress)
