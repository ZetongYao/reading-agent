from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import ImportBookError, ImportResult, ProgressCallback
from .epub import EPUBImporter


class CalibreImporter:
    def import_book(self, path: Path, progress: ProgressCallback) -> ImportResult:
        converter = shutil.which("ebook-convert")
        if not converter:
            raise ImportBookError(
                "导入 MOBI/AZW3 需要先安装 Calibre，并确保 ebook-convert 已加入系统 PATH。"
            )
        converted = path.with_name(f"{path.stem}.converted.epub")
        progress(0, 1, "正在通过 Calibre 转换电子书")
        completed = subprocess.run(
            [converter, str(path), str(converted)],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if completed.returncode != 0 or not converted.exists():
            raise ImportBookError(f"Calibre 转换失败：{completed.stderr[-500:]}")
        return EPUBImporter().import_book(converted, progress)

