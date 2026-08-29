from __future__ import annotations

import re
from pathlib import Path

from charset_normalizer import from_bytes

from ..text_utils import split_paragraphs
from .base import ImportResult, ParagraphData, ProgressCallback, SectionData, fallback_title


def read_text(path: Path) -> str:
    match = from_bytes(path.read_bytes()).best()
    if match is None:
        return path.read_text(encoding="utf-8", errors="replace")
    return str(match)


class TextImporter:
    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        text = read_text(path)
        pages = text.split("\f")
        sections = []
        for index, page in enumerate(pages, start=1):
            items = [ParagraphData(item, index) for item in split_paragraphs(page)]
            if items:
                sections.append(SectionData(f"第 {index} 部分" if len(pages) > 1 else "正文", items, index))
            progress(index, len(pages), f"正在整理第 {index}/{len(pages)} 部分")
        if not sections:
            sections = [SectionData("正文", [ParagraphData("[文件中没有可阅读文字]")])]
        return ImportResult(
            title=fallback_title(path),
            sections=sections,
            total_pages=len(pages),
            processed_pages=len(pages),
            char_count=sum(len(p.text) for s in sections for p in s.paragraphs),
        )


class MarkdownImporter:
    heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        text = read_text(path)
        sections: list[SectionData] = []
        title = fallback_title(path)
        current_title = "正文"
        current_lines: list[str] = []

        def flush() -> None:
            paragraphs = [ParagraphData(item) for item in split_paragraphs("\n".join(current_lines))]
            if paragraphs:
                sections.append(SectionData(current_title, paragraphs))

        for line in text.splitlines():
            match = self.heading.match(line)
            if match:
                flush()
                current_lines = []
                current_title = match.group(2).strip()
                if match.group(1) == "#" and title == fallback_title(path):
                    title = current_title
            else:
                current_lines.append(line)
        flush()
        if not sections:
            sections = [SectionData("正文", [ParagraphData("[文件中没有可阅读文字]")])]
        progress(len(sections), len(sections), "Markdown 整理完成")
        return ImportResult(
            title=title,
            sections=sections,
            total_pages=len(sections),
            processed_pages=len(sections),
            char_count=sum(len(p.text) for s in sections for p in s.paragraphs),
        )

