"""배포 사이트의 로고(아이콘)를 run 디렉터리에 받아 둔다 — 영상 연결·마무리 장면에 넣는다(11/24).

계약 밖 렌더 전용 자료다: render.mjs 가 run 의 logo.* 를 찾아 props.logo 로 넘긴다
(주소창 domain 과 같은 방식).
우선순위: apple-touch-icon(보통 180px) → 큰 icon(svg·png) → /favicon.ico. 못 받으면 로고 없이 간다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx

log = logging.getLogger(__name__)

TIMEOUT = 10
MAX_BYTES = 2_000_000
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_TYPES = {
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _attrs(tag: str) -> dict[str, str]:
    return {m[1].lower(): m[3] or m[4] or m[5] or "" for m in _ATTR.finditer(tag)}


def _size(sizes: str) -> int:
    nums = [int(n) for n in re.findall(r"(\d+)x\d+", sizes or "")]
    return max(nums, default=0)


def candidates(html: str, base_url: str) -> list[str]:
    """HTML의 아이콘 링크를 좋은 순서로. 마지막은 항상 /favicon.ico."""
    scored: list[tuple[int, str]] = []
    for tag in _LINK.findall(html):
        a = _attrs(tag)
        rel = a.get("rel", "").lower()
        href = a.get("href", "")
        if not href or "icon" not in rel or "mask-icon" in rel:
            continue
        score = _size(a.get("sizes", ""))
        if "apple-touch-icon" in rel:
            score += 1000
        if href.lower().endswith(".svg") or "svg" in a.get("type", ""):
            score += 500
        scored.append((score, urljoin(base_url, href)))
    urls = [u for _, u in sorted(scored, key=lambda x: -x[0])]
    urls.append(urljoin(base_url, "/favicon.ico"))
    return list(dict.fromkeys(urls))


_META = re.compile(r"<meta\b[^>]*>", re.I)
_TITLE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
_SEP = re.compile(r"\s+[|·\-–—:]\s+")
MAX_NAME = 20


def site_name(html: str) -> str | None:
    """배포 사이트가 스스로 밝힌 서비스 이름: og:site_name → application-name → <title>.

    title 은 '페이지 · 사이트' 꼴이 많아 구분자로 나눈 조각 중 가장 짧은 것을 쓴다.
    README 첫 제목은 슬로건인 경우가 많다(예: '꼬리에 꼬리를 무는 CS 공부' → 실제 'CS 길라잡이').
    """
    metas = {}
    for tag in _META.findall(html):
        a = _attrs(tag)
        key = (a.get("property") or a.get("name") or "").lower()
        if key and a.get("content"):
            metas.setdefault(key, a["content"].strip())
    for key in ("og:site_name", "application-name", "apple-mobile-web-app-title"):
        if 0 < len(metas.get(key, "")) <= MAX_NAME:
            return metas[key]
    if m := _TITLE.search(html):
        parts = [x.strip() for x in _SEP.split(m.group(1).strip()) if x.strip()]
        name = min(parts, key=len) if parts else ""
        if 0 < len(name) <= MAX_NAME:
            return name
    return None


def fetch_logo(base_url: str, run_dir: Path, client: httpx.Client | None = None) -> Path | None:
    """로고를 run_dir/logo.<확장자> 로, 사이트 이름을 run_dir/site_name.txt 로 저장한다.

    실패해도 예외 없이 None.
    """
    own = client is None
    c = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        try:
            html = c.get(base_url).text
        except httpx.HTTPError:
            html = ""
        if name := site_name(html):
            (run_dir / "site_name.txt").write_text(name)
        for url in candidates(html, base_url):
            try:
                res = c.get(url)
            except httpx.HTTPError:
                continue
            kind = res.headers.get("content-type", "").split(";")[0].strip().lower()
            ext = _TYPES.get(kind) or Path(url.split("?")[0]).suffix.lower()
            if res.status_code != 200 or ext not in _TYPES.values() or not res.content:
                continue
            if len(res.content) > MAX_BYTES:
                continue
            for old in run_dir.glob("logo.*"):
                old.unlink()
            out = run_dir / f"logo{ext}"
            out.write_bytes(res.content)
            return out
    except Exception:  # 로고는 장식 — 무슨 일이 있어도 영상은 만든다
        log.warning("로고 받기 실패 %s", base_url, exc_info=True)
    finally:
        if own:
            c.close()
    return None
