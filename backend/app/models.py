import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    telegram_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_licensed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="series")
    voices: Mapped[list["Voice"]] = relationship(back_populates="series")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    series_id: Mapped[str | None] = mapped_column(String, ForeignKey("series.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    automation_level: Mapped[str] = mapped_column(String, default="full_auto")
    status: Mapped[str] = mapped_column(String, default="new")
    # Intermediate pipeline artifacts (stage 1-2), cached so a re-run only redoes
    # what changed downstream (spec §3).
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    proxy_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    vocals_path: Mapped[str | None] = mapped_column(String, nullable=True)
    background_path: Mapped[str | None] = mapped_column(String, nullable=True)
    dialogue_mix_path: Mapped[str | None] = mapped_column(String, nullable=True)
    output_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    output_audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    output_srt_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    series: Mapped[Series | None] = relationship(back_populates="projects")
    jobs: Mapped[list["Job"]] = relationship(back_populates="project")
    lines: Mapped[list["Line"]] = relationship(back_populates="project")
    characters: Mapped[list["Character"]] = relationship(back_populates="project")
    review_items: Mapped[list["ReviewItem"]] = relationship(back_populates="project")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"))
    stage: Mapped[str] = mapped_column(String, default="prepare")
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|running|done|error
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumable_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="jobs")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"))
    voice_id: Mapped[str | None] = mapped_column(String, ForeignKey("voices.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, default="")
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    color: Mapped[str] = mapped_column(String, default="#6366f1")
    face_thumb_path: Mapped[str | None] = mapped_column(String, nullable=True)
    emotion_default: Mapped[str] = mapped_column(String, default="neutral")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    # Stock Khmer TTS voice (edge-tts) used until a cloned voice exists (M3).
    stock_voice: Mapped[str | None] = mapped_column(String, nullable=True)
    # Acoustic fingerprint (voice_engine.segment_fingerprint, averaged over this
    # character's lines) — compared against series_voices for cross-episode
    # voice reuse (spec §4.3).
    fingerprint: Mapped[list | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="characters")
    lines: Mapped[list["Line"]] = relationship(back_populates="character")
    voice: Mapped["Voice | None"] = relationship(foreign_keys=[voice_id])


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"))
    character_id: Mapped[str | None] = mapped_column(String, ForeignKey("characters.id"), nullable=True)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    source_text: Mapped[str] = mapped_column(Text, default="")
    khmer_text: Mapped[str] = mapped_column(Text, default="")
    emotion: Mapped[str] = mapped_column(String, default="neutral")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)  # overlap|unsure|missed|slot_overflow|...
    dirty: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="lines")
    character: Mapped[Character | None] = relationship(back_populates="lines")


class Voice(Base):
    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    series_id: Mapped[str | None] = mapped_column(String, ForeignKey("series.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    reference_path: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {voxcpm: id, elevenlabs: id}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    series: Mapped[Series | None] = relationship(back_populates="voices")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"))
    line_id: Mapped[str | None] = mapped_column(String, ForeignKey("lines.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String)  # overlap|unsure|missed|slot_overflow|low_clone_quality|tts_failed
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="review_items")


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
