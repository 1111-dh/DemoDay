"""앱 루트·프레임워크 탐지와 라우트 추출 진입점(routes_for).

- 파일 기반: Next.js(app·pages), Nuxt(pages/) — 이 파일
- 코드 기반: React Router · Vue Router — code_routes.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from app.github import RepoSnapshot

Framework = Literal["next-app", "next-pages", "nuxt", "react", "vue"]
_JS_PAGE = r"\.(?:tsx|jsx|ts|js)$"


@dataclass
class AppRoot:
    dir: str  # "" = 레포 루트
    framework: Framework
    package: dict = field(default_factory=dict)


@dataclass
class Route:
    path: str
    dynamic: bool
    file: str
    resolved: bool = True  # False = 컴포넌트를 못 찾아 file 이 라우터 파일 자체


def _deps(package: dict) -> dict:
    return {**package.get("dependencies", {}), **package.get("devDependencies", {})}


def _rel(path: str, base: str) -> str | None:
    """base 디렉터리 기준 상대경로. base 밖이면 None."""
    if not base:
        return path
    return path[len(base) + 1 :] if path.startswith(base + "/") else None


def _matches(paths: list[str], base: str, pattern: str) -> list[tuple[str, str]]:
    """(원본 경로, pattern 첫 그룹) — base 아래에서 pattern 에 맞는 파일."""
    out = []
    for p in paths:
        rel = _rel(p, base)
        if rel is not None and (m := re.match(pattern, rel)):
            out.append((p, m.group(1)))
    return out


def _app_router_files(paths: list[str], base: str) -> list[tuple[str, str]]:
    return _matches(paths, base, r"^(?:src/)?app/((?:.*/)?)page" + _JS_PAGE)


def _pages_router_files(paths: list[str], base: str) -> list[tuple[str, str]]:
    return _matches(paths, base, r"^(?:src/)?pages/(.*)" + _JS_PAGE)


def _nuxt_files(paths: list[str], base: str) -> list[tuple[str, str]]:
    return _matches(paths, base, r"^(?:src/|app/)?pages/(.*)\.vue$")


def _candidate(base: str, package: dict, paths: list[str]) -> tuple[int, int, AppRoot] | None:
    """(우선순위, 크기, AppRoot). 메타 프레임워크가 라이브러리보다 우선."""
    deps = _deps(package)
    if "next" in deps:
        app_files = _app_router_files(paths, base)
        fw: Framework = "next-app" if app_files else "next-pages"
        return 1, len(app_files or _pages_router_files(paths, base)), AppRoot(base, fw, package)
    if "nuxt" in deps:
        return 1, len(_nuxt_files(paths, base)), AppRoot(base, "nuxt", package)
    for lib in ("react", "vue"):
        if lib in deps:
            size = sum(1 for p in paths if _rel(p, base) is not None)
            return 0, size, AppRoot(base, lib, package)
    return None


def find_app_root(snap: RepoSnapshot) -> AppRoot | None:
    candidates: list[tuple[int, int, AppRoot]] = []
    for path, text in snap.files.items():
        name = path.rsplit("/", 1)[-1]
        base = path.rsplit("/", 1)[0] if "/" in path else ""
        if name != "package.json":
            continue
        try:
            package = json.loads(text)
        except json.JSONDecodeError:
            continue
        if c := _candidate(base, package, snap.paths):
            candidates.append(c)
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


def sort_routes(routes: list[Route]) -> list[Route]:
    def key(r: Route) -> tuple[int, str]:
        return (0 if r.path == "/" else r.path.count("/"), r.path)

    return sorted(routes, key=key)


def _is_group(seg: str) -> bool:
    return seg.startswith("(") and seg.endswith(")")


def next_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    routes: dict[str, Route] = {}
    if root.framework == "next-app":
        for file, sub in _app_router_files(snap.paths, root.dir):
            segments = [s for s in sub.split("/") if s]
            # 병렬(@slot)·인터셉트((.)...)·private(_x) 세그먼트가 있으면 제외
            if any(s.startswith(("@", "_", "(.")) for s in segments):
                continue
            path = "/" + "/".join(s for s in segments if not _is_group(s))
            routes.setdefault(path, Route(path, "[" in path, file))
    elif root.framework == "next-pages":
        for file, sub in _pages_router_files(snap.paths, root.dir):
            if sub.startswith("api/") or sub.split("/")[-1].startswith("_"):
                continue
            parts = sub.split("/")
            if parts[-1] == "index":
                parts = parts[:-1]
            path = "/" + "/".join(parts)
            routes.setdefault(path, Route(path, "[" in path, file))
    return sort_routes(list(routes.values()))


def nuxt_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    """pages/**/*.vue. index → 상위, (group) 제거, [id]·_id(Nuxt 2) 는 동적."""
    routes: dict[str, Route] = {}
    for file, sub in _nuxt_files(snap.paths, root.dir):
        parts = [s for s in sub.split("/") if s and not _is_group(s)]
        if parts and parts[-1] == "index":
            parts = parts[:-1]
        path = "/" + "/".join(parts)
        dynamic = "[" in path or any(s.startswith("_") for s in parts)
        routes.setdefault(path, Route(path, dynamic, file))
    return sort_routes(list(routes.values()))


def routes_for(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    from app.analyze.code_routes import code_routes

    if root.framework in ("next-app", "next-pages"):
        return next_routes(snap, root)
    if root.framework == "nuxt":
        return nuxt_routes(snap, root)
    return code_routes(snap, root)
