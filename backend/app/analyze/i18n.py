"""레포의 번역 파일(locales/en.json 등)에서 기본 언어 문구를 읽는다.

`$t('Type to search...')`·`t("nav.home")` 처럼 문구가 번역 함수 안에만 있는 앱(nuxt/movies)은
지금까지 요소를 하나도 못 뽑았다. 번역에 있는 키만 실제 문구로 바꾼다 — 없는 키는 여전히 버린다.
"""

from __future__ import annotations

import json
import re

from app.github import LOCALE_FILE, RepoSnapshot

# nuxt.config / i18n.config / next-i18next.config 등의 defaultLocale: 'en'
_DEFAULT = re.compile(r"""\bdefault(?:Locale|Language|Lng)\s*:\s*['"]([\w-]+)['"]""")
_CONFIG = re.compile(
    r"(?:^|/)(?:nuxt|i18n|next-i18next|next|vite)\.config\.[cm]?[jt]s$|i18n\.[jt]s$"
)


def _default_locale(snap: RepoSnapshot) -> str | None:
    for path in snap.paths:
        if _CONFIG.search(path) and (m := _DEFAULT.search(snap.read(path) or "")):
            return m.group(1).lower()
    return None


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()


def _pick(files: list[str], default: str | None) -> str | None:
    """기본 언어(설정) → en → ko → 첫 파일. 캡처 브라우저는 en-US 라 설정이 없으면 en 을 먼저."""
    for want in (default, "en", "ko"):
        if want:
            for f in files:
                stem = _stem(f)
                if stem == want or stem.startswith(want + "-") or stem.startswith(want + "_"):
                    return f
    return files[0] if files else None


def _flatten(node: object, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(node, str):
        out[prefix[:-1]] = node
    return out


def load_messages(snap: RepoSnapshot) -> dict[str, str]:
    """기본 언어 번역 파일 하나를 {키: 문구}로(중첩 키는 'a.b'). 없거나 못 읽으면 {}."""
    files = sorted(p for p in snap.paths if LOCALE_FILE.search(p) and "node_modules/" not in p)
    chosen = _pick(files, _default_locale(snap) if files else None)
    if chosen is None:
        return {}
    try:
        return _flatten(json.loads(snap.read(chosen) or "{}"))
    except ValueError:
        return {}
