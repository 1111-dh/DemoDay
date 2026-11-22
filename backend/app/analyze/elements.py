"""페이지 소스에서 클릭·입력 가능한 요소의 '리터럴' 문구와 Playwright 셀렉터를 뽑는다.

{t("x")} 같은 표현식 문구는 실제 화면 문구를 알 수 없으므로 버린다(가짜 데모 방지).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["button", "link", "input"]
MAX_TEXT = 30

_BUTTON = re.compile(r"<button\b([^>]*)>(.*?)</button>", re.S)
_LINK = re.compile(r"<(Link|a)\b([^>]*)>(.*?)</\1>", re.S)
_INPUT = re.compile(r"<input\b([^>]*?)/?>", re.S)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class Element:
    kind: Kind
    text: str
    selector: str


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'\b{name}\s*=\s*"([^"]*)"', attrs) or re.search(
        rf"\b{name}\s*=\s*'([^']*)'", attrs
    )
    return m.group(1).strip() if m else None


def _clean(inner: str) -> str | None:
    text = " ".join(_TAG.sub(" ", inner).split())
    if not text or "{" in text or "}" in text or len(text) > MAX_TEXT:
        return None
    return text


def _clickable(kind: Kind, attrs: str, inner: str) -> Element | None:
    if (label := _attr(attrs, "aria-label")) and len(label) <= MAX_TEXT:
        return Element(kind, label, f'[aria-label="{label}"]')
    if text := _clean(inner):
        return Element(kind, text, f"text={text}")
    return None


def _input(attrs: str) -> Element | None:
    if (name := _attr(attrs, "name")) and re.fullmatch(r"[\w.-]+", name):
        return Element("input", name, f"input[name={name}]")
    if (ph := _attr(attrs, "placeholder")) and len(ph) <= MAX_TEXT:
        return Element("input", ph, f'input[placeholder="{ph}"]')
    if (label := _attr(attrs, "aria-label")) and len(label) <= MAX_TEXT:
        return Element("input", label, f'[aria-label="{label}"]')
    return None


def extract_elements(source: str, limit: int = 15) -> list[Element]:
    found: list[tuple[int, Element]] = []
    for m in _BUTTON.finditer(source):
        if el := _clickable("button", m.group(1), m.group(2)):
            found.append((m.start(), el))
    for m in _LINK.finditer(source):
        if el := _clickable("link", m.group(2), m.group(3)):
            found.append((m.start(), el))
    for m in _INPUT.finditer(source):
        if el := _input(m.group(1)):
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
