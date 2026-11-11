import subprocess
import webbrowser

from waifu import actions


class Rec:
    """Ghi lại mọi lệnh thay vì chạy thật."""

    def __init__(self, monkeypatch, tasklist="", apps="[]"):
        self.popen, self.run, self.start, self.web, self.keys = [], [], [], [], []
        self.tasklist, self.apps = tasklist, apps
        monkeypatch.setattr(actions, "_apps", None)
        monkeypatch.setattr(subprocess, "Popen", lambda cmd, **k: self.popen.append(cmd))
        monkeypatch.setattr(subprocess, "run", self._run)
        monkeypatch.setattr(actions.os, "startfile", self.start.append, raising=False)
        monkeypatch.setattr(webbrowser, "open", self.web.append)
        u = type("U", (), {"keybd_event": lambda s, *a: self.keys.append((a[0], a[2])),
                           "LockWorkStation": lambda s: self.keys.append("lock")})()
        monkeypatch.setattr(actions, "_user32", lambda: u)

    def _run(self, cmd, **k):
        self.run.append(cmd)
        out = self.apps if cmd[0] == "powershell" else self.tasklist
        return subprocess.CompletedProcess(cmd, 0, stdout=out)


def test_unknown_and_never_raises(monkeypatch):
    Rec(monkeypatch)
    assert actions.run_action("hack", "") == "(lỗi) không biết hành động: hack"
    monkeypatch.setattr(webbrowser, "open", lambda u: 1 / 0)
    assert actions.run_action("search", "x").startswith("(lỗi)")


def test_open_url_path_and_app(monkeypatch, tmp_path):
    apps = ('[{"Name":"Google Chrome Beta","AppID":"B"},{"Name":"Google Chrome","AppID":"A"},'
            '{"Name":"Zalo","AppID":"Z"}]')
    r = Rec(monkeypatch, apps=apps)
    actions.run_action("open", "https://a.com")
    assert r.web == ["https://a.com"]
    actions.run_action("open", str(tmp_path))
    assert r.start == [str(tmp_path)]
    actions.run_action("open", "chrome")     # chứa -> tên ngắn nhất
    assert r.start[-1] == "shell:AppsFolder\\A"
    actions.run_action("open", "google chrome beta")
    assert r.start[-1].endswith("\\B")
    actions.run_action("open", "notepad_zz")  # không có app -> startfile
    assert r.start[-1] == "notepad_zz"


def test_open_single_app_json_object(monkeypatch):
    r = Rec(monkeypatch, apps='{"Name":"Zalo","AppID":"Z"}')
    actions.run_action("open", "zalo")
    assert r.start == ["shell:AppsFolder\\Z"]


def test_close_graceful_and_protected(monkeypatch):
    tl = ('"chrome.exe","1","Console","1","10 K"\n"chrome.exe","2","Console","1","10 K"\n'
          '"pythonw.exe","3","c","1","1 K"\n"explorer.exe","4","c","1","1 K"\n')
    r = Rec(monkeypatch, tasklist=tl)
    assert actions.run_action("close", "chrome").startswith("Đã")
    assert r.run[1:] == [["taskkill", "/IM", "chrome.exe"]]      # một lần, không /F
    for bad in ("ch", "", "python", "explorer"):
        assert actions.run_action("close", bad).startswith("(lỗi)")
    assert all("/F" not in c for c in r.run)


def test_search_media_lock_power_run(monkeypatch):
    r = Rec(monkeypatch)
    actions.run_action("search", "mèo con")
    assert r.web == ["https://www.google.com/search?q=m%C3%A8o+con"]
    actions.run_action("volume_up", "")
    assert len(r.keys) == 10 and r.keys[0] == (0xAF, 0) and r.keys[1] == (0xAF, 2)
    r.keys.clear()
    actions.run_action("play_pause", "")
    assert len(r.keys) == 2
    actions.run_action("lock", "")
    assert r.keys[-1] == "lock"
    actions.run_action("shutdown", "")
    actions.run_action("restart", "")
    actions.run_action("run", "Get-Date")
    assert r.popen == [["shutdown", "/s", "/t", "30"], ["shutdown", "/r", "/t", "30"],
                       ["powershell", "-NoProfile", "-Command", "Get-Date"]]


def test_needs_confirm():
    nc = actions.needs_confirm
    assert nc("run", "") and nc("shutdown", "") and nc("restart", "")
    for a in ("C:\\x\\Setup.EXE", '"C:\\a b\\run.bat"', "x.ps1", "a.lnk", "t.py'"):
        assert nc("open", a), a
    for a in ("notepad", "chrome", "https://example.com/a.exe", "C:\\docs\\a.pdf", ""):
        assert not nc("open", a), a
    assert not nc("search", "x.exe") and not nc("close", "x.exe")


def test_sleep_and_confirm_set(monkeypatch):
    r = Rec(monkeypatch)
    actions.run_action("sleep", "")
    assert r.popen == [["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]]
    assert actions.NEEDS_CONFIRM == {"run", "shutdown", "restart"}
