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
from app.analyze.facts import RepoFacts, build_facts
from app.contracts import schema_errors
from app.github import RepoSnapshot, fetch_repo
from app.llm import LLM, generate

MAX_STEPS = 7
MAX_PROMPT = 500
SCENARIO_VERSION = 2  # 시나리오 규칙이 바뀌면 올린다 — 이전 캐시를 쓰지 않게 (make warm 다시)
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

REFERENCE = (Path(__file__).parent / "prompts" / "reference.md").read_text().rstrip("\n")


def normalize_prompt(prompt: str | None) -> str | None:
    """앞뒤 공백 제거, MAX_PROMPT 자로 자르기. 비면 None."""
    # <<< >>> 는 참고 요청 블록의 경계 — 사용자 문장이 블록을 닫지 못하게 지운다
    text = (prompt or "").replace("<<<", "").replace(">>>", "").strip()[:MAX_PROMPT]
    return text or None


def with_reference(user: str, prompt: str | None, use: str) -> str:
    """사용자 프롬프트를 시스템 지시가 아닌 '참고 요청' 블록으로 user 메시지 끝에 붙인다."""
    return user + REFERENCE.format(use=use, prompt=prompt) if prompt else user


def _demo_page(path: str, dynamic: bool) -> bool:
    return not dynamic and not _NOT_DEMO.search(path) and not _STATEFUL.search(path)


def _static_pages(facts: RepoFacts) -> dict[str, set[str]]:
    return {
        p.path: {e.selector for e in p.elements}
        for p in facts.pages
        if _demo_page(p.path, p.dynamic)
    }


def _caption_for(path: str) -> str:
    if path == "/":
        return "메인 화면"
    return f"{path.rstrip('/').rsplit('/', 1)[-1]} 페이지"


def _ground(draft: ScenarioDraft, facts: RepoFacts) -> tuple[list[dict], list[str]]:
    pages = _static_pages(facts)
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
        if current is None:
            current = "/" if "/" in pages else next(iter(pages), "/")
            steps.append({"action": "goto", "path": current, "caption": _caption_for(current)})
        if s.selector not in pages.get(current, set()):
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
    data = json.loads(facts.to_json())
    data["pages"] = [p for p in data["pages"] if _demo_page(p["path"], p["dynamic"])]
    user = "RepoFacts:\n" + json.dumps(data, ensure_ascii=False, indent=2)
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
    raw_key = f"v{SCENARIO_VERSION}|{_base(base_url)}|{prompt or ''}"
    key = hashlib.sha1(raw_key.encode()).hexdigest()[:8]
    cache = cache_dir / f"scenario__{snap.owner}__{snap.repo}__{snap.sha}__{key}.json"

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
