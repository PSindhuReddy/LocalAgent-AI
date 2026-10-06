import base64, re
from email.message import EmailMessage
from agents.base import Agent

ADDR = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")

def valid_address(a): return bool(a) and len(a) <= 254 and bool(ADDR.match(a))

def clean_header(s):
    if "\r" in s or "\n" in s:
        raise ValueError("Line breaks are not allowed in the address or subject")
    return s.strip()

def mask(a):
    u, _, d = a.partition("@")
    return u[:1] + "***@" + d


class MailerAgent(Agent):
    name = "Mailer"

    def send(self, to, subject, body):
        to, subject = clean_header(to), clean_header(subject)
        if not valid_address(to):
            raise ValueError("That is not a valid email address")
        if not body.strip():
            raise ValueError("The message is empty")
        from googleapiclient.discovery import build
        from google_auth import get_credentials
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.log("running", f"Sending to {mask(to)}")
        svc = build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        self.log("done", f"Email sent to {mask(to)}")