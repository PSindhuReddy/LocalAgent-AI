import re
from ddgs import DDGS
from agents.base import Agent

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
LONGNUM = re.compile(r"\b\d{6,}\b")

def redact(q):
    return LONGNUM.sub("[num]", EMAIL.sub("[email]", q))

class WebRetrievalAgent(Agent):
    name = "Web"

    def retrieve(self, query):
        safe = redact(query)
        self.log("running", f"Web search (redacted): {safe}")
        results = DDGS().text(safe, max_results=self.cfg["top_k"])
        hits = [{"source": "web", "ref": r["href"],
                 "text": f"{r['title']}: {r['body']}", "score": round(1.0 - 0.1 * i, 2)}
                for i, r in enumerate(results)]
        self.log("done", f"{len(hits)} result(s)")
        return hits