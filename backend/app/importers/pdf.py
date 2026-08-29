from __future__ import annotations

import re
from pathlib import Path

import fitz

from ..text_utils import split_paragraphs
from .base import (
    ImportBookError,
    ImportResult,
    ParagraphData,
    ProgressCallback,
    ProtectedBookError,
    SectionData,
    fallback_title,
)
from .ocr import PaddleOCRService


class PDFImporter:
    def __init__(self, ocr_service: PaddleOCRService | None = None) -> None:
        self.ocr = ocr_service or PaddleOCRService()

    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        try:
            document = fitz.open(path)
        except Exception as exc:
            raise ImportBookError(f"无法打开 PDF：{exc}") from exc
        if document.needs_pass:
            document.close()
            raise ProtectedBookError("此 PDF 受密码保护，应用不支持导入加密文件。")

        metadata = document.metadata or {}
        total = document.page_count
        result = ImportResult(
            title=(metadata.get("title") or fallback_title(path)).strip(),
            author=(metadata.get("author") or "").strip() or None,
            total_pages=total,
        )
        for index in range(total):
            page_number = index + 1
            progress(index, total, f"正在处理第 {page_number}/{total} 页")
            page = document.load_page(index)
            text = self._extract_text(page)
            needs_ocr = len(re.sub(r"\W", "", text, flags=re.UNICODE)) < 20
            if needs_ocr:
                result.ocr_pages += 1
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
                    text = self.ocr.read_image(pixmap.tobytes("png"))
                    if not text.strip():
                        raise ValueError("OCR 未识别到英文文字")
                except Exception:
                    result.failed_pages.append(page_number)
                    text = ""
            paragraphs = [ParagraphData(item, page_number) for item in split_paragraphs(text)]
            if not paragraphs:
                message = "[本页未提取到文字]" if page_number not in result.failed_pages else "[本页 OCR 识别失败]"
                paragraphs = [ParagraphData(message, page_number)]
            result.sections.append(SectionData(f"第 {page_number} 页", paragraphs, page_number))
            result.processed_pages += 1
            result.char_count += sum(len(item.text) for item in paragraphs if not item.text.startswith("["))
            progress(page_number, total, f"正在处理第 {page_number}/{total} 页")
        document.close()
        return result

    @staticmethod
    def _extract_text(page: fitz.Page) -> str:
        blocks = page.get_text("blocks", sort=True)
        texts = []
        for block in blocks:
            if len(block) > 6 and block[6] != 0:
                continue
            value = str(block[4]).strip()
            if value:
                texts.append(value)
        return "\n\n".join(texts)

