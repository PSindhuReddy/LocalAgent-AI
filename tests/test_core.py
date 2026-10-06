from utils import keywords
from agents.web_retriever import redact
from agents.verifier import VerificationAgent
from agents.planner import PlannerAgent
from agents.rewriter import RewriterAgent
from datetime import datetime
from agents.calendar_retriever import parse_window
import pytest
from agents.composer import COMPOSE
from agents.mailer import valid_address, clean_header
NOW = datetime(2026, 10, 2, 10, 0) 

HIST = [{"q": "internship mails", "a": "Found 3 emails", "refs": ["TCS Training"]}]
class BadLLM:
    def chat_json(self, *a, **k): raise RuntimeError("offline")

def test_keywords_drop_stopwords():
    assert keywords("find my internship emails") == ["internship"]

def test_web_redaction():
    out = redact("mail bob@x.com about 1234567890")
    assert "bob@x.com" not in out and "1234567890" not in out
def test_mail_question_routes_to_gmail_not_web():
    class WebLLM:
        def chat_json(self, *a, **k):
            return {"steps": [{"agent": "web", "query": "internship"}]}
    p = PlannerAgent({"allowed_sources": ["local", "gmail", "drive", "web"]}, WebLLM())
    agents = [s["agent"] for s in p.plan("internship mails")]
    assert "gmail" in agents and "web" not in agents
def test_verifier_keeps_matching_personal_hits():
    v = VerificationAgent({}, None)
    hits = [{"source": "gmail", "ref": "Internship offer", "text": "join us"},
            {"source": "gmail", "ref": "Lunch", "text": "pizza friday"}]
    kept = v.verify("internship mails", hits)
    assert [h["ref"] for h in kept] == ["Internship offer"]

def test_planner_fallback_never_uses_web():
    p = PlannerAgent({"allowed_sources": ["local", "gmail", "web"]}, BadLLM())
    steps = p.plan("anything", ["local", "gmail", "web"])
    assert [s["agent"] for s in steps] == ["local", "gmail"]

def test_planner_respects_unticked_sources():
    p = PlannerAgent({"allowed_sources": ["local", "gmail"]}, BadLLM())
    assert [s["agent"] for s in p.plan("x", ["local"])] == ["local"]

def test_rewriter_skips_standalone_questions():
    r = RewriterAgent({}, BadLLM())
    assert r.rewrite("show internship emails from February", HIST) == "show internship emails from February"

def test_rewriter_falls_back_when_llm_fails():
    r = RewriterAgent({}, BadLLM())
    assert r.rewrite("which of those is from TCS?", HIST) == "which of those is from TCS?"

def test_rewriter_no_history_passthrough():
    assert RewriterAgent({}, None).rewrite("which of those?", []) == "which of those?"
def test_calendar_tomorrow_window():
    s, e = parse_window("what's on tomorrow", NOW)
    assert (s.day, e.day) == (3, 4)

def test_calendar_next_week_starts_monday():
    s, _ = parse_window("meetings next week", NOW)
    assert (s.month, s.day) == (10, 5)

def test_calendar_no_time_words():
    assert parse_window("review with rahul", NOW) == (NOW, NOW)
def test_audit_skips_token_events(tmp_path, monkeypatch):
    import audit
    monkeypatch.setattr(audit, "LOG", tmp_path / "a.jsonl")
    audit._write({"ts": 1, "agent": "System", "status": "token", "detail": "secret"})
    assert not (tmp_path / "a.jsonl").exists()
    
def test_compose_intent():
    assert COMPOSE.search("write a mail to rahul about leave")
    assert COMPOSE.search("Draft an email for my professor")
    assert not COMPOSE.search("internship mails")
    assert not COMPOSE.search("send me the mails about tcs")

def test_address_validation():
    assert valid_address("a@b.com")
    assert not valid_address("a b@c.com") and not valid_address("x")

def test_header_injection_blocked():
    with pytest.raises(ValueError):
        clean_header("hi\nBcc: x@y.com")