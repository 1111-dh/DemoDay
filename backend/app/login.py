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
_SUBMIT_EXACT = re.compile(r"^\s*(?:로그인|log ?in|sign ?in)\s*$", re.IGNORECASE)
# 소셜 로그인 버튼(서비스 이름) — 누르면 OAuth 페이지로 가서 로그인되지 않은 채 녹화된다.
# "Sign in with email" 같은 일반 버튼은 걸러지지 않게 서비스 이름만 본다.
_SOCIAL = re.compile(
    r"카카오|kakao|구글|google|네이버|naver|apple|애플|github|깃허브|facebook|페이스북",
    re.IGNORECASE,
)


def _form(page: PageFacts) -> tuple[list[Element], list[Element]]:
    inputs = [e for e in page.elements if e.kind == "input"]
    buttons = [e for e in page.elements if e.kind == "button" and not _SOCIAL.search(e.text)]
    return inputs, buttons


def _button_selector(button: Element) -> str:
    """text=로그인 은 화면에 안 보이는 제목(<h2 class=sr-only>로그인</h2>)에 먼저 걸릴 수 있다.

    HTML 버튼은 글자가 정확히 같은 <button>만 가리킨다. role 셀렉터(Flutter)는 이미 버튼만 가리킨다.
    """
    if not button.selector.startswith("text="):
        return button.selector
    text = button.text.replace("\\", "\\\\").replace('"', '\\"')
    return f'button:text-is("{text}")'


def login_steps(facts: RepoFacts, username: str, password: str) -> dict | None:
    """로그인 폼을 못 찾으면 None → API 400.

    비밀번호 칸·로그인 버튼을 확실히 못 찾으면 추측하지 않는다 — 캡처는 auth 실패에도 계속
    진행하므로, 잘못 고르면 에러 없이 로그아웃 상태가 녹화된다.
    """
    for page in facts.pages:
        if page.dynamic or not _LOGIN_PATH.search(page.path):
            continue
        inputs, buttons = _form(page)
        pw = next((e for e in inputs if _PASSWORD.search(f"{e.text} {e.selector}")), None)
        user = next((e for e in inputs if e is not pw), None)
        submit = next(
            (b for b in buttons if _SUBMIT_EXACT.match(b.text)),
            next((b for b in buttons if _SUBMIT.search(b.text)), None),
        )
        if pw is None or user is None or submit is None:
            continue
        steps = [
            {"action": "goto", "path": page.path, "caption": "로그인"},
            {"action": "type", "selector": user.selector, "value": username, "caption": "아이디"},
            {"action": "type", "selector": pw.selector, "value": password, "caption": "비밀번호"},
            {"action": "click", "selector": _button_selector(submit), "caption": "로그인"},
        ]
        return {"steps": [{"id": i, **s} for i, s in enumerate(steps, start=1)]}
    return None
