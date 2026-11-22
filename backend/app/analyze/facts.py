"""RepoSnapshot → RepoFacts: LLM에 넘길 레포 요약(이름·소개·스택·페이지별 요소)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from app.analyze.elements import Element, extract_elements
from app.analyze.resolve import imports_by_spec, reexports, resolve
from app.analyze.routes import AppRoot, Route, _deps, find_app_root, routes_for
from app.analyze.services import service_stack
from app.github import RepoSnapshot

SUMMARY_LIMIT = 300
README_LIMIT = 2000  # 이야기(문제·해결) 근거로 LLM에 넘기는 README 본문 상한
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
    readme: str = ""  # README 본문(마크업 제거, README_LIMIT 자)
    services: list[str] = field(default_factory=list)  # 프론트 밖 백엔드·DB·외부 API (services.py)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> RepoFacts:
        d = json.loads(text)
        d.setdefault("readme", "")  # 이전 run 의 facts.json
        d.setdefault("services", [])
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


_BADGE = re.compile(r"^\s*(?:\[!\[|!\[)")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_HTML_TAG = re.compile(r"<[^>]+>")


def readme_body(readme: str) -> str:
    """HTML 태그·이미지·배지·코드 블록(``` ~~~)을 뺀 README 본문 (README_LIMIT 자)."""
    out: list[str] = []
    fenced = False
    for line in readme.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced or _BADGE.match(line):
            continue
        text = _HTML_TAG.sub("", line)  # <p align=center>핵심 문장</p> → 핵심 문장
        if line.strip() and not text.strip():
            continue  # 태그만 있던 줄(<img>, </div>)은 빈 줄로도 남기지 않는다
        line = text
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line.rstrip())
    return "\n".join(out).strip()[:README_LIMIT]


_COMPONENT_DIRS = ("components/", "app/components/", "src/components/")
_TEMPLATE_TAG = re.compile(r"<([A-Za-z][\w-]*)")


def _norm(name: str) -> str:
    return name.replace("-", "").lower()


def component_registry(snap: RepoSnapshot, root: AppRoot) -> dict[str, str]:
    """Nuxt·unplugin-vue-components 자동 import: 태그 이름(정규화) → 컴포넌트 파일.

    components/media/Hero.vue → MediaHero (폴더가 접두어, 파일 이름이 이미 접두어로 시작하면 생략),
    파일 이름만(Hero)으로도 등록한다.
    """
    if root.framework not in ("nuxt", "vue"):
        return {}
    base = f"{root.dir}/" if root.dir else ""
    reg: dict[str, str] = {}
    for path in snap.paths:
        rel = path[len(base) :] if path.startswith(base) else None
        if rel is None or not rel.endswith(".vue"):
            continue
        for d in _COMPONENT_DIRS:
            if rel.startswith(d):
                parts = rel[len(d) : -len(".vue")].split("/")
                if parts[-1] == "index" and len(parts) > 1:
                    parts = parts[:-1]
                name = ""
                for part in parts:
                    name = part if _norm(part).startswith(_norm(name)) else name + part
                reg.setdefault(_norm(name), path)
                reg.setdefault(_norm(parts[-1]), path)
                break
    return reg


def _auto_components(src: str, registry: dict[str, str]) -> list[str]:
    out: list[str] = []
    for tag in _TEMPLATE_TAG.findall(src):
        key = _norm(tag)
        key = key.removeprefix("lazy") if key not in registry else key
        if (path := registry.get(key)) and path not in out:
            out.append(path)
    return out


def _next_specs(src: str, wanted: set[str] | None) -> list[tuple[str, set[str] | None]]:
    """다음에 따라갈 (모듈, 필요한 이름). 묶음(index) 파일이면 가져온 이름의 재export 만."""
    barrel = reexports(src)
    if wanted is None or not barrel:
        return imports_by_spec(src)
    picked: list[tuple[str, set[str] | None]] = []
    for spec, mapping in barrel:
        if mapping is None:  # export * from — 무엇이 들었는지 모르니 그대로 넘긴다
            picked.append((spec, wanted))
        elif hit := {orig for alias, orig in mapping.items() if alias in wanted}:
            picked.append((spec, hit))
    return picked


def page_elements(
    snap: RepoSnapshot, route: Route, root: AppRoot, others: frozenset[str] = frozenset()
) -> list[Element]:
    """페이지 파일의 요소 + 그 파일이 import 하는 컴포넌트의 요소 (BFS, 등장 순서).

    컴포넌트를 못 찾은 라우트(file=라우터 파일)는 따라가지 않는다 — 모든 페이지가 섞인다.
    others(다른 라우트의 페이지 파일)도 따라가지 않는다 — 이동하려고 import 한 다른 화면이다.
    """
    known = set(snap.paths) | set(snap.files)
    # (파일, 깊이, 이 파일에서 필요한 export 이름 | None=전부)
    registry = component_registry(snap, root)
    queue: list[tuple[str, int, set[str] | None]] = [(route.file, 0, None)]
    seen = {route.file}
    out: list[Element] = []
    selectors: set[str] = set()
    while queue and len(out) < MAX_ELEMENTS and len(seen) <= FOLLOW_FILES:
        file, depth, wanted = queue.pop(0)
        src = snap.read(file) or ""
        for el in extract_elements(src):
            if el.selector not in selectors:
                selectors.add(el.selector)
                out.append(el)
        if not route.resolved or depth >= FOLLOW_DEPTH:
            continue
        for spec, names in _next_specs(src, wanted):
            target = resolve(spec, file, known, root.dir)
            if target and target not in seen | others and not _NOT_UI.search(spec):
                seen.add(target)
                queue.append((target, depth + 1, names))
        for target in _auto_components(src, registry):
            if target not in seen | others:
                seen.add(target)
                queue.append((target, depth + 1, None))
    return out[:MAX_ELEMENTS]


def _elements(
    snap: RepoSnapshot, route: Route, root: AppRoot, pages: frozenset[str]
) -> list[Element]:
    """동적 경로는 goto 할 수 없으니 요소를 뽑지 않는다. Flutter 는 Dart 위젯에서 role 셀렉터."""
    if route.dynamic:
        return []
    if root.framework == "flutter":
        from app.analyze.flutter import flutter_page_elements

        return flutter_page_elements(snap, route, root, pages - {route.file})
    return page_elements(snap, route, root, pages - {route.file})


def build_facts(snap: RepoSnapshot) -> RepoFacts:
    text = _readme(snap)
    name, summary = _name_and_summary(text, snap.repo)
    readme = readme_body(text)
    root = find_app_root(snap)
    if root is None:
        return RepoFacts(name, summary, [], None, None, [], readme, service_stack(snap, None))
    routes = routes_for(snap, root)
    files = frozenset(r.file for r in routes if r.resolved)
    pages = [PageFacts(r.path, r.dynamic, r.file, _elements(snap, r, root, files)) for r in routes]
    snap.save()  # 분석 중 더 받은 컴포넌트 파일까지 캐시
    stack = sorted(_deps(root.package))
    services = service_stack(snap, root)
    return RepoFacts(name, summary, stack, root.dir, root.framework, pages, readme, services)
