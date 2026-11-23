"""캡처 스크린샷에 실제로 보이는 내용을 이미지 모델로 읽는다 — scene 자막이 추측 대신 화면 근거로.

Groq 는 이미지 한 장을 크기와 상관없이 약 2,000 토큰으로 잡고(분당 입력 7,000),
요청당 3장까지 받는다.
한 장씩 보내면 화면 5개에 85초가 걸려서, 번호를 단 스크린샷 4장을 2x2 한 이미지로 묶어
한 요청에 최대 3장(12화면)을 보낸다 — 시나리오 MAX_STEPS(7)면 요청 1번.

실패(한도·네트워크·모델 없음)는 None — 호출부는 그 화면을 설명 없이 둔다(지금까지와 같은 자막).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.llm import (
    BAZE_BASE_URL,
    BAZE_CHAT_PATH,
    BAZE_MODEL,
    GROQ_BASE_URL,
    is_down,
    post_with_rate_retry,
)

GROQ_VISION_MODEL = "qwen/qwen3.8-27b"  # Groq 무료 플랜에서 이미지 입력이 되는 모델(11/23 확인)
MAX_SEEN = 80
MAX_TOKENS = 16384  # 화면 11개(콜라주 3장)면 생각 토큰이 4096을 넘어 빈 답(11/24 운영 실측)
# 캡처 원본 크기 그대로 2x2(2560x1440) — Groq 토큰 추정은 이미지 크기와 무관(11/23 실측)
TILE = (1280, 720)
PER_IMAGE = 4
IMAGES_PER_REQUEST = 3  # Groq qwen 한도 "This model supports up to 3 images"
PER_REQUEST = PER_IMAGE * IMAGES_PER_REQUEST
PROMPT = (Path(__file__).parent / "prompts" / "vision.md").read_text()
log = logging.getLogger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_LINE = re.compile(r"^\W*(\d{1,2})\W*[:.)]\s*(.+)$")


class Describer(Protocol):
    def describe_many(self, images: list[bytes]) -> list[str | None]: ...


def _tile(data: bytes) -> Image.Image | None:
    try:
        return Image.open(io.BytesIO(data)).convert("RGB").resize(TILE, Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def collages(images: list[bytes], start: int = 1) -> list[bytes]:
    """PER_IMAGE 장씩 2x2 로 붙이고 칸마다 번호(start 부터)를 단다. 못 읽은 이미지 칸은 회색."""
    out = []
    for first in range(0, len(images), PER_IMAGE):
        sheet = Image.new("RGB", (TILE[0] * 2, TILE[1] * 2), (128, 128, 128))
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default(size=40)
        for k, data in enumerate(images[first : first + PER_IMAGE]):
            x, y = (k % 2) * TILE[0], (k // 2) * TILE[1]
            if tile := _tile(data):
                sheet.paste(tile, (x, y))
            draw.rectangle((x, y, x + 64, y + 56), fill=(0, 0, 0))
            draw.text((x + 14, y + 6), str(start + first + k), fill=(255, 255, 0), font=font)
        buf = io.BytesIO()
        sheet.save(buf, "PNG")
        out.append(buf.getvalue())
    return out


def _clean(text: str) -> str | None:
    text = " ".join(text.replace("*", "").split())
    return text[:MAX_SEEN] or None


def parse_numbered(content: str, n: int, start: int = 1) -> list[str | None]:
    """'1: 설명' 줄들 → 번호 순서 목록. 빠진 번호는 None."""
    found: dict[int, str | None] = {}
    for line in _THINK.sub("", content).splitlines():
        if m := _LINE.match(line.strip().replace("*", "")):
            found.setdefault(int(m.group(1)), _clean(m.group(2)))
    return [found.get(start + i) for i in range(n)]


class GroqVision:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        chat_path: str = "/chat/completions",
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.url = base_url.rstrip("/") + chat_path
        self.down = False  # 크레딧·인증·서버 오류 — FallbackDescriber 가 예비로 넘긴다
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self.client = client or httpx.Client(timeout=60)
        self.sleep = sleep

    def describe_many(self, images: list[bytes]) -> list[str | None]:
        out: list[str | None] = []
        for first in range(0, len(images), PER_REQUEST):
            chunk = images[first : first + PER_REQUEST]
            out += self._request(chunk, start=1) if chunk else []
        return out

    def _request(self, images: list[bytes], start: int) -> list[str | None]:
        n = len(images)
        text = PROMPT.format(n=n, last=start + n - 1)
        parts: list[dict] = [{"type": "text", "text": text}]
        for sheet in collages(images, start):
            url = "data:image/png;base64," + base64.b64encode(sheet).decode()
            parts.append({"type": "image_url", "image_url": {"url": url}})
        body = {
            "model": self.model,
            # 생각하는 모델(Haiku 5.5)은 답 전에 생각 토큰을 쓴다 — 작게 잡으면 빈 답(11/23).
            # 크레딧은 실제로 쓴 만큼만 나가니 넉넉히
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": parts}],
        }
        errors: list[int] = []
        res = post_with_rate_retry(
            self.client, self.url, self.headers, body, self.sleep, errors=errors
        )
        if res is None:
            self.down = any(is_down(e) for e in errors)
            return [None] * n
        try:
            choice = res.json()["choices"][0]
            content = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError):
            return [None] * n
        if not content.strip():
            log.warning("스크린샷 읽기 빈 답 (finish_reason=%s)", choice.get("finish_reason"))
        return parse_numbered(content, n, start)


class FallbackDescriber:
    """주 이미지 모델(BAZE)이 크레딧·인증·서버 오류로 내려가면 예비(Groq)로 읽는다."""

    def __init__(self, primary: GroqVision, backup: Describer):
        self.primary = primary
        self.backup = backup

    def describe_many(self, images: list[bytes]) -> list[str | None]:
        if not self.primary.down:
            out = self.primary.describe_many(images)
            if any(out) or not self.primary.down:
                return out
        return self.backup.describe_many(images)


def _groq_vision() -> GroqVision | None:
    key = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("GROQ_VISION_MODEL", GROQ_VISION_MODEL).strip()
    return GroqVision(base_url=GROQ_BASE_URL, api_key=key, model=model) if key and model else None


def get_describer() -> Describer | None:
    """LLM 공급자를 따른다: BAZE(기본 Haiku 5.5, BAZE_VISION_MODEL) → 예비 Groq qwen.

    Groq 만 쓸 때는 GROQ_VISION_MODEL(빈 값이면 끔). anthropic 등 다른 공급자는 None.
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    baze_key = os.environ.get("BAZE_API_KEY")
    if provider == "baze" or (not provider and baze_key):
        model = os.environ.get("BAZE_VISION_MODEL", BAZE_MODEL).strip()
        if not baze_key or not model:
            return _groq_vision()
        baze = GroqVision(
            base_url=BAZE_BASE_URL, api_key=baze_key, model=model, chat_path=BAZE_CHAT_PATH
        )
        backup = _groq_vision()
        return FallbackDescriber(baze, backup) if backup else baze
    if provider not in ("", "groq"):
        return None
    return _groq_vision()
