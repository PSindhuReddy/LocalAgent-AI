import re
from agents.base import Agent
from utils import keywords

WEB_SYSTEM = """Mark a web result relevant ONLY if it directly answers the question with
public information. Generic how-to or advice pages are NOT relevant to questions about
the user's own emails or files. Reply ONLY with JSON:
{"results":[{"id":<int>,"relevant":true,"reason":"<short reason>"}]}"""


def _toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _stem(w):
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


class VerificationAgent(Agent):
    name = "Verifier"

    def verify(self, question, hits):
        self.log("running", f"Checking {len(hits)} result(s)")

        # De-duplicate
        seen, uniq = set(), []
        for h in hits:
            key = (h["ref"], h["text"][:80])
            if key not in seen:
                seen.add(key)
                uniq.append(h)

        # 1) Personal sources: rule-based whole-word keyword check (fast, no LLM)
        kws = keywords(question)
        personal = []
        for h in uniq:
            if h["source"] == "web":
                continue
            stems = {_stem(t) for t in _toks(h["ref"] + " " + h["text"])}
            if h.get("semantic") or not kws or any(_stem(k) in stems for k in kws):
                personal.append({**h, "reason": "keyword match in your own data"})

        # 2) Web sources: LLM relevance check
        web = [h for h in uniq if h["source"] == "web"][:5]
        kept_web = []
        if web:
            listing = "\n".join(
                f"[{i}] {h['ref']}\n{h['text'][:200]}" for i, h in enumerate(web))
            try:
                data = self.llm.chat_json(
                    WEB_SYSTEM, f"Question: {question}\n\nResults:\n{listing}")
                ok = {int(r["id"]): r.get("reason", "")
                      for r in data.get("results", []) if r.get("relevant")}
                kept_web = [{**h, "reason": ok[i]} for i, h in enumerate(web) if i in ok]
            except Exception as e:
                self.log("warning", f"Web check failed ({e}); dropping web results")

        kept = personal + kept_web
        self.log("done", f"{len(kept)}/{len(uniq)} verified "
                         f"({len(personal)} personal, {len(kept_web)} web)")
        return kept