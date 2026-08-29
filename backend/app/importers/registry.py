from __future__ import annotations

from pathlib import Path

from .base import BookImporter, ImportBookError
from .calibre import CalibreImporter
from .docx import DOCXImporter
from .epub import EPUBImporter
from .html import HTMLImporter
from .image import ImageImporter
from .pdf import PDFImporter
from .plain_text import MarkdownImporter, TextImporter


_IMPORTERS: dict[str, type[BookImporter]] = {
    ".pdf": PDFImporter,
    ".epub": EPUBImporter,
    ".txt": TextImporter,
    ".md": MarkdownImporter,
    ".markdown": MarkdownImporter,
    ".html": HTMLImporter,
    ".htm": HTMLImporter,
    ".docx": DOCXImporter,
    ".jpg": ImageImporter,
    ".jpeg": ImageImporter,
    ".png": ImageImporter,
    ".mobi": CalibreImporter,
    ".azw3": CalibreImporter,
}


def supported_extensions() -> list[str]:
    return sorted(_IMPORTERS)


def get_importer(path: Path) -> BookImporter:
    importer_type = _IMPORTERS.get(path.suffix.lower())
    if not importer_type:
        raise ImportBookError(
            f"不支持 {path.suffix or '未知'} 格式。支持：{', '.join(supported_extensions())}"
        )
    return importer_type()

