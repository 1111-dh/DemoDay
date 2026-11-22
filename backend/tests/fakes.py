"""테스트용 가짜 LLM — 정해둔 응답을 순서대로 돌려주고 받은 user 메시지를 기록한다."""

from __future__ import annotations

from typing import Any


class FakeLLM:
    def __init__(self, *responses: Any):
        self.responses = list(responses)
        self.users: list[str] = []

    def parse(self, *, system: str, user: str, output: type) -> Any:
        self.users.append(user)
        return self.responses.pop(0) if self.responses else None
