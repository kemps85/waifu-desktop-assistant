import csv
import ctypes
import json
import os
import subprocess
import urllib.parse
import webbrowser

NEEDS_CONFIRM = {"run", "shutdown", "restart"}
# mở file chạy được/script = chạy mã: cũng phải hỏi (app theo tên và URL thì không)
_EXEC_EXT = (".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js", ".jse", ".wsf", ".hta", ".msi", ".scr",
             ".reg", ".py", ".pyw", ".jar", ".lnk")

_NOWIN = subprocess.CREATE_NO_WINDOW
_apps: list[dict] | None = None   # cache Get-StartApps (Name, AppID)
# không bao giờ đóng: chính app này, explorer và tiến trình hệ thống
_PROTECTED = {"explorer", "system", "registry", "smss", "csrss", "wininit", "winlogon",
              "services", "lsass", "svchost", "dwm", "fontdrvhost", "system idle process"}
# tên phím media -> (mã VK, số lần bấm); volume_up/down bấm 5 lần ~ 10%
_MEDIA = {"volume_up": (0xAF, 5), "volume_down": (0xAE, 5), "mute": (0xAD, 1),
          "play_pause": (0xB3, 1), "next": (0xB0, 1), "prev": (0xB1, 1)}


def needs_confirm(action: str, arg: str) -> bool:
    a = (arg or "").strip().rstrip("\"'").lower()
    return action in NEEDS_CONFIRM or (action == "open" and not a.startswith(("http://", "https://"))
                                       and a.endswith(_EXEC_EXT))


def _user32():
    return ctypes.windll.user32


def _installed_apps() -> list[dict]:
    global _apps
    if _apps is None:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_NOWIN)
        data = json.loads(r.stdout)
        _apps = [data] if isinstance(data, dict) else data
    return _apps


def _find_app(name: str) -> dict | None:
    low = name.lower()
    hits = [a for a in _installed_apps() if low in a["Name"].lower()]
    exact = [a for a in hits if a["Name"].lower() == low]
    return min(exact or hits, key=lambda a: len(a["Name"]), default=None)


def _open(arg: str) -> str:
    if not arg:
        return "(lỗi) thiếu tên app / đường dẫn / URL"
    if arg.lower().startswith(("http://", "https://")):
        webbrowser.open(arg)
        return f"Đã mở {arg}"
    if os.path.exists(arg):
        os.startfile(arg)
        return f"Đã mở {arg}"
    try:
        app = _find_app(arg)
    except Exception:   # không liệt kê được app -> thử mở thẳng bằng shell
        app = None
    if app:
        os.startfile("shell:AppsFolder\\" + app["AppID"])   # gọi qua explorer.exe + CREATE_NO_WINDOW thì không mở được
        return f"Đã mở {app['Name']}"
    os.startfile(arg)
    return f"Đã mở {arg}"


def _close(arg: str) -> str:
    if len(arg) < 3:
        return "(lỗi) tên app quá ngắn, cần ít nhất 3 ký tự"
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         errors="replace", timeout=30, creationflags=_NOWIN).stdout
    low, images = arg.lower(), set()
    for row in csv.reader(out.splitlines()):
        if not row:
            continue
        stem = row[0].lower().removesuffix(".exe")
        if low in stem and stem not in _PROTECTED and not stem.startswith("python"):
            images.add(row[0])
    if not images:
        return f"(lỗi) không thấy app nào đang chạy khớp '{arg}'"
    for img in sorted(images):   # không /F: app tự đóng êm, không mất dữ liệu
        subprocess.run(["taskkill", "/IM", img], capture_output=True, timeout=30, creationflags=_NOWIN)
    return "Đã yêu cầu đóng " + ", ".join(sorted(images))


def _media(action: str) -> str:
    vk, n = _MEDIA[action]
    u = _user32()
    for _ in range(n):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)   # KEYEVENTF_KEYUP
    return "Xong"


def _lock(_: str) -> str:
    _user32().LockWorkStation()
    return "Đã khoá máy"


def _sleep(_: str) -> str:
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=_NOWIN)
    return "Đang cho máy ngủ"


def _power(flag: str, msg: str):
    def f(_: str) -> str:   # 30 giây để còn kịp `shutdown /a`
        subprocess.Popen(["shutdown", flag, "/t", "30"], creationflags=_NOWIN)
        return msg
    return f


def _run(arg: str) -> str:
    if not arg:
        return "(lỗi) thiếu lệnh"
    subprocess.Popen(["powershell", "-NoProfile", "-Command", arg], creationflags=_NOWIN)
    return "Đã chạy lệnh"


def _search(arg: str) -> str:
    if not arg:
        return "(lỗi) thiếu từ khoá"
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(arg))
    return f"Đã tìm '{arg}'"


_HANDLERS = {
    "open": _open, "close": _close, "search": _search, "lock": _lock, "sleep": _sleep,
    "shutdown": _power("/s", "Sẽ tắt máy sau 30 giây (huỷ: shutdown /a)"),
    "restart": _power("/r", "Sẽ khởi động lại sau 30 giây (huỷ: shutdown /a)"),
    "run": _run,
    **{k: (lambda a, k=k: _media(k)) for k in _MEDIA},
}


def run_action(action: str, arg: str) -> str:
    """Chạy một hành động trên máy, trả về thông báo ngắn; không bao giờ raise."""
    handler = _HANDLERS.get(action)
    if handler is None:
        return f"(lỗi) không biết hành động: {action}"
    try:
        return handler((arg or "").strip())
    except Exception as e:
        return f"(lỗi) {e}"
