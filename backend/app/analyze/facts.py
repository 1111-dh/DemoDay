"""RepoSnapshot → RepoFacts: LLM에 넘길 레포 요약(이름·소개·스택·페이지별 요소)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from app.analyze.elements import Element, extract_elements
from app.analyze.routes import _deps, find_app_root, next_routes, react_routes
from app.github import RepoSnapshot

SUMMARY_LIMIT = 300


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


def build_facts(snap: RepoSnapshot) -> RepoFacts:
    name, summary = _name_and_summary(_readme(snap), snap.repo)
    root = find_app_root(snap)
    if root is None:
        return RepoFacts(name, summary, [], None, None, [])
    routes = react_routes(snap, root) if root.framework == "react" else next_routes(snap, root)
    pages = [
        PageFacts(r.path, r.dynamic, r.file, extract_elements(snap.files.get(r.file, "")))
        for r in routes
    ]
    stack = sorted(_deps(root.package))
    return RepoFacts(name, summary, stack, root.dir, root.framework, pages)
