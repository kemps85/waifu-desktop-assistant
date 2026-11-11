import sys
from pathlib import Path

import httpx2 as httpx  # .venv không có httpx; openai 3.49 kéo httpx2 (bản kế tiếp)


class TTSError(Exception):
    """Lỗi gọi server TTS (không kết nối được, HTTP khác 200)."""


def synthesize(text_ja: str, cfg: dict, mood: str = "") -> bytes:
    """Trả về bytes WAV của câu text_ja. cfg là dict từ load_config(). mood chọn kiểu giọng theo tts.styles."""
    if not text_ja.strip():
        raise ValueError("Câu cần đọc đang rỗng")
    text_ja = text_ja.strip()
    if text_ja[-1] not in "。！？!?…♪":
        text_ja += "。"   # thiếu dấu kết câu thì model đọc cụt và phẳng ở chữ cuối
    params = {"text": text_ja, "model_name": cfg["tts"]["model_name"], "language": "JP",
              "style": cfg["tts"].get("styles", {}).get(mood, cfg["tts"]["style"])}
    for k in ("sdp_ratio", "style_weight"):
        if k in cfg["tts"]:
            params[k] = cfg["tts"][k]
    while True:
        try:
            r = httpx.post(
                f"{cfg['tts']['base_url']}/voice",
                params=params,
                timeout=cfg["tts"]["timeout_s"],
            )
        except httpx.HTTPError as e:
            raise TTSError("Không kết nối được server TTS, hãy chạy scripts\\start_tts.bat") from e
        if r.status_code == 200 or params["style"] == cfg["tts"]["style"]:
            break
        params["style"] = cfg["tts"]["style"]   # server chưa có style này -> đọc bằng giọng mặc định còn hơn câm
    if r.status_code != 200:
        raise TTSError(f"Server TTS trả HTTP {r.status_code}: {r.text[:200]}")
    return r.content


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from waifu.config import load_config

    try:
        wav = synthesize(sys.argv[1], load_config())
    except (TTSError, ValueError) as e:
        print(f"(lỗi TTS) {e}")
        sys.exit(1)
    Path(sys.argv[2]).write_bytes(wav)
