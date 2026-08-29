from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    app_env: str = "production"
    test_translation: str | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def books_dir(self) -> Path:
        return self.data_dir / "books"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            data_dir=Path(os.getenv("BOOKLINGO_DATA_DIR", "./data")).resolve(),
            host=os.getenv("BOOKLINGO_HOST", "127.0.0.1"),
            port=int(os.getenv("BOOKLINGO_PORT", "8000")),
            app_env=os.getenv("BOOKLINGO_ENV", "production"),
            test_translation=os.getenv("BOOKLINGO_TEST_TRANSLATION"),
        )
