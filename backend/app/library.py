from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from .database import Database, utc_now
from .importers import get_importer
from .importers.base import ImportResult


class LibraryService:
    def __init__(self, database: Database, books_dir: Path):
        self.database = database
        self.books_dir = books_dir.resolve()

    def create_pending_book(self, filename: str, suffix: str, stored_path: Path) -> int:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO books
                (title, original_filename, file_type, file_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (Path(filename).stem or "未命名书籍", filename, suffix.lstrip("."), str(stored_path), now, now),
            )
            return int(cursor.lastrowid)

    def process_book(self, book_id: int, stored_path: Path) -> None:
        self._update_status(book_id, status="processing", error_message=None)

        def progress(done: int, total: int, message: str) -> None:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE books SET processed_pages=?, total_pages=?, error_message=?, updated_at=?
                    WHERE id=?
                    """,
                    (done, total, message, utc_now(), book_id),
                )

        try:
            result = get_importer(stored_path).import_book(stored_path, progress)
            self._save_result(book_id, result)
        except Exception as exc:
            self._update_status(book_id, status="failed", error_message=str(exc)[:1000])

    def _save_result(self, book_id: int, result: ImportResult) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM sections WHERE book_id=?", (book_id,))
            for section_index, section in enumerate(result.sections):
                section_cursor = connection.execute(
                    """
                    INSERT INTO sections (book_id, title, order_index, page_number)
                    VALUES (?, ?, ?, ?)
                    """,
                    (book_id, section.title, section_index, section.page_number),
                )
                section_id = int(section_cursor.lastrowid)
                connection.executemany(
                    """
                    INSERT INTO paragraphs
                    (book_id, section_id, order_index, text, page_number)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (book_id, section_id, index, paragraph.text, paragraph.page_number)
                        for index, paragraph in enumerate(section.paragraphs)
                    ],
                )
            connection.execute(
                """
                UPDATE books SET title=?, author=?, status='complete', error_message=NULL,
                    total_pages=?, processed_pages=?, char_count=?, ocr_pages=?, failed_pages=?, updated_at=?
                WHERE id=?
                """,
                (
                    result.title,
                    result.author,
                    result.total_pages,
                    result.processed_pages,
                    result.char_count,
                    result.ocr_pages,
                    json.dumps(result.failed_pages),
                    now,
                    book_id,
                ),
            )

    def _update_status(self, book_id: int, **values: object) -> None:
        allowed = {"status", "error_message"}
        items = [(key, value) for key, value in values.items() if key in allowed]
        assignments = ", ".join(f"{key}=?" for key, _ in items)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE books SET {assignments}, updated_at=? WHERE id=?",
                (*[value for _, value in items], utc_now(), book_id),
            )

    def delete_book(self, book_id: int) -> bool:
        book = self.database.fetch_one("SELECT file_path FROM books WHERE id=?", (book_id,))
        if not book:
            return False
        with self.database.connect() as connection:
            connection.execute("DELETE FROM books WHERE id=?", (book_id,))
        book_folder = Path(str(book["file_path"])).resolve().parent
        try:
            book_folder.relative_to(self.books_dir)
        except ValueError:
            return True
        if book_folder != self.books_dir and book_folder.exists():
            shutil.rmtree(book_folder)
        return True


def insert_annotation_and_vocabulary(
    connection: sqlite3.Connection,
    *,
    book: sqlite3.Row,
    paragraph: sqlite3.Row,
    section: sqlite3.Row,
    start_offset: int,
    end_offset: int,
    selected_text: str,
    chinese_annotation: str,
    all_chinese_meanings: list[str],
    sentence: str,
) -> dict[str, object]:
    page_or_chapter = (
        f"第 {paragraph['page_number']} 页" if paragraph["page_number"] else str(section["title"])
    )
    created_at = utc_now()
    cursor = connection.execute(
        """
        INSERT INTO annotations
        (book_id, paragraph_id, start_offset, end_offset, selected_text,
         chinese_annotation, all_chinese_meanings, sentence, page_or_chapter, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book["id"],
            paragraph["id"],
            start_offset,
            end_offset,
            selected_text,
            chinese_annotation,
            json.dumps(all_chinese_meanings, ensure_ascii=False),
            sentence,
            page_or_chapter,
            created_at,
        ),
    )
    annotation_id = int(cursor.lastrowid)
    duplicate_vocabulary = connection.execute(
        """
        SELECT id FROM vocabulary_entries
        WHERE lower(selected_text)=lower(?) AND sentence=?
        """,
        (selected_text, sentence),
    ).fetchone()
    if not duplicate_vocabulary:
        connection.execute(
            """
            INSERT INTO vocabulary_entries
            (annotation_id, selected_text, chinese_annotation,
             all_chinese_meanings, sentence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                annotation_id,
                selected_text,
                chinese_annotation,
                json.dumps(all_chinese_meanings, ensure_ascii=False),
                sentence,
                created_at,
            ),
        )
    return {
        "id": annotation_id,
        "book_id": book["id"],
        "paragraph_id": paragraph["id"],
        "start_offset": start_offset,
        "end_offset": end_offset,
        "selected_text": selected_text,
        "chinese_annotation": chinese_annotation,
        "all_chinese_meanings": all_chinese_meanings,
        "sentence": sentence,
        "page_or_chapter": page_or_chapter,
        "created_at": created_at,
        "existing": False,
    }
