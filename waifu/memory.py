import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

Message = dict   # {"role": "user" | "assistant", "content": str}
EmbedFn = Callable[[list[str]], np.ndarray]   # n câu -> mảng float32 shape (n, d), mỗi hàng đã chuẩn hoá L2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, text TEXT NOT NULL, embedding BLOB NOT NULL);
"""


def make_embedder(base_url: str, model: str) -> EmbedFn:
    """Embedding qua API tương thích OpenAI của Ollama (POST {base_url}/embeddings)."""
    import openai

    client = openai.OpenAI(base_url=base_url, api_key="ollama")

    def embed(texts: list[str]) -> np.ndarray:
        resp = client.embeddings.create(model=model, input=texts)
        v = np.array([d.embedding for d in resp.data], dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    return embed


class MemoryStore:
    def __init__(self, db_path: str | Path, embed_fn: EmbedFn, dedupe_threshold: float = 0.9):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._embed = embed_fn
        self._threshold = dedupe_threshold
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def add_message(self, role: str, content: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO messages (ts, role, content) VALUES (?, ?, ?)", (time.time(), role, content)
            )
            self._db.commit()

    def recent_messages(self, limit: int = 20) -> list[Message]:
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def _matrix(self) -> tuple[list[str], np.ndarray]:
        with self._lock:
            rows = self._db.execute("SELECT text, embedding FROM memories ORDER BY id").fetchall()
        texts = [t for t, _ in rows]
        m = np.stack([np.frombuffer(b, dtype=np.float32) for _, b in rows]) if rows else np.empty((0, 0), np.float32)
        return texts, m

    def remember(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        v = np.asarray(self._embed([text])[0], dtype=np.float32)
        _, m = self._matrix()
        if len(m) and float((m @ v).max()) >= self._threshold:
            return False
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (ts, text, embedding) VALUES (?, ?, ?)",
                (time.time(), text, v.astype(np.float32).tobytes()),
            )
            self._db.commit()
        return True

    # shortcut: quét toàn bộ bằng numpy, đủ nhanh tới ~50k mẩu; quá mức đó thì chuyển sang sqlite-vec.
    def search(self, query: str, top_k: int = 5) -> list[str]:
        texts, m = self._matrix()
        if not texts:
            return []
        q = np.asarray(self._embed([query])[0], dtype=np.float32)
        order = np.argsort(-(m @ q), kind="stable")[:top_k]
        return [texts[i] for i in order]

    def close(self) -> None:
        with self._lock:
            self._db.close()


if __name__ == "__main__":
    from waifu.config import load_config

    mem = load_config()["memory"]
    store = MemoryStore(mem["db_path"], make_embedder(mem["embed_base_url"], mem["embed_model"]), mem["dedupe_threshold"])
    print(store.search(sys.argv[1], mem["top_k"]))
    store.close()
