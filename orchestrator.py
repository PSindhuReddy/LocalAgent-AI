import importlib
import threading
import audit  # noqa: F401
import config
from events import bus
from llm import LocalLLM
from agents.planner import PlannerAgent
from agents.rewriter import RewriterAgent
from agents.verifier import VerificationAgent
from agents.summarizer import SummarizationAgent

REGISTRY = {
    "local": ("agents.local_retriever", "LocalRetrievalAgent"),
    "gmail": ("agents.gmail_retriever", "GmailRetrievalAgent"),
    "drive": ("agents.drive_retriever", "DriveRetrievalAgent"),
    "web":   ("agents.web_retriever",   "WebRetrievalAgent"),
    "calendar": ("agents.calendar_retriever", "CalendarRetrievalAgent"),
    "tasks": ("agents.task_retriever", "TasksRetrievalAgent")
}

class Orchestrator:
    def __init__(self):
        self.cfg = config.load()
        self.llm = LocalLLM(self.cfg)
        self.planner = PlannerAgent(self.cfg, self.llm)
        self.rewriter = RewriterAgent(self.cfg, self.llm)
        self.verifier = VerificationAgent(self.cfg, self.llm)
        self.summarizer = SummarizationAgent(self.cfg, self.llm)
        self.retrievers = {}
        self.history = []                      # in-memory only
        self.lock = threading.Lock()

    def _get(self, name):
        if name not in self.retrievers:
            mod, cls = REGISTRY[name]
            self.retrievers[name] = getattr(importlib.import_module(mod), cls)(self.cfg, self.llm)
        return self.retrievers[name]

    def reset(self):
        with self.lock:
            self.history = []

    def run(self, question, sources=None, on_token=None):
        with self.lock:
            return self._run(question, sources, on_token)

    def _run(self, question, sources=None, on_token=None):
        allowed = [s for s in self.cfg["allowed_sources"] if sources is None or s in sources]
        if not allowed:
            return {"question": question, "answer": "No sources were selected for this query.",
                    "sources": [], "raw_results": []}
        standalone = self.rewriter.rewrite(question, self.history)
        results = []
        for step in self.planner.plan(standalone, allowed):
            name = step["agent"]
            if name in allowed and name in REGISTRY:
                try:
                    # results += self._get(name).retrieve(step["query"])
                    q = standalone if name in ("calendar", "tasks") else step["query"]
                    results += self._get(name).retrieve(q)
                except Exception as e:
                    bus.emit(name, "error", str(e))
        verified = self.verifier.verify(standalone, results)
        answer = self.summarizer.summarize(standalone, verified, on_token=on_token)
        self.history.append({"q": question, "a": answer,
                             "refs": [s["ref"][:80] for s in verified]})
        self.history = self.history[-5:]
        return {"question": question, "answer": answer,
                "sources": verified, "raw_results": results}