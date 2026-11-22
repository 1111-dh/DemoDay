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


def _groq(handler):
    import httpx

    from app.llm import OpenAICompatLLM

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatLLM(base_url="https://api.test/v1", api_key="k", model="m", client=client)


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
