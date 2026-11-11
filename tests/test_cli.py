import numpy as np
import pytest

from waifu import cli as cli_mod
from waifu import memory as memory_mod
from waifu.llm import LLMError
from waifu.reply import Say


class FakeEngine:
    def __init__(self, raises=None):
        self.texts = []
        self.raises = raises

    def send(self, text):
        self.texts.append(text)
        if self.raises is not None:
            raise self.raises
        yield Say("happy", "やあ", "Chào")


def reader(values):
    it = iter(values)

    def read(prompt=""):
        return next(it)

    return read


def test_run_loop_prints_reply_then_stops_on_exit_command():
    lines = []
    cli_mod.run_loop(FakeEngine(), read=reader(["hi", "/thoat"]), write=lines.append)
    assert lines == ["[happy] Chào", "    やあ"]


def test_run_loop_skips_blank_line_and_handles_eof():
    lines = []

    def read(prompt=""):
        raise EOFError

    cli_mod.run_loop(FakeEngine(), read=read, write=lines.append)
    assert lines == []

    engine = FakeEngine()
    cli_mod.run_loop(engine, read=reader(["", "/thoat"]), write=lines.append)
    assert engine.texts == []


def test_run_loop_reports_llm_error_and_keeps_going():
    lines = []
    engine = FakeEngine(raises=LLMError("x"))
    cli_mod.run_loop(engine, read=reader(["hi", "/thoat"]), write=lines.append)
    assert len(lines) == 1
    assert lines[0].startswith("(lỗi LLM)")
    assert engine.texts == ["hi"]


def test_build_engine_uses_config(monkeypatch):
    cfg = {
        "character": "remielle",
        "llm": {"active": "ollama", "max_history": 7, "temperature": 0.8, "max_tokens": 400},
        "memory": {"enabled": False, "top_k": 3},
    }

    class FakeLLM:
        def generate(self, messages):
            return iter([])

    monkeypatch.setattr(cli_mod, "make_llm", lambda c: FakeLLM())

    engine = cli_mod.build_engine(cfg)

    assert engine.max_history == 7
    assert engine.top_k == 3
    assert engine.memory is None
    assert "Remielle" in engine.persona


class FakeSpeaker:
    def __init__(self):
        self.calls = []

    def say(self, t):
        self.calls.append(("say", t))

    def stop(self):
        self.calls.append(("stop",))

    def wait(self):
        self.calls.append(("wait",))

    def close(self):
        self.calls.append(("close",))


class TwoSayEngine:
    def __init__(self, says):
        self.says = says
        self.texts = []

    def send(self, text):
        self.texts.append(text)
        yield from self.says


def test_run_loop_speaks_each_say_in_order_and_cleans_up():
    sp = FakeSpeaker()
    engine = TwoSayEngine([Say("happy", "A", "a"), Say("happy", "B", "b")])
    cli_mod.run_loop(engine, read=reader(["hi", "/thoat"]), write=lambda s: None, speaker=sp)
    assert sp.calls == [("stop",), ("say", "A"), ("say", "B"), ("wait",), ("close",)]


def test_run_loop_does_not_speak_empty_ja():
    sp = FakeSpeaker()
    engine = TwoSayEngine([Say("happy", "", "a"), Say("happy", "B", "b")])
    cli_mod.run_loop(engine, read=reader(["hi", "/thoat"]), write=lambda s: None, speaker=sp)
    assert ("say", "") not in sp.calls
    assert [c for c in sp.calls if c[0] == "say"] == [("say", "B")]


def test_run_loop_blank_line_uses_listen():
    engine = FakeEngine()
    cli_mod.run_loop(engine, read=reader(["", "/thoat"]), write=lambda s: None,
                     listen=lambda: "xin chào")
    assert engine.texts == ["xin chào"]


def test_run_loop_listen_empty_reports_and_skips_engine():
    lines = []
    engine = FakeEngine()
    cli_mod.run_loop(engine, read=reader(["", "/thoat"]), write=lines.append, listen=lambda: "")
    assert lines == ["(không nghe rõ)"]
    assert engine.texts == []


def test_make_listen_records_then_transcribes():
    order, lines = [], []

    class Rec:
        def start(self):
            order.append("start")

        def stop(self):
            order.append("stop")
            return "audio"

    class Stt:
        def transcribe(self, audio):
            order.append(("stt", audio))
            return "chào"

    listen = cli_mod.make_listen(Rec(), Stt(), read=lambda p="": order.append("read") or "", write=lines.append)
    assert listen() == "chào"
    assert order == ["start", "read", "stop", ("stt", "audio")]
    assert lines[-1] == "Bạn (mic): chào"


def test_build_engine_memory_disabled_gives_no_store(monkeypatch):
    monkeypatch.setattr(cli_mod, "make_llm", lambda c: object())
    cfg = {"character": "remielle", "llm": {"max_history": 7}, "memory": {"enabled": False, "top_k": 3}}
    assert cli_mod.build_engine(cfg).memory is None


def test_build_engine_memory_enabled_opens_store_at_db_path(monkeypatch, tmp_path):
    calls = []

    def fake_make_embedder(base_url, model):
        calls.append((base_url, model))
        return lambda texts: np.zeros((len(texts), 4), np.float32)

    monkeypatch.setattr(cli_mod, "make_llm", lambda c: object())
    monkeypatch.setattr(memory_mod, "make_embedder", fake_make_embedder)
    db = tmp_path / "m.db"
    cfg = {"character": "remielle", "llm": {"max_history": 7},
           "memory": {"enabled": True, "db_path": db, "embed_base_url": "http://x/v1",
                      "embed_model": "bge-m3", "top_k": 3, "dedupe_threshold": 0.9}}

    engine = cli_mod.build_engine(cfg)

    assert isinstance(engine.memory, memory_mod.MemoryStore)
    assert db.exists()
    assert calls == [("http://x/v1", "bge-m3")]
    engine.memory.close()
