"""LLM 호출 + 검증 + 재시도. 실패는 예외가 아니라 None — 호출부가 규칙 기반 기본값을 쓴다."""

from __future__ import annotations

import logging
import os
import re
import time
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


RATE_RETRIES = 2  # 429(분당 토큰 한도)면 안내 시간만큼 기다렸다 같은 요청을 다시 보낸다
MAX_RATE_WAIT = 30.0
_TRY_AGAIN = re.compile(r"try again in ([\d.]+)\s*(ms|s)\b", re.IGNORECASE)


def _rate_wait(res: httpx.Response) -> float:
    """429 안내 "try again in 5.9s/640ms"(없으면 retry-after, 그것도 없으면 5초) + 0.5초."""
    if m := _TRY_AGAIN.search(res.text):
        sec = float(m.group(1)) / (1000 if m.group(2).lower() == "ms" else 1)
    else:
        try:
            sec = float(res.headers.get("retry-after", "5"))
        except ValueError:
            sec = 5.0
    return min(MAX_RATE_WAIT, sec + 0.5)


def post_with_rate_retry(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    body: dict,
    sleep: Callable[[float], None],
) -> httpx.Response | None:
    """POST 하고 429면 안내 시간만큼 기다렸다 다시(최대 RATE_RETRIES). 200이 아니면 None."""
    for attempt in range(RATE_RETRIES + 1):
        try:
            res = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as e:
            log.warning("LLM 연결 실패: %s", type(e).__name__)
            return None
        if res.status_code != 429 or attempt == RATE_RETRIES:
            break
        wait = _rate_wait(res)
        log.warning("LLM 분당 한도(429) — %.1f초 뒤 다시 시도", wait)
        sleep(wait)
    if res.status_code != 200:
        # 본문에는 Groq 조직 ID 등이 들어 있어 로그에 남기지 않는다 — 상태 코드와 오류 코드만
        try:
            code = res.json().get("error", {}).get("code", "")
        except ValueError:
            code = ""
        log.warning("LLM API 오류 %s %s", res.status_code, code)
        return None
    return res


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
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.sleep = sleep
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
        res = post_with_rate_retry(self.client, self.url, self.headers, body, self.sleep)
        if res is None:
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
