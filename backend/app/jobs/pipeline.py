"""Pipeline stage functions (spec §3).

Each stage caches its output on the `Project` row so re-running only redoes what
changed (spec rule: editing one line re-generates one line and re-mixes, nothing
else — partial re-runs land in M4). Without a Gemini key configured, `transcribe`
degrades to zero lines and a review item instead of failing the job, so a project
without providers still finishes as a straight passthrough of the original audio —
"never a blocked or half-finished job" (spec §3/§8).
"""

import os
import shutil
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import OUTPUTS_DIR, settings
from app.models import Character, Line, Project, ReviewItem
from app.services import audio_mix, dubber, ffmpeg_tools, subtitles, tts_stock, vocal_separator

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
        raw_lines = await dubber.extract_dialogue_timeline(
            source_audio, project.duration_sec or 0, api_key, tmp_dir,
            on_progress=lambda pct: on_progress(pct * 0.9, STAGE_LABELS["transcribe"]),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

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
    # M2 trusts Gemini's own speaker split from the transcribe stage. M3 refines it with
    # the acoustic voice engine (MFCC + pitch clustering) ported from
    # scripts/voice_split_offline.py, merging overlap/unsure/missed flags in here.
    on_progress(100, STAGE_LABELS["diarize"])


async def stage_cast(project: Project, db: Session, on_progress: ProgressFn) -> None:
    on_progress(0, STAGE_LABELS["cast"])
    characters = db.query(Character).filter(Character.project_id == project.id).all()
    for character in characters:
        if not character.stock_voice:
            character.stock_voice = tts_stock.voice_for_gender(character.gender)
    db.commit()
    on_progress(100, STAGE_LABELS["cast"])


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
        voice = (character.stock_voice if character else None) or tts_stock.voice_for_gender(
            character.gender if character else None
        )
        out_path = os.path.join(lines_dir, f"{line.id}.mp3")
        tmp_path = os.path.join(lines_dir, f"{line.id}.raw.mp3")
        slot = max(0.0, line.end_sec - line.start_sec)

        energy_db = None
        vocals_source = project.vocals_path or project.audio_path
        if vocals_source:
            energy_db = await ffmpeg_tools.measure_segment_mean_volume(vocals_source, line.start_sec, line.end_sec)

        try:
            fit_ok, _ = await tts_stock.synthesize_fit_to_slot(
                line.khmer_text, voice, out_path, slot, tmp_path,
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
