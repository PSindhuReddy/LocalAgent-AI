from datetime import datetime, timedelta
from googleapiclient.discovery import build
from agents.base import Agent
from google_auth import get_credentials
from utils import keywords
SKIP_CAL = ("#holiday@", "#contacts@")
CAL_STOP = {"calendar", "schedule", "meeting", "meetings", "event", "events", "appointment",
            "appointments", "agenda", "today", "tomorrow", "yesterday", "week", "month",
            "next", "this", "upcoming", "have", "what", "whats", "when", "free"}
def _start_key(e, tz):
    s = e.get("start", {})
    v = s.get("dateTime") or (s.get("date", "9999-12-31") + "T00:00:00")
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return datetime.max.replace(tzinfo=tz)
    return d if d.tzinfo else d.replace(tzinfo=tz)
def parse_window(q, now):
    """Return (start, end) for time words in the question, or None."""
    low = q.lower()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = timedelta(days=1)
    if "tomorrow" in low:   return sod + day, sod + 2 * day
    if "yesterday" in low:  return sod - day, sod
    if "today" in low:      return sod, sod + day
    if "next week" in low:
        mon = sod + timedelta(days=7 - sod.weekday()); return mon, mon + 7 * day
    if "this week" in low:
        mon = sod - timedelta(days=sod.weekday()); return mon, mon + 7 * day
    if "this month" in low:
        start = sod.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1)
    return None

def _fmt(info):
    if "dateTime" in info:
        try:
            return datetime.fromisoformat(info["dateTime"]).strftime("%a %d %b %Y, %I:%M %p")
        except ValueError:
            return info["dateTime"]
    try:
        return datetime.fromisoformat(info.get("date", "")).strftime("%a %d %b %Y (all day)")
    except ValueError:
        return info.get("date", "")

class CalendarRetrievalAgent(Agent):
    name = "Calendar"

    def __init__(self, cfg, llm=None):
        super().__init__(cfg, llm)
        self.creds = get_credentials()

    def retrieve(self, query):
        self.log("running", f"Searching Calendar: {query}")
        now = datetime.now().astimezone()
        kws = [k for k in keywords(query) if k not in CAL_STOP]
        window = parse_window(query, now)
        if window is None:
            sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window = ((sod - timedelta(days=30), sod + timedelta(days=90)) if kws
                      else (sod, sod + timedelta(days=14)))
        svc = build("calendar", "v3", credentials=self.creds, cache_discovery=False)
        cals = svc.calendarList().list().execute().get("items", [])
        cals = [c for c in cals if c.get("selected", True)
                and not any(s in c["id"] for s in SKIP_CAL)]

        events = []
        for cal in cals:
            params = dict(calendarId=cal["id"], timeMin=window[0].isoformat(),
                          timeMax=window[1].isoformat(), singleEvents=True,
                          orderBy="startTime", maxResults=15)
            if kws:
                params["q"] = " ".join(kws)
            try:
                for e in svc.events().list(**params).execute().get("items", []):
                    events.append((cal.get("summaryOverride") or cal.get("summary", "Calendar"), e))
            except Exception as ex:
                self.log("warning", f"{cal.get('summary', cal['id'])}: {ex}")

        events.sort(key=lambda ce: _start_key(ce[1], now.tzinfo))
        hits = []
        for i, (cname, e) in enumerate(events[: max(self.cfg["top_k"] * 2, 10)]):
            title = e.get("summary", "(no title)")
            when = _fmt(e.get("start", {}))
            text = (f"{title}\nCalendar: {cname}\nWhen: {when} to {_fmt(e.get('end', {}))}\n"
                    f"Where: {e.get('location', 'not specified')}\n"
                    f"{(e.get('description') or '')[:400]}")
            hits.append({"source": "calendar", "ref": f"{title} | {when} | {cname}",
                         "text": text, "score": round(1.0 - 0.05 * i, 2), "semantic": True})
        self.log("done", f"{len(hits)} event(s) from {len(cals)} calendar(s)")
        return hits