from __future__ import annotations

import re


SENTENCE_END = re.compile(r"[.!?。！？](?:[\"'”’)]*)\s+")


def sentence_at(text: str, start: int, end: int) -> str:
    """Return the complete sentence containing an offset range."""
    left = 0
    for match in SENTENCE_END.finditer(text, 0, start):
        left = match.end()
    right = len(text)
    match = SENTENCE_END.search(text, end)
    if match:
        right = match.end()
    return text[left:right].strip()


def split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n+", text)
    result = []
    for block in blocks:
        normalized = re.sub(r"(?<![.!?:;])\n(?!\s*[-*#])", " ", block).strip()
        if normalized:
            result.append(normalized)
    return result

