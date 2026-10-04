import json, re, time
from events import bus
from utils import keywords, expand_terms
from agents.planner import HINTS

DATA = json.load(open("sample_data.json", encoding="utf-8"))
for it in DATA:
    it["text"], it["demo"] = it["full"], True

ORDER = ["local", "gmail", "drive", "calendar", "tasks"]
NAME = {"local": "LocalFiles", "gmail": "Gmail", "drive": "Drive",
        "calendar": "Calendar", "tasks": "Tasks"}
_toks = lambda s: set(re.findall(r"[a-z0-9]+", s.lower()))
_stem = lambda w: w[:-1] if w.endswith("s") and len(w) > 3 else w


class DemoOrchestrator:
    def __init__(self):
        self.cfg = {"allowed_sources": ORDER, "llm_model": "demo, no LLM", "allowed_dirs": []}

    def reset(self):
        pass

    def run(self, question, sources=None, on_token=None):
        allowed = [s for s in ORDER if sources is None or s in sources]
        bus.emit("Planner", "running", f"Understanding: {question}")
        low = question.lower()
        hinted = [s for s, p in HINTS.items() if s in allowed and re.search(p, low)]
        steps = hinted or allowed
        bus.emit("Planner", "done", f"{len(steps)} step(s): " + ", ".join(steps))
        kws = [_stem(k) for k in expand_terms(keywords(question))]
        hits = []
        for src in steps:
            bus.emit(NAME[src], "running", f"Searching sample {src} data")
            time.sleep(0.2)
            # items = [it for it in DATA if it["source"] == src]
            # found = []
            # for it in items:
            #     stems = {_stem(t) for t in _toks(it["ref"] + " " + it["full"])}
            #     sc = sum(1 for k in kws if k in stems)
            #     if sc:
            #         found.append((sc, it))
            items = [it for it in DATA if it["source"] == src]
            found = []
            for it in items:
                title = {_stem(t) for t in _toks(it["ref"].split(" | ")[0])}
                body = {_stem(t) for t in _toks(it["full"])}
                sc = sum(3 for k in kws if k in title) + sum(1 for k in kws if k in body)
                if sc:
                    found.append((sc, it))
            if not found and src in hinted:
                found = [(0, it) for it in items]
            found.sort(key=lambda x: -x[0])
            hits += [dict(it, score=sc) for sc, it in found[:3]]
            bus.emit(NAME[src], "done", f"{len(found[:3])} hit(s)")
        if hits:                                   # drop weak matches
            best = max(h["score"] for h in hits)
            hits = [h for h in hits if h["score"] >= 0.5 * best]
        bus.emit("Verifier", "running", f"Checking {len(hits)} result(s)")
        time.sleep(0.2)
        bus.emit("Verifier", "done", f"{len(hits)}/{len(hits)} verified (demo rules)")
        bus.emit("Summarizer", "running", "Writing answer")
        if hits:
            lines = [f"Found {len(hits)} matching item(s) in the sample data:"]
            lines += [f"* {h['ref'].split(' | ')[0]}: {h['summary']} [{i}]"
                      for i, h in enumerate(hits, 1)]
            answer = "\n".join(lines)
        else:
            answer = "I couldn't find relevant information in the sample data."
        if on_token:
            for piece in re.findall(r"\S+\s*", answer):
                on_token(piece)
                time.sleep(0.02)
        bus.emit("Summarizer", "done", "Answer ready")
        return {"answer": answer, "sources": hits}