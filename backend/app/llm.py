"""LLM 호출 + 검증 + 재시도. 실패는 예외가 아니라 None — 호출부가 규칙 기반 기본값을 쓴다."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Protocol

import anthropic
import httpx
import pydantic

MODEL = "claude-opus-5-5"
log = logging.getLogger(__name__)


class LLM(Protocol):
    def parse[T: pydantic.BaseModel](
        self, *, system: str, user: str, output: type[T]
    ) -> T | None: ...


class ClaudeLLM:
    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()

    def parse[T: pydantic.BaseModel](self, *, system: str, user: str, output: type[T]) -> T | None:
        try:
            res = self.client.messages.parse(
                model=MODEL,
                max_tokens=16000,
                output_config={"effort": "low"},
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=output,
            )
        except anthropic.APIConnectionError as e:
            log.warning("LLM 연결 실패: %s", type(e).__name__)
            return None
        except anthropic.APIStatusError as e:
            log.warning("LLM API 오류 %s", e.status_code)
            return None
        except pydantic.ValidationError:
            log.warning("LLM 출력 파싱 실패")
            return None
        if res.stop_reason == "refusal":
            log.warning("LLM refusal")
            return None
        return res.parsed_output


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"


class OpenAICompatLLM:
    """OpenAI 호환 chat/completions (Groq 무료 플랜 등). JSON schema 응답을 pydantic으로 검증."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self.client = client or httpx.Client(timeout=90)

    def parse[T: pydantic.BaseModel](self, *, system: str, user: str, output: type[T]) -> T | None:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": output.__name__, "schema": output.model_json_schema()},
            },
        }
        try:
            res = self.client.post(self.url, headers=self.headers, json=body)
        except httpx.HTTPError as e:
            log.warning("LLM 연결 실패: %s", type(e).__name__)
            return None
        if res.status_code != 200:
            log.warning("LLM API 오류 %s: %s", res.status_code, res.text[:300])
            return None
        try:
            content = res.json()["choices"][0]["message"]["content"]
            return output.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError):
            log.warning("LLM 출력 파싱 실패")
            return None


def generate[T: pydantic.BaseModel](
    llm: LLM,
    *,
    system: str,
    user: str,
    output: type[T],
    check: Callable[[T], list[str]],
    retries: int = 2,
) -> T | None:
    prompt = user
    for _ in range(retries + 1):
        result = llm.parse(system=system, user=prompt, output=output)
        errors = ["응답이 없거나 형식이 잘못됨"] if result is None else check(result)
        if not errors:
            return result
        prompt = (
            f"{user}\n\n이전 응답에 다음 문제가 있었다. 모두 고쳐서 다시 답하라:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
    return None


def get_llm() -> LLM | None:
    """LLM_PROVIDER(groq|anthropic)를 따르고, 비어 있으면 키가 있는 쪽을 쓴다.

    키가 없으면 None — 호출부가 규칙 기반 기본값을 쓴다.
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    groq_key = os.environ.get("GROQ_API_KEY")
    if provider == "groq" or (not provider and groq_key):
        if not groq_key:
            return None
        return OpenAICompatLLM(
            base_url=GROQ_BASE_URL,
            api_key=groq_key,
            model=os.environ.get("GROQ_MODEL", GROQ_MODEL),
        )
    return ClaudeLLM() if os.environ.get("ANTHROPIC_API_KEY") else None
