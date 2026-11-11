import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prepare_voice_dataset.py"
_spec = importlib.util.spec_from_file_location("prepare_voice_dataset", SCRIPT)
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)

SAMPLE = """## 001. startup — câu 1

**Tiếng Việt:** Ồ, cậu gọi tôi à?

**Cách nói:** Ngọt ngào.

```text
[playful, sweet tone] 呼んだ？じゃあ今日から、キミのことは共犯者の私に任せてね〜
```
"""


def test_parse_script_extracts_japanese_and_drops_tags():
    assert pv.parse_script(SAMPLE) == {
        "001": "呼んだ？じゃあ今日から、キミのことは共犯者の私に任せてね〜"
    }


def test_parse_script_handles_two_entries():
    md = SAMPLE + """
## 002. startup — câu 2

```text
[calm] 百年も眠ってたんだもの。
```
"""
    got = pv.parse_script(md)
    assert sorted(got) == ["001", "002"]
    assert got["002"] == "百年も眠ってたんだもの。"


def test_parse_script_removes_tag_in_the_middle():
    md = """## 003. x

```text
あ [laughs] い
```
"""
    assert pv.parse_script(md) == {"003": "あ い"}
