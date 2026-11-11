import os
import sys
from typing import Iterator, Protocol

from openai import OpenAI, OpenAIError

Message = dict   # {"role": "system" | "user" | "assistant", "content": str}


class LLMError(Exception):
    """Mọi lỗi gọi LLM (thiếu key, mạng, HTTP)."""


class LLM(Protocol):
    def generate(self, messages: list[Message]) -> Iterator[str]:
        """Yield lần lượt từng mẩu chữ (delta) của câu trả lời. Lỗi -> raise LLMError."""


class OpenAICompatLLM:
    def __init__(self, base_url: str, model: str, api_key: str,
                 extra_body: dict | None = None,
                 temperature: float = 0.8, max_tokens: int = 400):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.extra_body = extra_body or {}
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, messages: list[Message]) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self.extra_body,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content
        except OpenAIError as e:
            raise LLMError(str(e)) from e


def make_llm(cfg: dict) -> LLM:
    """cfg là dict từ waifu.config.load_config()."""
    llm_cfg = cfg["llm"]
    active = llm_cfg["active"]
    providers = llm_cfg.get("providers") or {}
    if active not in providers:
        raise LLMError(
            f"llm.active = {active!r} nhưng không có mục \"{active}\" trong llm.providers của config.yaml"
        )
    p = providers[active]
    env_name = p.get("api_key_env") or ""
    if env_name:
        api_key = os.environ.get(env_name) or ""
        if not api_key:
            raise LLMError(f"Thiếu biến môi trường {env_name}, hãy điền vào .env")
    else:
        api_key = "none"
    return OpenAICompatLLM(
        base_url=p["base_url"],
        model=p["model"],
        api_key=api_key,
        extra_body=p.get("extra_body"),
        temperature=llm_cfg.get("temperature", 0.8),
        max_tokens=llm_cfg.get("max_tokens", 400),
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from waifu.config import load_config

    try:
        llm = make_llm(load_config())
        for piece in llm.generate([{"role": "user", "content": sys.argv[1]}]):
            print(piece, end="", flush=True)
        print()
    except LLMError as e:
        print(f"(lỗi LLM) {e}")
        sys.exit(1)
