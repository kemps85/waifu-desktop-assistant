import ctypes
import os
import random
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from waifu import vision
from waifu.actions import needs_confirm, run_action
from waifu.llm import LLMError

AVATAR_H = 300      # chiều cao chibi (px)
WIN_W = 400
BUBBLE_MS = 6000    # bong bóng tự ẩn sau chừng này ms
TALK_VK = {"right_ctrl": 0xA3, "right_alt": 0xA5, **{f"f{i}": 0x6F + i for i in range(2, 13)}}
TALK_NAME = {"right_ctrl": "Ctrl phải", "right_alt": "Alt phải"}


def avatar_path(character: str, mood: str, root: Path = Path("characters")) -> Path:
    """Chọn ngẫu nhiên (random.choice) trong các file tồn tại: <mood>.png, <mood>_2.png.
    Không có file nào -> normal.png."""
    d = root / character / "images"
    found = [p for p in (d / f"{mood}.png", d / f"{mood}_2.png") if p.exists()]
    return random.choice(found) if found else d / "normal.png"


class ChatWorker(QThread):
    say = Signal(str, str, str)     # mood, ja, vi
    failed = Signal(str)            # thông báo lỗi

    def __init__(self, engine, text: str):
        super().__init__()
        self.engine, self.text = engine, text

    def run(self) -> None:
        try:
            for s in self.engine.send(self.text):
                self.say.emit(s.mood, s.ja, s.vi)
        except Exception as e:
            self.failed.emit(str(e))


