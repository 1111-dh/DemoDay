import io
import json

import httpx
import pytest
from PIL import Image

from app.vision import MAX_SEEN, PER_REQUEST, GroqVision, collages, get_describer


def png(color: str, size=(1280, 720)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _vision(handler, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    sleep = sleeps.append if sleeps is not None else lambda s: None
    return GroqVision(
        base_url="https://api.test/v1", api_key="k", model="vm", client=client, sleep=sleep
    )


def _reply(content: str):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_collages_tile_four_screens_per_image():
    """Groq 는 이미지 한 장마다 토큰을 크게 잡는다 — 4장씩 한 이미지로 묶는다."""
    images = [png(c) for c in ("red", "green", "blue", "white", "black")]
    out = collages(images)
    assert len(out) == 2
    first = Image.open(io.BytesIO(out[0]))
    assert first.size == (2560, 1440)
    assert first.getpixel((640, 400))[0] > 200  # 1번 칸(왼쪽 위)은 빨강
    assert first.getpixel((1920, 1100))[:3] == (255, 255, 255)  # 4번 칸(오른쪽 아래)은 흰색


def test_describe_many_one_request_numbered_lines():
    seen = {}

    def handler(req):
        seen.setdefault("bodies", []).append(json.loads(req.content))
        return _reply(
            "1: '비어 있는 공간에' 제목과 분석 시작 버튼\n2: 후기 카드\n4: 로딩 중인 빈 화면"
        )

    out = _vision(handler).describe_many([png("red")] * 5)
    assert out == [
        "'비어 있는 공간에' 제목과 분석 시작 버튼",
        "후기 카드",
        None,  # 답에 없는 번호
        "로딩 중인 빈 화면",
        None,
    ]
    assert len(seen["bodies"]) == 1
    body = seen["bodies"][0]
    assert body["model"] == "vm"
    parts = body["messages"][-1]["content"]
    images = [p for p in parts if p["type"] == "image_url"]
    assert len(images) == 2 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "5장" in parts[0]["text"]


def test_describe_many_splits_requests_and_cleans_text():
    calls = []

    def handler(req):
        calls.append(1)
        n = len(calls)
        long = "가" * (MAX_SEEN + 30)
        return _reply(f"<think>음…</think>\n1. {long}\n**2**: 둘째 {n}")

    total = PER_REQUEST + 1  # 한 요청에 담을 수 있는 장수를 넘으면 나눠 보낸다
    out = _vision(handler).describe_many([png("red")] * total)
    assert len(calls) == 2
    assert out[0] == "가" * MAX_SEEN and out[1] == "둘째 1"
    assert out[PER_REQUEST] == "가" * MAX_SEEN


def test_describe_many_failure_is_all_none(caplog):
    msg = "Rate limit reached in organization `org_01abc`. Please try again in 1.5s."
    sleeps: list[float] = []
    vision = _vision(lambda req: httpx.Response(429, json={"error": {"message": msg}}), sleeps)
    assert vision.describe_many([png("red")] * 3) == [None, None, None]
    assert sleeps and sleeps[0] == pytest.approx(2.0)
    assert "org_01abc" not in caplog.text


def test_describe_many_bad_image_is_none_not_crash():
    out = _vision(lambda req: _reply("2: 둘째")).describe_many([b"not a png", png("red")])
    assert out == [None, "둘째"]


def test_get_describer_follows_groq_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert get_describer() is None
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_VISION_MODEL", "other/vision")
    d = get_describer()
    assert isinstance(d, GroqVision) and d.model == "other/vision"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert get_describer() is None  # 이미지 읽기는 Groq 일 때만
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_VISION_MODEL", "")
    assert get_describer() is None  # 빈 값이면 끈다


def test_get_describer_baze_first_then_groq(monkeypatch):
    from app.vision import FallbackDescriber

    monkeypatch.setenv("LLM_PROVIDER", "baze")
    monkeypatch.setenv("BAZE_API_KEY", "b")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    monkeypatch.delenv("BAZE_VISION_MODEL", raising=False)
    d = get_describer()
    assert isinstance(d, FallbackDescriber)
    assert d.primary.model == "claude-haiku-5-5" and d.primary.url.endswith("/chat/completions/")
    assert d.backup.model == "qwen/qwen3.8-27b"


def test_fallback_describer_switches_when_primary_is_down():
    from app.vision import FallbackDescriber

    class Backup:
        def describe_many(self, images):
            return ["백업"] * len(images)

    down = _vision(lambda req: httpx.Response(402, json={"detail": "크레딧 부족"}))
    d = FallbackDescriber(down, Backup())
    assert d.describe_many([png("red")]) == ["백업"]
    ok = _vision(lambda req: _reply("1: 주 모델"))
    assert FallbackDescriber(ok, Backup()).describe_many([png("red")]) == ["주 모델"]


def test_describe_many_leaves_room_for_thinking(
    caplog,
):  # 11/23 Haiku: 생각 토큰에 500을 다 써서 빈 답
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        )

    assert _vision(handler).describe_many([png("red")] * 2) == [None, None]
    assert seen["body"]["max_tokens"] >= 4000
    assert "length" in caplog.text  # 조용히 실패하지 않는다
