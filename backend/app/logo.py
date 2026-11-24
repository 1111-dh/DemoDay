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


# 템플릿 기본 제목 — 서비스 이름이 아니다(리뷰 #84)
_DEFAULT_TITLES = re.compile(
    r"^(react app|vite\b.*|create (next|react) app|next\.?js( app)?|nuxt( app)?|svelte ?kit( app)?|"
    r"vue( app)?|document|home|index|welcome|untitled|my app|app|title)$",
    re.I,
)
MAX_CANDIDATES = 4


def _is_image(data: bytes, ext: str) -> bool:
    """내용이 정말 이미지인지(매직바이트). SPA는 없는 /favicon.ico 에도 200 text/html 을 준다."""
    head = data[:512].lstrip()
    if ext == ".svg":
        return b"<svg" in head[:512].lower() or (
            head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()
        )
    return (
        data.startswith(b"\x89PNG")
        or data.startswith(b"\x00\x00\x01\x00")  # ICO
        or data.startswith(b"\xff\xd8")  # JPEG
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )


def _get_capped(c: httpx.Client, url: str) -> httpx.Response | None:
    """MAX_BYTES 까지만 받는다 — 큰 파일은 받는 도중에 끊는다."""
    with c.stream("GET", url) as res:
        if int(res.headers.get("content-length") or 0) > MAX_BYTES:
            return None
        body = b""
        for chunk in res.iter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                return None
        # 이미 풀린 바이트다 — content-encoding(gzip 등)을 넘기면 httpx 가 한 번 더 풀다 실패해
        # 압축해서 주는 사이트(Vercel 등)의 로고를 전부 놓쳤다(11/24 우리 사이트 실측)
        headers = {"content-type": res.headers.get("content-type", "")}
        return httpx.Response(res.status_code, headers=headers, content=body)


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
        value = metas.get(key, "")
        if 0 < len(value) <= MAX_NAME and not _DEFAULT_TITLES.match(value):
            return value
    if m := _TITLE.search(html):
        parts = [x.strip() for x in _SEP.split(m.group(1).strip()) if x.strip()]
        name = min(parts, key=len) if parts else ""
        if 0 < len(name) <= MAX_NAME and not _DEFAULT_TITLES.match(name):
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
        for url in candidates(html, base_url)[:MAX_CANDIDATES]:
            try:
                res = _get_capped(c, url)
            except httpx.HTTPError:
                continue
            if res is None or res.status_code != 200:
                continue
            kind = res.headers.get("content-type", "").split(";")[0].strip().lower()
            ext = _TYPES.get(kind) or Path(url.split("?")[0]).suffix.lower()
            if ext not in _TYPES.values() or not _is_image(res.content, ext):
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
