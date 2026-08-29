from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol


class ImportBookError(Exception):
    """A user-facing import error."""


class ProtectedBookError(ImportBookError):
    pass


class OCRUnavailableError(ImportBookError):
    pass


ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class ParagraphData:
    text: str
    page_number: int | None = None


@dataclass(slots=True)
class SectionData:
    title: str
    paragraphs: list[ParagraphData]
    page_number: int | None = None


@dataclass(slots=True)
class ImportResult:
    title: str
    author: str | None = None
    sections: list[SectionData] = field(default_factory=list)
    total_pages: int = 0
    processed_pages: int = 0
    char_count: int = 0
    ocr_pages: int = 0
    failed_pages: list[int] = field(default_factory=list)


class BookImporter(Protocol):
    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult: ...


def fallback_title(path: Path) -> str:
    return path.stem.replace("_", " ").strip() or "未命名书籍"

