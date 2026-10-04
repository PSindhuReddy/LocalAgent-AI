# from agents.base import Agent

# SYSTEM = """You answer using ONLY the numbered sources, which are search results from the
# user's own files, Gmail, Drive and Google Calendar (sometimes web pages).
# Rules:
# - Write in the third person about the sources ("The resume lists..."), never as "I".
# - Go through EVERY numbered source, in order, one bullet per source.
# - For emails: subject, sender and date.
# - For files: file name and a one-line summary.
# - For tasks: title, due date and status (pending, overdue or completed).
# - For calendar events: title, date and time, and place.
# - Cite each bullet like [1].
# - If a source does not actually relate to the question, say "This does not appear to
#   match your question" instead of guessing.
# - Never guess what the user's files might contain. Never invent facts."""

# class SummarizationAgent(Agent):
#     name = "Summarizer"

#     def summarize(self, question, hits):
#         self.log("running", "Writing answer")
#         if not hits:
#             self.log("done", "No verified sources")
#             return "I couldn't find relevant information in your permitted sources."
#         ctx = "\n\n".join(f"[{i+1}] ({h['source']}) {h['ref']}\n{h['text'][:800]}"
#                           for i, h in enumerate(hits))
#         try:
#             answer = self.llm.chat(
#                 SYSTEM,
#                 f"Question: {question}\n\nThere are {len(hits)} sources. "
#                 f"Cover all {len(hits)}.\n\nSources:\n{ctx}")
#         except Exception:
#             self.log("warning", "Local LLM unreachable; showing sources without a summary")
#             answer = ("The local LLM (Ollama) isn't running, so here are the matching "
#                       "sources without a summary. Start Ollama and ask again.")
#         self.log("done", "Answer ready")
#         return answer
from agents.base import Agent

SYSTEM = """You answer using ONLY the numbered sources, which are search results from the
user's own files, Gmail, Drive, Google Calendar and Google Tasks (sometimes web pages).
Rules:
- Write in the third person about the sources ("The resume lists..."), never as "I".
- Go through EVERY numbered source, in order, one bullet per source.
- For emails: subject, sender and date.
- For files: file name and a one-line summary.
- For calendar events: title, date and time, and place.
- For tasks: title, due date and status (pending, overdue or completed).
- Cite each bullet like [1].
- If a source does not actually relate to the question, say "This does not appear to
  match your question" instead of guessing.
- Never guess what the user's files might contain. Never invent facts."""

class SummarizationAgent(Agent):
    name = "Summarizer"

    def summarize(self, question, hits, on_token=None):
        self.log("running", "Writing answer")
        if not hits:
            self.log("done", "No verified sources")
            return "I couldn't find relevant information in your permitted sources."
        ctx = "\n\n".join(f"[{i+1}] ({h['source']}) {h['ref']}\n{h['text'][:800]}"
                          for i, h in enumerate(hits))
        user = (f"Question: {question}\n\nThere are {len(hits)} sources. "
                f"Cover all {len(hits)}.\n\nSources:\n{ctx}")
        try:
            if on_token:
                parts = []
                for t in self.llm.chat_stream(SYSTEM, user):
                    parts.append(t)
                    on_token(t)
                answer = "".join(parts)
            else:
                answer = self.llm.chat(SYSTEM, user)
        except Exception:
            self.log("warning", "Local LLM unreachable; showing sources without a summary")
            answer = ("The local LLM (Ollama) isn't running, so here are the matching "
                      "sources without a summary. Start Ollama and ask again.")
        self.log("done", "Answer ready")
        return answer