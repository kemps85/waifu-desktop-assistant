import queue
import sys
import threading
from typing import Callable


class Speaker:
    """Hai thread: một tổng hợp trước, một phát — câu sau sẵn sàng khi câu trước còn đang phát."""

    def __init__(self,
                 synth: Callable[[str], bytes],          # câu tiếng Nhật -> bytes WAV (có thể raise)
                 play: Callable[[bytes], None],          # phát WAV, chặn tới khi xong
                 stop_play: Callable[[], None] | None = None,       # dừng âm đang phát
                 on_speaking: Callable[[bool], None] | None = None  # True khi bắt đầu nói, False khi hết hàng đợi
                 ):
        self._synth, self._play, self._stop_play, self._on_speaking = synth, play, stop_play, on_speaking
        self._q: queue.Queue = queue.Queue()     # câu chờ tổng hợp
        self._pq: queue.Queue = queue.Queue()    # (đời, wav) chờ phát
        self._gen = 0  # tăng mỗi lần stop(); kết quả tổng hợp của đời cũ bị bỏ
        self._lock = threading.Lock()
        self._pending = 0       # số câu đã say() mà chưa phát xong / chưa bị bỏ
        self._speaking = False
        self._threads = [threading.Thread(target=f, daemon=True) for f in (self._synth_loop, self._play_loop)]
        for t in self._threads:
            t.start()

    def say(self, text_ja: str, mood: str = "") -> None:
        """Xếp câu vào hàng đợi, trả về ngay. Chuỗi rỗng (sau strip) thì bỏ qua. mood (nếu có) được đưa cho synth."""
        if text_ja.strip():
            with self._lock:
                self._pending += 1
            self._q.put((text_ja, mood))

    def wait(self) -> None:
        """Chặn tới khi mọi câu đã xếp được phát xong."""
        self._q.join()
        self._pq.join()

    def stop(self) -> None:
        """Ngắt lời: xoá các câu đang chờ và dừng câu đang phát."""
        self._gen += 1
        for q in (self._q, self._pq):
            try:
                while True:
                    q.get_nowait()
                    q.task_done()
                    self._finish_one()
            except queue.Empty:
                pass
        if self._stop_play:
            self._stop_play()

    def close(self) -> None:
        """Kết thúc 2 thread nền."""
        self._q.put(None)
        for t in self._threads:
            t.join(timeout=2)

    def _finish_one(self) -> None:
        with self._lock:
            self._pending -= 1
            ended = self._pending == 0 and self._speaking
            if ended:
                self._speaking = False
        if ended and self._on_speaking:
            self._on_speaking(False)

    def _synth_loop(self) -> None:
        while True:
            text = self._q.get()
            try:
                if text is None:
                    self._pq.put(None)
                    return
                with self._lock:
                    started = not self._speaking
                    self._speaking = True
                if started and self._on_speaking:
                    self._on_speaking(True)
                gen, wav = self._gen, None
                try:
                    wav = self._synth(*text) if text[1] else self._synth(text[0])
                except Exception as e:
                    print(f"(lỗi TTS) {e}", file=sys.stderr)
                self._pq.put((gen, wav))
            finally:
                self._q.task_done()

    def _play_loop(self) -> None:
        while True:
            item = self._pq.get()
            try:
                if item is None:
                    return
                gen, wav = item
                if wav is not None and gen == self._gen:
                    try:
                        self._play(wav)
                    except Exception as e:
                        print(f"(lỗi TTS) {e}", file=sys.stderr)
                self._finish_one()
            finally:
                self._pq.task_done()