class Job(QThread):
    """Chạy fn() trên thread nền; kết quả về qua signal (nhận trên thread giao diện)."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn())
        except Exception as e:
            self.failed.emit(str(e))



def talk_vk(name: str) -> int:
    """Tên phím giữ-để-nói -> mã VK; tên lạ thì dùng Ctrl phải."""
    return TALK_VK.get(str(name).strip().lower(), TALK_VK["right_ctrl"])


def key_down(vk: int) -> bool:
    """Phím đang được giữ (toàn hệ thống, kể cả khi đang ở app khác)."""
    f = ctypes.windll.user32.GetAsyncKeyState
    f.restype = ctypes.c_short
    return f(vk) < 0   # bit cao = đang nhấn


def set_topmost(win: QWidget, on: bool) -> None:
    """Bật: nổi lên trên mọi cửa sổ và ở yên đó. Tắt: lùi xuống dưới cùng cho khỏi vướng.
    Dùng Win32 vì đổi cờ WindowStaysOnTopHint của Qt sẽ ẩn rồi hiện lại cửa sổ (nháy)."""
    if QApplication.platformName() != "windows":
        return
    # HWND_TOPMOST = -1, HWND_BOTTOM = 1; SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(int(win.winId())), ctypes.c_void_p(-1 if on else 1),
                                      0, 0, 0, 0, 0x0013)


def port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _tts_addr(cfg: dict) -> tuple[str, int]:
    u = urllib.parse.urlparse(cfg["tts"]["base_url"])
    return u.hostname or "127.0.0.1", u.port or 80


def start_tts(cfg: dict):
    """Bật server TTS ẩn nếu chưa có ai nghe ở cổng; trả về Popen (None nếu đã có sẵn)."""
    if port_open(*_tts_addr(cfg)):
        return None
    return subprocess.Popen(["cmd", "/c", "scripts\\start_tts.bat"], creationflags=subprocess.CREATE_NO_WINDOW)


def stop_tts(proc) -> None:
    if proc is not None:   # chỉ tắt server do app này bật; /T để diệt cả cây tiến trình
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)


def wait_port(host: str, port: int, timeout: float, stop: threading.Event) -> None:
    end = time.monotonic() + timeout
    while not stop.is_set() and time.monotonic() < end and not port_open(host, port):
        stop.wait(0.5)


def greet_prompt() -> str:
    h = time.localtime().tm_hour
    part = "khuya" if h < 5 else "sáng" if h < 11 else "trưa" if h < 14 else "chiều" if h < 18 else "tối"
    return (f"(Hệ thống: người dùng vừa mở máy, đang là buổi {part}. Hãy chào họ một câu ngắn, "
            "không nhắc giờ giấc cụ thể hay lần mở máy trước, không thực hiện hành động nào.)")


class MainWindow(QWidget):
    speaking = Signal(bool)     # phát từ thread nền của Speaker
    act = Signal(str, str)      # (action, arg) từ thread nền của ChatEngine -> chạy trên thread giao diện

    def __init__(self, engine, cfg: dict, speaker=None, recorder=None, make_stt=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool)   # "luôn ở trên" bật/tắt bằng phím ui.top_key
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.engine, self.cfg, self.speaker = engine, cfg, speaker
        self.recorder, self.stt = recorder, None
        self.worker = self.loader = self.stt_job = self.greeter = self.look_job = None
        self.recording = self.is_speaking = False
        self.closing = threading.Event()
        self.english = False
        self.set_english(cfg.get("ui", {}).get("english", False))
        self.run_action = run_action    # tests thay bằng hàm giả
        self.vision_on, self.last_seen = cfg["vision"]["enabled"], ""
        self.grab, self.describe = vision.grab_screen, vision.describe   # tests thay: không chụp/gọi Ollama thật
        self._bob = False
        self._press = None              # [vị trí chuột, vị trí cửa sổ, đã kéo?] khi đang giữ chuột trái
        self.timer = QTimer(self, interval=150)
        self.timer.timeout.connect(self._bob_tick)
        self.hide_timer = QTimer(self, interval=BUBBLE_MS, singleShot=True)
        self.hide_timer.timeout.connect(self._hide_bubble)
        self.speaking.connect(self.set_speaking)
        self.act.connect(self.do_action)
        self.current_avatar = None
        self.setWindowTitle(cfg["character"].capitalize())
        self.setFixedWidth(WIN_W)

        key = cfg["ui"]["talk_key"]
        self.talk_vk, self._key_held = talk_vk(key), False
        self.top_vk, self._top_held = talk_vk(cfg["ui"].get("top_key", "right_alt")), False
        self.pinned = bool(cfg["ui"].get("on_top", False))
        self.talk_text = f"Giữ để nói ({TALK_NAME.get(key, str(key).upper())})"

        self.avatar = QLabel(alignment=Qt.AlignHCenter | Qt.AlignBottom)
        self.avatar.setFixedHeight(AVATAR_H + 6)   # +6 chỗ cho chibi nhún khi nói
        self.vi_label = QLabel(wordWrap=True)
        self.vi_label.setFont(QFont(self.font().family(), 13))
        self.vi_label.setStyleSheet("color: white")
        self.ja_label = QLabel(wordWrap=True)
        self.ja_label.setFont(QFont(self.font().family(), 9))
        self.ja_label.setStyleSheet("color: #aaaaaa")
        self.bubble = QFrame(objectName="bubble")
        self.bubble.setStyleSheet("#bubble { background: rgba(20, 20, 30, 200); border-radius: 12px; }")
        bl = QVBoxLayout(self.bubble)
        bl.addWidget(self.vi_label)
        bl.addWidget(self.ja_label)
        self.bubble.hide()

        self.input = QLineEdit(placeholderText="Gõ tin nhắn rồi Enter…")
        self.input.returnPressed.connect(self._submit)
        self.talk_button = QPushButton("Đang nạp model nghe…")
        self.talk_button.setEnabled(False)
        self.talk_button.pressed.connect(self.start_talk)
        self.talk_button.released.connect(self.stop_talk)
        self.row = QWidget()
        self.row.setStyleSheet(
            "QLineEdit, QPushButton { background: rgba(20, 20, 30, 220); color: white;"
            " border: 1px solid #666; border-radius: 8px; padding: 6px; }"
            "QPushButton:disabled { color: #888; }")
        rl = QHBoxLayout(self.row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.input)
        rl.addWidget(self.talk_button)
        self.row.hide()
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.hide_input)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 6)
        lay.setSpacing(4)
        # chibi nằm dưới cùng, sát góc neo -> bong bóng / ô chat hiện hay ẩn chỉ mọc lên trên, chibi đứng yên
        for w in (self.bubble, self.row, self.avatar):
            lay.addWidget(w)
        self._show_avatar("normal")
        self._anchor = QApplication.primaryScreen().availableGeometry().bottomRight()   # góc đáy-phải cửa sổ
        self._fit()

        if recorder is None or make_stt is None:
            self.talk_button.hide()
        else:
            self.loader = Job(make_stt)
            self.loader.done.connect(self._stt_ready)
            self.loader.failed.connect(lambda m: self.talk_button.setText("Không nạp được model nghe"))
            self.loader.start()
            if sys.platform == "win32":
                self.key_timer = QTimer(self, interval=30)
                self.key_timer.timeout.connect(self._poll_key)
                self.key_timer.start()

    # --- bố cục / bong bóng -------------------------------------------------
    def _fit(self) -> None:
        """Co cửa sổ vừa nội dung, giữ nguyên góc đáy-phải (self._anchor) nên cửa sổ luôn nằm trong màn hình."""
        anchor = self._anchor
        lay = self.layout()
        lay.invalidate()
        lay.activate()
        # adjustSize() tính sai chiều cao của nhãn xuống dòng nên tự tính theo bề rộng cố định
        h = lay.totalHeightForWidth(WIN_W) if lay.hasHeightForWidth() else lay.sizeHint().height()
        self.setFixedSize(WIN_W, h)
        self.move(anchor.x() - self.width() + 1, anchor.y() - self.height() + 1)

    def _show_bubble(self) -> None:
        self.bubble.setVisible(bool(self.vi_label.text() or self.ja_label.text()))
        self._fit()

    def _note(self, text: str) -> None:
        """Thay nội dung bong bóng bằng một dòng thông báo."""
        self.vi_label.setText(text)
        self.ja_label.clear()
        self._show_bubble()
        self._arm_hide()

    def _arm_hide(self) -> None:
        if not self.is_speaking:
            self.hide_timer.start()

    def _hide_bubble(self) -> None:
        if self.recording:
            return
        self.vi_label.clear()
        self.ja_label.clear()
        self._show_bubble()

    def show_input(self) -> None:
        self.row.show()
        self._fit()
        self.activateWindow()
        self.input.setFocus()

    def hide_input(self) -> None:
        self.row.hide()
        self._fit()

    def toggle_input(self) -> None:
        self.show_input() if self.row.isHidden() else self.hide_input()

    # --- chuột: kéo chibi, bấm trái = bật/tắt ô chat, bấm phải = menu --------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.avatar.geometry().contains(event.position().toPoint()):
            self._press = [event.globalPosition().toPoint(), self.pos(), False]

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        d = event.globalPosition().toPoint() - self._press[0]
        if self._press[2] or d.manhattanLength() > 4:
            self._press[2] = True
            self.move(self._press[1] + d)
            self._anchor = self.geometry().bottomRight()

    def mouseReleaseEvent(self, event) -> None:
        press, self._press = self._press, None
        if event.button() == Qt.LeftButton and press is not None and not press[2]:
            self.toggle_input()

    def contextMenuEvent(self, event) -> None:
        if not self.avatar.geometry().contains(event.pos()):
            return
        menu = QMenu(self)
        menu.addAction("Chat", self.show_input)
        en = menu.addAction("Chế độ tiếng Anh")
        en.setCheckable(True)
        en.setChecked(self.english)
        en.toggled.connect(self.set_english)
        vs = menu.addAction("Nhìn màn hình")
        vs.setCheckable(True)
        vs.setChecked(self.vision_on)
        vs.toggled.connect(lambda on: setattr(self, "vision_on", on))
        menu.addAction("Nhìn ngay", lambda: self.look())   # lambda: tránh `checked` của triggered rơi vào `question`
        menu.addAction("Thoát", self._quit)
        menu.exec(event.globalPos())

    def _quit(self) -> None:
        self.close()
        QApplication.quit()

    # --- nghe ----------------------------------------------------------------
    def set_english(self, on: bool) -> None:
        """Bật: mic nghe tiếng Anh, Remielle sửa lỗi tiếng Anh (vẫn trả lời Việt + Nhật). Tắt: mic nghe tiếng Việt."""
        self.english = self.engine.english = bool(on)
        if self.stt is not None:
            self.stt.language = "en" if on else self.cfg["stt"]["language"]

    def _stt_ready(self, stt) -> None:
        self.stt = stt
        self.set_english(self.english)
        self.talk_button.setEnabled(True)
        self.talk_button.setText(self.talk_text)

    def _busy(self) -> bool:
        return any(t is not None and t.isRunning() for t in (self.worker, self.stt_job))

    def _key_state(self) -> bool:
        return key_down(self.talk_vk)

    def _poll_key(self) -> None:
        down = self._key_state()
        if down != self._key_held:   # chỉ phản ứng khi đổi trạng thái: giữ phím lúc đang bận không tự thu âm
            self._key_held = down
            self.start_talk() if down else self.stop_talk()
        top = key_down(self.top_vk)
        if top and not self._top_held:   # mỗi lần nhấn (không phải giữ) đổi một lần
            self.set_pinned(not self.pinned)
        self._top_held = top

    def set_pinned(self, on: bool) -> None:
        self.pinned = on
        if on:
            self.show()
            self.raise_()
        set_topmost(self, on)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        set_topmost(self, self.pinned) if self.pinned else None

    def start_talk(self) -> None:
        if self.stt is None or self.recording or self._busy():
            return
        if self.speaker:
            self.speaker.stop()
        self.recorder.start()
        self.recording = True
        self.talk_button.setText("Đang nghe…")
        self._note("Đang nghe…")
        self.hide_timer.stop()

    def stop_talk(self) -> None:
        if not self.recording:
            return
        self.recording = False
        audio = self.recorder.stop()
        self.talk_button.setText(self.talk_text)
        self.stt_job = Job(lambda: self.stt.transcribe(audio))
        self.stt_job.done.connect(self._heard)
        self.stt_job.failed.connect(lambda m: self._note("(lỗi) " + m))
        self.stt_job.start()

    def _heard(self, text: str) -> None:
        if text.strip():
            self.send_text(text)
        else:
            self._note("(không nghe rõ)")

    # --- nói / hành động -----------------------------------------------------
    def set_speaking(self, on: bool) -> None:
        self.is_speaking = on
        self._bob = False
        self.avatar.setContentsMargins(0, 0, 0, 0)
        if on:
            self.timer.start()
            self.hide_timer.stop()
        else:
            self.timer.stop()
            self._arm_hide()

    def _bob_tick(self) -> None:
        self._bob = not self._bob
        self.avatar.setContentsMargins(0, 0, 0, 6 if self._bob else 0)

    def _show_avatar(self, mood: str) -> None:
        self.current_avatar = avatar_path(self.cfg["character"], mood)
        pm = QPixmap(str(self.current_avatar))
        self.avatar.setPixmap(pm.scaledToHeight(AVATAR_H, Qt.SmoothTransformation))

    def _submit(self) -> None:
        text = self.input.text()
        self.send_text(text)
        self.input.clear()

    def send_text(self, text: str, quiet: bool = False) -> None:
        text = text.strip()
        if not text or (self.worker is not None and self.worker.isRunning()):
            return
        if self.speaker:
            self.speaker.stop()
        self.hide_timer.stop()
        self.vi_label.clear()
        self.ja_label.clear()
        self._show_bubble()
        self.input.setEnabled(False)
        self.worker = ChatWorker(self.engine, text)
        self.worker.say.connect(self.on_say)
        self.worker.failed.connect(lambda m: quiet or self._note("(lỗi) " + m))   # quiet: lượt liếc tự phát, lỗi thì im
        self.worker.finished.connect(self._unlock)
        self.worker.start()

    def _unlock(self) -> None:
        self.input.setEnabled(True)
        if not self.row.isHidden():
            self.input.setFocus()

    def greet(self, wait_ready) -> None:
        """Chào một câu khi wait_ready(stop_event) xong (chạy ở thread nền, không chặn giao diện)."""
        self.greeter = Job(lambda: wait_ready(self.closing))
        self.greeter.done.connect(lambda _: self.closing.is_set() or self.send_text(greet_prompt()))
        self.greeter.start()

    # --- nhìn màn hình ---------------------------------------------------------
    def _looking(self) -> bool:
        return self.look_job is not None and self.look_job.isRunning()

    def look(self, question: str = "", proactive: bool = False) -> None:
        """Chụp màn hình (thread giao diện) -> model ảnh local tóm tắt (thread nền) -> lượt ẩn gửi cho LLM."""
        if self._looking() or (self.worker is not None and self.worker.isRunning()):
            return
        try:
            jpeg = self.grab()
        except Exception as e:
            return None if proactive else self._note(f"(lỗi) không nhìn được màn hình: {e}")
        self.look_job = Job(lambda: self.describe(jpeg, self.cfg, question))
        self.look_job.done.connect(lambda summary: self._looked(summary, question, proactive))
        self.look_job.failed.connect(lambda m: proactive or self._note(f"(lỗi) không nhìn được màn hình: {m}"))
        self.look_job.start()

    def _looked(self, summary: str, question: str, proactive: bool) -> None:
        if not summary or self.closing.is_set():
            return
        s = " ".join(summary.splitlines())   # dòng đầu của lượt = "(Màn hình: ...)", chat.py chỉ lưu dòng đó
        if proactive:
            # mất ~30 s để nhìn: nếu trong lúc đó người dùng bắt đầu nói/gõ hoặc cô ấy đang nói thì thôi, không chen ngang
            if self.is_speaking or self.recording or self._busy() or self.input.text():
                return
            self.send_text(
                f"(Màn hình: {s})\nLần liếc trước bạn thấy: {self.last_seen or 'chưa liếc lần nào'}. "
                "Nếu họ đang làm việc khác hẳn lần trước hoặc có gì đáng hỏi han, trêu hay quan tâm thì nói ĐÚNG MỘT "
                "câu ngắn đúng tính cách; nếu vẫn như cũ hoặc không có gì đáng nói thì im lặng bằng cách chỉ xuất một "
                'dòng {"mood":"normal","ja":"","vi":""}. Không thực hiện hành động nào.', quiet=True)
            self.last_seen = s
        else:
            asked = f', họ hỏi: "{question}"' if question else ""
            self.send_text(f"(Màn hình: {s})\nNgười dùng vừa nhờ bạn nhìn màn hình{asked}. "
                           "Dựa vào đó trả lời họ 1-2 câu, đúng tính cách.")

    def _look_when_free(self, question: str) -> None:
        """Hành động look do chính worker đang chạy phát ra -> đợi nó xong rồi mới nhìn, không bỏ lượt."""
        if self.closing.is_set():
            return
        if self._looking() or (self.worker is not None and self.worker.isRunning()):
            QTimer.singleShot(100, lambda: self._look_when_free(question))
        else:
            self.look(question)

    def glance_tick(self) -> None:
        """Hẹn giờ: thỉnh thoảng liếc màn hình nếu người dùng còn ở đó và GPU không bận."""
        v = self.cfg["vision"]
        if (not self.vision_on or self.recording or self.is_speaking or self._busy() or self._looking()
                or not vision.should_glance(vision.idle_seconds(), vision.vram_used_mb(),
                                            v["interval_min"] * 60, v["max_vram_mb"])
                or vision.is_private(vision.foreground_title(), v.get("private_titles", []))):
            return
        self.look(proactive=True)

    def do_action(self, action: str, arg: str) -> None:
        if action == "look":
            self._look_when_free(arg)
            return
        if needs_confirm(action, arg) and self.cfg["actions"]["confirm"]:
            ask = QMessageBox.question(
                self, "Xác nhận", f"Remielle muốn thực hiện: {action} {arg}\nBạn có đồng ý không?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ask != QMessageBox.Yes:
                self._note("(đã huỷ)")
                return
        result = self.run_action(action, arg)
        if result.startswith("(lỗi)"):
            vi = self.vi_label.text()
            self.vi_label.setText(f"{vi}\n{result}" if vi else result)
            self._show_bubble()
            self._arm_hide()

    # shortcut: chữ hiện ngay còn tiếng tới sau vài trăm ms; đồng bộ chữ theo tiếng khi cần.
    def on_say(self, mood: str, ja: str, vi: str) -> None:
        self._show_avatar(mood)
        for label, s in ((self.vi_label, vi), (self.ja_label, ja)):
            label.setText(f"{label.text()}\n{s}" if label.text() else s)
        self._show_bubble()
        if self.speaker and ja:
            self.hide_timer.stop()   # set_speaking(False) sẽ hẹn giờ ẩn khi nói xong
            self.speaker.say(ja, mood)   # mood chọn kiểu giọng (vui, dỗi, ngại...)
        else:
            self._arm_hide()

    def closeEvent(self, event) -> None:
        self.closing.set()
        if self.speaker:
            self.speaker.stop()
            self.speaker.close()
        self.timer.stop()
        self.hide_timer.stop()
        if hasattr(self, "key_timer"):
            self.key_timer.stop()
        for t in (self.worker, self.loader, self.stt_job, self.greeter, self.look_job):
            # shortcut: chờ 3 s rồi terminate() thread còn chạy (nạp Whisper, liếc màn hình 10-30 s) vì Qt abort cả tiến trình
            # nếu huỷ QThread đang chạy -> stop_tts không chạy, server giọng giữ VRAM; terminate không dọn tài nguyên, đổi sang cờ huỷ nếu gặp lỗi
            if t is not None and t.isRunning() and not t.wait(3000):
                t.terminate()
                t.wait(1000)
        super().closeEvent(event)
        QApplication.quit()   # cửa sổ Qt.Tool đóng thì Qt không tự thoát -> tiến trình và server giọng sẽ treo lại


def main() -> None:
    # để config.yaml, characters/, models/, data/ ... đúng chỗ khi chạy từ shortcut
    os.chdir(Path(__file__).resolve().parent.parent)
    Path("data").mkdir(exist_ok=True)
    lock = QLockFile("data/remielle.lock")   # giữ sống suốt main(): chỉ một Remielle chạy một lúc
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        sys.exit(0)
    if sys.stdout is None or sys.stderr is None:   # pythonw: không có console -> ghi log thay vì nuốt lỗi
        log = Path("data/remielle.log")
        f = open(log, "w" if log.exists() and log.stat().st_size > 1_000_000 else "a", encoding="utf-8", buffering=1)
        sys.stdout, sys.stderr = sys.stdout or f, sys.stderr or f
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "Remielle khởi động", file=sys.stderr)
    try:
        from waifu.audio import Recorder
        from waifu.cli import build_engine, build_speaker
        from waifu.config import load_config
        from waifu.stt import STT

        cfg = load_config()
        app = QApplication(sys.argv)
        try:
            engine = build_engine(cfg)
        except LLMError as e:
            QMessageBox.critical(None, "Lỗi", str(e))
            sys.exit(1)
        tts_proc = start_tts(cfg)
        win = MainWindow(engine, cfg, speaker=None, recorder=Recorder(), make_stt=lambda: STT(cfg))
        win.speaker = build_speaker(cfg, on_speaking=win.speaking.emit)
        engine.on_do = win.act.emit
        win.show()
        glance = QTimer(win, interval=int(cfg["vision"]["interval_min"] * 60_000))
        glance.timeout.connect(win.glance_tick)
        glance.start()
        if cfg["ui"]["greet"]:
            host, port = _tts_addr(cfg)
            win.greet(lambda stop: wait_port(host, port, 90, stop))
        try:
            code = app.exec()
        finally:
            stop_tts(tts_proc)
        sys.exit(code)
    except Exception:
        traceback.print_exc()   # pythonw: vào data/remielle.log
        raise


if __name__ == "__main__":
    main()
