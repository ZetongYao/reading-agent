from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    total_pages INTEGER NOT NULL DEFAULT 0,
    processed_pages INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    ocr_pages INTEGER NOT NULL DEFAULT 0,
    failed_pages TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    page_number INTEGER,
    UNIQUE(book_id, order_index)
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    UNIQUE(section_id, order_index)
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    selected_text TEXT NOT NULL,
    chinese_annotation TEXT NOT NULL,
    all_chinese_meanings TEXT NOT NULL DEFAULT '[]',
    sentence TEXT NOT NULL,
    page_or_chapter TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(paragraph_id, start_offset, end_offset)
);

CREATE TABLE IF NOT EXISTS vocabulary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annotation_id INTEGER NOT NULL UNIQUE REFERENCES annotations(id) ON DELETE CASCADE,
    selected_text TEXT NOT NULL,
    chinese_annotation TEXT NOT NULL,
    all_chinese_meanings TEXT NOT NULL DEFAULT '[]',
    sentence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(selected_text, sentence)
);

CREATE TABLE IF NOT EXISTS reading_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL UNIQUE REFERENCES books(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    paragraph_id INTEGER REFERENCES paragraphs(id) ON DELETE SET NULL,
    scroll_ratio REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translation_cache (
    cache_key TEXT PRIMARY KEY,
    selected_text TEXT NOT NULL,
    sentence TEXT NOT NULL,
    contextual_translation TEXT NOT NULL,
    all_chinese_meanings TEXT NOT NULL DEFAULT '[]',
    prompt_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ollama_url TEXT NOT NULL,
    ollama_model TEXT NOT NULL,
    theme TEXT NOT NULL,
    font_size INTEGER NOT NULL,
    line_height REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sections_book_order ON sections(book_id, order_index);
CREATE INDEX IF NOT EXISTS idx_paragraphs_book_section ON paragraphs(book_id, section_id, order_index);
CREATE INDEX IF NOT EXISTS idx_annotations_paragraph_offsets ON annotations(paragraph_id, start_offset, end_offset);
CREATE INDEX IF NOT EXISTS idx_vocabulary_created ON vocabulary_entries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_translation_cache_text
ON translation_cache(selected_text COLLATE NOCASE, updated_at DESC);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self, ollama_url: str, ollama_model: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_column(
                connection,
                "annotations",
                "all_chinese_meanings",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                "vocabulary_entries",
                "all_chinese_meanings",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                "translation_cache",
                "prompt_version",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._migrate_vocabulary_table(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO app_settings
                (id, ollama_url, ollama_model, theme, font_size, line_height, updated_at)
                VALUES (1, ?, ?, 'light', 20, 1.9, ?)
                """,
                (ollama_url, ollama_model, utc_now()),
            )
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _migrate_vocabulary_table(connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(vocabulary_entries)").fetchall()
        }
        legacy_source_columns = {"book_id", "paragraph_id", "book_title", "page_or_chapter"}
        if not columns.intersection(legacy_source_columns):
            return
        connection.execute("ALTER TABLE vocabulary_entries RENAME TO vocabulary_entries_legacy")
        connection.execute(
            """
            CREATE TABLE vocabulary_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                annotation_id INTEGER NOT NULL UNIQUE
                    REFERENCES annotations(id) ON DELETE CASCADE,
                selected_text TEXT NOT NULL,
                chinese_annotation TEXT NOT NULL,
                all_chinese_meanings TEXT NOT NULL DEFAULT '[]',
                sentence TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(selected_text, sentence)
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO vocabulary_entries
            (id, annotation_id, selected_text, chinese_annotation,
             all_chinese_meanings, sentence, created_at)
            SELECT id, annotation_id, selected_text, chinese_annotation,
                   all_chinese_meanings, sentence, created_at
            FROM vocabulary_entries_legacy
            """
        )
        connection.execute("DROP TABLE vocabulary_entries_legacy")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vocabulary_created
            ON vocabulary_entries(created_at DESC)
            """
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
            return self._row(row) if row else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [self._row(row) for row in connection.execute(sql, params).fetchall()]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        if "failed_pages" in result and isinstance(result["failed_pages"], str):
            result["failed_pages"] = json.loads(result["failed_pages"] or "[]")
        if "all_chinese_meanings" in result and isinstance(result["all_chinese_meanings"], str):
            result["all_chinese_meanings"] = json.loads(
                result["all_chinese_meanings"] or "[]"
            )
        return result
