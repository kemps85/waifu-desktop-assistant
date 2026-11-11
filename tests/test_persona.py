from pathlib import Path

from waifu.persona import MEMORY_HEADER, build_messages, load_persona


def test_load_persona_reads_utf8_and_strips(tmp_path: Path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "persona.md").write_text("  Tên: Hinata, thích ăn phở.\n", encoding="utf-8")
    assert load_persona("x", root=tmp_path) == "Tên: Hinata, thích ăn phở."


def test_build_messages_without_memories():
    msgs = build_messages("P", [], [], "hi")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"].startswith("P\n\n")
    assert "CÁCH TRẢ LỜI" in msgs[0]["content"]
    assert MEMORY_HEADER not in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_build_messages_appends_memories():
    msgs = build_messages("P", ["a", "b"], [], "hi")
    assert msgs[0]["content"].endswith(MEMORY_HEADER + "\n- a\n- b")


def test_build_messages_keeps_history_and_input_list():
    history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    before = list(history)
    msgs = build_messages("P", [], history, "hi")
    assert len(msgs) == 4
    assert msgs[1:3] == before
    assert msgs[3] == {"role": "user", "content": "hi"}
    assert history == before


def test_build_messages_english_mode_after_static_prefix():
    from waifu.persona import ENGLISH_MODE, OUTPUT_RULES

    off = build_messages("P", ["m"], [], "hi")[0]["content"]
    on = build_messages("P", ["m"], [], "hi", english=True)[0]["content"]
    assert ENGLISH_MODE not in off
    assert on.startswith("P\n\n" + OUTPUT_RULES + "\n\n" + ENGLISH_MODE)   # tiền tố tĩnh giữ nguyên để cache
    assert on.endswith("- m")


def test_output_rules_mention_look_and_screen_turn():
    from waifu.persona import OUTPUT_RULES
    assert "look (arg" in OUTPUT_RULES and '"(Màn hình:"' in OUTPUT_RULES
