# import base64
# from googleapiclient.discovery import build
# from agents.base import Agent
# from google_auth import get_credentials
# from utils import keywords

# def _body(payload):
#     data = payload.get("body", {}).get("data")
#     if payload.get("mimeType") == "text/plain" and data:
#         return base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
#     for part in payload.get("parts") or []:
#         t = _body(part)
#         if t:
#             return t
#     return ""

# class GmailRetrievalAgent(Agent):
#     name = "Gmail"

#     def __init__(self, cfg, llm=None):
#         super().__init__(cfg, llm)
#         self.creds = get_credentials()

#     def retrieve(self, query):
#         self.log("running", f"Searching Gmail: {query}")
#         svc = build("gmail", "v1", credentials=self.creds, cache_discovery=False)
#         q = "{" + " ".join(keywords(query)) + "}"
#         msgs = svc.users().messages().list(
#             userId="me", q=q, maxResults=self.cfg["top_k"]).execute().get("messages", [])
#         hits = []
#         for i, m in enumerate(msgs):
#             msg = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
#             h = {x["name"].lower(): x["value"] for x in msg["payload"]["headers"]}
#             text = _body(msg["payload"]) or msg.get("snippet", "")
#             hits.append({"source": "gmail",
#                          "ref": f"{h.get('subject','(no subject)')} | {h.get('from','')} | {h.get('date','')}",
#                          "text": text.strip()[:1500], "score": round(1.0 - 0.1 * i, 2)})
#         self.log("done", f"{len(hits)} email(s)")
#         return hits
import base64, re
import html as ihtml
from googleapiclient.discovery import build
from agents.base import Agent
from google_auth import get_credentials
from utils import keywords

def _dec(d):
    return base64.urlsafe_b64decode(d).decode("utf-8", "ignore")

def _walk(p, plain, htm, atts):
    mt, body = p.get("mimeType", ""), p.get("body", {})
    if p.get("filename") and body.get("attachmentId"):
        atts.append({"name": p["filename"], "mime": mt, "size": body.get("size", 0),
                     "att_id": body["attachmentId"]})
    elif mt == "text/plain" and body.get("data"):
        plain.append(_dec(body["data"]))
    elif mt == "text/html" and body.get("data"):
        htm.append(_dec(body["data"]))
    for part in p.get("parts") or []:
        _walk(part, plain, htm, atts)

def _strip(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = ihtml.unescape(h)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", h)).strip()

class GmailRetrievalAgent(Agent):
    name = "Gmail"

    def __init__(self, cfg, llm=None):
        super().__init__(cfg, llm)
        self.creds = get_credentials()

    def _svc(self):
        return build("gmail", "v1", credentials=self.creds, cache_discovery=False)

    def fetch_attachment(self, msg_id, att_id):
        a = self._svc().users().messages().attachments().get(
            userId="me", messageId=msg_id, id=att_id).execute()
        return base64.urlsafe_b64decode(a["data"])

    def retrieve(self, query):
        self.log("running", f"Searching Gmail: {query}")
        svc = self._svc()
        q = "{" + " ".join(keywords(query)) + "}"
        msgs = svc.users().messages().list(
            userId="me", q=q, maxResults=self.cfg["top_k"]).execute().get("messages", [])
        hits = []
        for i, m in enumerate(msgs):
            msg = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
            h = {x["name"].lower(): x["value"] for x in msg["payload"]["headers"]}
            plain, htm, atts = [], [], []
            _walk(msg["payload"], plain, htm, atts)
            body = "\n".join(plain).strip() or _strip("\n".join(htm)) or msg.get("snippet", "")
            subj = h.get("subject", "(no subject)")
            head = (f"From: {h.get('from','')}\nTo: {h.get('to','')}\n"
                    f"Date: {h.get('date','')}\nSubject: {subj}")
            if atts:
                head += "\nAttachments: " + ", ".join(a["name"] for a in atts)
            hits.append({
                "source": "gmail",
                "ref": f"{subj} | {h.get('from','')} | {h.get('date','')}",
                "text": (head + "\n\n" + body)[:1500], "full": body,
                "meta": {"id": m["id"], "from": h.get("from", ""), "to": h.get("to", ""),
                         "cc": h.get("cc", ""), "date": h.get("date", ""),
                         "subject": subj, "attachments": atts},
                "score": round(1.0 - 0.1 * i, 2)})
        self.log("done", f"{len(hits)} email(s)")
        return hits