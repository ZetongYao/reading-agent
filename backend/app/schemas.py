from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AnnotationCreate(BaseModel):
    book_id: int
    paragraph_id: int
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    selected_text: str = Field(min_length=1, max_length=300)
    chinese_annotation: str | None = Field(default=None, min_length=1, max_length=200)
    all_chinese_meanings: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_offsets(self) -> "AnnotationCreate":
        if self.end_offset <= self.start_offset:
            raise ValueError("结束位置必须大于开始位置")
        return self


class TranslationPreviewCreate(BaseModel):
    selected_text: str = Field(min_length=1, max_length=300)
    sentence: str = Field(min_length=1, max_length=5000)


class VocabularyUpdate(BaseModel):
    chinese_annotation: str = Field(min_length=1, max_length=200)


class ReadingProgressUpdate(BaseModel):
    section_id: int | None = None
    paragraph_id: int | None = None
    scroll_ratio: float = Field(default=0, ge=0, le=1)


class AppSettingsUpdate(BaseModel):
    ollama_url: str | None = None
    ollama_model: str | None = None
    theme: str | None = Field(default=None, pattern="^(light|dark)$")
    font_size: int | None = Field(default=None, ge=14, le=36)
    line_height: float | None = Field(default=None, ge=1.2, le=3.0)
