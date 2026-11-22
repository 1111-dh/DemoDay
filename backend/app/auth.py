"""scenario.auth(캡처 전 로그인)의 비밀값 다루기.

- run 디렉터리의 scenario.json 에만 실제 값을 둔다(runs/ 는 git 제외). LLM·캐시에는 넣지 않는다.
- API 응답에는 가린 값(redact)을 내보내고,
  웹이 가린 채로 다시 보내면 저장된 실제 값을 되살린다(restore).
"""

from __future__ import annotations

import copy

MASK = "***"


def _mask_step(step: dict) -> dict:
    step = dict(step)
    if "value" in step:
        step["value"] = MASK
    if "?" in step.get("path", ""):
        step["path"] = step["path"].split("?", 1)[0] + "?" + MASK
    return step


def redact(scenario: dict) -> dict:
    if "auth" not in scenario:
        return scenario
    out = copy.deepcopy(scenario)
    out["auth"]["steps"] = [_mask_step(s) for s in scenario["auth"]["steps"]]
    return out


def restore(incoming: dict, stored: dict) -> dict:
    """incoming 의 auth 가 stored 를 가린 것과 같으면 stored 의 실제 auth 로 바꾼다."""
    if "auth" in incoming and "auth" in stored and redact(stored)["auth"] == incoming["auth"]:
        return {**incoming, "auth": stored["auth"]}
    return incoming
