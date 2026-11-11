import sqlite3

import numpy as np

from waifu.memory import MemoryStore

KEYS = ["phở", "mèo", "game", "nhạc", "ngủ", "làm", "mưa", "trà"]


def fake_embed(texts):
    v = np.array([[1.0 if k in t.lower() else 0.0 for k in KEYS] for t in texts], dtype=np.float32) + 0.01
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def make(tmp_path, fn=fake_embed):
    return MemoryStore(tmp_path / "m.db", fn)


def test_search_best_match(tmp_path):
    s = make(tmp_path)
    s.remember("Người dùng thích ăn phở")
    s.remember("Người dùng nuôi một con mèo")
    assert s.search("tối nay ăn phở không", top_k=1) == ["Người dùng thích ăn phở"]


def test_dedupe(tmp_path):
    s = make(tmp_path)
    assert s.remember("Người dùng thích ăn phở") is True
    assert s.remember("Người dùng thích ăn phở") is False
    n = sqlite3.connect(tmp_path / "m.db").execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert n == 1


def test_search_empty_no_embed_call(tmp_path):
    calls = []

    def counting(texts):
        calls.append(texts)
        return fake_embed(texts)

    assert make(tmp_path, counting).search("gì đó") == []
    assert calls == []


def test_recent_messages_order(tmp_path):
    s = make(tmp_path)
    for i in range(5):
        s.add_message("user" if i % 2 == 0 else "assistant", f"m{i}")
    assert s.recent_messages(3) == [
        {"role": "user", "content": "m2"},
        {"role": "assistant", "content": "m3"},
        {"role": "user", "content": "m4"},
    ]


def test_persistence(tmp_path):
    s = make(tmp_path)
    s.add_message("user", "chào")
    s.remember("Người dùng thích nghe nhạc")
    s.close()
    s2 = make(tmp_path)
    assert s2.recent_messages() == [{"role": "user", "content": "chào"}]
    assert s2.search("nhạc") == ["Người dùng thích nghe nhạc"]


def test_remember_blank(tmp_path):
    assert make(tmp_path).remember("   ") is False


def test_top_k_larger_than_count(tmp_path):
    s = make(tmp_path)
    s.remember("thích phở")
    s.remember("nuôi mèo")
    assert sorted(s.search("phở", top_k=10)) == ["nuôi mèo", "thích phở"]
