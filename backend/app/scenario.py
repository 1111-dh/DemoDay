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


def _demo_page(path: str, dynamic: bool) -> bool:
    return not dynamic and not _NOT_DEMO.search(path)


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


def _user_message(facts: RepoFacts) -> str:
    data = json.loads(facts.to_json())
    data["pages"] = [p for p in data["pages"] if _demo_page(p["path"], p["dynamic"])]
    return "RepoFacts:\n" + json.dumps(data, ensure_ascii=False, indent=2)


def scenario_from_llm(facts: RepoFacts, base_url: str, llm: LLM) -> dict | None:
    need = _min_steps(facts)

    def check(draft: ScenarioDraft) -> list[str]:
        steps, dropped = _ground(draft, facts)
        problems = schema_errors("scenario", {"baseUrl": _base(base_url), "steps": steps})
        if len(steps) < need:
            problems.append(f"유효한 단계가 {len(steps)}개뿐 — {need}개 이상 필요")
        return problems + dropped if problems else []

    draft = generate(
        llm, system=SYSTEM, user=_user_message(facts), output=ScenarioDraft, check=check
    )
    if draft is None:
        return None
    return {"baseUrl": _base(base_url), "steps": ground(draft, facts)}


def build_scenario(facts: RepoFacts, base_url: str, llm: LLM | None) -> dict:
    result = scenario_from_llm(facts, base_url, llm) if llm else None
    return result or default_scenario(facts, base_url)


def analyze(
    repo_url: str,
    base_url: str,
    out_dir: Path,
    llm: LLM | None,
    *,
    fetch: Callable[[str], RepoSnapshot] = fetch_repo,
    cache_dir: Path = paths.CACHE,
) -> dict:
    snap = fetch(repo_url)
    facts = build_facts(snap)
    key = hashlib.sha1(_base(base_url).encode()).hexdigest()[:8]
    cache = cache_dir / f"scenario__{snap.owner}__{snap.repo}__{snap.sha}__{key}.json"

    if cache.exists():
        scenario = json.loads(cache.read_text())
    else:
        scenario = scenario_from_llm(facts, base_url, llm) if llm else None
        if scenario is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(scenario, ensure_ascii=False))
        else:
            scenario = default_scenario(facts, base_url)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "facts.json").write_text(facts.to_json())
    (out_dir / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=2))
    return scenario
