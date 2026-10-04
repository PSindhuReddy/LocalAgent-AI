import json, pathlib
from events import bus

LOG = pathlib.Path("audit_log.jsonl")

def _write(ev):
    if ev["agent"] == "System" and ev["status"] in ("result", "token"):
        return
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")

bus.subscribe(_write)

def tail(n=60):
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()[-n:]]