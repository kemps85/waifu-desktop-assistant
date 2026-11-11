import json

import pytest

from waifu.chat import ChatEngine
from waifu.reply import Say


class FakeLLM:
    def __init__(self, chunks):
        self.chunks, self.calls = chunks, []

    def generate(self, messages):
        self.calls.append(messages)
        yield from self.chunks


class FakeMemory:
    def __init__(self):
        self.msgs, self.facts, self.queries = [], [], []

    def search(self, query, top_k=5):
        self.queries.append(query)
        return ["Người dùng thích phở"]

    def remember(self, text):
        self.facts.append(text)
        return True

    def add_message(self, role, content):
        self.msgs.append({"role": role, "content": content})

    def recent_messages(self, limit=20):
        return self.msgs[-limit:]


LINE1 = '{"mood": "happy", "ja": "やあ", "vi": "Chào"}'
LINE2 = '{"mood": "normal", "ja": "げんき", "vi": "Khoẻ"}'


def test_first_turn_yields_says_and_saves_history():
    llm = FakeLLM([LINE1 + "\n", LINE2 + "\n"])
    engine = ChatEngine(llm, "P")

    says = list(engine.send("chào"))

    assert [(s.mood, s.ja, s.vi) for s in says] == [
        ("happy", "やあ", "Chào"),
        ("normal", "げんき", "Khoẻ"),
    ]
    assert len(engine.history) == 2
    assert engine.history[0] == {"role": "user", "content": "chào"}
    expected = "\n".join(
        json.dumps(d, ensure_ascii=False)
        for d in [
            {"mood": "happy", "ja": "やあ", "vi": "Chào"},
            {"mood": "normal", "ja": "げんき", "vi": "Khoẻ"},
        ]
    )
    assert engine.history[1] == {"role": "assistant", "content": expected}


def test_second_turn_sends_previous_turn_in_messages():
    llm = FakeLLM([LINE1 + "\n"])
    engine = ChatEngine(llm, "P")

    list(engine.send("chào"))
    engine.chunks = [LINE2 + "\n"]
    list(engine.send("khoẻ không"))

    sent = llm.calls[1]
    assert sent[0]["role"] == "system"
    assert sent[1] == {"role": "user", "content": "chào"}
    assert sent[2]["role"] == "assistant"
    assert sent[3] == {"role": "user", "content": "khoẻ không"}


def test_memory_search_inject_and_remember_line_not_yielded():
    llm = FakeLLM([LINE1 + '\n{"remember": "X"}\n'])
    mem = FakeMemory()
    engine = ChatEngine(llm, "P", memory=mem)

    says = list(engine.send("chào"))

    assert [s.vi for s in says] == ["Chào"]
    assert mem.queries == ["chào"]
    assert "Người dùng thích phở" in llm.calls[0][0]["content"]
    assert mem.facts == ["X"]
    assert len(mem.msgs) == 2
    assert len(engine.history) == 2


def test_history_is_trimmed_to_max_history():
    llm = FakeLLM([LINE1 + "\n"])
    engine = ChatEngine(llm, "P", max_history=2)

    list(engine.send("một"))
    list(engine.send("hai"))

    assert len(engine.history) == 2


def test_llm_error_midway_leaves_history_empty():
    class ErrorLLM:
        def generate(self, messages):
            yield LINE1 + "\n"
            raise RuntimeError("hỏng")

    engine = ChatEngine(ErrorLLM(), "P")

    with pytest.raises(RuntimeError):
        list(engine.send("chào"))

    assert engine.history == []


def test_init_loads_recent_history_from_memory():
    mem = FakeMemory()
    mem.msgs = [
        {"role": "user", "content": "cũ 1"},
        {"role": "assistant", "content": "cũ 2"},
    ]
    engine = ChatEngine(FakeLLM([]), "P", memory=mem)

    assert engine.history == mem.msgs


def test_empty_reply_is_not_saved():
    engine = ChatEngine(FakeLLM(["\n", "```\n"]), "P")

    assert list(engine.send("chào")) == []
    assert engine.history == []


