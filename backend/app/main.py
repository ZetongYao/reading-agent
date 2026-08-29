from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import Settings
from .database import Database, utc_now
from .importers import supported_extensions
from .library import LibraryService, insert_annotation_and_vocabulary
from .schemas import (
    AnnotationCreate,
    AppSettingsUpdate,
    ReadingProgressUpdate,
    TranslationPreviewCreate,
    VocabularyUpdate,
)
from .text_utils import sentence_at
from .translator import (
    OllamaTranslator,
    OllamaUnavailableError,
    TranslationGenerationError,
)


TRANSLATION_CACHE_VERSION = 2


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    database = Database(config.database_path)
    library = LibraryService(database, config.books_dir)
    translation_tasks: dict[str, asyncio.Task[dict[str, object]]] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.books_dir.mkdir(parents=True, exist_ok=True)
        database.initialize(
            os.getenv("OLLAMA_URL", "http://localhost:11434"),
            os.getenv("OLLAMA_MODEL", "qwen3:4b"),
        )
        app.state.ollama_client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=0.5),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        warmup_task: asyncio.Task[bool] | None = None
        if config.app_env != "test":
            warmup_task = asyncio.create_task(translator_from_settings().warmup())
        try:
            yield
        finally:
            if warmup_task and not warmup_task.done():
                warmup_task.cancel()
            running = [task for task in translation_tasks.values() if not task.done()]
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
            await app.state.ollama_client.aclose()

    app = FastAPI(title="原阅 · 英文原版书阅读与单词本", version="1.0.0", lifespan=lifespan)
    app.state.settings = config
    app.state.database = database
    app.state.library = library
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/formats")
    def formats() -> dict[str, list[str]]:
        return {"extensions": supported_extensions()}

    @app.post("/api/books", status_code=status.HTTP_202_ACCEPTED)
    async def import_book(
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, File(...)],
    ) -> dict[str, object]:
        safe_name = Path(file.filename or "book.txt").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in supported_extensions():
            raise HTTPException(415, f"不支持 {suffix or '未知'} 格式")
        book_folder = config.books_dir / uuid.uuid4().hex
        book_folder.mkdir(parents=True, exist_ok=False)
        stored_path = book_folder / safe_name
        try:
            with stored_path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    target.write(chunk)
        except Exception:
            shutil.rmtree(book_folder, ignore_errors=True)
            raise
        book_id = library.create_pending_book(safe_name, suffix, stored_path)
        background_tasks.add_task(library.process_book, book_id, stored_path)
        return {"id": book_id, "status": "pending", "message": "文件已保存，正在导入"}

    @app.get("/api/books")
    def list_books() -> list[dict[str, object]]:
        return database.fetch_all(
            """
            SELECT b.*, COUNT(DISTINCT s.id) AS section_count
            FROM books b LEFT JOIN sections s ON s.book_id=b.id
            GROUP BY b.id ORDER BY b.created_at DESC
            """
        )

    @app.get("/api/books/{book_id}")
    def get_book(book_id: int) -> dict[str, object]:
        book = database.fetch_one("SELECT * FROM books WHERE id=?", (book_id,))
        if not book:
            raise HTTPException(404, "没有找到这本书")
        book["sections"] = database.fetch_all(
            "SELECT * FROM sections WHERE book_id=? ORDER BY order_index", (book_id,)
        )
        book["progress"] = database.fetch_one(
            "SELECT * FROM reading_progress WHERE book_id=?", (book_id,)
        )
        return book

    @app.delete("/api/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    def delete_book(book_id: int) -> Response:
        if not library.delete_book(book_id):
            raise HTTPException(404, "没有找到这本书")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/sections/{section_id}")
    def get_section(section_id: int) -> dict[str, object]:
        section = database.fetch_one("SELECT * FROM sections WHERE id=?", (section_id,))
        if not section:
            raise HTTPException(404, "没有找到章节")
        paragraphs = database.fetch_all(
            "SELECT * FROM paragraphs WHERE section_id=? ORDER BY order_index", (section_id,)
        )
        for paragraph in paragraphs:
            paragraph["annotations"] = database.fetch_all(
                """
                SELECT * FROM annotations WHERE paragraph_id=?
                ORDER BY start_offset, end_offset
                """,
                (paragraph["id"],),
            )
        section["paragraphs"] = paragraphs
        return section

    @app.get("/api/books/{book_id}/content")
    def get_book_content(book_id: int) -> dict[str, object]:
        if not database.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
            raise HTTPException(404, "没有找到这本书")
        sections = database.fetch_all(
            "SELECT * FROM sections WHERE book_id=? ORDER BY order_index", (book_id,)
        )
        paragraphs = database.fetch_all(
            """
            SELECT * FROM paragraphs WHERE book_id=?
            ORDER BY section_id, order_index
            """,
            (book_id,),
        )
        annotations = database.fetch_all(
            """
            SELECT a.* FROM annotations a
            JOIN paragraphs p ON p.id=a.paragraph_id
            WHERE p.book_id=? ORDER BY a.paragraph_id, a.start_offset, a.end_offset
            """,
            (book_id,),
        )
        annotations_by_paragraph: dict[int, list[dict[str, object]]] = {}
        for annotation in annotations:
            annotations_by_paragraph.setdefault(int(annotation["paragraph_id"]), []).append(annotation)
        paragraphs_by_section: dict[int, list[dict[str, object]]] = {}
        for paragraph in paragraphs:
            paragraph["annotations"] = annotations_by_paragraph.get(int(paragraph["id"]), [])
            paragraphs_by_section.setdefault(int(paragraph["section_id"]), []).append(paragraph)
        for section in sections:
            section["paragraphs"] = paragraphs_by_section.get(int(section["id"]), [])
        return {"book_id": book_id, "sections": sections}

    @app.get("/api/books/{book_id}/search")
    def search_book(book_id: int, q: str = Query(min_length=1, max_length=100)) -> list[dict[str, object]]:
        pattern = f"%{q}%"
        return database.fetch_all(
            """
            SELECT p.id AS paragraph_id, p.section_id, p.text, s.title AS section_title,
                   p.page_number
            FROM paragraphs p JOIN sections s ON s.id=p.section_id
            WHERE p.book_id=? AND p.text LIKE ? COLLATE NOCASE
            ORDER BY s.order_index, p.order_index LIMIT 100
            """,
            (book_id, pattern),
        )

    @app.put("/api/books/{book_id}/progress")
    def update_progress(book_id: int, payload: ReadingProgressUpdate) -> dict[str, object]:
        if not database.fetch_one("SELECT id FROM books WHERE id=?", (book_id,)):
            raise HTTPException(404, "没有找到这本书")
        now = utc_now()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO reading_progress
                (book_id, section_id, paragraph_id, scroll_ratio, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(book_id) DO UPDATE SET
                    section_id=excluded.section_id,
                    paragraph_id=excluded.paragraph_id,
                    scroll_ratio=excluded.scroll_ratio,
                    updated_at=excluded.updated_at
                """,
                (book_id, payload.section_id, payload.paragraph_id, payload.scroll_ratio, now),
            )
        return {"book_id": book_id, **payload.model_dump(), "updated_at": now}

    def translator_from_settings() -> OllamaTranslator:
        app_settings = database.fetch_one("SELECT * FROM app_settings WHERE id=1")
        assert app_settings is not None
        return OllamaTranslator(
            str(app_settings["ollama_url"]),
            str(app_settings["ollama_model"]),
            config.test_translation if config.app_env == "test" else None,
            getattr(app.state, "ollama_client", None),
        )

    def translation_cache_key(selected_text: str, sentence: str) -> str:
        normalized_text = " ".join(selected_text.casefold().split())
        normalized_sentence = " ".join(sentence.casefold().split())
        return hashlib.sha256(
            f"{normalized_text}\0{normalized_sentence}".encode("utf-8")
        ).hexdigest()

    def has_chinese_translation(row: dict[str, object] | None) -> bool:
        return bool(
            row
            and re.search(r"[\u3400-\u9fff]", str(row["contextual_translation"]))
        )

    def cached_translation(
        cache_key: str, selected_text: str, sentence: str
    ) -> dict[str, object] | None:
        cached = database.fetch_one(
            """
            SELECT cache_key, contextual_translation, all_chinese_meanings
            FROM translation_cache WHERE cache_key=? AND prompt_version=?
            """,
            (cache_key, TRANSLATION_CACHE_VERSION),
        )
        if cached and not has_chinese_translation(cached):
            with database.connect() as connection:
                connection.execute(
                    "DELETE FROM translation_cache WHERE cache_key=?", (cache_key,)
                )
            cached = None
        if not cached:
            existing = database.fetch_one(
                """
                SELECT chinese_annotation AS contextual_translation,
                       all_chinese_meanings
                FROM vocabulary_entries
                WHERE selected_text=? COLLATE NOCASE AND sentence=?
                ORDER BY created_at DESC LIMIT 1
                """,
                (selected_text, sentence),
            )
            cached = existing if has_chinese_translation(existing) else None
            cache_scope = "vocabulary"
        else:
            cache_scope = "exact"
        if not cached:
            return None
        return {
            "contextual_translation": str(cached["contextual_translation"]),
            "meanings": [str(item) for item in cached["all_chinese_meanings"]],
            "cache_hit": True,
            "cache_scope": cache_scope,
        }

    def store_translation(
        cache_key: str,
        selected_text: str,
        sentence: str,
        translation: dict[str, object],
    ) -> dict[str, object]:
        contextual = str(translation["contextual_translation"])
        meanings = [str(item) for item in translation["meanings"]]
        now = utc_now()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO translation_cache
                (cache_key, selected_text, sentence, contextual_translation,
                 all_chinese_meanings, prompt_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    contextual_translation=excluded.contextual_translation,
                    all_chinese_meanings=excluded.all_chinese_meanings,
                    prompt_version=excluded.prompt_version,
                    updated_at=excluded.updated_at
                """,
                (
                    cache_key,
                    selected_text,
                    sentence,
                    contextual,
                    json.dumps(meanings, ensure_ascii=False),
                    TRANSLATION_CACHE_VERSION,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                DELETE FROM translation_cache WHERE cache_key IN (
                    SELECT cache_key FROM translation_cache
                    ORDER BY updated_at DESC LIMIT -1 OFFSET 5000
                )
                """
            )
        return {
            "contextual_translation": contextual,
            "meanings": meanings,
            "cache_hit": False,
            "cache_scope": "generated",
        }

    async def generate_translation(
        cache_key: str, selected_text: str, sentence: str
    ) -> dict[str, object]:
        translation = await translator_from_settings().translate(selected_text, sentence)
        return store_translation(cache_key, selected_text, sentence, translation)

    @app.post("/api/translations/preview")
    async def preview_translation(payload: TranslationPreviewCreate) -> dict[str, object]:
        selected_text = " ".join(payload.selected_text.strip().split())
        sentence = " ".join(payload.sentence.strip().split())
        cache_key = translation_cache_key(selected_text, sentence)
        cached = cached_translation(cache_key, selected_text, sentence)
        if cached:
            return cached
        task = translation_tasks.get(cache_key)
        if task is None:
            task = asyncio.create_task(
                generate_translation(cache_key, selected_text, sentence)
            )
            translation_tasks[cache_key] = task

            def remove_finished(finished: asyncio.Task[dict[str, object]]) -> None:
                if translation_tasks.get(cache_key) is finished:
                    translation_tasks.pop(cache_key, None)

            task.add_done_callback(remove_finished)
        try:
            return await asyncio.shield(task)
        except TranslationGenerationError as exc:
            raise HTTPException(502, str(exc)) from exc
        except OllamaUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/annotations")
    async def create_annotation(payload: AnnotationCreate) -> dict[str, object]:
        existing = database.fetch_one(
            """
            SELECT * FROM annotations
            WHERE paragraph_id=? AND start_offset=? AND end_offset=?
            """,
            (payload.paragraph_id, payload.start_offset, payload.end_offset),
        )
        if existing:
            existing["existing"] = True
            return existing
        overlapping = database.fetch_one(
            """
            SELECT id FROM annotations
            WHERE paragraph_id=? AND NOT (end_offset<=? OR start_offset>=?)
            """,
            (payload.paragraph_id, payload.start_offset, payload.end_offset),
        )
        if overlapping:
            raise HTTPException(409, "所选文字与已有注释重叠，请选择未注释的词或词组")
        with database.connect() as connection:
            paragraph = connection.execute(
                "SELECT * FROM paragraphs WHERE id=?", (payload.paragraph_id,)
            ).fetchone()
            book = connection.execute("SELECT * FROM books WHERE id=?", (payload.book_id,)).fetchone()
            if not paragraph or not book or paragraph["book_id"] != book["id"]:
                raise HTTPException(404, "没有找到对应的段落或书籍")
            text = str(paragraph["text"])
            if payload.end_offset > len(text) or text[payload.start_offset : payload.end_offset] != payload.selected_text:
                raise HTTPException(422, "所选文字与段落位置不一致，请重新选择")
            section = connection.execute(
                "SELECT * FROM sections WHERE id=?", (paragraph["section_id"],)
            ).fetchone()
            assert section is not None
            sentence = sentence_at(text, payload.start_offset, payload.end_offset)
        if payload.chinese_annotation:
            chinese = payload.chinese_annotation.strip()
            meanings = [
                item.strip()[:200]
                for item in (payload.all_chinese_meanings or [])
                if item.strip()
            ]
            meanings = list(dict.fromkeys([chinese, *meanings]))[:8]
        else:
            try:
                translation = await translator_from_settings().translate(
                    payload.selected_text, sentence
                )
            except OllamaUnavailableError as exc:
                raise HTTPException(503, str(exc)) from exc
            chinese = str(translation["contextual_translation"])
            meanings = [str(item) for item in translation["meanings"]]
        try:
            with database.connect() as connection:
                return insert_annotation_and_vocabulary(
                    connection,
                    book=book,
                    paragraph=paragraph,
                    section=section,
                    start_offset=payload.start_offset,
                    end_offset=payload.end_offset,
                    selected_text=payload.selected_text,
                    chinese_annotation=chinese,
                    all_chinese_meanings=meanings,
                    sentence=sentence,
                )
        except sqlite3.IntegrityError:
            duplicate = database.fetch_one(
                """
                SELECT * FROM annotations
                WHERE paragraph_id=? AND start_offset=? AND end_offset=?
                """,
                (payload.paragraph_id, payload.start_offset, payload.end_offset),
            )
            if duplicate:
                duplicate["existing"] = True
                return duplicate
            raise

    @app.get("/api/vocabulary")
    def list_vocabulary(search: str = "") -> list[dict[str, object]]:
        clauses = ["1=1"]
        params: list[object] = []
        if search.strip():
            clauses.append(
                "(v.selected_text LIKE ? COLLATE NOCASE OR v.chinese_annotation LIKE ? "
                "OR v.all_chinese_meanings LIKE ? OR v.sentence LIKE ? COLLATE NOCASE)"
            )
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        return database.fetch_all(
            f"""
            SELECT v.id, v.annotation_id, v.selected_text, v.chinese_annotation,
                   v.all_chinese_meanings, v.sentence, v.created_at
            FROM vocabulary_entries v
            WHERE {' AND '.join(clauses)} ORDER BY v.created_at DESC
            """,
            tuple(params),
        )

    @app.patch("/api/vocabulary/{entry_id}")
    def update_vocabulary(entry_id: int, payload: VocabularyUpdate) -> dict[str, object]:
        with database.connect() as connection:
            entry = connection.execute(
                "SELECT * FROM vocabulary_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if not entry:
                raise HTTPException(404, "没有找到单词记录")
            connection.execute(
                """
                UPDATE vocabulary_entries
                SET chinese_annotation=?, all_chinese_meanings=? WHERE id=?
                """,
                (
                    payload.chinese_annotation,
                    json.dumps(
                        list(
                            dict.fromkeys(
                                [
                                    payload.chinese_annotation,
                                    *json.loads(str(entry["all_chinese_meanings"] or "[]")),
                                ]
                            )
                        )[:8],
                        ensure_ascii=False,
                    ),
                    entry_id,
                ),
            )
            connection.execute(
                """
                UPDATE annotations SET chinese_annotation=?, all_chinese_meanings=(
                    SELECT all_chinese_meanings FROM vocabulary_entries WHERE id=?
                ) WHERE id=?
                """,
                (payload.chinese_annotation, entry_id, entry["annotation_id"]),
            )
        updated = database.fetch_one(
            """
            SELECT id, annotation_id, selected_text, chinese_annotation,
                   all_chinese_meanings, sentence, created_at
            FROM vocabulary_entries WHERE id=?
            """,
            (entry_id,),
        )
        assert updated is not None
        return updated

    @app.delete("/api/vocabulary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    def delete_vocabulary(entry_id: int) -> Response:
        with database.connect() as connection:
            entry = connection.execute(
                "SELECT annotation_id FROM vocabulary_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if not entry:
                raise HTTPException(404, "没有找到单词记录")
            connection.execute("DELETE FROM annotations WHERE id=?", (entry["annotation_id"],))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/vocabulary/export.csv")
    def export_vocabulary(search: str = "") -> StreamingResponse:
        entries = list_vocabulary(search)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["单词或词组", "当前语境释义", "全部中文释义", "完整原句", "添加时间"])
        for entry in entries:
            writer.writerow(
                [
                    entry["selected_text"],
                    entry["chinese_annotation"],
                    "；".join(entry["all_chinese_meanings"]),
                    entry["sentence"],
                    entry["created_at"],
                ]
            )
        data = ("\ufeff" + output.getvalue()).encode("utf-8")
        filename = quote("原阅单词本.csv")
        return StreamingResponse(
            iter([data]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    @app.get("/api/settings")
    def get_settings() -> dict[str, object]:
        result = database.fetch_one("SELECT * FROM app_settings WHERE id=1")
        assert result is not None
        return result

    @app.put("/api/settings")
    def update_settings(payload: AppSettingsUpdate) -> dict[str, object]:
        values = payload.model_dump(exclude_none=True)
        if not values:
            return get_settings()
        allowed = {"ollama_url", "ollama_model", "theme", "font_size", "line_height"}
        values = {key: value for key, value in values.items() if key in allowed}
        if "ollama_url" in values:
            values["ollama_url"] = str(values["ollama_url"]).rstrip("/")
            if not str(values["ollama_url"]).startswith(("http://", "https://")):
                raise HTTPException(422, "Ollama 地址必须以 http:// 或 https:// 开头")
        assignments = ", ".join(f"{key}=?" for key in values)
        with database.connect() as connection:
            connection.execute(
                f"UPDATE app_settings SET {assignments}, updated_at=? WHERE id=1",
                (*values.values(), utc_now()),
            )
        return get_settings()

    @app.post("/api/ollama/check")
    async def check_ollama() -> dict[str, object]:
        current = get_settings()
        translator = OllamaTranslator(
            str(current["ollama_url"]),
            str(current["ollama_model"]),
            config.test_translation if config.app_env == "test" else None,
        )
        return await translator.check()

    return app


app = create_app()
