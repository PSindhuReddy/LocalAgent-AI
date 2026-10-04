from datetime import datetime
from googleapiclient.discovery import build
from agents.base import Agent
from agents.calendar_retriever import parse_window
from google_auth import get_credentials
from utils import keywords

TASK_STOP = {"task", "tasks", "todo", "list", "pending", "due", "overdue", "remaining",
             "completed", "done", "finished", "today", "tomorrow", "yesterday", "week",
             "month", "next", "this", "what", "have", "reminder", "reminders", "still"}

class TasksRetrievalAgent(Agent):
    name = "Tasks"

    def __init__(self, cfg, llm=None):
        super().__init__(cfg, llm)
        self.creds = get_credentials()

    def retrieve(self, query):
        self.log("running", f"Searching Tasks: {query}")
        low = query.lower()
        now = datetime.now().astimezone()
        today = now.date()
        want_done = any(w in low for w in ("completed", "finished", "done"))
        overdue = "overdue" in low
        window = parse_window(query, now)
        kws = [k for k in keywords(query) if k not in TASK_STOP]

        svc = build("tasks", "v1", credentials=self.creds, cache_discovery=False)
        lists = svc.tasklists().list(maxResults=20).execute().get("items", [])
        rows = []
        for tl in lists:
            res = svc.tasks().list(tasklist=tl["id"], maxResults=100,
                                   showCompleted=want_done, showHidden=want_done).execute()
            for t in res.get("items", []):
                title = (t.get("title") or "").strip()
                if not title:
                    continue
                done = t.get("status") == "completed"
                if done != want_done:
                    continue
                due = datetime.fromisoformat(t["due"].replace("Z", "+00:00")).date() if t.get("due") else None
                if overdue and not (due and due < today and not done):
                    continue
                if window and not (due and window[0].date() <= due < window[1].date()):
                    continue
                blob = f"{title} {t.get('notes', '')} {tl.get('title', '')}".lower()
                if kws and not any(k in blob for k in kws):
                    continue
                rows.append((due, tl.get("title", "Tasks"), t, title, done))

        rows.sort(key=lambda r: (r[0] is None, r[0] or today))
        hits = []
        for i, (due, lname, t, title, done) in enumerate(rows[:15]):
            due_s = due.strftime("%a %d %b %Y") if due else "no due date"
            status = "completed" if done else ("overdue" if due and due < today else "pending")
            text = (f"Task: {title}\nList: {lname}\nDue: {due_s}\nStatus: {status}\n"
                    f"Notes: {(t.get('notes') or '')[:300]}")
            hits.append({"source": "tasks", "ref": f"{title} | due {due_s} | {status}",
                         "text": text, "score": round(1.0 - 0.05 * i, 2), "semantic": True})
        self.log("done", f"{len(hits)} task(s)")
        return hits