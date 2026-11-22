"""코드에 라우트를 적는 프레임워크: React Router(JSX·객체) · Vue Router (· Flutter는 flutter.py).

중첩(`<Route>` 안 `<Route>`, 객체의 `children`)은 부모 path와 이어 붙인다.
라우트가 가리키는 컴포넌트 파일을 import 맵으로 찾고,
못 찾으면 라우터 파일 자체를 쓴다(resolved=False).
"""

from __future__ import annotations

import re

from app.analyze.jsx import tag_end
from app.analyze.resolve import import_map, resolve
from app.analyze.routes import AppRoot, Route, sort_routes
from app.github import CODE_EXT, RepoSnapshot

_JS = (".tsx", ".jsx", ".ts", ".js", ".mjs")
_ROUTE_TAG = re.compile(r"<Route\b")
_ROUTE_CLOSE = re.compile(r"</Route\s*>")
_ROUTER_HINT = re.compile(
    r"create\w*Router|RouteObject|RouteRecordRaw|useRoutes|VueRouter|\broutes\s*[:=]\s*\["
)
_PATH_KEY = re.compile(r"""path\s*:\s*(["'`])([^"'`]*)\1""")
_DYN_IMPORT = re.compile(r"""import\(\s*["']([^"']+)["']""")
_OBJ_COMP = re.compile(r"(?:\belement\s*:\s*<\s*(\w+))|(?:\b[Cc]omponent\s*:\s*(\w+))")
_JSX_COMP = (
    re.compile(r"\belement\s*=\s*\{\s*<\s*(\w+)"),
    re.compile(r"\bComponent\s*=\s*\{\s*(\w+)"),
    re.compile(r"\belement\s*=\s*\{\s*(?:[\w.]+\(\s*)?(\w+)"),  # element={screen(page)}
)


def join_paths(segments: list[str | None]) -> str:
    parts: list[str] = []
    for seg in segments:
        if seg is None:
            continue
        if seg.startswith("/"):
            parts = []
        parts += [x for x in seg.split("/") if x]
    return "/" + "/".join(parts)


def _skip_string(src: str, i: int) -> int:
    quote, j = src[i], i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == quote:
            return j + 1
        j += 1
    return j


def object_routes(src: str) -> list[tuple[str, str, bool]]:
    """`{ path: 'x', …, children: [{ … }] }` 중첩 → (전체 경로, 객체 자기 부분 텍스트, index).

    문자열·주석 안의 중괄호는 무시한다. 자기 부분 = `children` 앞까지.
    """
    stack: list[list] = []  # [시작 위치, path | None]
    out: list[tuple[str, str, bool]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            i = _skip_string(src, i)
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if c == "p" and stack and stack[-1][1] is None and (i == 0 or not src[i - 1].isalnum()):
            if m := _PATH_KEY.match(src, i):
                stack[-1][1] = m.group(2).strip()
                i = m.end()
                continue
        if c == "{":
            stack.append([i, None])
        elif c == "}" and stack:
            start, path = stack.pop()
            own = src[start : i + 1].split("children", 1)[0]
            is_index = bool(re.search(r"\bindex\s*:\s*true", own))
            if path is not None or is_index:
                parents = [p for _, p in stack]
                full = join_paths([*parents, path]) if path is not None else join_paths(parents)
                out.append((full, own, is_index))
        i += 1
    return out


def jsx_routes(src: str) -> list[tuple[str, str]]:
    """중첩 <Route> → (전체 경로, 태그 텍스트).

    path 없는 레이아웃 Route는 경로에 끼지 않고, index Route는 부모 경로가 된다.
    """
    events = [(m.start(), m.end()) for m in _ROUTE_TAG.finditer(src)]
    events += [(m.start(), -1) for m in _ROUTE_CLOSE.finditer(src)]
    stack: list[str | None] = []
    hits: list[tuple[str, str]] = []
    for _, after in sorted(events):
        if after < 0:
            if stack:
                stack.pop()
            continue
        end, self_closing = tag_end(src, after)
        tag = src[after:end]
        p = re.search(r"""\bpath\s*=\s*["']([^"']*)["']""", tag)
        raw = p.group(1).strip() if p else None
        if raw is not None:
            hits.append((join_paths([*stack, raw]), tag))
        elif re.search(r"\bindex\b", tag):
            hits.append((join_paths(stack), tag))
        if not self_closing:
            stack.append(raw)
    return hits


def _target(
    text: str, patterns, imports: dict[str, str], file: str, known: set[str], root: AppRoot
) -> str | None:
    if m := _DYN_IMPORT.search(text):
        return resolve(m.group(1), file, known, root.dir)
    for pat in patterns:
        if (m := pat.search(text)) and (name := next(g for g in m.groups() if g)) in imports:
            return resolve(imports[name], file, known, root.dir)
    return None


def code_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    known = set(snap.paths) | set(snap.files)
    routes: dict[str, Route] = {}
    for file, src in snap.files.items():
        if not file.endswith(_JS) or (root.dir and not file.startswith(root.dir + "/")):
            continue
        imports = import_map(src)
        found: list[tuple[str, str | None]] = []
        for path, tag in jsx_routes(src):
            found.append((path, _target(tag, _JSX_COMP, imports, file, known, root)))
        if _ROUTER_HINT.search(src):
            for path, own, _ in object_routes(src):
                target = _target(own, (_OBJ_COMP,), imports, file, known, root)
                if target is None and re.search(r"\bredirect\s*:", own):
                    continue  # { path: '/old', redirect: '/' } 는 화면이 아니다
                found.append((path, target))
        for path, target in found:
            if path == "/*" or path in routes:
                continue
            dynamic = ":" in path or "*" in path
            routes[path] = Route(path, dynamic, target or file, resolved=target is not None)
    return sort_routes(list(routes.values()))


react_routes = code_routes
vue_routes = code_routes

__all__ = ["CODE_EXT", "code_routes", "jsx_routes", "object_routes", "react_routes", "vue_routes"]
