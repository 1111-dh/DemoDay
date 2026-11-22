"""Flutter web 라우트: go_router(`GoRoute(path: …, routes: [...])`) · `MaterialApp.routes` 맵.

Flutter web 은 canvas 로 그려 DOM 셀렉터가 없으므로 페이지 이동(goto)만 만든다.
URL 전략: `usePathUrlStrategy()`/`PathUrlStrategy` 가 없으면 기본 해시 URL(`/#/x`).
"""

from __future__ import annotations

import re

from app.analyze.code_routes import join_paths
from app.analyze.routes import AppRoot, Route, sort_routes
from app.github import RepoSnapshot

_CONST = re.compile(r"""\bconst\s+(?:String\s+)?(\w+)\s*=\s*['"]([^'"$]*)['"]""")
_PATH_ARG = re.compile(r"""path\s*:\s*(?:(['"])([^'"$]*)\1|([\w.]+))""")
_MAP_ROUTE = re.compile(r"""['"](/[^'"$]*)['"]\s*:\s*\(""")
_CASE_ROUTE = re.compile(r"""\bcase\s+['"](/[^'"$]*)['"]\s*:""")
_PATH_STRATEGY = re.compile(r"usePathUrlStrategy|PathUrlStrategy")


def _skip_string(src: str, i: int) -> int:
    quote, j = src[i], i + 1
    while j < len(src) and src[j] != quote:
        j += 2 if src[j] == "\\" else 1
    return j + 1


def go_routes(src: str, consts: dict[str, str]) -> list[str]:
    """`GoRoute(path: …)` 를 괄호 중첩으로 부모 path 와 잇는다. 상수 참조는 값으로 바꾼다."""
    stack: list[str | None] = []
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            i = _skip_string(src, i)
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        if c == "p" and stack and stack[-1] is None and not src[i - 1].isalnum():
            if m := _PATH_ARG.match(src, i):
                value = m.group(2) if m.group(1) else consts.get(m.group(3).rsplit(".", 1)[-1])
                stack[-1] = value
                i = m.end()
                continue
        if c == "(":
            stack.append(None)
        elif c == ")" and stack:
            path = stack.pop()
            if path is not None:
                out.append(join_paths([*stack, path]))
        i += 1
    return out


def flutter_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    prefix = f"{root.dir}/" if root.dir else ""
    main = f"{prefix}lib/main.dart"
    snap.read(main)  # URL 전략은 대개 main.dart 에 있다
    dart = {f: s for f, s in snap.files.items() if f.startswith(prefix) and f.endswith(".dart")}
    consts = {name: value for src in dart.values() for name, value in _CONST.findall(src)}
    hash_urls = not any(_PATH_STRATEGY.search(src) for src in dart.values())

    routes: dict[str, Route] = {}
    for file, src in dart.items():
        paths = go_routes(src, consts) if "GoRoute" in src else []
        paths += _MAP_ROUTE.findall(src) + _CASE_ROUTE.findall(src)
        for path in paths:
            url = "/#" + path if hash_urls and path != "/" else path
            routes.setdefault(url, Route(url, ":" in path, file, resolved=False))
    return sort_routes(list(routes.values()))
