import threading

from waifu.speaker import Speaker


def _synth(t):
    return t.encode()


def test_order():
    got = []
    s = Speaker(_synth, got.append)
    for t in "abc":
        s.say(t)
    s.wait()
    s.close()
    assert got == [b"a", b"b", b"c"]


def test_synth_error_skips_sentence():
    got = []

    def synth(t):
        if t == "b":
            raise RuntimeError("boom")
        return t.encode()

    s = Speaker(synth, got.append)
    for t in "abc":
        s.say(t)
    s.wait()
    s.close()
    assert got == [b"a", b"c"]


def test_on_speaking_once_per_burst():
    events, gate = [], threading.Event()

    def play(wav):
        gate.wait(2)  # giữ câu đầu tới khi cả 2 câu đã xếp hàng, tránh chạy đua

    s = Speaker(_synth, play, on_speaking=events.append)
    s.say("a")
    s.say("b")
    gate.set()
    s.wait()
    s.close()
    assert events == [True, False]


def test_stop_interrupts():
    got, started, release, stops = [], threading.Event(), threading.Event(), []

    def play(wav):
        got.append(wav)
        started.set()
        release.wait(2)

    s = Speaker(_synth, play, stop_play=lambda: stops.append(1))
    for t in "abc":
        s.say(t)
    assert started.wait(2)
    s.stop()
    release.set()
    s.wait()
    s.close()
    assert got == [b"a"]
    assert stops == [1]


def test_mood_reaches_synth():
    seen = []
    s = Speaker(lambda t, mood="": seen.append((t, mood)) or b"w", lambda wav: None)
    s.say("a", "pout")
    s.say("b")
    s.wait()
    s.close()
    assert seen == [("a", "pout"), ("b", "")]


def test_synth_ahead_while_playing():
    synthed_b, release = threading.Event(), threading.Event()

    def synth(t):
        if t == "b":
            synthed_b.set()
        return t.encode()

    s = Speaker(synth, lambda wav: release.wait(2))
    s.say("a")
    s.say("b")
    assert synthed_b.wait(2)  # "b" tổng hợp xong khi "a" còn đang phát
    release.set()
    s.wait()
    s.close()


def test_blank_ignored():
    got = []
    s = Speaker(_synth, got.append)
    s.say("  ")
    s.wait()
    s.close()
    assert got == []
