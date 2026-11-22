"""Flutter web 라우트와 요소: go_router(`GoRoute(path: …, routes: [...])`) · `MaterialApp.routes`.

Flutter web 은 canvas 로 그리지만 semantics 모드를 켜면(캡처가 `flt-semantics-placeholder` 클릭)
버튼·입력이 role 과 이름을 가진 DOM 노드가 된다 → `role=button[name="다음"]` 로 클릭한다.
URL 전략: `usePathUrlStrategy()`/`PathUrlStrategy` 가 없으면 기본 해시 URL(`/#/x`).
"""

from __future__ import annotations

import re

from app.analyze.code_routes import join_paths
from app.analyze.elements import MAX_TEXT, Element
from app.analyze.routes import AppRoot, Route, sort_routes
from app.github import RepoSnapshot

FOLLOW_FILES = 8
MAX_ELEMENTS = 15

_CONST = re.compile(r"""\bconst\s+(?:String\s+)?(\w+)\s*=\s*['"]([^'"$]*)['"]""")
_PATH_ARG = re.compile(r"""path\s*:\s*(?:(['"])([^'"$]*)\1|([\w.]+))""")
_CASE_ROUTE = re.compile(r"""\bcase\s+['"](/[^'"$]*)['"]\s*:""")
_PATH_STRATEGY = re.compile(r"usePathUrlStrategy|PathUrlStrategy")
_WIDGET = re.compile(r"(?:=>|\breturn\b|\bchild\s*:)\s*(?:const\s+|new\s+)?([A-Z]\w*)\s*\(")
_MAP_ENTRY = re.compile(r"""['"](/[^'"$]*)['"]\s*:\s*\([^)]*\)\s*=>\s*(?:const\s+)?([A-Z]\w*)""")
_IMPORT = re.compile(r"""^\s*import\s+['"]([^'"]+\.dart)['"]""", re.MULTILINE)
_BUTTON = re.compile(r"\b(_?[A-Z]\w*Button)(?:\.\w+)?\s*\(")  # _Private 위젯 포함
_FIELD = re.compile(r"\b(TextField|TextFormField|CupertinoTextField)\s*\(")
_LIT = r"""(['"])([^'"$\\]+)\1"""
_BUTTON_NAME = (
    re.compile(r"\b(?:child|label|title)\s*:\s*(?:const\s+)?Text\(\s*" + _LIT),
    re.compile(r"\b(?:label|text|title|tooltip)\s*:\s*" + _LIT),
)
_FIELD_NAME = (
    re.compile(r"\blabelText\s*:\s*" + _LIT),
    re.compile(r"\bhintText\s*:\s*" + _LIT),
    re.compile(r"\bplaceholder\s*:\s*" + _LIT),
)
# UI 가 아닌 폴더는 따라가지 않는다
_NOT_UI = re.compile(
    r"/(?:models?|providers?|services?|repositor(?:y|ies)|data|api|utils?|config|constants"
    r"|theme|l10n|state|blocs?|controllers?)/"
)


def _skip_string(src: str, i: int) -> int:
    quote, j = src[i], i + 1
    while j < len(src) and src[j] != quote:
        j += 2 if src[j] == "\\" else 1
    return j + 1


def go_routes(src: str, consts: dict[str, str]) -> list[tuple[str, str]]:
    """`GoRoute(path: …)` 를 괄호 중첩으로 부모 path 와 잇는다 → (전체 경로, 자기 인자 텍스트).

    상수 참조(`AppRoutes.login`)는 값으로 바꾼다. 자기 인자 = 하위 `routes:` 앞까지.
    """
    stack: list[list] = []  # [시작 위치, path | None]
    out: list[tuple[str, str]] = []
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
        if c == "p" and stack and stack[-1][1] is None and not src[i - 1].isalnum():
            if m := _PATH_ARG.match(src, i):
                value = m.group(2) if m.group(1) else consts.get(m.group(3).rsplit(".", 1)[-1])
                stack[-1][1] = value
                i = m.end()
                continue
        if c == "(":
            stack.append([i, None])
        elif c == ")" and stack:
            start, path = stack.pop()
            if path is not None:
                own = re.split(r"\broutes\s*:", src[start:i], maxsplit=1)[0]
                out.append((join_paths([p for _, p in stack] + [path]), own))
        i += 1
    return out


def _args(src: str, open_paren: int) -> str:
    """`(` 위치부터 짝이 맞는 `)` 까지의 인자 텍스트 (문자열 안 괄호 무시)."""
    depth, i = 0, open_paren
    while i < len(src):
        c = src[i]
        if c in "'\"":
            i = _skip_string(src, i)
            continue
        depth += {"(": 1, ")": -1}.get(c, 0)
        if depth == 0:
            return src[open_paren + 1 : i]
        i += 1
    return src[open_paren + 1 :]


