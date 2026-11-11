import httpx2 as httpx
import pytest

from waifu.tts import TTSError, synthesize

CFG = {"tts": {"base_url": "http://127.0.0.1:5000", "model_name": "remielle",
               "style": "Neutral", "timeout_s": 30}}


class FakeResp:
    def __init__(self, status_code, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


def test_returns_wav_bytes_and_sends_expected_request(monkeypatch):
    seen = {}

    def fake_post(url, **kw):
        seen.update(url=url, **kw)
        return FakeResp(200, content=b"RIFFxxxx")

    monkeypatch.setattr("waifu.tts.httpx.post", fake_post)
    assert synthesize("こんにちは", CFG) == b"RIFFxxxx"
    assert seen["url"] == "http://127.0.0.1:5000/voice"
    assert seen["params"] == {"text": "こんにちは。", "model_name": "remielle",   # tự thêm dấu kết câu
                              "language": "JP", "style": "Neutral"}
    synthesize("本当？", {"tts": {**CFG["tts"], "sdp_ratio": 0.5}})
    assert seen["params"]["text"] == "本当？" and seen["params"]["sdp_ratio"] == 0.5
    styled = {"tts": {**CFG["tts"], "styles": {"pout": "Pout"}, "style_weight": 3}}
    synthesize("もう", styled, "pout")
    assert seen["params"]["style"] == "Pout" and seen["params"]["style_weight"] == 3
    synthesize("もう", styled, "normal")   # mood không có trong bảng -> kiểu mặc định
    assert seen["params"]["style"] == "Neutral"
    assert seen["timeout"] == 30


def test_missing_style_falls_back_to_default(monkeypatch):
    styles = []

    def fake_post(url, **kw):
        styles.append(kw["params"]["style"])
        return FakeResp(422 if kw["params"]["style"] == "Pout" else 200, content=b"RIFF", text="no style")

    monkeypatch.setattr("waifu.tts.httpx.post", fake_post)
    cfg = {"tts": {**CFG["tts"], "styles": {"pout": "Pout"}}}
    assert synthesize("もう", cfg, "pout") == b"RIFF" and styles == ["Pout", "Neutral"]
    monkeypatch.setattr("waifu.tts.httpx.post", lambda url, **kw: styles.append(1) or FakeResp(422, text="bad"))
    styles.clear()
    with pytest.raises(TTSError):    # kiểu mặc định cũng lỗi thì không thử lại mãi
        synthesize("もう", CFG)
    assert styles == [1]


def test_non_200_raises_tts_error(monkeypatch):
    monkeypatch.setattr("waifu.tts.httpx.post", lambda url, **kw: FakeResp(422, text="bad"))
    with pytest.raises(TTSError, match="422.*bad"):
        synthesize("こんにちは", CFG)


def test_connect_error_raises_tts_error(monkeypatch):
    def fake_post(url, **kw):
        raise httpx.ConnectError("x")

    monkeypatch.setattr("waifu.tts.httpx.post", fake_post)
    with pytest.raises(TTSError, match="start_tts"):
        synthesize("こんにちは", CFG)


def test_blank_text_raises_value_error(monkeypatch):
    monkeypatch.setattr("waifu.tts.httpx.post", lambda url, **kw: pytest.fail("không được gọi mạng"))
    with pytest.raises(ValueError):
        synthesize("  ", CFG)
