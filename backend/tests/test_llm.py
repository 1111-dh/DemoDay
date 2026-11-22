import pytest
from pydantic import BaseModel

from app.llm import generate, get_llm
from tests.fakes import FakeLLM


class Out(BaseModel):
    n: int


def positive(o: Out) -> list[str]:
    return [] if o.n > 0 else ["n은 양수여야 함"]


def test_generate_returns_first_valid():
    llm = FakeLLM(Out(n=1))
    assert generate(llm, system="s", user="u", output=Out, check=positive) == Out(n=1)
    assert len(llm.users) == 1


def test_generate_retries_with_errors():
    llm = FakeLLM(Out(n=0), Out(n=2))
    assert generate(llm, system="s", user="u", output=Out, check=positive) == Out(n=2)
    assert llm.users[0] == "u"
    assert "n은 양수여야 함" in llm.users[1]


def test_generate_gives_up_after_retries():
    llm = FakeLLM(Out(n=0), Out(n=0), Out(n=0), Out(n=5))
    assert generate(llm, system="s", user="u", output=Out, check=positive, retries=2) is None
    assert len(llm.users) == 3


def test_generate_none_is_failure():
    llm = FakeLLM(None, Out(n=3))
    assert generate(llm, system="s", user="u", output=Out, check=positive) == Out(n=3)
    assert len(llm.users) == 2


def test_get_llm_without_key(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert get_llm() is None


def _groq(handler, sleeps=None):
    import httpx

    from app.llm import OpenAICompatLLM

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sleep = sleeps.append if sleeps is not None else lambda s: None
    return OpenAICompatLLM(
        base_url="https://api.test/v1", api_key="k", model="m", client=client, sleep=sleep
    )


def _reply(content: str, status: int = 200):
    import httpx

    body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    return httpx.Response(status, json=body)


def test_groq_parses_structured_output():
    import json

    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return _reply('{"n": 3}')

    assert _groq(handler).parse(system="s", user="u", output=Out) == Out(n=3)
    assert seen["url"] == "https://api.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    body = seen["body"]
    assert body["model"] == "m"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["properties"]["n"]


def test_groq_http_error_returns_none():
    import httpx

    assert (
        _groq(lambda req: httpx.Response(429, json={})).parse(system="s", user="u", output=Out)
        is None
    )


def test_groq_invalid_json_returns_none():
    assert _groq(lambda req: _reply('{"n": "x"}')).parse(system="s", user="u", output=Out) is None


def test_get_llm_picks_groq(monkeypatch):
    from app.llm import OpenAICompatLLM

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert isinstance(get_llm(), OpenAICompatLLM)


def _rate_limited(wait: str):
    import httpx

    msg = (
        f"Rate limit reached ... on tokens per minute (TPM). Please try again in {wait}. Need more"
    )
    return httpx.Response(429, json={"error": {"message": msg}})


def test_groq_waits_and_retries_on_rate_limit():  # 무료 플랜 TPM 한도 — 바로 재시도하면 또 429
    replies = [_rate_limited("5.9475s"), _rate_limited("640ms"), _reply('{"n": 2}')]
    sleeps: list[float] = []
    out = _groq(lambda req: replies.pop(0), sleeps).parse(system="s", user="u", output=Out)
    assert out == Out(n=2)
    assert sleeps == [pytest.approx(6.4475), pytest.approx(1.14)]  # 안내 시간 + 0.5초


def test_groq_rate_limit_wait_is_capped_and_gives_up():
    from app.llm import MAX_RATE_WAIT, RATE_RETRIES

    sleeps: list[float] = []
    llm = _groq(lambda req: _rate_limited("90s"), sleeps)
    assert llm.parse(system="s", user="u", output=Out) is None
    assert sleeps == [MAX_RATE_WAIT] * RATE_RETRIES
