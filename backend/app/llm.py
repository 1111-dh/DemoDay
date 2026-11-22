"""LLM 호출 + 검증 + 재시도. 실패는 예외가 아니라 None — 호출부가 규칙 기반 기본값을 쓴다."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Protocol

import anthropic
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
    return ClaudeLLM() if os.environ.get("ANTHROPIC_API_KEY") else None
