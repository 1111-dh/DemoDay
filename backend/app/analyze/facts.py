"""RepoSnapshot → RepoFacts: LLM에 넘길 레포 요약(이름·소개·스택·페이지별 요소)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from app.analyze.elements import Element, extract_elements
from app.analyze.resolve import local_specs, resolve
from app.analyze.routes import AppRoot, Route, _deps, find_app_root, routes_for
from app.github import RepoSnapshot

SUMMARY_LIMIT = 300
MAX_ELEMENTS = 15
FOLLOW_FILES = 12  # 페이지 하나에서 따라갈 컴포넌트 파일 수
FOLLOW_DEPTH = 4  # 페이지 → (재export index) → 위젯 → 하위 컴포넌트
# UI가 아닌 모듈은 따라가지 않는다 (예산 낭비)
_NOT_UI = re.compile(
    r"(?:^|/)(?:api|apis|hooks?|stores?|models?|types?|utils?|config|constants|i18n|locales?"
    r"|styles?|assets|services?|queries|schemas?)(?:/|$)|\.(?:css|scss|svg|png|json)$"
)


@dataclass
class PageFacts:
    path: str
    dynamic: bool
    file: str
    elements: list[Element] = field(default_factory=list)


@dataclass
class RepoFacts:
    name: str
    summary: str
    stack: list[str]
    app_dir: str | None
    framework: str | None
    pages: list[PageFacts] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> RepoFacts:
        d = json.loads(text)
        d["pages"] = [
            PageFacts(**{**p, "elements": [Element(**e) for e in p["elements"]]})
            for p in d["pages"]
        ]
        return cls(**d)


def _readme(snap: RepoSnapshot) -> str:
    for path, text in snap.files.items():
        if "/" not in path and path.lower().startswith("readme"):
            return text
    return ""


def _name_and_summary(readme: str, fallback: str) -> tuple[str, str]:
    lines = readme.splitlines()
    name, start = fallback, 0
    for i, line in enumerate(lines):
        if m := re.match(r"^#\s+(.+)", line):
            name, start = m.group(1).strip(), i + 1
            break
    para: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            if para:
                break
            continue
        if line.lstrip().startswith(("#", "!", "<", "[!", "```")):
            if para:
                break
            continue
        para.append(line.strip())
    return name, " ".join(para)[:SUMMARY_LIMIT]


def page_elements(snap: RepoSnapshot, route: Route, root: AppRoot) -> list[Element]:
    """페이지 파일의 요소 + 그 파일이 import 하는 컴포넌트의 요소 (BFS, 등장 순서).

    컴포넌트를 못 찾은 라우트(file=라우터 파일)는 따라가지 않는다 — 모든 페이지가 섞인다.
    """
    known = set(snap.paths) | set(snap.files)
    queue, seen = [(route.file, 0)], {route.file}
    out: list[Element] = []
    selectors: set[str] = set()
    while queue and len(out) < MAX_ELEMENTS and len(seen) <= FOLLOW_FILES:
        file, depth = queue.pop(0)
        src = snap.read(file) or ""
        for el in extract_elements(src):
            if el.selector not in selectors:
                selectors.add(el.selector)
                out.append(el)
        if not route.resolved or depth >= FOLLOW_DEPTH:
            continue
        for spec in local_specs(src):
            target = resolve(spec, file, known, root.dir)
            if target and target not in seen and not _NOT_UI.search(spec):
                seen.add(target)
                queue.append((target, depth + 1))
    return out[:MAX_ELEMENTS]


def build_facts(snap: RepoSnapshot) -> RepoFacts:
    name, summary = _name_and_summary(_readme(snap), snap.repo)
    root = find_app_root(snap)
    if root is None:
        return RepoFacts(name, summary, [], None, None, [])
    pages = [
        PageFacts(r.path, r.dynamic, r.file, [] if r.dynamic else page_elements(snap, r, root))
        for r in routes_for(snap, root)
    ]
    snap.save()  # 분석 중 더 받은 컴포넌트 파일까지 캐시
    stack = sorted(_deps(root.package))
    return RepoFacts(name, summary, stack, root.dir, root.framework, pages)
