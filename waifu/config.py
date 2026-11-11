from pathlib import Path

import yaml
from dotenv import load_dotenv


def load_config(path: str | Path = "config.yaml") -> dict:
    """Gọi dotenv.load_dotenv() (nạp .env vào os.environ nếu có), rồi trả về nội dung YAML dạng dict thuần.
    File không tồn tại -> để FileNotFoundError tự nổi lên."""
    load_dotenv()
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
