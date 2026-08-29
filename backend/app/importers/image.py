from __future__ import annotations

from pathlib import Path

from .base import ImportResult, ParagraphData, ProgressCallback, SectionData, fallback_title
from .ocr import PaddleOCRService


class ImageImporter:
    def __init__(self, ocr_service: PaddleOCRService | None = None) -> None:
        self.ocr = ocr_service or PaddleOCRService()

    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        progress(0, 1, "正在识别图片文字")
        failed: list[int] = []
        try:
            text = self.ocr.read_image(path.read_bytes())
            if not text:
                raise ValueError("没有识别到文字")
        except Exception:
            failed = [1]
            text = "[图片 OCR 识别失败]"
        progress(1, 1, "图片处理完成")
        return ImportResult(
            title=fallback_title(path),
            sections=[SectionData("第 1 页", [ParagraphData(text, 1)], 1)],
            total_pages=1,
            processed_pages=1,
            char_count=0 if failed else len(text),
            ocr_pages=1,
            failed_pages=failed,
        )

