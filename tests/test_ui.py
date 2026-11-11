import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import random

import pytest
import yaml
import socket

from PySide6.QtCore import QPoint, QThread, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from waifu import ui
from waifu.reply import Say
from waifu.ui import MainWindow, avatar_path, port_open, start_tts, talk_vk


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    monkeypatch.setattr(ui, "key_down", lambda vk: False)   # test không phụ thuộc phím thật


@pytest.fixture
def cfg():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class FakeEngine:
    def send(self, text):
        yield Say("happy", "あ", "A")


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, t, mood=""):
        self.said.append(t)

    def stop(self):
        pass

    def close(self):
        pass


def test_avatar_single(tmp_path):
    d = tmp_path / "x" / "images"
    d.mkdir(parents=True)
    (d / "happy.png").touch()
    assert avatar_path("x", "happy", root=tmp_path) == d / "happy.png"


def test_avatar_random_last(tmp_path, monkeypatch):
    d = tmp_path / "x" / "images"
    d.mkdir(parents=True)
    (d / "happy.png").touch()
    (d / "happy_2.png").touch()
    monkeypatch.setattr(random, "choice", lambda seq: seq[-1])
    assert avatar_path("x", "happy", root=tmp_path) == d / "happy_2.png"


def test_avatar_fallback(tmp_path):
    assert avatar_path("x", "sad", root=tmp_path) == tmp_path / "x" / "images" / "normal.png"


