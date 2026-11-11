"""Tạo các kiểu giọng theo cảm xúc cho model remielle mà KHÔNG cần train lại.

Model đã học vector phong cách riêng của từng câu mẫu (wavs/NNN.wav.npy). Gom các câu cùng cảm xúc,
lấy trung bình -> một kiểu giọng. Ghi style_vectors.npy + config.json (bản cũ lưu thành *.bak).
Chạy: .venv\\Scripts\\python scripts\\make_voice_styles.py   rồi mở lại Remielle.
"""
import json
import shutil
from pathlib import Path

import numpy as np

SBV2 = Path(__file__).resolve().parent.parent / "vendor" / "Style-Bert-VITS2"
WAVS = SBV2 / "Data" / "remielle" / "wavs"
MODEL = SBV2 / "model_assets" / "remielle"

# số thứ tự câu trong esd.list, xếp theo cảm xúc của lời thoại; muốn chỉnh kiểu nào thì sửa danh sách đó
STYLES = {
    "Happy": [1, 3, 6, 8, 11, 13, 16, 24, 28, 36, 53, 57, 63, 68, 77, 82, 83, 87, 89, 94, 100, 109, 117, 123, 132,
              141, 146, 147, 148, 150, 153],
    "Shy": [41, 49, 61, 64, 78, 79, 80, 115, 121, 122, 125, 127, 128, 130, 131, 133, 135, 139, 151],
    "Pout": [5, 19, 37, 66, 71, 81, 88, 98, 112, 118, 134, 140],
    "Worried": [18, 33, 34, 38, 42, 43, 56, 144],
    "Sad": [12, 75, 86, 99, 104, 107, 110, 129, 143, 154],
    "Determined": [22, 31, 58, 59, 95, 119, 120, 124, 136, 145],
}


def vec(n: int) -> np.ndarray:
    return np.load(WAVS / f"{n:03d}.wav.npy")


def main() -> None:
    mean = np.mean([np.load(p) for p in sorted(WAVS.glob("*.npy"))], axis=0)   # Neutral = trung bình mọi câu
    rows = [mean] + [np.mean([vec(n) for n in ids], axis=0) for ids in STYLES.values()]
    names = ["Neutral", *STYLES]
    for f in ("style_vectors.npy", "config.json"):
        if not (MODEL / (f + ".bak")).exists():
            shutil.copy(MODEL / f, MODEL / (f + ".bak"))
    np.save(MODEL / "style_vectors.npy", np.stack(rows).astype(np.float32))
    cfg_path = MODEL / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["data"]["num_styles"] = len(names)
    cfg["data"]["style2id"] = {n: i for i, n in enumerate(names)}
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    for n, r in zip(names, rows):
        print(f"{n:11s} cách Neutral {np.linalg.norm(r - mean):.2f}")


if __name__ == "__main__":
    main()
