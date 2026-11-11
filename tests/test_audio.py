import io
import wave

import numpy as np
import pytest

from waifu import audio


def make_wav(sr=22050, ch=1, width=2, secs=0.1) -> bytes:
    n = int(sr * secs)
    t = np.arange(n) / sr
    sig = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype("<i2") if width == 2 else np.full(n, 128, np.uint8)
    if ch > 1:
        sig = np.repeat(sig[:, None], ch, axis=1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(width)
        w.setframerate(sr)
        w.writeframes(sig.tobytes())
    return buf.getvalue()


def test_decode_mono():
    data, sr = audio.decode_wav(make_wav())
    assert sr == 22050 and data.dtype == np.float32 and data.shape == (2205,)
    assert data.min() >= -1 and data.max() <= 1


def test_decode_stereo():
    data, _ = audio.decode_wav(make_wav(ch=2))
    assert data.shape == (2205, 2)


def test_decode_8bit_raises():
    with pytest.raises(ValueError):
        audio.decode_wav(make_wav(width=1))


def test_play_wav(monkeypatch):
    calls = {"play": [], "wait": 0}
    monkeypatch.setattr(audio.sd, "play", lambda data, sr: calls["play"].append((sr, data)))
    monkeypatch.setattr(audio.sd, "wait", lambda: calls.__setitem__("wait", calls["wait"] + 1))
    audio.play_wav(make_wav())
    (sr, data), = calls["play"]
    assert sr == 22050 and calls["wait"] == 1
    n = len(audio.decode_wav(make_wav())[0])
    assert len(data) == n + int(22050 * 0.3) and not data[n:].any()   # đuôi im lặng để không cụt chữ cuối


def test_recorder_stop_without_start():
    out = audio.Recorder().stop()
    assert out.shape == (0,)
