from waifu.config import load_config


def test_load_config_reads_nested_yaml(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("a: {b: 1}", encoding="utf-8")
    assert load_config(p)["a"]["b"] == 1


def test_project_config_has_llm_providers():
    cfg = load_config("config.yaml")
    assert cfg["llm"]["active"] == "deepseek"
    assert set(cfg["llm"]["providers"]) == {"deepseek", "openai", "ollama"}
