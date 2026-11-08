"""SQLAlchemy models (PLAN.md section 6). JSON columns hold flexible parts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


BOOK_STATUSES = ("draft", "analyzed", "themed", "characters", "specced", "generating", "review", "exported")
PAGE_STATUSES = ("planned", "queued", "generated", "failed", "approved", "rejected")
JOB_STATUSES = ("queued", "running", "done", "failed", "cancelled")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Untitled book")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source_type: Mapped[str] = mapped_column(String(20), default="none")  # url|url_pages|text|none
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    book_language: Mapped[str] = mapped_column(String(5), default="en")
    trim_size: Mapped[str] = mapped_column(String(40), default="8.5x11in")
    bleed: Mapped[bool] = mapped_column(Boolean, default=False)
    page_count: Mapped[int] = mapped_column(Integer, default=24)
    theme_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Additions beyond section 6 (see STATE.md "Decisions"):
    # style_anchor: {rules, reference_path}; meta: fetched source info, sample page,
    # per-book image provider, cover settings, belongs_to flag, etc.
    style_anchor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recipe: Mapped[Recipe | None] = relationship(back_populates="book", uselist=False, cascade="all, delete-orphan")
    themes: Mapped[list[ThemeOption]] = relationship(cascade="all, delete-orphan", order_by="ThemeOption.id")
    formats: Mapped[list[FormatOption]] = relationship(cascade="all, delete-orphan", order_by="FormatOption.id")
    pages: Mapped[list[Page]] = relationship(cascade="all, delete-orphan", order_by="Page.index")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), unique=True)
    mood: Mapped[str] = mapped_column(String(200), default="")
    age_group: Mapped[str] = mapped_column(String(50), default="")
    line_weight: Mapped[str] = mapped_column(String(50), default="")
    detail_level: Mapped[str] = mapped_column(String(50), default="")
    page_mix: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    notes: Mapped[str] = mapped_column(Text, default="")

    book: Mapped[Book] = relationship(back_populates="recipe")


class ThemeOption(Base):
    __tablename__ = "theme_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)


class FormatOption(Base):
    __tablename__ = "format_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{type, share}]
    description: Mapped[str] = mapped_column(Text, default="")
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    species: Mapped[str] = mapped_column(String(200), default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    signature_feature: Mapped[str] = mapped_column(String(300), default="")
    proportions: Mapped[str] = mapped_column(String(300), default="")
    # brief: {outfit, prompt, versions:[...], consistency:{...}, library_source_id}
    brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved
    in_library: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assets: Mapped[list[CharacterAsset]] = relationship(
        cascade="all, delete-orphan", order_by="CharacterAsset.id", back_populates="character"
    )


class CharacterAsset(Base):
    __tablename__ = "character_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # candidate|sheet|expression|test_scene
    path: Mapped[str] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    character: Mapped[Character] = relationship(back_populates="assets")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text, default="")
    text_content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    batch_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Additions: one-line scene description, character ids on the page, user note for redo.
    description: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(40))  # text|vision|image
    units: Mapped[float] = mapped_column(Float, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    book_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    page_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(60), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
