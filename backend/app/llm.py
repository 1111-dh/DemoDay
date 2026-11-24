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
_DAILY = re.compile(r"per day|\(TPD\)|\(RPD\)", re.IGNORECASE)


def is_daily_limit(res: httpx.Response) -> bool:
    """429 중 하루 한도(TPD·RPD) — 기다려도 몇 분~몇 시간은 안 풀린다."""
    return res.status_code == 429 and bool(_DAILY.search(res.text))


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
    *,
    keep_daily: bool = False,
    errors: list[int] | None = None,
) -> httpx.Response | None:
    """POST 하고 429면 안내 시간만큼 기다렸다 다시(최대 RATE_RETRIES). 200이 아니면 None.

    하루 한도(TPD) 429는 기다리지 않는다. keep_daily 면 그 응답을 돌려줘 호출부가 모델을 바꾼다.
    """
    for attempt in range(RATE_RETRIES + 1):
        try:
            res = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as e:
            log.warning("LLM 연결 실패: %s", type(e).__name__)
            if errors is not None:
                errors.append(0)
            return None
        if res.status_code != 429 or attempt == RATE_RETRIES or is_daily_limit(res):
            break
        wait = _rate_wait(res)
        log.warning("LLM 분당 한도(429) — %.1f초 뒤 다시 시도", wait)
        sleep(wait)
    if keep_daily and is_daily_limit(res):
        return res
    if res.status_code != 200:
        # 본문에는 Groq 조직 ID 등이 들어 있어 로그에 남기지 않는다 — 상태 코드와 오류 코드만
        try:
            code = res.json().get("error", {}).get("code", "")
        except ValueError:
            code = ""
        daily = " (하루 한도)" if is_daily_limit(res) else ""
        log.warning("LLM API 오류 %s %s%s", res.status_code, code, daily)
        if errors is not None:
            errors.append(res.status_code)
        return None
    return res


def is_down(status: int) -> bool:
    """이 공급자를 당분간 못 쓰는 오류: 연결 실패(0)·인증·크레딧·한도·서버. 400(형식)은 아님."""
    return status == 0 or status in (401, 402, 403, 404, 429) or status >= 500


def strict_schema(schema: dict) -> dict:
    """strict JSON schema(BAZE): 모든 object 에 additionalProperties:false, 필드 모두 required."""

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"
# 큰 모델의 하루 한도(TPD 20만)를 다 쓰면 — 한도는 모델마다 따로. gpt-oss-20b는 scene JSON
# 필드를 빠뜨려 실패했고(11/23 실측) qwen은 이미지 읽기와 같은 모델이라 분당 한도를 나눠 쓴다
GROQ_FALLBACK = "qwen/qwen3.8-27b"
# 학교 BAZE 게이트웨이(OpenAI 호환, 크레딧). Haiku 5.5: 1K당 입력 0.1·출력 0.5cr, 이미지 가능 —
# 11/23 비교에서 Gemini 3.8 Flash·GPT-6 Luna보다 스크린샷 읽기·자막이 정확하고
# 가장 쌌다(영상 1개 ≈ 4cr)
BAZE_BASE_URL = "https://api.baze.co/v1/gateway"
BAZE_CHAT_PATH = "/chat/completions/"  # 끝 / 없으면 리다이렉트
BAZE_MODEL = "claude-haiku-5-5"  # 화면 읽기·에이전트(호출이 많다)
# 시나리오·자막 글쓰기(영상당 2~3번) — 문장·기능 선택 품질이 영상에 보인다(11/24).
# Haiku의 약 20배 단가
BAZE_TEXT_MODEL = "claude-sonnet-5-5"


