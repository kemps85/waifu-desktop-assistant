import json
from dataclasses import dataclass
from typing import Iterable, Iterator

MOODS = ("normal", "happy", "shy", "worried", "pout", "determined", "sad")


@dataclass
class Say:
    mood: str   # luôn thuộc MOODS
    ja: str     # câu tiếng Nhật để TTS đọc (có thể rỗng)
    vi: str     # câu tiếng Việt để hiện chữ


@dataclass
class Remember:
    text: str


@dataclass
class Do:
    action: str   # chữ thường, ví dụ "open"
    arg: str


def _parse_line(line: str) -> Say | Remember | Do | None:
    line = line.strip()
    if not line or line.startswith("```"):
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return Say("normal", "", line)
    if not isinstance(obj, dict):
        return Say("normal", "", line)
    rem = obj.get("remember")
    if isinstance(rem, str) and rem.strip():
        return Remember(rem.strip())
    do = obj.get("do")
    if isinstance(do, str) and do.strip():
        return Do(do.strip().lower(), str(obj.get("arg") or "").strip())
    ja, vi = obj.get("ja") or "", obj.get("vi") or ""
    if not (ja or vi):
        return None
    mood = obj.get("mood")
    return Say(mood if mood in MOODS else "normal", ja, vi)


def parse_stream(chunks: Iterable[str]) -> Iterator[Say | Remember | Do]:
    buf = ""
    for chunk in chunks:
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if (ev := _parse_line(line)) is not None:
                yield ev
    if (ev := _parse_line(buf)) is not None:
        yield ev
