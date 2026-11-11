import argparse
import sys

from waifu.chat import ChatEngine
from waifu.config import load_config
from waifu.llm import LLMError, make_llm
from waifu.persona import load_persona


def build_engine(cfg: dict) -> ChatEngine:
    """Tạo ChatEngine từ cấu hình: make_llm(cfg), load_persona(cfg["character"]),
    max_history=cfg["llm"]["max_history"], top_k=cfg["memory"]["top_k"];
    memory là MemoryStore khi cfg["memory"]["enabled"], ngược lại None."""
    m = cfg["memory"]
    if m["enabled"]:
        from waifu.memory import MemoryStore, make_embedder

        memory = MemoryStore(m["db_path"], make_embedder(m["embed_base_url"], m["embed_model"]), m["dedupe_threshold"])
    else:
        memory = None
    return ChatEngine(
        make_llm(cfg),
        load_persona(cfg["character"]),
        memory=memory,
        max_history=cfg["llm"]["max_history"],
        top_k=m["top_k"],
    )


def build_speaker(cfg: dict, on_speaking=None):
    """Speaker(lambda t: synthesize(t, cfg), play_wav, stop_playback, on_speaking)."""
    from waifu.audio import play_wav, stop_playback
    from waifu.speaker import Speaker
    from waifu.tts import synthesize

    return Speaker(lambda t, mood="": synthesize(t, cfg, mood), play_wav, stop_playback, on_speaking)


def make_listen(recorder, stt, read=input, write=print):
    """Trả về hàm listen() -> str: ghi âm tới khi Enter, STT, in và trả chữ."""

    def listen() -> str:
        write("(đang nghe… Enter để gửi)")
        recorder.start()
        read("")
        audio = recorder.stop()
        text = stt.transcribe(audio)
        write(f"Bạn (mic): {text}")
        return text

    return listen


def run_loop(engine, read=input, write=print, speaker=None, listen=None) -> None:
    try:
        while True:
            try:
                text = read("Bạn: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == "/thoat":
                break
            if not text and listen is not None:
                if speaker:
                    speaker.stop()
                text = listen().strip()
                if not text:
                    write("(không nghe rõ)")
                    continue
            if not text:
                continue
            if speaker:
                speaker.stop()
            try:
                for say in engine.send(text):
                    write(f"[{say.mood}] {say.vi}")
                    if say.ja:
                        write(f"    {say.ja}")
                        if speaker:
                            speaker.say(say.ja)
            except LLMError as e:
                write(f"(lỗi LLM) {e}")
    finally:
        if speaker:
            speaker.wait()
            speaker.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trò chuyện với Remielle bằng chữ.")
    parser.add_argument("--config", default="config.yaml", help="đường dẫn file cấu hình")
    parser.add_argument("--voice", action="store_true", help="đọc câu trả lời bằng giọng")
    parser.add_argument("--mic", action="store_true", help="nghe bằng mic (kéo theo --voice)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config(args.config)
    try:
        engine = build_engine(cfg)
    except LLMError as e:
        print(f"(lỗi LLM) {e}")
        sys.exit(1)
    speaker = listen = None
    if args.voice or args.mic:
        speaker = build_speaker(cfg)
    if args.mic:
        print("Đang nạp model nghe…")
        from waifu.audio import Recorder
        from waifu.stt import STT

        listen = make_listen(Recorder(), STT(cfg))
        print("Nhấn Enter (để trống) để nói, Enter lần nữa để gửi. "
              "Gõ chữ rồi Enter để gửi chữ. /thoat để thoát.")
    run_loop(engine, speaker=speaker, listen=listen)


if __name__ == "__main__":
    main()