def test_on_say_accumulates(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    w.on_say("shy", "あ", "A")
    w.on_say("happy", "い", "B")
    assert w.vi_label.text() == "A\nB"
    assert w.ja_label.text() == "あ\nい"
    assert w.current_avatar.name.startswith("happy")


def test_on_say_speaks(app, cfg):
    sp = FakeSpeaker()
    w = MainWindow(FakeEngine(), cfg, sp)
    w.on_say("happy", "あ", "A")
    w.on_say("happy", "", "B")
    assert sp.said == ["あ"]


def test_send_text(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    w.send_text("hi")
    w.worker.wait(2000)
    app.processEvents()
    assert w.vi_label.text() == "A"
    assert w.input.isEnabled()


class RecEngine:
    def __init__(self):
        self.got = []

    def send(self, text):
        self.got.append(text)
        yield Say("happy", "あ", "A")


class FakeRecorder:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return b""


class FakeSTT:
    def __init__(self, text):
        self.text = text

    def transcribe(self, audio):
        return self.text


def wait_for(app, cond):
    for _ in range(200):
        app.processEvents()
        if cond():
            return True
        QThread.msleep(10)
    return False


@pytest.fixture
def voice(app, cfg):
    made = []

    def make(text="xin chào", engine=None):
        rec, eng = FakeRecorder(), engine or RecEngine()
        w = MainWindow(eng, cfg, recorder=rec, make_stt=lambda: FakeSTT(text))
        made.append(w)
        return w, rec, eng

    yield make
    for w in made:
        w.close()


def test_no_recorder_hides_button(app, cfg):
    assert MainWindow(FakeEngine(), cfg).talk_button.isHidden()


def test_talk_flow(app, voice):
    w, rec, eng = voice()
    assert wait_for(app, w.talk_button.isEnabled)
    w.start_talk()
    assert rec.calls == ["start"]
    w.stop_talk()
    assert wait_for(app, lambda: eng.got)
    assert eng.got == ["xin chào"]


def test_talk_empty(app, voice):
    w, rec, eng = voice("")
    assert wait_for(app, w.talk_button.isEnabled)
    w.start_talk()
    w.stop_talk()
    assert wait_for(app, lambda: w.vi_label.text() == "(không nghe rõ)")
    assert w.vi_label.text() == "(không nghe rõ)"
    assert eng.got == []


def test_talk_before_stt_loaded(app, voice):
    w, rec, _ = voice()
    w.start_talk()
    assert rec.calls == []
    wait_for(app, w.talk_button.isEnabled)


def test_speaking_bob(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    w.set_speaking(True)
    assert w.is_speaking is True and w.timer.isActive()
    w.set_speaking(False)
    assert not w.timer.isActive() and w.avatar.contentsMargins().bottom() == 0


def test_talk_vk():
    assert talk_vk("right_ctrl") == 0xA3 and talk_vk("right_alt") == 0xA5
    assert talk_vk("f2") == 0x71 and talk_vk("F12") == 0x7B
    assert talk_vk("lạ") == 0xA3


def test_port_open():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        port = srv.getsockname()[1]
        assert port_open("127.0.0.1", port)
    assert not port_open("127.0.0.1", port)


def test_start_tts(monkeypatch, cfg):
    started = []
    monkeypatch.setattr(ui.subprocess, "Popen", lambda *a, **k: started.append(a[0]) or "proc")
    monkeypatch.setattr(ui, "port_open", lambda h, p: True)
    assert start_tts(cfg) is None and started == []
    monkeypatch.setattr(ui, "port_open", lambda h, p: False)
    assert start_tts(cfg) == "proc"
    assert started == [["cmd", "/c", "scripts\\start_tts.bat"]]


def test_overlay_flags_and_bubble(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    assert not w.windowFlags() & Qt.WindowStaysOnTopHint and w.windowFlags() & Qt.FramelessWindowHint
    assert w.bubble.isHidden() and w.row.isHidden()
    w.show()
    bottom = w.mapToGlobal(w.avatar.geometry().bottomLeft())
    w.on_say("happy", "あ", "A")
    w.show_input()
    assert w.mapToGlobal(w.avatar.geometry().bottomLeft()) == bottom   # chibi không xê dịch khi chat
    w.hide_input()
    w._hide_bubble()
    w.on_say("happy", "あ", "A")
    assert not w.bubble.isHidden()
    w._hide_bubble()
    assert w.bubble.isHidden() and w.vi_label.text() == ""


def test_fit_keeps_window_inside_screen(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    geo = app.primaryScreen().availableGeometry()
    w._anchor = geo.bottomRight() + QPoint(0, 80)   # góc neo nằm sau taskbar (bật cùng máy lúc taskbar chưa có)
    w._fit()
    assert w.geometry().bottom() <= geo.bottom() and w.geometry().right() <= geo.right()


def test_bubble_timer_follows_speaker(app, cfg):
    w = MainWindow(FakeEngine(), cfg, FakeSpeaker())
    w.on_say("happy", "あ", "A")
    assert not w.hide_timer.isActive()      # đang chờ tiếng
    w.set_speaking(True)
    w.set_speaking(False)
    assert w.hide_timer.isActive()
    w2 = MainWindow(FakeEngine(), cfg)
    w2.on_say("happy", "あ", "A")
    assert w2.hide_timer.isActive()         # không có speaker


def test_click_toggles_input_but_drag_does_not(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    w.show()
    c = w.avatar.geometry().center()
    QTest.mouseClick(w, Qt.LeftButton, pos=c)
    assert not w.row.isHidden()
    w.hide_input()
    assert w.row.isHidden()
    start = w.pos()
    QTest.mousePress(w, Qt.LeftButton, pos=c)
    QTest.mouseMove(w, c + QPoint(30, 20))
    QTest.mouseRelease(w, Qt.LeftButton, pos=c + QPoint(30, 20))
    assert w.row.isHidden() and w.pos() != start
    w.close()


def test_push_to_talk_poll(app, voice):
    w, rec, _ = voice()
    assert wait_for(app, w.talk_button.isEnabled)
    states = iter([True, True, False])
    w._key_state = lambda: next(states)
    for _ in range(3):
        w._poll_key()
    assert rec.calls == ["start", "stop"]
    assert w.talk_button.text() == "Giữ để nói (Ctrl phải)"


def test_top_key_toggles_pinned(app, cfg, monkeypatch):
    w = MainWindow(FakeEngine(), cfg)
    calls = []
    monkeypatch.setattr(ui, "set_topmost", lambda win, on: calls.append(on))
    w._key_state = lambda: False
    for down in (True, True, False, True, False):   # giữ phím không đổi liên tục; nhấn lần hai thì tắt
        monkeypatch.setattr(ui, "key_down", lambda vk, d=down: d)
        w._poll_key()
    assert calls[0] is True and calls[-1] is False and w.pinned is False


def act_window(cfg, monkeypatch, answer):
    w = MainWindow(FakeEngine(), cfg)
    ran = []
    w.run_action = lambda a, g: ran.append((a, g)) or "(lỗi) hỏng"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answer)
    return w, ran


def test_do_action_confirm_no(app, cfg, monkeypatch):
    w, ran = act_window(cfg, monkeypatch, QMessageBox.No)
    w.do_action("shutdown", "")
    assert ran == [] and w.vi_label.text() == "(đã huỷ)"


def test_do_action_confirm_yes_and_error_shown(app, cfg, monkeypatch):
    w, ran = act_window(cfg, monkeypatch, QMessageBox.Yes)
    w.do_action("run", "dir")
    assert ran == [("run", "dir")] and w.vi_label.text() == "(lỗi) hỏng"


def test_do_action_no_confirm_for_safe_or_disabled(app, cfg, monkeypatch):
    w, ran = act_window(cfg, monkeypatch, QMessageBox.No)    # có hỏi thì sẽ bị từ chối
    w.do_action("open", "notepad")
    cfg["actions"]["confirm"] = False
    w.do_action("shutdown", "")
    assert ran == [("open", "notepad"), ("shutdown", "")]


def test_do_action_confirms_open_executable(app, cfg, monkeypatch):
    w, ran = act_window(cfg, monkeypatch, QMessageBox.No)
    w.do_action("open", "C:\\x\\setup.exe")
    w.do_action("open", "chrome")
    assert ran == [("open", "chrome")]


def test_act_signal_runs_action(app, cfg, monkeypatch):
    w, ran = act_window(cfg, monkeypatch, QMessageBox.Yes)
    w.act.emit("open", "x")
    assert ran == [("open", "x")]


# --- nhìn màn hình ---------------------------------------------------------
@pytest.fixture
def seer(app, cfg):
    """MainWindow với grab/describe giả: không chụp màn hình thật, không gọi Ollama."""
    made = []

    def make(engine=None, summary="đang xem YouTube"):
        w = MainWindow(engine or RecEngine(), cfg)
        w.calls = []
        w.grab = lambda: b"jpeg"
        w.describe = lambda jpeg, c, q="", cpu=False: w.calls.append((jpeg, q)) or w.cpu.append(cpu) or summary
        w.cpu = []
        made.append(w)
        return w

    yield make
    for w in made:
        w.close()


def test_look_on_demand_sends_hidden_turn(app, seer):
    w = seer()
    w.look("cái này là gì")
    assert wait_for(app, lambda: w.engine.got)
    assert w.calls == [(b"jpeg", "cái này là gì")]
    assert w.engine.got[0].startswith("(Màn hình: đang xem YouTube)\nNgười dùng vừa nhờ")
    assert 'họ hỏi: "cái này là gì"' in w.engine.got[0]
    assert w.last_seen == ""                      # chỉ lượt tự liếc mới cập nhật
    assert wait_for(app, lambda: w.input.isEnabled() and not w.worker.isRunning())
    assert w.vi_label.text() == "A"               # câu hỏi ẩn không hiện ra bong bóng


def test_look_proactive_carries_last_seen_and_stays_silent(app, seer):
    class Mute:
        got = []

        def send(self, text):
            self.got.append(text)
            return iter(())

    w = seer(Mute())
    w.look(proactive=True)
    assert wait_for(app, lambda: Mute.got)
    assert "Lần liếc trước bạn thấy: chưa liếc lần nào" in Mute.got[0] and w.last_seen == "đang xem YouTube"
    assert wait_for(app, lambda: not w.worker.isRunning())
    app.processEvents()
    assert w.bubble.isHidden() and w.input.isEnabled()
    w.look(proactive=True)
    assert wait_for(app, lambda: len(Mute.got) == 2)
    assert "Lần liếc trước bạn thấy: đang xem YouTube" in Mute.got[1]


def test_look_failure_on_demand_shows_error_proactive_silent(app, seer):
    w = seer()

    def boom(*a, **k):
        raise RuntimeError("ollama tắt")

    w.describe = boom
    w.look(proactive=True)
    assert wait_for(app, lambda: not w._looking())
    app.processEvents()
    assert w.vi_label.text() == "" and w.engine.got == []
    w.look()
    assert wait_for(app, lambda: w.vi_label.text() != "")
    assert w.vi_label.text() == "(lỗi) không nhìn được màn hình: ollama tắt"


def test_look_empty_summary_and_busy_ignored(app, seer):
    w = seer(summary="")
    w.look()
    assert wait_for(app, lambda: w.calls and not w._looking())
    app.processEvents()
    assert w.engine.got == []
    w2 = seer()
    w2.send_text("hi")                    # worker đang chạy
    w2.look()
    assert w2.calls == []
    wait_for(app, lambda: not w2.worker.isRunning())


def test_look_action_waits_for_running_worker(app, seer):
    class LookEngine(RecEngine):
        def send(self, text):
            self.got.append(text)
            if len(self.got) == 1:
                yield Say("happy", "あ", "để tôi xem")
                QThread.msleep(150)       # worker còn chạy khi do_action(look) tới
                return
            yield Say("happy", "い", "B")

    w = seer(LookEngine())
    w.send_text("nhìn màn hình đi")
    assert wait_for(app, lambda: w.vi_label.text() == "để tôi xem")
    w.act.emit("look", "đây là gì")       # đúng đường engine.on_do -> do_action trong lúc worker còn chạy
    assert wait_for(app, lambda: len(w.engine.got) == 2)
    assert w.calls == [(b"jpeg", "đây là gì")] and w.engine.got[1].startswith("(Màn hình:")


def test_look_never_goes_to_run_action(app, seer):
    w = seer()
    ran = []
    w.run_action = lambda a, g: ran.append(a) or ""
    w.do_action("look", "")
    assert wait_for(app, lambda: w.engine.got) and ran == []


def test_glance_tick_conditions(app, seer, monkeypatch):
    w = seer()
    state = {"idle": 5, "vram": 1000}
    monkeypatch.setattr(ui.vision, "idle_seconds", lambda: state["idle"])
    monkeypatch.setattr(ui.vision, "vram_used_mb", lambda: state["vram"])
    monkeypatch.setattr(ui.vision, "foreground_title", lambda: state.get("title", "YouTube - Chrome"))
    monkeypatch.setattr(ui.vision, "foreground_fullscreen", lambda: state.get("fs", False))
    w.glance_tick()
    assert wait_for(app, lambda: len(w.calls) == 1)
    wait_for(app, lambda: not w.worker.isRunning())
    state["idle"] = 10_000                # đi vắng
    w.glance_tick()
    state["idle"], state["vram"], state["fs"] = 10_000, 9000, True   # chơi game toàn màn hình: vẫn liếc, chạy CPU
    w.glance_tick()
    assert wait_for(app, lambda: len(w.calls) == 2) and w.cpu == [False, True]
    wait_for(app, lambda: not w.worker.isRunning())
    state["idle"], state["fs"] = 5, False
    w.calls.clear()
    w.vision_on, state["vram"] = False, 1000  # đã tắt
    w.glance_tick()
    w.vision_on, state["title"] = True, "Vietcombank - Google Chrome"   # cửa sổ riêng tư
    w.glance_tick()
    state["title"], w.recording = "YouTube", True    # đang thu âm
    w.glance_tick()
    app.processEvents()
    assert w.calls == []


def test_raises_when_speaking_then_sinks(app, cfg, monkeypatch):
    w = MainWindow(FakeEngine(), cfg)
    calls = []
    monkeypatch.setattr(ui, "set_topmost", lambda win, on: calls.append(on))
    w.on_say("happy", "あ", "A")
    assert calls[-1] is True and w.hide_timer.interval() == 5000
    w._hide_bubble()
    assert calls[-1] is False
    w.on_say("happy", "あ", "A" * 200)
    assert w.hide_timer.interval() == 10000       # câu dài giữ lâu hơn, tối đa 10 s
    w.pinned = True
    w._hide_bubble()
    assert calls[-1] is True                      # đang ghim thì không lặn


def test_vision_defaults_from_config(app, cfg):
    w = MainWindow(FakeEngine(), cfg)
    assert w.vision_on is cfg["vision"]["enabled"] and w.last_seen == ""
    assert w.grab is ui.vision.grab_screen and w.describe is ui.vision.describe
