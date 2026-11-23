"""페이지 소스에서 클릭·입력 가능한 요소의 '리터럴' 문구와 Playwright 셀렉터를 뽑는다.

{t("x")} 같은 표현식 문구는 실제 화면 문구를 알 수 없으므로 버린다(가짜 데모 방지).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal

from app.analyze.jsx import tag_end

Kind = Literal["button", "link", "input"]
MAX_TEXT = 30

# 네이티브 태그 + Vue/Nuxt 링크 + 디자인 시스템 컴포넌트(…Button · …Link · …Input/…Field)
_OPEN = re.compile(
    r"<(button|a|input|textarea|router-link"
    r"|[A-Z]\w*(?:Button|Link|Input|Field|Textarea)|Button|Link|Input)(?=[\s/>])"
)
_TAG = re.compile(r"<[^>]+>")
_REGISTER = re.compile(r"""\bregister\(\s*["']([\w.-]+)["']""")  # react-hook-form → name


def _kind(tag: str) -> Kind:
    if tag in ("input", "textarea") or tag.endswith(("Input", "Field", "Textarea")):
        return "input"
    if tag in ("a", "router-link") or tag.endswith("Link"):
        return "link"
    return "button"


@dataclass
class Element:
    kind: Kind
    text: str
    selector: str


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'(?<![\w:@-]){name}\s*=\s*"([^"]*)"', attrs) or re.search(
        rf"(?<![\w:@-]){name}\s*=\s*'([^']*)'", attrs
    )
    return m.group(1).strip() if m else None


def _clean(inner: str) -> str | None:
    text = " ".join(html.unescape(_TAG.sub(" ", inner)).split())
    if not text or "{" in text or "}" in text or len(text) > MAX_TEXT:
        return None
    return text


def _external(attrs: str) -> bool:
    """다른 사이트로 나가거나 새 탭을 여는 링크 — 데모 화면 밖이라 누르지 않는다."""
    target = _attr(attrs, "href") or _attr(attrs, "to") or ""
    rel = _attr(attrs, "rel") or ""
    return (
        bool(re.match(r"(?:https?:)?//|mailto:|tel:", target))
        or _attr(attrs, "target") == "_blank"
        or bool(re.search(r"\bnoopener\b|\bnoreferrer\b", rel))
    )


def _clickable(kind: Kind, attrs: str, inner: str) -> Element | None:
    if (label := _attr(attrs, "aria-label")) and len(label) <= MAX_TEXT:
        return Element(kind, label, f'[aria-label="{label}"]')
    if text := _clean(inner):
        return Element(kind, text, f"text={text}")
    # 아이콘만 있는 링크(nuxt/movies 왼쪽 메뉴) — title 속성이 화면 이름
    if (title := _attr(attrs, "title")) and len(title) <= MAX_TEXT:
        return Element(kind, title, f'[title="{title}"]')
    return None


# 번역 호출: {{ $t('k') }} · {t("k")} · :attr="$t('k')" · attr={t('k')}
_T_CALL = r"""\$?t\(\s*['"]([^'"\n]{1,120})['"]\s*\)"""
_T_TEXT = re.compile(r"\{\{\s*" + _T_CALL + r"\s*\}\}|\{\s*" + _T_CALL + r"\s*\}")
_T_ATTR = re.compile(
    r"""(?<![\w-]):?([\w-]+)=(?:"\s*""" + _T_CALL + r"""\s*"|\{\s*""" + _T_CALL + r"\s*\})"
)


def _translate(source: str, messages: dict[str, str]) -> str:
    """번역에 있는 키만 실제 문구로 바꾼다. 따옴표·중괄호가 든 문구는 셀렉터가 깨져서 안 바꾼다."""

    def ok(text: str | None) -> bool:
        return bool(text) and not any(c in text for c in '"{}<>')

    def text(m: re.Match) -> str:
        found = messages.get(m.group(1) or m.group(2))
        return found if ok(found) else m.group(0)

    def attr(m: re.Match) -> str:
        found = messages.get(m.group(2) or m.group(3))
        return f'{m.group(1)}="{found}"' if ok(found) else m.group(0)

    return _T_TEXT.sub(text, _T_ATTR.sub(attr, source))


def _input(attrs: str) -> Element | None:
    name = _attr(attrs, "name") or ((m := _REGISTER.search(attrs)) and m.group(1))
    if name and re.fullmatch(r"[\w.-]+", name):
        return Element("input", name, f"input[name={name}]")
    if (ph := _attr(attrs, "placeholder")) and len(ph) <= MAX_TEXT:
        return Element("input", ph, f'input[placeholder="{ph}"]')
    if (label := _attr(attrs, "aria-label")) and len(label) <= MAX_TEXT:
        return Element("input", label, f'[aria-label="{label}"]')
    return None


# 메뉴·탭 설정 배열의 항목: { label: '회의록', to: paths.meetings } → 화면에 보이는 링크
_OBJ = re.compile(r"\{[^{}]*\}")
_NAV_LABEL = re.compile(r"""\b(?:label|title)\s*:\s*(["'])([^"'\n]{1,30})\1""")
_NAV_TARGET = re.compile(r"\b(?:to|href|path)\s*:")


def _nav_items(source: str) -> list[tuple[int, Element]]:
    found = []
    for m in _OBJ.finditer(source):
        body = m.group(0)
        if (label := _NAV_LABEL.search(body)) and _NAV_TARGET.search(body):
            text = label.group(2).strip()
            if text and "{" not in text:
                found.append((m.start(), Element("link", text, f"text={text}")))
    return found


def extract_elements(
    source: str, limit: int = 15, messages: dict[str, str] | None = None
) -> list[Element]:
    if messages:
        source = _translate(source, messages)
    found: list[tuple[int, Element]] = _nav_items(source)
    for m in _OPEN.finditer(source):
        tag = m.group(1)
        end, self_closing = tag_end(source, m.end())
        attrs = source[m.end() : end - (2 if self_closing else 1)]
        kind = _kind(tag)
        if kind == "link" and _external(attrs):
            continue
        if kind == "input":
            el = _input(attrs)
        elif self_closing:
            continue
        else:
            close = source.find(f"</{tag}>", end)
            if close < 0:
                continue
            el = _clickable(kind, attrs, source[end:close])
        if el:
            found.append((m.start(), el))

    out: list[Element] = []
    seen: set[str] = set()
    for _, el in sorted(found, key=lambda f: f[0]):
        if el.selector not in seen:
            seen.add(el.selector)
            out.append(el)
        if len(out) == limit:
            break
    return out
