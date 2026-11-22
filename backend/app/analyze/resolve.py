"""import 경로 해석 — '이 이름/경로는 레포의 어느 파일인가'.

지원: 상대경로(`./`, `../`), 별칭 `@/`·`~/`·`~~/`(가장 가까운 src/, 없으면 앱 루트),
`$lib/`(src/lib).
"""

from __future__ import annotations

import re

from app.github import CODE_EXT

_LOCAL = ("./", "../", "@/", "~/", "~~/", "$lib/")
_DEFAULT = re.compile(r"""import\s+(\w+)\s*(?:,\s*\{[^}]*\})?\s+from\s+["']([^"']+)["']""")
_NAMED = re.compile(r"""import\s+(?:\w+\s*,\s*)?\{([^}]*)\}\s+from\s+["']([^"']+)["']""")
# const X = lazy(() => import('…')) · lazyPage(…) · defineAsyncComponent(…) 등 감싼 동적 import
_LAZY = re.compile(
    r"""(\w+)\s*=\s*[\w.]*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*import\(\s*["']([^"']+)["']"""
)
_SPECS = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|^\s*import\s+)["']([^"']+)["']""", re.MULTILINE
)


def is_local(spec: str) -> bool:
    return spec.startswith(_LOCAL)


def resolve(spec: str, from_file: str, known: set[str], root_dir: str = "") -> str | None:
    if not is_local(spec):
        return None
    if spec.startswith(("./", "../")):
        parts = from_file.split("/")[:-1]
        rest = spec.split("/")
    else:
        prefix, rest_str = spec.split("/", 1)
        parts = from_file.split("/")[:-1]
        while parts and parts[-1] != "src":
            parts.pop()
        if not parts:
            parts = root_dir.split("/") if root_dir else []
        if prefix == "$lib":
            parts = [*parts, "lib"]
        rest = rest_str.split("/")
    for seg in rest:
        if seg == "..":
            parts = parts[:-1]
        elif seg not in (".", ""):
            parts.append(seg)
    base = "/".join(parts)
    for cand in (base, *(base + e for e in CODE_EXT), *(f"{base}/index{e}" for e in CODE_EXT)):
        if cand in known and cand.endswith(CODE_EXT):
            return cand
    return None


def import_map(src: str) -> dict[str, str]:
    """이름 → import 경로 (default · named · 감싼 동적 import)."""
    names: dict[str, str] = {}
    for name, spec in _DEFAULT.findall(src):
        names.setdefault(name, spec)
    for group, spec in _NAMED.findall(src):
        for item in group.split(","):
            alias = item.split(" as ")[-1].strip()
            if re.fullmatch(r"\w+", alias):
                names.setdefault(alias, spec)
    for name, spec in _LAZY.findall(src):
        names.setdefault(name, spec)
    return names


def local_specs(src: str) -> list[str]:
    """파일이 가져오거나 다시 내보내는 로컬 모듈 경로 (등장 순서, 중복 제거)."""
    out: list[str] = []
    for spec in _SPECS.findall(src):
        if is_local(spec) and spec not in out:
            out.append(spec)
    return out
