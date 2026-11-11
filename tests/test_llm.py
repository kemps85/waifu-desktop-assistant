from types import SimpleNamespace

import pytest
from openai import OpenAIError

from waifu import llm as llm_mod
from waifu.llm import LLMError, OpenAICompatLLM, make_llm


def chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def empty_choices():
    return SimpleNamespace(choices=[])


class FakeOpenAI:
    """Thay cho openai.OpenAI: payload là list chunk, hoặc một Exception để raise."""

    payload = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.create_kwargs = {}
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        if isinstance(FakeOpenAI.payload, Exception):
            raise FakeOpenAI.payload
        return iter(FakeOpenAI.payload)


@pytest.fixture
def fake_openai(monkeypatch):
    monkeypatch.setattr(llm_mod, "OpenAI", FakeOpenAI)
    FakeOpenAI.payload = []
    return FakeOpenAI


def cfg(active="deepseek"):
    return {
        "llm": {
            "active": active,
            "temperature": 0.8,
            "max_tokens": 400,
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "model": "deepseek-flash",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "extra_body": {"thinking": {"type": "disabled"}},
                },
                "ollama": {
                    "base_url": "http://localhost:11434/v1",
                    "model": "waifu-gemma",
                    "api_key_env": "",
                    "extra_body": {"reasoning_effort": "none"},
                },
            },
        }
    }


def test_generate_yields_content_in_order_skipping_empty(fake_openai):
    fake_openai.payload = [chunk("Xin "), chunk(None), empty_choices(), chunk("chào")]
    llm = OpenAICompatLLM("http://x", "m", "k")
    assert list(llm.generate([{"role": "user", "content": "hi"}])) == ["Xin ", "chào"]


def test_create_receives_model_stream_and_extra_body(fake_openai):
    fake_openai.payload = [chunk("a")]
    llm = OpenAICompatLLM("http://x", "m", "k", extra_body={"thinking": {"type": "disabled"}},
                          temperature=0.5, max_tokens=99)
    list(llm.generate([{"role": "user", "content": "hi"}]))
    kw = llm.client.create_kwargs
    assert kw["model"] == "m"
    assert kw["stream"] is True
    assert kw["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kw["temperature"] == 0.5
    assert kw["max_tokens"] == 99


def test_openai_error_becomes_llm_error(fake_openai):
    fake_openai.payload = OpenAIError("x")
    llm = OpenAICompatLLM("http://x", "m", "k")
    with pytest.raises(LLMError):
        list(llm.generate([{"role": "user", "content": "hi"}]))


def test_error_during_iteration_becomes_llm_error(fake_openai):
    def bad_stream():
        yield chunk("a")
        raise OpenAIError("mạng đứt")

    llm = OpenAICompatLLM("http://x", "m", "k")
    llm.client.create = lambda **kw: bad_stream()
    with pytest.raises(LLMError):
        list(llm.generate([{"role": "user", "content": "hi"}]))


def test_make_llm_missing_key_raises_with_env_name(fake_openai, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(LLMError) as exc:
        make_llm(cfg("deepseek"))
    assert "DEEPSEEK_API_KEY" in str(exc.value)


def test_make_llm_ollama_needs_no_env(fake_openai, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = make_llm(cfg("ollama"))
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.client.kwargs["api_key"] == "none"
    assert llm.client.kwargs["base_url"] == "http://localhost:11434/v1"
    assert llm.model == "waifu-gemma"


def test_make_llm_unknown_provider_raises(fake_openai):
    with pytest.raises(LLMError):
        make_llm(cfg("khong-co"))
