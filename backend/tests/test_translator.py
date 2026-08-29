from __future__ import annotations

import asyncio
import json

import httpx

from backend.app.translator import OllamaTranslator


def test_translation_uses_sentence_and_cleans_echoed_source() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": '{"translation":"hippies（嬉皮士）"}'}},
        )

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            translator = OllamaTranslator("http://ollama.test", "qwen3:4b", client=client)
            return await translator.translate(
                "hippies", "The block was a collection of hippies."
            )

    result = asyncio.run(run())

    assert result == {"contextual_translation": "嬉皮士", "meanings": ["嬉皮士"]}
    assert isinstance(captured[0]["format"], dict)
    assert "The block was a collection of hippies." in str(captured[0]["messages"])


def test_malformed_model_response_is_retried() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        content = (
            '{"translation":'
            if call_count == 1
            else '{"translation":"马车（名词）"}'
        )
        return httpx.Response(200, json={"message": {"content": content}})

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            translator = OllamaTranslator("http://ollama.test", "qwen3:4b", client=client)
            return await translator.translate("wagon", "Can I ride in your wagon?")

    result = asyncio.run(run())

    assert call_count == 2
    assert result["contextual_translation"] == "马车"
