from __future__ import annotations

import hashlib
import json
from time import perf_counter

from fastapi.testclient import TestClient

from backend.app.main import create_app


SAMPLE = b"The company faced an existential crisis. Another sentence follows."


def import_sample(client: TestClient) -> tuple[int, int, int]:
    response = client.post("/api/books", files={"file": ("Context Book.txt", SAMPLE, "text/plain")})
    assert response.status_code == 202
    book_id = response.json()["id"]
    book = client.get(f"/api/books/{book_id}").json()
    assert book["status"] == "complete"
    section_id = book["sections"][0]["id"]
    paragraph_id = client.get(f"/api/sections/{section_id}").json()["paragraphs"][0]["id"]
    return book_id, section_id, paragraph_id


def test_annotation_offsets_vocabulary_and_persistence(client: TestClient, app_settings):
    book_id, section_id, paragraph_id = import_sample(client)
    preview = client.post(
        "/api/translations/preview",
        json={
            "selected_text": "company",
            "sentence": "The company faced an existential crisis.",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["contextual_translation"] == "测试释义"
    assert preview.json()["meanings"] == ["测试释义", "公司；企业"]
    started = perf_counter()
    cached_preview = client.post(
        "/api/translations/preview",
        json={
            "selected_text": "company",
            "sentence": "The company faced an existential crisis.",
        },
    )
    assert perf_counter() - started < 0.5
    assert cached_preview.json()["cache_hit"] is True
    assert cached_preview.json()["cache_scope"] == "exact"
    term_preview = client.post(
        "/api/translations/preview",
        json={"selected_text": "company", "sentence": "This company grew quickly."},
    )
    assert term_preview.json()["cache_hit"] is False
    assert term_preview.json()["cache_scope"] == "generated"
    response = client.post(
        "/api/annotations",
        json={
            "book_id": book_id,
            "paragraph_id": paragraph_id,
            "start_offset": 4,
            "end_offset": 11,
            "selected_text": "company",
        },
    )
    assert response.status_code == 200
    annotation = response.json()
    assert annotation["chinese_annotation"] == "测试释义"
    assert annotation["all_chinese_meanings"] == ["测试释义", "公司；企业"]
    assert annotation["sentence"] == "The company faced an existential crisis."

    duplicate = client.post(
        "/api/annotations",
        json={
            "book_id": book_id,
            "paragraph_id": paragraph_id,
            "start_offset": 4,
            "end_offset": 11,
            "selected_text": "company",
        },
    ).json()
    assert duplicate["existing"] is True
    assert len(client.get("/api/vocabulary").json()) == 1

    phrase = client.post(
        "/api/annotations",
        json={
            "book_id": book_id,
            "paragraph_id": paragraph_id,
            "start_offset": 21,
            "end_offset": 39,
            "selected_text": "existential crisis",
        },
    )
    assert phrase.status_code == 200
    rendered_data = client.get(f"/api/sections/{section_id}").json()
    assert [(item["start_offset"], item["end_offset"]) for item in rendered_data["paragraphs"][0]["annotations"]] == [(4, 11), (21, 39)]
    continuous = client.get(f"/api/books/{book_id}/content").json()
    assert continuous["sections"][0]["paragraphs"][0]["text"].startswith("The company")
    assert len(continuous["sections"][0]["paragraphs"][0]["annotations"]) == 2

    progress = {"section_id": section_id, "paragraph_id": paragraph_id, "scroll_ratio": 0.42}
    assert client.put(f"/api/books/{book_id}/progress", json=progress).status_code == 200

    # Recreate the whole FastAPI application against the same SQLite file.
    with TestClient(create_app(app_settings)) as restarted:
        saved_book = restarted.get(f"/api/books/{book_id}").json()
        assert saved_book["progress"]["paragraph_id"] == paragraph_id
        saved_section = restarted.get(f"/api/sections/{section_id}").json()
        assert len(saved_section["paragraphs"][0]["annotations"]) == 2
        assert len(restarted.get("/api/vocabulary").json()) == 2


def test_english_only_translation_cache_is_replaced(client: TestClient):
    selected_text = "indoctrinated"
    sentence = (
        "My father was a red-diaper baby and grew up indoctrinated "
        "in the philosophy of the left."
    )
    normalized = f"{selected_text.casefold()}\0{sentence.casefold()}"
    cache_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    now = "2026-08-18T00:00:00+00:00"
    with client.app.state.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO translation_cache
            (cache_key, selected_text, sentence, contextual_translation,
             all_chinese_meanings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                selected_text,
                sentence,
                selected_text,
                json.dumps([selected_text]),
                now,
                now,
            ),
        )

    response = client.post(
        "/api/translations/preview",
        json={"selected_text": selected_text, "sentence": sentence},
    )

    assert response.status_code == 200
    assert response.json()["contextual_translation"] == "测试释义"
    assert response.json()["cache_hit"] is False
    cached = client.app.state.database.fetch_one(
        "SELECT contextual_translation FROM translation_cache WHERE cache_key=?",
        (cache_key,),
    )
    assert cached and cached["contextual_translation"] == "测试释义"


def test_csv_edit_delete_and_cascade(client: TestClient):
    book_id, _section_id, paragraph_id = import_sample(client)
    vocabulary_columns = {
        item["name"]
        for item in client.app.state.database.fetch_all("PRAGMA table_info(vocabulary_entries)")
    }
    assert not vocabulary_columns.intersection(
        {"book_id", "paragraph_id", "book_title", "page_or_chapter"}
    )
    client.post(
        "/api/annotations",
        json={"book_id": book_id, "paragraph_id": paragraph_id, "start_offset": 4, "end_offset": 11, "selected_text": "company"},
    )
    entry = client.get("/api/vocabulary").json()[0]
    updated = client.patch(f"/api/vocabulary/{entry['id']}", json={"chinese_annotation": "公司"})
    assert updated.json()["chinese_annotation"] == "公司"
    csv_response = client.get("/api/vocabulary/export.csv")
    assert csv_response.status_code == 200
    csv_text = csv_response.content.decode("utf-8-sig")
    assert "单词或词组,当前语境释义,全部中文释义,完整原句,添加时间" in csv_text
    assert "company,公司" in csv_text
    assert "The company faced an existential crisis." in csv_text
    assert "Context Book" not in csv_text

    assert client.delete(f"/api/books/{book_id}").status_code == 204
    assert client.get("/api/vocabulary").json() == []


def test_rejects_incorrect_annotation_offset(client: TestClient):
    book_id, _section_id, paragraph_id = import_sample(client)
    response = client.post(
        "/api/annotations",
        json={"book_id": book_id, "paragraph_id": paragraph_id, "start_offset": 0, "end_offset": 7, "selected_text": "company"},
    )
    assert response.status_code == 422
