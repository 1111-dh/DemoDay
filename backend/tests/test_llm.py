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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_llm() is None
