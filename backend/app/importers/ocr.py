from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from .base import OCRUnavailableError


class PaddleOCRService:
    """Lazy PaddleOCR adapter supporting both 2.x and 3.x result shapes."""

    def __init__(self) -> None:
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        configured_root = os.getenv("PADDLE_OCR_BASE_DIR")
        if configured_root:
            model_root = Path(configured_root).expanduser().resolve()
        elif os.name == "nt" and os.getenv("LOCALAPPDATA"):
            # Paddle's Windows native runtime cannot open model paths containing
            # non-ASCII characters, so keep model weights in an ASCII cache path.
            model_root = Path(os.environ["LOCALAPPDATA"]) / "Yuanyue" / "ocr-models"
        else:
            model_root = Path.home() / ".yuanyue" / "ocr-models"
        model_root.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("PADDLE_OCR_BASE_DIR", str(model_root))
        try:
            from paddleocr import PaddleOCR
        except (ImportError, OSError) as exc:
            raise OCRUnavailableError(
                "此文件需要 OCR。请重新运行 setup.ps1 安装 PaddleOCR；安装完成后再导入。"
            ) from exc
        try:
            self._engine = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                show_log=False,
            )
        except TypeError:
            self._engine = PaddleOCR(lang="en", use_angle_cls=True, show_log=False)
        return self._engine

    def read_image(self, image_bytes: bytes) -> str:
        engine = self._get_engine()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        try:
            result = engine.predict(image)
        except AttributeError:
            import numpy as np

            result = engine.ocr(np.asarray(image), cls=True)
        texts = self._extract_texts(result)
        return "\n".join(text for text in texts if text.strip()).strip()

    @classmethod
    def _extract_texts(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if hasattr(value, "json"):
            value = value.json
            if callable(value):
                value = value()
            if isinstance(value, str):
                value = json.loads(value)
        if isinstance(value, dict):
            if isinstance(value.get("rec_texts"), list):
                return [str(item) for item in value["rec_texts"]]
            if isinstance(value.get("res"), dict):
                return cls._extract_texts(value["res"])
            texts: list[str] = []
            for child in value.values():
                texts.extend(cls._extract_texts(child))
            return texts
        if isinstance(value, (list, tuple)):
            # PaddleOCR 2.x line: [box, (text, confidence)]
            if (
                len(value) == 2
                and isinstance(value[1], (list, tuple))
                and value[1]
                and isinstance(value[1][0], str)
            ):
                return [value[1][0]]
            texts = []
            for child in value:
                texts.extend(cls._extract_texts(child))
            return texts
        return []
