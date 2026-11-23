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


def test_groq_error_log_hides_org_id(caplog):  # #36 — 로그에 Groq 조직 ID 가 찍혔다
    import httpx

    body = {
        "error": {
            "message": "Request too large in organization `org_01abc` on TPM",
            "code": "rate_limit_exceeded",
        }
    }
    llm = _groq(lambda req: httpx.Response(413, json=body))
    with caplog.at_level("WARNING"):
        assert llm.parse(system="s", user="u", output=Out) is None
    assert "org_01abc" not in caplog.text
    assert "413" in caplog.text and "rate_limit_exceeded" in caplog.text


def _daily_limited():
    import httpx

    msg = (
        "Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01abc` "
        "on tokens per day (TPD): Limit 200000, Used 197268, Requested 4122. "
        "Please try again in 10m0.48s."
    )
    return httpx.Response(429, json={"error": {"message": msg, "code": "rate_limit_exceeded"}})


def test_daily_limit_switches_to_fallback_without_waiting():  # 11/23 TPD 소진 — 3분 기다리다 기본값
    import json

    import httpx

    from app.llm import OpenAICompatLLM

    models: list[str] = []

    def handler(req):
        model = json.loads(req.content)["model"]
        models.append(model)
        return _daily_limited() if model == "big" else _reply('{"n": 3}')

    sleeps: list[float] = []
    llm = OpenAICompatLLM(
        base_url="https://api.test/v1",
        api_key="k",
        model="big",
        fallback_models=["small"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )
    assert llm.parse(system="s", user="u", output=Out) == Out(n=3)
    assert models == ["big", "small"] and sleeps == []
    assert llm.parse(system="s", user="u", output=Out) == Out(n=3)
    assert models[-1] == "small"  # 한 번 바꾸면 그 인스턴스는 계속 작은 모델


def test_daily_limit_without_fallback_fails_fast(caplog):
    sleeps: list[float] = []
    llm = _groq(lambda req: _daily_limited(), sleeps)
    assert llm.parse(system="s", user="u", output=Out) is None
    assert sleeps == []  # 하루 한도는 기다려도 안 풀린다
    assert "org_01abc" not in caplog.text


def test_get_llm_groq_fallback_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.delenv("GROQ_FALLBACK_MODEL", raising=False)
    assert get_llm().fallback_models == ["qwen/qwen3.8-27b"]
    monkeypatch.setenv("GROQ_FALLBACK_MODEL", "")
    assert get_llm().fallback_models == []


def _baze(handler, **kw):
    import httpx

    from app.llm import BAZE_BASE_URL, OpenAICompatLLM

    return OpenAICompatLLM(
        base_url=BAZE_BASE_URL,
        api_key="k",
        model="claude-haiku-5-5",
        chat_path="/chat/completions/",
        strict=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
        **kw,
    )


def test_baze_strict_schema_and_trailing_slash():
    """BAZE 는 strict 스키마에 additionalProperties:false 가 필수."""
    import json

    from pydantic import BaseModel

    class Inner(BaseModel):
        a: int

    class Outer(BaseModel):
        items: list[Inner]
        note: str = ""

    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return _reply('{"items": [{"a": 1}], "note": ""}')

    out = _baze(handler).parse(system="s", user="u", output=Outer)
    assert out == Outer(items=[Inner(a=1)])
    assert seen["url"] == "https://api.baze.co/v1/gateway/chat/completions/"
    fmt = seen["body"]["response_format"]["json_schema"]
    assert fmt["strict"] is True
    schema = fmt["schema"]
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == ["items", "note"]  # strict 는 모든 필드가 required
    assert schema["$defs"]["Inner"]["additionalProperties"] is False


def test_fallback_llm_switches_when_primary_is_down():
    import httpx

    from app.llm import FallbackLLM
    from tests.fakes import FakeLLM

    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(402, json={"detail": {"code": 402, "message": "크레딧 부족"}})

    primary = _baze(handler)
    backup = FakeLLM(Out(n=5), Out(n=6))
    llm = FallbackLLM(primary, backup)
    assert llm.parse(system="s", user="u", output=Out) == Out(n=5)
    assert llm.parse(system="s", user="u", output=Out) == Out(n=6)
    assert len(calls) == 1  # 한 번 내려가면 다시 두드리지 않는다


def test_fallback_llm_keeps_primary_on_bad_output():
    """형식 오류는 generate 재시도 몫 — 예비로 넘기지 않는다."""
    from app.llm import FallbackLLM
    from tests.fakes import FakeLLM

    primary = _baze(lambda req: _reply('{"n": "x"}'))
    backup = FakeLLM(Out(n=5))
    assert FallbackLLM(primary, backup).parse(system="s", user="u", output=Out) is None
    assert backup.users == []


def test_get_llm_picks_baze_with_groq_backup(monkeypatch):
    from app.llm import FallbackLLM, OpenAICompatLLM

    monkeypatch.setenv("LLM_PROVIDER", "baze")
    monkeypatch.setenv("BAZE_API_KEY", "b")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.delenv("BAZE_MODEL", raising=False)
    llm = get_llm()
    assert isinstance(llm, FallbackLLM)
    assert llm.primary.model == "claude-haiku-5-5" and llm.primary.strict
    assert isinstance(llm.backup, OpenAICompatLLM) and "groq" in llm.backup.url
    monkeypatch.delenv("GROQ_API_KEY")
    only = get_llm()
    assert isinstance(only, OpenAICompatLLM) and only.model == "claude-haiku-5-5"
    monkeypatch.delenv("BAZE_API_KEY")
    assert get_llm() is None


def test_unknown_provider_warns(monkeypatch, caplog):  # 11/23 'groq, baze' → 조용히 기본 자막
    monkeypatch.setenv("LLM_PROVIDER", "groq, baze")
    monkeypatch.setenv("BAZE_API_KEY", "b")
    assert get_llm() is None
    assert "LLM_PROVIDER" in caplog.text and "groq, baze" in caplog.text
