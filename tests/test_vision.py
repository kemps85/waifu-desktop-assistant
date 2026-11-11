import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import io
import json
import subprocess

import pytest
from PySide6.QtGui import QGuiApplication

from waifu import vision

CFG = {"vision": {"base_url": "http://x:1/", "model": "m", "timeout_s": 7}}


def test_should_glance():
    assert vision.should_glance(10, 360, False)
    assert not vision.should_glance(361, 360, False)   # đi vắng
    assert vision.should_glance(10_000, 360, True)     # xem phim toàn màn hình, không chạm chuột vẫn liếc


def test_describe_cpu_option(monkeypatch):
    sent = []
    monkeypatch.setattr(vision.urllib.request, "urlopen", lambda req, timeout: sent.append(json.loads(req.data))
                        or io.BytesIO(b'{"message": {"content": "x"}}'))
    vision.describe(b"x", CFG, cpu=True)
    vision.describe(b"x", CFG)
    assert sent[0]["options"]["num_gpu"] == 0 and "num_gpu" not in sent[1]["options"]


def test_is_private():
    words = ["bank", "ví", "zalo"]
    assert vision.is_private("My BANK - Chrome", words) and vision.is_private("Zalo", words)
    assert not vision.is_private("YouTube - Chrome", words) and not vision.is_private("", words)
    assert not vision.is_private("Bất kỳ", [])


def test_describe_request_shape(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, body=json.loads(req.data), timeout=timeout)
        return io.BytesIO(json.dumps({"message": {"content": "  Đang gõ code \n"}}).encode())

    monkeypatch.setattr(vision.urllib.request, "urlopen", fake_urlopen)
    assert vision.describe(b"\xff\xd8", CFG) == "Đang gõ code"
    b = seen["body"]
    assert seen["url"] == "http://x:1/api/chat" and seen["timeout"] == 7
    assert (b["model"], b["stream"], b["keep_alive"], b["think"]) == ("m", False, 0, False)
    assert b["options"] == {"num_ctx": 4096, "temperature": 0.2}
    msg = b["messages"][0]
    assert msg["role"] == "user" and msg["images"] == ["/9g="] and "mô tả họ đang làm gì" in msg["content"]
    vision.describe(b"x", CFG, "đây là gì")
    q = seen["body"]["messages"][0]["content"]
    assert q.startswith("Đây là ảnh chụp màn hình") and "câu hỏi sau dựa trên ảnh: đây là gì." in q


def test_vram_used_mb(monkeypatch):
    run = lambda out, rc=0: (lambda *a, **k: subprocess.CompletedProcess(a, rc, out, ""))
    monkeypatch.setattr(vision.subprocess, "run", run("3456\n"))
    assert vision.vram_used_mb() == 3456
    monkeypatch.setattr(vision.subprocess, "run", run("", 9))
    assert vision.vram_used_mb() is None

    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(vision.subprocess, "run", boom)
    assert vision.vram_used_mb() is None


def test_idle_seconds():
    assert 0 <= vision.idle_seconds() < 10 ** 7


def test_grab_screen_is_jpeg_offscreen():
    app = QGuiApplication.instance() or QGuiApplication([])
    assert app.platformName() == "offscreen"   # không bao giờ chụp màn hình thật trong test
    assert vision.grab_screen(64)[:2] == b"\xff\xd8"