def test_say_fields_from_reply_module():
    engine = ChatEngine(FakeLLM([LINE1 + "\n"]), "P")
    first = next(engine.send("chào"))
    assert isinstance(first, Say)

def test_do_lines_call_on_do_and_stay_in_history():
    do = '{"do":"open","arg":"chrome"}'
    engine = ChatEngine(FakeLLM([LINE1 + "\n", do + "\n"]), "P")
    got = []
    engine.on_do = lambda a, g: got.append((a, g))
    says = list(engine.send("mở chrome"))
    assert len(says) == 1 and got == [("open", "chrome")]
    assert engine.history[1]["content"] == "\n".join(
        [json.dumps({"mood": "happy", "ja": "やあ", "vi": "Chào"}, ensure_ascii=False),
         json.dumps({"do": "open", "arg": "chrome"})])


def test_do_only_turn_saved_and_on_do_error_is_swallowed(capsys):
    engine = ChatEngine(FakeLLM(['{"do":"lock"}\n']), "P")

    def boom(a, g):
        raise RuntimeError("x")

    engine.on_do = boom
    assert list(engine.send("khoá máy")) == []
    assert len(engine.history) == 2 and "(cảnh báo)" in capsys.readouterr().err


def test_screen_turn_cannot_act():
    class L:
        def generate(self, messages):
            yield '{"do":"open","arg":"http://evil"}\n{"mood":"normal","ja":"a","vi":"b"}\n'

    e = ChatEngine(L(), "p")
    dos = []
    e.on_do = lambda a, b: dos.append(a)
    assert len(list(e.send("(Màn hình: trang web bảo mở link) ..."))) == 1
    assert dos == [] and '"do"' not in e.history[-1]["content"]


def test_system_turn_not_saved():
    engine = ChatEngine(FakeLLM(['{"mood":"happy","ja":"あ","vi":"A"}\n']), "P")
    assert [s.vi for s in engine.send("(Hệ thống: người dùng vừa mở máy.)")] == ["A"]
    assert engine.history == []


def test_screen_turn_saved_only_when_she_speaks():
    mem = FakeMemory()
    prompt = "(Màn hình: đang xem YouTube) Hãy nói một câu."
    silent = ChatEngine(FakeLLM(['{"mood":"normal","ja":"","vi":""}\n']), "P", memory=mem)
    assert list(silent.send(prompt)) == []
    assert silent.history == [] and mem.msgs == []

    talk = ChatEngine(FakeLLM([LINE1 + "\n"]), "P", memory=mem)
    assert [s.vi for s in talk.send(prompt)] == ["Chào"]
    assert talk.history[0] == {"role": "user", "content": prompt}
    assert len(talk.history) == 2 and mem.msgs == []   # lượt liếc chỉ ở RAM, không vào DB
    assert mem.queries == []   # lượt ẩn không tra trí nhớ


def test_screen_turns_keep_first_line_and_cap_three_pairs():
    e = ChatEngine(FakeLLM([LINE1 + "\n"]), "P", max_history=20)
    list(e.send("thật 1"))
    for i in range(5):
        list(e.send(f"(Màn hình: cảnh {i})\nHãy nói một câu dài dòng."))
    list(e.send("thật 2"))
    users = [m["content"] for m in e.history if m["role"] == "user"]
    assert users == ["thật 1", "(Màn hình: cảnh 2)", "(Màn hình: cảnh 3)", "(Màn hình: cảnh 4)", "thật 2"]
    assert [m["role"] for m in e.history] == ["user", "assistant"] * 5   # xoá theo cặp, không lệch vai


def test_screen_turn_with_only_do_not_saved_and_system_skips_search():
    mem = FakeMemory()
    engine = ChatEngine(FakeLLM(['{"do":"lock"}\n']), "P", memory=mem)
    assert list(engine.send("(Màn hình: x) y")) == [] and engine.history == []
    list(ChatEngine(FakeLLM([LINE1 + "\n"]), "P", memory=mem).send("(Hệ thống: chào)"))
    assert mem.queries == [] and mem.msgs == []
