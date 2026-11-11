"""STT tiếng Việt bằng faster-whisper (local)."""
import importlib.util
import os
import sys
import sysconfig
import time

import numpy as np

WhisperModel = None  # nạp lười trong STT.__init__ (sau khi thêm DLL CUDA)


def _add_cuda_dll_dirs() -> list[str]:
    spec = importlib.util.find_spec("nvidia")
    roots = list(spec.submodule_search_locations or []) if spec else []
    roots.append(os.path.join(sysconfig.get_paths()["purelib"], "nvidia"))
    added: list[str] = []
    for root in roots:
        for pkg in ("cublas", "cudnn"):
            path = os.path.join(root, pkg, "bin")
            if path not in added and os.path.isdir(path):
                os.add_dll_directory(path)
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                added.append(path)
    return added


class STT:
    def __init__(self, cfg: dict):
        """Nạp model theo cfg["stt"] (lần đầu sẽ tự tải ~1,6 GB về cache Hugging Face trên ổ C:)."""
        global WhisperModel
        c = cfg["stt"]
        if c["device"] == "cuda":
            _add_cuda_dll_dirs()
        if WhisperModel is None:
            from faster_whisper import WhisperModel
        self.language = self._cfg_language = c["language"]   # .language đổi được lúc chạy (vd "en")
        self._prompt = c.get("prompt") or None      # gợi ý từ vựng (tên riêng, tên app) cho Whisper
        self._save_last = c.get("save_last")        # đường dẫn wav lưu bản thu gần nhất để chẩn đoán
        self._model = WhisperModel(c["model"], device=c["device"], compute_type=c["compute_type"],
                                   download_root="models")  # ~/.cache không ghi được trên máy này

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32, 16 kHz, mono, shape (n,). Trả chữ đã strip; rỗng nếu không có tiếng nói."""
        if len(audio) < 4800:
            return ""
        if self._save_last:
            import wave
            with wave.open(self._save_last, "wb") as w:   # bản gốc, trước khi chuẩn hoá
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        peak = float(np.abs(audio).max())
        if peak > 0.005:    # mic nhỏ tiếng làm Whisper nghe sai; dưới ngưỡng này coi như im lặng, không khuếch đại nhiễu
            audio = audio * (0.9 / peak)
        segments, _ = self._model.transcribe(
            audio, language=self.language, beam_size=5, vad_filter=True, condition_on_previous_text=False,
            # gợi ý viết bằng ngôn ngữ trong config; dùng cho ngôn ngữ khác sẽ kéo Whisper nghe lệch
            initial_prompt=self._prompt if self.language == self._cfg_language else None)
        text = "".join(seg.text for seg in segments).strip()
        # Whisper hay bịa câu kết video YouTube khi nghe không ra (vd "Hãy subscribe cho kênh La La School…")
        low = text.lower()
        keys = ("lalaschool", "la la school", "ghiền mì gõ") + (("subscribe",) if self.language == self._cfg_language else ())
        return "" if any(k in low for k in keys) else text   # "subscribe" là tiếng Anh thật khi đang ở chế độ English


if __name__ == "__main__":
    import argparse

    import yaml

    from waifu.audio import Recorder

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", type=float, default=4)
    secs = ap.parse_args().mic
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    t0 = time.perf_counter()
    stt = STT(cfg)
    print(f"Nạp model: {time.perf_counter() - t0:.2f}s")
    rec = Recorder()
    print(f"Nói đi ({secs}s)...")
    rec.start()
    time.sleep(secs)
    audio = rec.stop()
    t0 = time.perf_counter()
    text = stt.transcribe(audio)
    print(f"Nhận dạng: {time.perf_counter() - t0:.2f}s")
    print(f"Câu: {text}")
