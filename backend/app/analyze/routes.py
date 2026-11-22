"""앱 루트 탐지와 라우트 추출. 파일 경로(Next) 또는 라우터 정의 문자열(React Router)만 본다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from app.github import RepoSnapshot

Framework = Literal["next-app", "next-pages", "react"]
_PAGE_EXT = r"\.(?:tsx|jsx|ts|js)$"


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


def _deps(package: dict) -> dict:
    return {**package.get("dependencies", {}), **package.get("devDependencies", {})}


def _rel(path: str, base: str) -> str | None:
    """base 디렉터리 기준 상대경로. base 밖이면 None."""
    if not base:
        return path
    return path[len(base) + 1 :] if path.startswith(base + "/") else None


def _app_router_files(paths: list[str], base: str) -> list[tuple[str, str]]:
    """(원본 경로, app/ 이후 경로) — app/ 또는 src/app/ 아래 page 파일."""
    out = []
    for p in paths:
        rel = _rel(p, base)
        if rel is None:
            continue
        m = re.match(r"^(?:src/)?app/(.*)page" + _PAGE_EXT, rel)
        if m:
            out.append((p, m.group(1)))
    return out


def _pages_router_files(paths: list[str], base: str) -> list[tuple[str, str]]:
    out = []
    for p in paths:
        rel = _rel(p, base)
        if rel is None:
            continue
        m = re.match(r"^(?:src/)?pages/(.*)" + _PAGE_EXT, rel)
        if m:
            out.append((p, m.group(1)))
    return out


def find_app_root(snap: RepoSnapshot) -> AppRoot | None:
    candidates: list[tuple[int, int, AppRoot]] = []
    for path, text in snap.files.items():
        if path.rsplit("/", 1)[-1] != "package.json":
            continue
        try:
            package = json.loads(text)
        except json.JSONDecodeError:
            continue
        deps = _deps(package)
        base = path.rsplit("/", 1)[0] if "/" in path else ""
        if "next" in deps:
            app_files = _app_router_files(snap.paths, base)
            framework: Framework = "next-app" if app_files else "next-pages"
            count = len(app_files or _pages_router_files(snap.paths, base))
            candidates.append((1, count, AppRoot(base, framework, package)))
        elif "react" in deps:
            count = sum(1 for p in snap.paths if _rel(p, base) is not None)
            candidates.append((0, count, AppRoot(base, "react", package)))
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


def _sort(routes: list[Route]) -> list[Route]:
    def key(r: Route) -> tuple[int, str]:
        return (0 if r.path == "/" else r.path.count("/"), r.path)

    return sorted(routes, key=key)


def _is_dynamic(path: str) -> bool:
    return "[" in path


def next_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    routes: dict[str, Route] = {}
    if root.framework == "next-app":
        for file, sub in _app_router_files(snap.paths, root.dir):
            segments = [s for s in sub.split("/") if s]
            # 병렬(@slot)·인터셉트((.)...)·private(_x) 세그먼트가 있으면 제외
            if any(s.startswith(("@", "_", "(.")) for s in segments):
                continue
            kept = [s for s in segments if not (s.startswith("(") and s.endswith(")"))]
            path = "/" + "/".join(kept)
            routes.setdefault(path, Route(path, _is_dynamic(path), file))
    elif root.framework == "next-pages":
        for file, sub in _pages_router_files(snap.paths, root.dir):
            if sub.startswith("api/") or sub.split("/")[-1].startswith("_"):
                continue
            parts = sub.split("/")
            if parts[-1] == "index":
                parts = parts[:-1]
            path = "/" + "/".join(parts)
            routes.setdefault(path, Route(path, _is_dynamic(path), file))
    return _sort(list(routes.values()))


_CODE = (".tsx", ".jsx", ".ts", ".js")
_IMPORT = re.compile(r"""import\s+(\w+)\s+from\s+["'](\.{1,2}/[^"']+)["']""")
_ROUTE_TAG = re.compile(r"<Route\b")
_OBJ_PATH = re.compile(r"""\bpath\s*:\s*["']([^"']*)["']""")


def _resolve_import(snap: RepoSnapshot, from_file: str, spec: str) -> str | None:
    parts = from_file.split("/")[:-1]
    for seg in spec.split("/"):
        if seg == "..":
            parts = parts[:-1]
        elif seg != ".":
            parts.append(seg)
    base = "/".join(parts)
    known = set(snap.paths) | set(snap.files)
    if base in known:
        return base
    for cand in [base + ext for ext in _CODE] + [f"{base}/index{ext}" for ext in _CODE]:
        if cand in known:
            return cand
    return None


def _norm_react_path(raw: str) -> str | None:
    raw = raw.strip()
    if raw in ("", "*", "/*"):
        return None
    return raw if raw.startswith("/") else "/" + raw


def react_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    routes: dict[str, Route] = {}
    for file, src in snap.files.items():
        if not file.endswith(_CODE) or _rel(file, root.dir) is None:
            continue
        imports = dict(_IMPORT.findall(src))
        hits: list[tuple[str, str | None]] = []
        for m in _ROUTE_TAG.finditer(src):
            window = src[m.end() : m.end() + 300].split("<Route", 1)[0]
            p = re.search(r"""\bpath\s*=\s*["']([^"']*)["']""", window)
            el = re.search(r"\belement\s*=\s*\{\s*<(\w+)", window)
            if p:
                hits.append((p.group(1), el.group(1) if el else None))
        for m in _OBJ_PATH.finditer(src):
            start = src.rfind("{", 0, m.start())
            end = src.find("}", m.end())
            window = src[start if start >= 0 else m.start() : end if end >= 0 else len(src)]
            el = re.search(r"\belement\s*:\s*<(\w+)", window) or re.search(
                r"\bComponent\s*:\s*(\w+)", window
            )
            hits.append((m.group(1), el.group(1) if el else None))
        for raw, comp in hits:
            path = _norm_react_path(raw)
            if path is None or path in routes:
                continue
            target = None
            if comp and comp in imports:
                target = _resolve_import(snap, file, imports[comp])
            dynamic = ":" in path or "*" in path
            routes[path] = Route(path, dynamic, target or file)
    return _sort(list(routes.values()))
