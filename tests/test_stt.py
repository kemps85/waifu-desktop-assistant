from types import SimpleNamespace

import numpy as np

from waifu import stt


def make_fake(calls, segs=()):
    class Fake:
        def __init__(self, name, **kw):
            calls["init"] = (name, kw)

        def transcribe(self, audio, **kw):
            calls["transcribe"] = kw
            return iter([SimpleNamespace(text=t) for t in segs]), None

    return Fake


def cfg(device="cuda"):
    return {"stt": {"model": "m", "device": device, "compute_type": "int8", "language": "vi"}}


def test_transcribe_joins_segments(monkeypatch):
    calls = {}
    monkeypatch.setattr(stt, "WhisperModel", make_fake(calls, [" Xin chào", " cậu "]))
    monkeypatch.setattr(stt, "_add_cuda_dll_dirs", lambda: [])
    assert stt.STT(cfg()).transcribe(np.zeros(16000, np.float32)) == "Xin chào cậu"
    assert calls["transcribe"]["language"] == "vi"


def test_hallucination_dropped(monkeypatch):
    monkeypatch.setattr(stt, "WhisperModel", make_fake({}, [" Hãy subscribe cho kênh lalaschool"]))
    assert stt.STT(cfg("cpu")).transcribe(np.zeros(16000, np.float32)) == ""


def test_subscribe_kept_in_english_mode(monkeypatch):
    monkeypatch.setattr(stt, "WhisperModel", make_fake({}, [" I subscribed to a channel"]))
    s = stt.STT(cfg("cpu"))
    s.language = "en"
    assert s.transcribe(np.zeros(16000, np.float32)) == "I subscribed to a channel"


def test_short_audio_skips_model(monkeypatch):
    calls = {}
    monkeypatch.setattr(stt, "WhisperModel", make_fake(calls, [" x"]))
    assert stt.STT(cfg("cpu")).transcribe(np.zeros(1000, np.float32)) == ""
    assert "transcribe" not in calls


def test_cpu_args(monkeypatch):
    calls = {}
    monkeypatch.setattr(stt, "WhisperModel", make_fake(calls))
    stt.STT(cfg("cpu"))
    assert calls["init"][1] == {"device": "cpu", "compute_type": "int8", "download_root": "models"}