class OpenAICompatLLM:
    """OpenAI 호환 chat/completions (Groq 무료 플랜 등). JSON schema 응답을 pydantic으로 검증."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        fallback_models: list[str] | None = None,
        chat_path: str = "/chat/completions",
        strict: bool = False,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.url = base_url.rstrip("/") + chat_path
        self.strict = strict
        self.down = False  # 크레딧·인증·서버 오류로 이 공급자를 못 쓴다 — FallbackLLM 이 본다
        self.sleep = sleep
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self.fallback_models = list(fallback_models or [])
        self.client = client or httpx.Client(timeout=90)

    def _json_schema(self, output: type[pydantic.BaseModel]) -> dict:
        schema = output.model_json_schema()
        if self.strict:
            return {"name": output.__name__, "strict": True, "schema": strict_schema(schema)}
        return {"name": output.__name__, "schema": schema}

    def parse[T: pydantic.BaseModel](self, *, system: str, user: str, output: type[T]) -> T | None:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_schema", "json_schema": self._json_schema(output)},
        }
        while True:
            body["model"] = self.model
            errors: list[int] = []
            res = post_with_rate_retry(
                self.client,
                self.url,
                self.headers,
                body,
                self.sleep,
                keep_daily=True,
                errors=errors,
            )
            if res is None:
                self.down = any(is_down(e) for e in errors)
            if res is None or not is_daily_limit(res):
                break
            if not self.fallback_models:
                return None
            # 하루 한도는 기다려도 안 풀린다 — 다음 모델로 바꾸고 이 인스턴스는 계속 그 모델을 쓴다
            self.model = self.fallback_models.pop(0)
            log.warning("LLM 하루 한도 — %s 로 바꿔요", self.model)
        if res is None:
            return None
        try:
            content = res.json()["choices"][0]["message"]["content"]
            return output.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError):
            log.warning("LLM 출력 파싱 실패")
            return None


class FallbackLLM:
    """주 공급자(BAZE)가 크레딧·인증·서버 오류로 내려가면 그 뒤로는 예비(Groq)를 쓴다."""

    def __init__(self, primary: OpenAICompatLLM, backup: LLM):
        self.primary = primary
        self.backup = backup

    def parse[T: pydantic.BaseModel](self, *, system: str, user: str, output: type[T]) -> T | None:
        if not self.primary.down:
            result = self.primary.parse(system=system, user=user, output=output)
            if result is not None or not self.primary.down:
                return result
            log.warning("주 LLM(%s)을 못 써서 예비 LLM으로 바꿔요", self.primary.model)
        return self.backup.parse(system=system, user=user, output=output)


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


def _groq_llm() -> OpenAICompatLLM | None:
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return None
    return OpenAICompatLLM(
        base_url=GROQ_BASE_URL,
        api_key=groq_key,
        model=os.environ.get("GROQ_MODEL", GROQ_MODEL),
        fallback_models=[m for m in [os.environ.get("GROQ_FALLBACK_MODEL", GROQ_FALLBACK)] if m],
    )


def get_llm() -> LLM | None:
    """LLM_PROVIDER(baze|groq|anthropic)를 따르고, 비어 있으면 키가 있는 쪽(BAZE → Groq)을 쓴다.

    BAZE 는 Groq 키가 있으면 예비로 Groq 를 붙인다. 키가 없으면 None — 규칙 기반 기본값.
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    baze_key = os.environ.get("BAZE_API_KEY")
    if provider == "baze" or (not provider and baze_key):
        if not baze_key:
            return None
        baze = OpenAICompatLLM(
            base_url=BAZE_BASE_URL,
            api_key=baze_key,
            model=os.environ.get("BAZE_MODEL", BAZE_TEXT_MODEL),
            chat_path=BAZE_CHAT_PATH,
            strict=True,
        )
        backup = _groq_llm()
        return FallbackLLM(baze, backup) if backup else baze
    if provider == "groq" or (not provider and os.environ.get("GROQ_API_KEY")):
        return _groq_llm()
    if provider not in ("", "anthropic"):
        # 모르는 값이면 조용히 규칙 기반 기본값으로 떨어진다 — 꼭 알린다
        log.warning("LLM_PROVIDER=%r 를 모른다 — baze·groq·anthropic 중 하나만 쓴다", provider)
        return None
    return ClaudeLLM() if os.environ.get("ANTHROPIC_API_KEY") else None
