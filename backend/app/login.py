"""테스트 계정 아이디·비밀번호 → scenario.auth 로그인 단계.

레포 분석이 찾은 로그인 페이지(입력칸 2개 이상 + 버튼)에서 셀렉터를 고른다.
값은 run 디렉터리 scenario.json 에만 들어간다 (auth.py 규칙 그대로).
"""

from __future__ import annotations

import re

from app.analyze.elements import Element
from app.analyze.facts import PageFacts, RepoFacts

_LOGIN_PATH = re.compile(r"(?:^|/)(?:log-?in|sign-?in)(?=$|/)", re.IGNORECASE)
_PASSWORD = re.compile(r"password|비밀번호|비번|\bpw\b", re.IGNORECASE)
_SUBMIT = re.compile(r"로그인|log ?in|sign ?in", re.IGNORECASE)


def _form(page: PageFacts) -> tuple[list[Element], list[Element]]:
    inputs = [e for e in page.elements if e.kind == "input"]
    buttons = [e for e in page.elements if e.kind == "button"]
    return inputs, buttons


def login_steps(facts: RepoFacts, username: str, password: str) -> dict | None:
    """로그인 폼을 못 찾으면 None (예: 소셜 로그인 버튼만 있는 앱)."""
    for page in facts.pages:
        if not _LOGIN_PATH.search(page.path):
            continue
        inputs, buttons = _form(page)
        if len(inputs) < 2 or not buttons:
            continue
        pw = next((e for e in inputs if _PASSWORD.search(f"{e.text} {e.selector}")), inputs[1])
        user = next(e for e in inputs if e is not pw)
        submit = next((b for b in buttons if _SUBMIT.search(b.text)), buttons[-1])
        steps = [
            {"action": "goto", "path": page.path, "caption": "로그인"},
            {"action": "type", "selector": user.selector, "value": username, "caption": "아이디"},
            {"action": "type", "selector": pw.selector, "value": password, "caption": "비밀번호"},
            {"action": "click", "selector": submit.selector, "caption": "로그인"},
        ]
        return {"steps": [{"id": i, **s} for i, s in enumerate(steps, start=1)]}
    return None
