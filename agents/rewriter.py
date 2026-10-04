import re
from agents.base import Agent

FOLLOW = re.compile(r"\b(it|its|that|those|them|these|this|he|she|they|his|her|their|"
                    r"above|previous|earlier|first|second|third|same|more|also|another|else)\b", re.I)

SYSTEM = """Decide whether the latest message depends on the earlier conversation.
- If it is a NEW topic that makes sense on its own, return it UNCHANGED.
- Only if it refers back to earlier results (it, those, them, the first one, from them...),
  rewrite it as a short standalone search question using the conversation.
Do NOT answer it. Do NOT add topics from the conversation to a new topic.
Reply ONLY with JSON: {"question":"<question>"}"""

class RewriterAgent(Agent):
    name = "Rewriter"

    def rewrite(self, question, history):
        if not FOLLOW.search(question):
            return question                                  # standalone, skip the LLM
        if not history:
            return question
        if not (FOLLOW.search(question) or len(question.split()) <= 3):
            return question                                  # already standalone, skip the LLM
        self.log("running", "Resolving follow-up question")
        ctx = "\n".join(f"User: {t['q']}\nAssistant: {t['a'][:300]}\nSources: {'; '.join(t['refs'][:5])}"
                        for t in history[-3:])
        try:
            data = self.llm.chat_json(SYSTEM, f"Conversation:\n{ctx}\n\nLatest message: {question}")
            new = str(data.get("question", "")).strip()
            if not new or len(new) > 200:
                raise ValueError("bad rewrite")
        except Exception as e:
            self.log("warning", f"Rewrite failed ({e}); using original")
            return question
        self.log("done", f"-> {new}")
        return new