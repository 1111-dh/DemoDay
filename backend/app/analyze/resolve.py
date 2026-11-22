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


_IMPORT_CLAUSE = re.compile(r"""\bimport\s+([^;'"`]*?)\s+from\s+["']([^"']+)["']""")
_BARE = re.compile(r"""(?:\bimport\s*\(\s*|^\s*import\s+)["']([^"']+)["']""", re.MULTILINE)
_EXPORT_FROM = re.compile(
    r"""\bexport\s+(type\s+)?(\*(?:\s+as\s+\w+)?|\{[^}]*\})\s+from\s+["']([^"']+)["']"""
)


def _names(group: str) -> dict[str, str]:
    """`A, B as C, type D` → {바깥 이름: 원래 이름} (type 제외)."""
    out: dict[str, str] = {}
    for item in group.strip("{} \n").split(","):
        item = item.strip()
        if not item or item.startswith("type "):
            continue
        orig, _, alias = item.partition(" as ")
        out[(alias or orig).strip()] = orig.strip()
    return out


def reexports(src: str) -> list[tuple[str, dict[str, str] | None]]:
    """`export {A as B} from 'x'` → ('x', {B: A}), `export * from 'x'` → ('x', None)."""
    out = []
    for is_type, what, spec in _EXPORT_FROM.findall(src):
        if not is_type and is_local(spec):
            out.append((spec, None if what.startswith("*") else _names(what)))
    return out


def imports_by_spec(src: str) -> list[tuple[str, set[str] | None]]:
    """로컬 모듈별로 가져오는 원래 이름들. None = 이름을 알 수 없음(default·namespace·동적)."""
    hits: list[tuple[int, str, set[str] | None]] = []
    for m in _IMPORT_CLAUSE.finditer(src):
        clause, spec = m.group(1).strip(), m.group(2)
        if clause.startswith("type ") or not is_local(spec):
            continue
        head = clause.split("{", 1)[0].strip().rstrip(",").strip()
        named = re.search(r"\{([^}]*)\}", clause)
        names = set(_names(named.group(1)).values()) if named and not head else None
        hits.append((m.start(), spec, names))
    for m in _BARE.finditer(src):
        if is_local(m.group(1)):
            hits.append((m.start(), m.group(1), None))
    for m in _EXPORT_FROM.finditer(src):
        if not m.group(1) and is_local(m.group(3)):
            what = m.group(2)
            hits.append(
                (
                    m.start(),
                    m.group(3),
                    None if what.startswith("*") else set(_names(what).values()),
                )
            )
    merged: dict[str, set[str] | None] = {}
    for _, spec, names in sorted(hits, key=lambda h: h[0]):
        if spec in merged:
            prev = merged[spec]
            merged[spec] = None if prev is None or names is None else prev | names
        else:
            merged[spec] = names
    return list(merged.items())
