from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub

from .base import ImportBookError, ImportResult, ParagraphData, ProgressCallback, ProtectedBookError, SectionData, fallback_title


class EPUBImporter:
    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        try:
            book = epub.read_epub(str(path), options={"ignore_ncx": True})
        except Exception as exc:
            message = str(exc).lower()
            if "encrypt" in message or "drm" in message:
                raise ProtectedBookError("此 EPUB 可能含有 DRM 或加密内容，无法导入。") from exc
            raise ImportBookError(f"无法读取 EPUB：{exc}") from exc
        title_values = book.get_metadata("DC", "title")
        creator_values = book.get_metadata("DC", "creator")
        title = str(title_values[0][0]).strip() if title_values else fallback_title(path)
        author = str(creator_values[0][0]).strip() if creator_values else None
        items = [item for item in book.get_items() if item.get_type() == ITEM_DOCUMENT]
        sections: list[SectionData] = []
        total = len(items)
        for index, item in enumerate(items, start=1):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            for tag in soup(["script", "style", "nav"]):
                tag.decompose()
            heading = soup.find(["h1", "h2", "h3"])
            section_title = heading.get_text(" ", strip=True) if heading else f"第 {index} 章"
            paragraphs: list[ParagraphData] = []
            for element in soup.find_all(["p", "li", "blockquote"]):
                if element.find_parent(["p", "li", "blockquote"]):
                    continue
                value = element.get_text(" ", strip=True)
                if value:
                    paragraphs.append(ParagraphData(value))
            if paragraphs:
                sections.append(SectionData(section_title, paragraphs))
            progress(index, total, f"正在处理第 {index}/{total} 个章节")
        if not sections:
            raise ImportBookError("EPUB 中没有找到可阅读的正文；文件可能受 DRM 保护。")
        return ImportResult(
            title=title,
            author=author,
            sections=sections,
            total_pages=total,
            processed_pages=total,
            char_count=sum(len(p.text) for s in sections for p in s.paragraphs),
        )

