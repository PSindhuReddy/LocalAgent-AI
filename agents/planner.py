import re
from agents.base import Agent
from utils import keywords

SYSTEM = """You are a planner for a personal search assistant.
Break the request into retrieval steps. Available agents: {sources}.
Reply ONLY with JSON: {{"steps":[{{"agent":"<name>","query":"<focused query>"}}]}}
'local'=files on this computer, 'gmail'=emails, 'drive'=Google Drive, 'web'=public internet.
Use as few steps as needed.
'calendar'=Google Calendar events and meetings.
'tasks'=Google Tasks to-do items and reminders.
The query must be 2-5 plain keywords only. No operators (AND, OR, subject:, to:),
no parentheses, no quotes, no placeholders."""

# Wording that clearly points to a source (rules beat a small LLM)
HINTS = {
        "tasks": r"\b(task|tasks|todo|to-do|to do|reminder|reminders|pending|overdue)\b",
    "calendar": r"\b(calendar|meeting|meetings|schedule|appointment|appointments|agenda|event|events)\b",
    "gmail": r"\b(mail|mails|email|emails|inbox|gmail|message|messages|sender)\b",
    "drive": r"\b(drive|gdoc|google doc|shared doc|spreadsheet|sheet|slides)\b",
    "local": r"\b(file|files|folder|document|documents|notes|resume|pdf|docx|laptop|computer|local)\b",
    "web":   r"\b(web|online|internet|latest|news|website|google it)\b",
}

class PlannerAgent(Agent):
    name = "Planner"

    def plan(self, question, allowed=None):
        self.log("running", f"Understanding: {question}")
        allowed = allowed or self.cfg["allowed_sources"]
        low = question.lower()

        # 1) LLM proposal
        try:
            data = self.llm.chat_json(SYSTEM.format(sources=", ".join(allowed)), question)
            steps = [s for s in data.get("steps", [])
                     if s.get("agent") in allowed and s.get("query")]
        except Exception as e:
            self.log("warning", f"LLM planning failed ({e}); using rules")
            steps = []

        # 2) Add any source the wording clearly points to
        chosen = {s["agent"] for s in steps}
        query = " ".join(keywords(question)) or question
        for src, pat in HINTS.items():
            if src in allowed and src not in chosen and re.search(pat, low):
                steps.append({"agent": src, "query": query})

        # 3) Web only when the user actually asked for public/online info
        if not re.search(HINTS["web"], low):
            steps = [s for s in steps if s["agent"] != "web"]

        # 4) Nothing left: search all private sources
        if not steps:
            steps = [{"agent": a, "query": query} for a in allowed if a != "web"]

        self.log("done", f"{len(steps)} step(s): " + ", ".join(s["agent"] for s in steps))
        return steps