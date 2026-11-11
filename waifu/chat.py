import json
import sys
from typing import Iterator

from waifu.persona import build_messages
from waifu.reply import Do, Remember, Say, parse_stream


class ChatEngine:
    def __init__(self, llm, persona: str, memory=None,
                 max_history: int = 20, top_k: int = 5):
        self.llm = llm
        self.persona = persona
        self.memory = memory
        self.max_history = max_history
        self.top_k = top_k
        self.english = False   # chế độ luyện tiếng Anh: người dùng nói tiếng Anh, Remielle sửa lỗi
        self.on_do = None  # callable(action, arg); gọi từ thread nền của send()
        self.history = list(memory.recent_messages(max_history)) if memory is not None else []

    def send(self, user_text: str) -> Iterator[Say]:
        memories = []
        hidden = user_text.startswith(("(Hệ thống:", "(Màn hình:"))   # lượt app tự gửi: khỏi tra trí nhớ
        if self.memory is not None and not hidden:
            try:
                memories = self.memory.search(user_text, self.top_k)
            except Exception as e:  # Ollama tắt -> vẫn chat được, chỉ thiếu trí nhớ dài hạn
                print(f"(cảnh báo) không tra được trí nhớ: {e}", file=sys.stderr)
        messages = build_messages(self.persona, memories, self.history, user_text, self.english)

        items: list[Say | Do] = []   # theo thứ tự đến, để lịch sử khớp giao thức
        for item in parse_stream(self.llm.generate(messages)):
            if isinstance(item, Say):
                items.append(item)
                yield item
            elif isinstance(item, Do):
                if user_text.startswith("(Màn hình:"):
                    continue   # chữ trên màn hình (trang web lạ) không được phép sai khiến máy
                items.append(item)
                if self.on_do is not None:
                    try:
                        self.on_do(item.action, item.arg)
                    except Exception as e:
                        print(f"(cảnh báo) không chạy được hành động: {e}", file=sys.stderr)
            elif isinstance(item, Remember):
                if self.memory is not None:
                    try:
                        self.memory.remember(item.text)
                    except Exception as e:
                        print(f"(cảnh báo) không ghi được trí nhớ: {e}", file=sys.stderr)

        # lượt do app tự gửi (lời chào lúc mở) không lưu: lưu lại thì nó cứ nhắc mãi chuyện "mở máy lúc mấy giờ"
        if not items or user_text.startswith("(Hệ thống:"):
            return
        # lượt "(Màn hình:" chỉ lưu khi cô ấy thật sự nói; im lặng thì không lưu gì
        if user_text.startswith("(Màn hình:") and not any(isinstance(i, Say) for i in items):
            return

        content = "\n".join(
            json.dumps({"do": s.action, "arg": s.arg} if isinstance(s, Do)
                       else {"mood": s.mood, "ja": s.ja, "vi": s.vi}, ensure_ascii=False)
            for s in items
        )
        screen = user_text.startswith("(Màn hình:")
        if screen:
            user_text = user_text.split("\n", 1)[0]   # chỉ giữ dòng tóm tắt, bỏ phần chỉ dẫn dài
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": content})
        if screen:   # chỉ ở RAM, tối đa 3 cặp: lượt liếc không được đẩy hội thoại thật ra khỏi lịch sử
            while len(idx := [i for i, m in enumerate(self.history)
                              if m["role"] == "user" and m["content"].startswith("(Màn hình:")]) > 3:
                del self.history[idx[0]:idx[0] + 2]
        elif self.memory is not None:
            self.memory.add_message("user", user_text)
            self.memory.add_message("assistant", content)
        if self.max_history > 0:
            self.history = self.history[-self.max_history:]