def _name(args: str, patterns) -> str | None:
    for pat in patterns:
        if (m := pat.search(args)) and len(text := m.group(2).strip()) <= MAX_TEXT:
            # '0' 같은 숫자·기호뿐인 이름은 셀렉터·자막으로 쓸모가 없다
            return text if re.search(r"[^\W\d_]", text) else None
    return None


def dart_elements(src: str) -> list[Element]:
    """리터럴 문구가 있는 버튼(…Button)·입력(TextField) → role 셀렉터. 등장 순서, 중복 제거."""
    found: list[tuple[int, Element]] = []
    for m in _BUTTON.finditer(src):
        if name := _name(_args(src, m.end() - 1), _BUTTON_NAME):
            found.append((m.start(), Element("button", name, f'role=button[name="{name}"]')))
    for m in _FIELD.finditer(src):
        if name := _name(_args(src, m.end() - 1), _FIELD_NAME):
            found.append((m.start(), Element("input", name, f'role=textbox[name="{name}"]')))
    out: list[Element] = []
    for _, el in sorted(found, key=lambda f: f[0]):
        if el.selector not in {e.selector for e in out}:
            out.append(el)
    return out[:MAX_ELEMENTS]


def _imports(src: str, file: str, root: AppRoot) -> list[str]:
    """`package:<앱이름>/x.dart` → <root>/lib/x.dart, 상대 경로는 file 기준. 외부 패키지는 제외."""
    prefix = f"{root.dir}/" if root.dir else ""
    app = root.package.get("name", "")
    out = []
    for spec in _IMPORT.findall(src):
        if spec.startswith("package:"):
            pkg, _, rest = spec[len("package:") :].partition("/")
            if pkg != app:
                continue
            out.append(f"{prefix}lib/{rest}")
        elif not spec.startswith("dart:"):
            parts = file.split("/")[:-1]
            for seg in spec.split("/"):
                if seg == "..":
                    parts = parts[:-1]
                elif seg != ".":
                    parts.append(seg)
            out.append("/".join(parts))
    return out


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _screen_file(
    snap: RepoSnapshot, router_file: str, own: str, root: AppRoot, known: set[str]
) -> str | None:
    """빌더가 만드는 위젯 클래스가 정의된 파일 (라우터의 import → 파일 이름 추정 순)."""
    imported = [
        p for p in _imports(snap.files.get(router_file, ""), router_file, root) if p in known
    ]
    for name in _WIDGET.findall(own):
        guess = [p for p in known if p.endswith(f"/{_snake(name)}.dart")]
        for path in [*imported, *guess]:
            if re.search(rf"\bclass\s+{name}\b", snap.read(path) or ""):
                return path
    return None


def flutter_routes(snap: RepoSnapshot, root: AppRoot) -> list[Route]:
    prefix = f"{root.dir}/" if root.dir else ""
    snap.read(f"{prefix}lib/main.dart")  # URL 전략은 대개 main.dart 에 있다
    dart = {f: s for f, s in snap.files.items() if f.startswith(prefix) and f.endswith(".dart")}
    consts = {name: value for src in dart.values() for name, value in _CONST.findall(src)}
    hash_urls = not any(_PATH_STRATEGY.search(src) for src in dart.values())
    known = set(snap.paths) | set(snap.files)

    routes: dict[str, Route] = {}
    for file, src in dart.items():
        found = go_routes(src, consts) if "GoRoute" in src else []
        found += [(path, f"=> {widget}(") for path, widget in _MAP_ENTRY.findall(src)]
        found += [(path, "") for path in _CASE_ROUTE.findall(src)]
        for path, own in found:
            url = "/#" + path if hash_urls and path != "/" else path
            if url in routes:
                continue
            screen = _screen_file(snap, file, own, root, known) if own else None
            routes[url] = Route(url, ":" in path, screen or file, resolved=screen is not None)
    return sort_routes(list(routes.values()))


def flutter_page_elements(
    snap: RepoSnapshot, route: Route, root: AppRoot, others: frozenset[str] = frozenset()
) -> list[Element]:
    """화면 파일 + 그 파일이 import 하는 앱 내부 위젯 파일의 요소.

    UI 아닌 폴더와 다른 라우트의 화면 파일(others)은 따라가지 않는다.
    """
    if not route.resolved:
        return []
    known = set(snap.paths) | set(snap.files)
    queue, seen, out = [route.file], {route.file}, []
    while queue and len(out) < MAX_ELEMENTS:
        file = queue.pop(0)
        src = snap.read(file) or ""
        for el in dart_elements(src):
            if el.selector not in {e.selector for e in out}:
                out.append(el)
        for target in _imports(src, file, root):
            if target in known and target not in seen | others and not _NOT_UI.search(target):
                if len(seen) >= FOLLOW_FILES:
                    break
                seen.add(target)
                queue.append(target)
    return out[:MAX_ELEMENTS]
