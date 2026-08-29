from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from .base import ImportResult, ParagraphData, ProgressCallback, SectionData, fallback_title
from .plain_text import read_text


def sections_from_html(content: str, default_title: str) -> tuple[str, list[SectionData]]:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "nav", "noscript"]):
        tag.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "") or default_title
    sections: list[SectionData] = []
    current_title = "正文"
    current: list[ParagraphData] = []

    def flush() -> None:
        nonlocal current
        if current:
            sections.append(SectionData(current_title, current))
            current = []

    root = soup.body or soup
    for element in root.find_all(["h1", "h2", "h3", "p", "li", "blockquote"], recursive=True):
        value = element.get_text(" ", strip=True)
        if not value:
            continue
        if element.name in {"h1", "h2", "h3"}:
            flush()
            current_title = value
        elif not element.find_parent(["p", "li", "blockquote"]):
            current.append(ParagraphData(value))
    flush()
    if not sections:
        text = root.get_text(" ", strip=True)
        sections = [SectionData("正文", [ParagraphData(text or "[文件中没有可阅读文字]")])]
    return title, sections


class HTMLImporter:
    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        title, sections = sections_from_html(read_text(path), fallback_title(path))
        progress(1, 1, "HTML 整理完成")
        return ImportResult(
            title=title,
            sections=sections,
            total_pages=len(sections),
            processed_pages=len(sections),
            char_count=sum(len(p.text) for s in sections for p in s.paragraphs),
        )

