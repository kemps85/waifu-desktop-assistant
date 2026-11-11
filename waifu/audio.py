import io
import time
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # tần số thu mic


def decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """WAV PCM 16-bit -> (mảng float32 trong [-1, 1], shape (n,) nếu mono hoặc (n, kênh) nếu nhiều kênh; sample_rate)."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"chỉ hỗ trợ WAV 16-bit, nhận {8 * w.getsampwidth()}-bit")
        sr, ch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return (data if ch == 1 else data.reshape(-1, ch)), sr


def play_wav(wav_bytes: bytes) -> None:
    """Phát ra loa mặc định, CHẶN tới khi phát xong (hoặc tới khi stop_playback() được gọi từ thread khác)."""
    data, sr = decode_wav(wav_bytes)
    # wav của TTS kết thúc sát tiếng cuối (~10 ms); thiết bị nuốt mất đuôi -> đệm 0.3 s im lặng cho chữ cuối kịp ra loa
    data = np.pad(data, [(0, int(sr * 0.3))] + [(0, 0)] * (data.ndim - 1))
    sd.play(data, sr)
    sd.wait()


def stop_playback() -> None:
    """Dừng âm thanh đang phát (gọi được từ thread khác)."""
    sd.stop()


class Recorder:
    """Thu mic mặc định, 16 kHz, mono, float32."""

    def __init__(self) -> None:
        self._stream = None
        self._chunks: list[np.ndarray] = []

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=lambda indata, frames, t, status: self._chunks.append(indata.copy()),
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Dừng thu, trả mảng float32 shape (n,). Chưa start hoặc không thu được gì -> mảng rỗng shape (0,)."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).reshape(-1)


if __name__ == "__main__":
    rec = Recorder()
    rec.start()
    time.sleep(3)
    audio = rec.stop()
    print(f"số mẫu: {audio.size}, biên độ lớn nhất: {np.abs(audio).max() if audio.size else 0.0:.4f}")
    sd.play(audio, SAMPLE_RATE)
    sd.wait()
