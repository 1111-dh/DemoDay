"""RepoFacts → scenario.json.

LLM 초안은 코드에서 확인된 경로·셀렉터만 남기고(ground), 실패하면 규칙 기반 기본값.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app import paths
from app.analyze.elements import Element
from app.analyze.facts import RepoFacts, build_facts
from app.contracts import schema_errors
from app.github import RepoSnapshot, fetch_repo
from app.llm import LLM, generate

MAX_STEPS = 7
MAX_PROMPT = 500
README_FOR_SCENARIO = 1200  # 시나리오 LLM 에 보내는 README 본문 (토큰 한도)
SCENARIO_VERSION = 8  # 시나리오 규칙이 바뀌면 올린다 — 이전 캐시를 쓰지 않게 (make warm 다시)
MIN_STEPS = 5
DEFAULT_PAGES = 6
SYSTEM = (Path(__file__).parent / "prompts" / "scenario.md").read_text()


class StepDraft(BaseModel):
    action: Literal["goto", "click", "type"]
    path: str
    selector: str
    value: str
    caption: str


class ScenarioDraft(BaseModel):
    steps: list[StepDraft]


# 데모에 보여주지 않는 페이지: 로그인·가입·비밀번호(MVP 제외), 약관·탈퇴, _private·__mock, 오류
_NOT_DEMO = re.compile(
    r"(?:^|/)(?:_[^/]*|(?:log-?in|sign-?in|sign-?up|register|log-?out|forgot(?:-password)?"
    r"|reset(?:-password)?|password(?:-reset)?|terms(?:-of-service)?|privacy(?:-policy)?|policy"
    r"|withdraw(?:al)?|404|not-found|error))(?=$|/)",
    re.IGNORECASE,
)


# 앞 단계 상태(입력·선택)가 있어야 열리는 흐름 중간 화면 — 바로 goto하면 에러 화면이 찍힌다
_STATEFUL = re.compile(r"(?:^|/)(?:results?|loading|success|complete|callback)(?=$|/)", re.I)

# 누르면 세션·데이터를 망가뜨리는 요소 — 데모 계정에서 누르지 않는다 (LLM 에 보이지도 않게)
_DANGER = re.compile(
    r"로그아웃|log ?out|sign ?out|탈퇴|삭제|delete|remove|결제|구매|purchase|checkout|pay\b"
    r"|초기화|reset|송금|환불|refund|unsubscribe|구독 ?취소"
    r"|다시 ?시도|재시도|retry|try again",  # 에러 상태에만 보이는 버튼 — 데모 흐름이 아니다
    re.IGNORECASE,
)


# 승인·반려 버튼 자체 — 데모 계정 데이터를 되돌릴 수 없게 바꾼다(심사용 '승인 대기 1개'가
# 첫 캡처에 사라진다). "승인 대기 보기" 같은 이동 링크는 두고, 글자 전체가 이 말일 때만 막는다
_DECIDE = re.compile(r"^\s*(?:승인|반려|거절|approve|reject|decline)(?:하기)?\s*$", re.IGNORECASE)


def _safe(element: dict | Element) -> bool:
    text = element["text"] if isinstance(element, dict) else element.text
    return not (_DANGER.search(text) or _DECIDE.match(text))


REFERENCE = (Path(__file__).parent / "prompts" / "reference.md").read_text().rstrip("\n")


def normalize_prompt(prompt: str | None) -> str | None:
    """앞뒤 공백 제거, MAX_PROMPT 자로 자르기. 비면 None."""
    # <<< >>> 는 참고 요청 블록의 경계 — 사용자 문장이 블록을 닫지 못하게 지운다
    text = (prompt or "").replace("<<<", "").replace(">>>", "").strip()[:MAX_PROMPT]
    return text or None


def with_reference(user: str, prompt: str | None, use: str) -> str:
    """사용자 프롬프트를 시스템 지시가 아닌 '참고 요청' 블록으로 user 메시지 끝에 붙인다."""
    return user + REFERENCE.format(use=use, prompt=prompt) if prompt else user


# 첫 가입 직후 화면 — 온보딩을 마친 데모 계정에선 리다이렉트되거나, 진행하면 데이터를 만든다
_FIRST_RUN = re.compile(r"(?:^|/)(?:onboarding|welcome|setup|get-?started)(?=$|/)", re.IGNORECASE)

# 단계형 화면의 2단계 이후(/input/2, /step/3) — 앞 단계 입력 없이 가면 깨진다. 1단계만
_LATER_STEP = re.compile(r"(?:^|/)(?:input|step|steps|wizard|stage)/(?:[2-9]|\d{2,})(?=$|/)", re.I)


def _demo_page(path: str, dynamic: bool) -> bool:
    return not dynamic and _shown(path)


def _shown(path: str) -> bool:
    """데모에 보여줄 만한 화면(로그인·약관·결과·단계형 중간 제외). 동적 여부와는 따로 본다."""
    return not (
        _NOT_DEMO.search(path)
        or _STATEFUL.search(path)
        or _LATER_STEP.search(path)
        or _FIRST_RUN.search(path)
    )


def _click_only_pages(facts: RepoFacts) -> dict[str, set[str]]:
    """동적 경로(/items/:id) — goto 는 못 하고, 바로 앞 click 으로 들어간 뒤에만 요소를 쓴다."""
    return {
        p.path: {e.selector for e in p.elements if _safe(e)}
        for p in facts.pages
        if p.dynamic and p.elements and _shown(p.path)
    }


def _static_pages(facts: RepoFacts) -> dict[str, set[str]]:
    return {
        p.path: {e.selector for e in p.elements if _safe(e)}
        for p in facts.pages
        if _demo_page(p.path, p.dynamic)
    }


def _caption_for(path: str) -> str:
    if path == "/":
        return "메인 화면"
    return f"{path.rstrip('/').rsplit('/', 1)[-1]} 페이지"


def _ground(draft: ScenarioDraft, facts: RepoFacts) -> tuple[list[dict], list[str]]:
    pages = _static_pages(facts)
    click_only = _click_only_pages(facts)
    steps: list[dict] = []
    dropped: list[str] = []
    current: str | None = None
    for s in draft.steps:
        caption = s.caption.strip()
        if s.action == "goto":
            if s.path not in pages:
                dropped.append(f"goto {s.path!r}: pages에 없는(또는 동적) 경로")
                continue
            current = s.path
            steps.append(
                {"action": "goto", "path": s.path, "caption": caption or _caption_for(s.path)}
            )
            continue
        if s.path in click_only and s.path != current:  # 동적 화면 — 앞 단계 click 으로만 들어간다
            if not steps or steps[-1]["action"] != "click":
                dropped.append(f"{s.action} {s.selector!r}: 동적 화면 {s.path}는 앞 click 뒤에만")
                continue
            current = s.path
        if current is None:
            current = "/" if "/" in pages else next(iter(pages), "/")
            steps.append({"action": "goto", "path": current, "caption": _caption_for(current)})
        if s.selector not in pages.get(current, click_only.get(current, set())):
            dropped.append(f"{s.action} {s.selector!r}: 페이지 {current}의 elements에 없음")
            continue
        if s.action == "type":
            if not s.value.strip():
                dropped.append(f"type {s.selector!r}: value가 비어 있음")
                continue
            steps.append(
                {"action": "type", "selector": s.selector, "value": s.value, "caption": caption}
            )
        else:
            steps.append({"action": "click", "selector": s.selector, "caption": caption})
    steps = steps[:MAX_STEPS]
    return [{"id": i, **s} for i, s in enumerate(steps, start=1)], dropped


def ground(draft: ScenarioDraft, facts: RepoFacts) -> list[dict]:
    return _ground(draft, facts)[0]


def _base(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def default_scenario(facts: RepoFacts, base_url: str) -> dict:
    pages = list(_static_pages(facts))[:DEFAULT_PAGES] or ["/"]
    steps = [
        {"id": i, "action": "goto", "path": p, "caption": _caption_for(p)}
        for i, p in enumerate(pages, start=1)
    ]
    return {"baseUrl": _base(base_url), "steps": steps}


def _min_steps(facts: RepoFacts) -> int:
    possible = sum(1 + len(sels) for sels in _static_pages(facts).values())
    return max(1, min(MIN_STEPS, possible))


def _user_message(facts: RepoFacts, prompt: str | None = None) -> str:
    """LLM 입력은 작게 — 무료 플랜 분당 토큰 한도(Groq 8000)를 넘으면 413 으로 거절된다.

    파일 경로·의존성 목록은 빼고, 요소는 셀렉터 문자열만, JSON 은 공백 없이.
    """
    pages = [
        {
            "path": p.path,
            "dynamic": p.dynamic,
            "elements": [e.selector for e in p.elements if _safe(e)],
        }
        for p in facts.pages
        if _demo_page(p.path, p.dynamic) or (p.dynamic and p.elements and _shown(p.path))
    ]
    data = {
        "name": facts.name,
        "summary": facts.summary,
        "readme": facts.readme[:README_FOR_SCENARIO],
        "pages": pages,
    }
    user = "RepoFacts:\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return with_reference(user, prompt, "화면 순서와 보여줄 기능에만 반영한다")


def scenario_from_llm(
    facts: RepoFacts, base_url: str, llm: LLM, prompt: str | None = None
) -> dict | None:
    need = _min_steps(facts)

    def check(draft: ScenarioDraft) -> list[str]:
        steps, dropped = _ground(draft, facts)
        problems = schema_errors("scenario", {"baseUrl": _base(base_url), "steps": steps})
        if len(steps) < need:
            problems.append(f"유효한 단계가 {len(steps)}개뿐 — {need}개 이상 필요")
        return problems + dropped if problems else []

    draft = generate(
        llm,
        system=SYSTEM,
        user=_user_message(facts, normalize_prompt(prompt)),
        output=ScenarioDraft,
        check=check,
    )
    if draft is None:
        return None
    return {"baseUrl": _base(base_url), "steps": ground(draft, facts)}


def build_scenario(
    facts: RepoFacts, base_url: str, llm: LLM | None, prompt: str | None = None
) -> dict:
    result = scenario_from_llm(facts, base_url, llm, prompt) if llm else None
    return result or default_scenario(facts, base_url)


def scenario_cache_path(
    snap: RepoSnapshot,
    base_url: str,
    prompt: str | None,
    facts: RepoFacts,
    cache_dir: Path = paths.CACHE,
) -> Path:
    """이 커밋·배포 URL·프롬프트·규칙 버전·분석 결과(facts)의 LLM 시나리오 캐시 파일.

    분석 규칙이 바뀌어 facts 가 달라지면(외부 링크 제외 등) 자동으로 새로 만든다.
    """
    facts_key = hashlib.sha1(facts.to_json().encode()).hexdigest()[:12]
    prompt_key = normalize_prompt(prompt) or ""
    raw_key = f"v{SCENARIO_VERSION}|{_base(base_url)}|{prompt_key}|{facts_key}"
    key = hashlib.sha1(raw_key.encode()).hexdigest()[:8]
    return cache_dir / f"scenario__{snap.owner}__{snap.repo}__{snap.sha}__{key}.json"


def analyze(
    repo_url: str,
    base_url: str,
    out_dir: Path,
    llm: LLM | None,
    *,
    prompt: str | None = None,
    fetch: Callable[[str], RepoSnapshot] = fetch_repo,
    cache_dir: Path = paths.CACHE,
) -> dict:
    """프롬프트가 있으면 out_dir/prompt.txt 에도 남긴다 — scene 생성이 같은 요청을 쓴다."""
    prompt = normalize_prompt(prompt)
    snap = fetch(repo_url)
    facts = build_facts(snap)
    cache = scenario_cache_path(snap, base_url, prompt, facts, cache_dir)

    if cache.exists():
        scenario = json.loads(cache.read_text())
    else:
        scenario = scenario_from_llm(facts, base_url, llm, prompt) if llm else None
        if scenario is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(scenario, ensure_ascii=False))
        else:
            scenario = default_scenario(facts, base_url)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "facts.json").write_text(facts.to_json())
    if prompt:
        (out_dir / "prompt.txt").write_text(prompt)
    (out_dir / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=2))
    return scenario
