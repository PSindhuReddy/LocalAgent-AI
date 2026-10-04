import json, pathlib

CONFIG_PATH = pathlib.Path("permissions.json")
DEFAULTS = {
    "llm_model": "llama3.2",
    "ollama_url": "http://localhost:11434",
    "allowed_sources": ["local"],       # local | gmail | drive | web
    "allowed_dirs": ["~/Documents"],
    "max_file_mb": 10,
    "top_k": 5,
}

def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2))
    return cfg

def source_allowed(cfg, source): return source in cfg["allowed_sources"]