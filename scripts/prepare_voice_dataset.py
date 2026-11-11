"""Chuyển mp3 giọng Remielle + kịch bản tiếng Nhật thành bộ dữ liệu train Style-Bert-VITS2.

Đầu ra: <out>\\raw\\<source_id>.wav và <out>\\esd.list.
Chỉ đọc thư mục nguồn, không sửa gì ở đó.
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_CSV = Path("voice_source/VOICE_FILE_MAPPING.csv")   # cột: tên file mp3 <-> số thứ tự câu
DEFAULT_SCRIPTS = Path("voice_source/scripts")              # các file .md chứa kịch bản tiếng Nhật

_HEADING = re.compile(r"^##\s+(\d{3})\.", re.MULTILINE)
_TEXT_BLOCK = re.compile(r"```text[ \t]*\r?\n(.*?)```", re.DOTALL)
_TAG = re.compile(r"\[[^\]]*\]")
_SPACES = re.compile(r"\s+")


def parse_script(md_text: str) -> dict[str, str]:
    """Trả về {"001": "câu tiếng Nhật", ...} từ nội dung một file kịch bản.
    Xoá mọi thẻ dạng [ ... ] (ví dụ "[playful, sweet tone]"), gộp khoảng trắng liền nhau thành một dấu cách, strip."""
    result: dict[str, str] = {}
    heads = list(_HEADING.finditer(md_text))
    for i, head in enumerate(heads):
        start = head.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md_text)
        block = _TEXT_BLOCK.search(md_text, start, end)
        if not block:
            continue
        text = _SPACES.sub(" ", _TAG.sub(" ", block.group(1))).strip()
        if text:
            result[head.group(1)] = text
    return result


def _convert(mp3: Path, wav: Path) -> str | None:
    """Chạy ffmpeg. Trả None nếu ổn, ngược lại trả thông báo lỗi."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
           "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return "không tìm thấy ffmpeg trong PATH"
    if res.returncode != 0:
        msg = (res.stderr or "").strip()
        return msg or f"ffmpeg trả mã {res.returncode}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chuẩn bị dữ liệu train giọng từ mp3 + kịch bản.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--scripts-dir", type=Path, default=DEFAULT_SCRIPTS)
    parser.add_argument("--character", default="Remielle")
    parser.add_argument("--model-name", default="remielle")
    parser.add_argument("--out", default=r"data\voice\remielle")
    args = parser.parse_args(argv)

    out = Path(args.out)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    scripts: dict[str, str] = {}
    for md in sorted(Path(args.scripts_dir).glob("kich_ban_*.md")):
        scripts.update(parse_script(md.read_text(encoding="utf-8")))

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("character") or "") == args.character]
    rows.sort(key=lambda r: (r.get("source_id") or "").strip())

    lines: list[str] = []
    skipped = False
    for row in rows:
        sid = (row.get("source_id") or "").strip()
        mp3 = args.csv.parent / (row.get("relative_path") or "")
        ja = scripts.get(sid)
        if not mp3.is_file():
            print(f"BỎ QUA {sid}: không thấy file {mp3}", file=sys.stderr)
            skipped = True
            continue
        if not ja:
            print(f"BỎ QUA {sid}: kịch bản không có câu tiếng Nhật", file=sys.stderr)
            skipped = True
            continue
        wav = raw / f"{sid}.wav"
        err = _convert(mp3, wav)
        if err is not None:
            print(f"BỎ QUA {sid}: ffmpeg lỗi: {err}", file=sys.stderr)
            skipped = True
            continue
        lines.append(f"{wav.name}|{args.model_name}|JP|{ja}")

    with open(out / "esd.list", "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(line + "\n" for line in lines))

    if skipped:
        return 1
    print(f"{len(lines)} câu -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
