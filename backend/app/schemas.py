"""Pydantic schemas: structured LLM outputs and API payloads."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

IMAGE_PAGE_TYPES = ("single_character", "scene", "pattern_mandala", "hidden_objects_scene")
CODE_PAGE_TYPES = (
    "maze",
    "dot_to_dot",
    "word_search",
    "trace_write",
    "qa_page",
    "story_text",
    "title_page",
    "belongs_to_page",
    "end_page",
)
PAGE_TYPES = IMAGE_PAGE_TYPES + CODE_PAGE_TYPES
# Types a format may contain (front/back matter is added automatically).
CONTENT_PAGE_TYPES = tuple(t for t in PAGE_TYPES if t not in ("title_page", "belongs_to_page", "end_page"))

PageType = Literal[
    "single_character",
    "scene",
    "pattern_mandala",
    "hidden_objects_scene",
    "maze",
    "dot_to_dot",
    "word_search",
    "trace_write",
    "qa_page",
    "story_text",
    "title_page",
    "belongs_to_page",
    "end_page",
]


def is_image_type(t: str) -> bool:
    return t in IMAGE_PAGE_TYPES


# ---------------------------------------------------------------- LLM outputs


class PageMixItem(BaseModel):
    type: str
    share: float = Field(ge=0, le=100)


class RecipeOut(BaseModel):
    mood: str
    age_group: str
    line_weight: str
    detail_level: str
    page_mix: list[PageMixItem] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    notes: str = ""


class ThemeOut(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)


class ThemesOut(BaseModel):
    themes: list[ThemeOut] = Field(min_length=1)


class FormatBlock(BaseModel):
    type: PageType
    share: int = Field(ge=0, le=100)


class FormatOut(BaseModel):
    name: str
    description: str = ""
    blocks: list[FormatBlock] = Field(min_length=1)

    @field_validator("blocks")
    @classmethod
    def _content_types_only(cls, v: list[FormatBlock]) -> list[FormatBlock]:
        for b in v:
            if b.type not in CONTENT_PAGE_TYPES:
                raise ValueError(f"format blocks may not contain front/back matter type '{b.type}'")
        return v


class FormatsOut(BaseModel):
    formats: list[FormatOut] = Field(min_length=1)


class PlannedPage(BaseModel):
    type: PageType
    description: str = ""
    characters: list[str] = []
    text_content: dict[str, Any] = {}
    prompt: str = ""  # full image prompt for image pages (used directly in manual mode)


class PagePlanOut(BaseModel):
    pages: list[PlannedPage] = Field(min_length=1)


class CharacterBriefOut(BaseModel):
    name: str
    species: str
    personality: str
    proportions: str
    signature_feature: str
    outfit: str = ""


class CharacterBriefsOut(BaseModel):
    characters: list[CharacterBriefOut] = Field(min_length=1)


class CharacterEditOut(BaseModel):
    prompt: str
    changed: str = ""


class ImagePromptOut(BaseModel):
    prompt: str


class StoryTextOut(BaseModel):
    text: str


class QAContentOut(BaseModel):
    ok: bool
    issues: list[str] = []


class VisionVerdict(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[str] = []
    checks: dict[str, Any] = {}

    model_config = {"populate_by_name": True}

    def as_dict(self) -> dict[str, Any]:
        return {"pass": self.pass_, "issues": self.issues, "checks": self.checks}


# ---------------------------------------------------------------- API payloads


class BookCreate(BaseModel):
    title: str | None = None
    book_language: Literal["en", "ar"] | None = None
    trim_size: str | None = None


class BookUpdate(BaseModel):
    title: str | None = None
    book_language: Literal["en", "ar"] | None = None
    trim_size: str | None = None
    bleed: bool | None = None
    page_count: int | None = Field(default=None, ge=4, le=200)
    meta: dict[str, Any] | None = None


class RecipeIn(BaseModel):
    mood: str | None = None
    age_group: str | None = None
    line_weight: str | None = None
    detail_level: str | None = None
    page_mix: list[PageMixItem] | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    notes: str | None = None


class FormatBlocksIn(BaseModel):
    blocks: list[FormatBlock]

    @model_validator(mode="after")
    def _sum_100(self) -> FormatBlocksIn:
        total = sum(b.share for b in self.blocks)
        if total != 100:
            raise ValueError(f"shares must sum to 100 (got {total})")
        return self


class PageEdit(BaseModel):
    type: PageType | None = None
    description: str | None = None
    prompt: str | None = None
    text_content: dict[str, Any] | None = None
    status: Literal["planned", "queued", "generated", "failed", "approved", "rejected"] | None = None
    note: str | None = None
