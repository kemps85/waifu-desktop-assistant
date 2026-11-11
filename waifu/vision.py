import base64
import ctypes
import json
import subprocess
import urllib.request

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication

_FIRST = "Đây là ảnh chụp màn hình máy tính của người dùng."
_PROMPT = (_FIRST + " Trong 1-2 câu tiếng Việt, mô tả họ đang làm gì: app nào đang mở ở phía trước và nội dung chính."
           " Không chép lại mật khẩu, mã, hay nội dung tin nhắn riêng.")


def grab_screen(width: int = 1280) -> bytes:
    """JPEG (chất lượng 80) của màn hình chính, thu về bề rộng `width`. Chỉ gọi trên thread giao diện."""
    pm = QGuiApplication.primaryScreen().grabWindow(0)
    if pm.width() > width:
        pm = pm.scaledToWidth(width, Qt.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "JPG", 80)
    return bytes(buf.data())


def describe(jpeg: bytes, cfg: dict, question: str = "") -> str:
    """Nhờ model ảnh local (Ollama) tóm tắt màn hình; ảnh không rời máy. Lỗi mạng/HTTP -> raise."""
    v = cfg["vision"]
    prompt = _PROMPT if not question else (
        f"{_FIRST} Trả lời ngắn gọn bằng tiếng Việt câu hỏi sau dựa trên ảnh: {question}. Không chép lại mật khẩu hay mã.")
    body = {
        "model": v["model"], "stream": False, "keep_alive": 0, "think": False,   # keep_alive 0: nhả VRAM ngay
        "options": {"num_ctx": 4096, "temperature": 0.2},
        "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(jpeg).decode()]}],
    }
    req = urllib.request.Request(v["base_url"].rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=v["timeout_s"]) as r:
        return json.load(r)["message"]["content"].strip()


def vram_used_mb() -> int | None:
    """VRAM GPU đầu tiên đang dùng (MB); None nếu không có nvidia-smi / lỗi."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        return int(r.stdout.split()[0])
    except Exception:
        return None


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """Số giây từ lần gõ phím/di chuột cuối (toàn hệ thống)."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO))
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def foreground_title() -> str:
    """Tiêu đề cửa sổ đang ở phía trước; "" nếu lỗi."""
    try:
        u = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(u.GetForegroundWindow(), buf, 256)
        return buf.value
    except Exception:
        return ""


def is_private(title: str, words: list[str]) -> bool:
    """Tiêu đề chứa một trong các từ (không phân biệt hoa thường) -> cửa sổ riêng tư, đừng liếc."""
    low = title.lower()
    return any(w and w.lower() in low for w in words)


def should_glance(idle_s: float, vram_mb: int | None, interval_s: float, max_vram_mb: int) -> bool:
    """Không liếc khi người dùng đã đi vắng (idle quá một chu kỳ) hoặc GPU đang bận (đang chơi game)."""
    return not (idle_s > interval_s or (vram_mb is not None and vram_mb > max_vram_mb))
