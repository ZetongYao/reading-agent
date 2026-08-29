from __future__ import annotations

import json
import re

import httpx


class OllamaUnavailableError(Exception):
    pass


class TranslationGenerationError(Exception):
    pass


_CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")


class OllamaTranslator:
    def __init__(
        self,
        url: str,
        model: str,
        test_translation: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.test_translation = test_translation
        self.client = client

    async def _get(self, path: str) -> httpx.Response:
        if self.client:
            return await self.client.get(f"{self.url}{path}")
        async with httpx.AsyncClient(timeout=3) as client:
            return await client.get(f"{self.url}{path}")

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        if self.client:
            return await self.client.post(f"{self.url}{path}", json=payload)
        async with httpx.AsyncClient(timeout=12) as client:
            return await client.post(f"{self.url}{path}", json=payload)

    async def warmup(self) -> bool:
        """Load the model and compile the same short path used by translation."""
        if self.test_translation:
            return True
        try:
            await self.translate("book", "book")
            return True
        except (OllamaUnavailableError, TranslationGenerationError):
            return False

    async def check(self) -> dict[str, object]:
        if self.test_translation:
            return {
                "running": True,
                "model_installed": True,
                "model": self.model,
                "message": "测试翻译服务已就绪",
            }
        try:
            response = await self._get("/api/tags")
            response.raise_for_status()
            names = [item.get("name", "") for item in response.json().get("models", [])]
            model_installed = self.model in names or any(
                name.split(":")[0] == self.model.split(":")[0] for name in names
            )
            return {
                "running": True,
                "model_installed": model_installed,
                "model": self.model,
                "message": (
                    "Ollama 和模型均已就绪"
                    if model_installed
                    else f"Ollama 已启动，但未找到 {self.model}。请运行：ollama pull {self.model}"
                ),
            }
        except (httpx.HTTPError, ValueError):
            return {
                "running": False,
                "model_installed": False,
                "model": self.model,
                "message": (
                    "未检测到 Ollama。请安装并启动 Ollama，然后运行："
                    f"ollama pull {self.model}"
                ),
            }

    async def translate(self, selected_text: str, sentence: str) -> dict[str, object]:
        if self.test_translation:
            return {
                "contextual_translation": self.test_translation,
                "meanings": [self.test_translation, "公司；企业"],
            }
        translation: dict[str, object] | None = None
        try:
            translation = await self._translate_once(
                selected_text, sentence, detailed=False
            )
        except TranslationGenerationError:
            pass
        if translation is None or not self._is_chinese_translation(
            str(translation["contextual_translation"]), selected_text
        ):
            translation = await self._translate_once(
                selected_text, sentence, detailed=True
            )
        if not self._is_chinese_translation(
            str(translation["contextual_translation"]), selected_text
        ):
            raise TranslationGenerationError("模型未返回有效的中文释义，请点击重新生成。")
        return translation

    @staticmethod
    def _is_chinese_translation(value: str, selected_text: str) -> bool:
        normalized_value = " ".join(value.casefold().split())
        normalized_source = " ".join(selected_text.casefold().split())
        return bool(_CHINESE_PATTERN.search(value)) and normalized_value != normalized_source

    async def _translate_once(
        self, selected_text: str, prompt_context: str, *, detailed: bool
    ) -> dict[str, object]:
        selection_kind = "词组" if re.search(r"\s", selected_text.strip()) else "单词"
        if detailed:
            system = (
                "你是严谨的专业英汉词典。先根据完整原句确定待译英文的词性和准确含义，"
                "再给出标准、简短的简体中文词条。只翻译待译部分，不得解释或翻译整句。"
                "所有 JSON 值必须为简体中文，禁止返回英文。仅输出 JSON，字段为 "
                "contextual_translation 和 meanings。"
            )
            user_prompt = (
                f"待译英文{selection_kind}：{json.dumps(selected_text, ensure_ascii=False)}\n"
                f"完整原句：{prompt_context}\n只输出准确的中文短释义。"
            )
            predict_tokens = 96
        else:
            system = (
                "专业英汉词典。根据完整原句判断待译英文的词性和语境义。只翻译待译英文，"
                "不翻译或解释整句。必须使用标准、简短的简体中文词条；动词须保留被动含义。"
            )
            user_prompt = (
                f"待译英文{selection_kind}：{json.dumps(selected_text, ensure_ascii=False)}\n"
                f"完整原句：{prompt_context}"
            )
            predict_tokens = 24
        response_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "translation": {
                    "type": "string",
                    "description": "待译英文在原句中的简体中文短释义，严禁英文，不解释",
                }
            },
            "required": ["translation"],
        }
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json" if detailed else response_schema,
            "think": False,
            "keep_alive": -1,
            "messages": [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "options": {
                "temperature": 0,
                "num_ctx": 512,
                "num_predict": predict_tokens,
                "seed": 0,
            },
        }
        try:
            response = await self._post("/api/chat", payload)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.IGNORECASE).strip()
            parsed = json.loads(content)
            contextual = str(
                parsed.get("translation")
                or parsed.get("t")
                or parsed.get("contextual_translation")
                or parsed.get("chinese_translation")
                or ""
            ).strip()
            raw_meanings = parsed.get("meanings", [])
            meanings = []
            if isinstance(raw_meanings, list):
                for item in raw_meanings:
                    if not isinstance(item, str):
                        continue
                    meaning = re.sub(
                        re.escape(selected_text), "", item, flags=re.IGNORECASE
                    ).strip(" \t\r\n-—:：()（）[]【】")
                    if meaning and _CHINESE_PATTERN.search(meaning):
                        meanings.append(meaning[:200])
            if not contextual:
                raise ValueError("模型没有返回释义")
            contextual = re.sub(
                re.escape(selected_text), "", contextual, flags=re.IGNORECASE
            )
            contextual = re.sub(
                r"^\s*[（(]?(?:名词|动词|形容词|副词|词组|短语)[）)]?\s*[:：]?\s*",
                "",
                contextual,
            )
            contextual = re.sub(
                r"\s*[（(](?:名词|动词|形容词|副词|词组|短语)[）)]?\s*$",
                "",
                contextual,
            ).strip(" \t\r\n-—:：()（）[]【】")
            if not contextual or not _CHINESE_PATTERN.search(contextual):
                raise ValueError("模型没有返回中文释义")
            contextual = contextual[:200]
            deduplicated = []
            for meaning in [contextual, *meanings]:
                if meaning not in deduplicated:
                    deduplicated.append(meaning)
            return {
                "contextual_translation": contextual,
                "meanings": deduplicated[:8],
            }
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError(
                "本地翻译模型响应超时，请点击重新生成。"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"无法连接本地 Ollama。请确认 Ollama 已启动且已安装 {self.model}。"
            ) from exc
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            raise TranslationGenerationError(
                "模型返回格式异常，正在重新生成中文释义。"
            ) from exc
