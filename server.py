# import json, queue, threading
# import mimetypes, pathlib, os, tempfile
# from datetime import datetime
# from urllib.parse import quote
# from fastapi import FastAPI, HTTPException
# from fastapi.responses import (HTMLResponse, StreamingResponse, Response,
#                                PlainTextResponse, FileResponse)
# from pydantic import BaseModel
# from audit import tail
# from events import bus
# from orchestrator import Orchestrator

# app = FastAPI()
# orch = Orchestrator()
# subs = []
# STATE = {"items": []}          # verified results of the latest question (for the viewer)

# bus.subscribe(lambda ev: [q.put(ev) for q in list(subs)])

# INLINE_OK = ("application/pdf", "text/plain", "image/png", "image/jpeg",
#              "image/gif", "image/webp")
# PREVIEW_EXT = {".pdf", ".docx", ".txt", ".md", ".csv", ".log", ".json"}


# class Ask(BaseModel):
#     question: str
#     sources: list[str] | None = None


# # ---------- helpers ----------
# def _human(n):
#     n = float(n)
#     for u in ("B", "KB", "MB", "GB"):
#         if n < 1024 or u == "GB":
#             return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
#         n /= 1024


# def _lite(s):
#     m = s.get("meta", {})
#     return {"source": s["source"], "ref": s["ref"],
#             "meta": {k: m[k] for k in ("from", "to", "date") if k in m}}


# def _get_item(i):
#     items = STATE["items"]
#     if not 0 <= i < len(items):
#         raise HTTPException(404)
#     return items[i]


# def _local_path(s):
#     p = pathlib.Path(s["ref"]).resolve()
#     roots = [pathlib.Path(d).expanduser().resolve() for d in orch.cfg["allowed_dirs"]]
#     if not p.is_file() or not any(r == p or r in p.parents for r in roots):
#         raise HTTPException(403)
#     return p


# def _disp(name, dl, mime):
#     kind = "inline" if (not dl and mime in INLINE_OK) else "attachment"
#     return {"Content-Disposition": f"{kind}; filename*=UTF-8''{quote(name)}",
#             "X-Content-Type-Options": "nosniff"}


# def _bytes_to_text(name, data):
#     from agents.local_retriever import read_file
#     with tempfile.NamedTemporaryFile(delete=False, suffix=pathlib.Path(name).suffix) as f:
#         f.write(data)
#         tmp = f.name
#     try:
#         return read_file(pathlib.Path(tmp))
#     except Exception:
#         return ""
#     finally:
#         os.unlink(tmp)


# # ---------- pages and info ----------
# @app.get("/")
# def index():
#     return HTMLResponse(open("static/index.html", encoding="utf-8").read())


# @app.get("/config")
# def config_view():
#     return {"sources": orch.cfg["allowed_sources"], "model": orch.cfg["llm_model"]}


# @app.get("/audit")
# def audit_view():
#     return tail(60)


# @app.get("/health")
# def health():
#     import requests
#     cfg = orch.cfg
#     out = {"ollama": False, "llm_model": False, "embed_model": False}
#     try:
#         r = requests.get(cfg["ollama_url"] + "/api/tags", timeout=2)
#         names = [m["name"] for m in r.json().get("models", [])]
#         out["ollama"] = True
#         out["llm_model"] = any(n.startswith(cfg["llm_model"]) for n in names)
#         out["embed_model"] = any(n.startswith(cfg.get("embed_model", "nomic-embed-text"))
#                                  for n in names)
#     except Exception:
#         pass
#     out["google_token"] = os.path.exists("token.json")
#     out["missing_dirs"] = [d for d in cfg["allowed_dirs"]
#                            if not pathlib.Path(d).expanduser().exists()]
#     return out


# # ---------- viewer ----------
# @app.get("/item/{i}")
# def item(i: int):
#     s = _get_item(i)
#     bus.emit("Viewer", "opened", f"{s['source']} item")
#     m = dict(s.get("meta", {}))
#     atts = [{"name": a["name"], "size_h": _human(a["size"]),
#              "previewable": pathlib.Path(a["name"]).suffix.lower() in PREVIEW_EXT,
#              "inline": a["mime"] in INLINE_OK} for a in m.pop("attachments", [])]
#     m.pop("id", None)
#     body, is_file = s.get("full") or s["text"], False
#     if s["source"] == "local":
#         from agents.local_retriever import read_file
#         p = _local_path(s)
#         try:
#             body = read_file(p) or "(No readable text. Use Open original.)"
#         except Exception:
#             body = "(Could not read this file. Use Open original.)"
#         st = p.stat()
#         m = {"path": str(p), "size": _human(st.st_size),
#              "modified": datetime.fromtimestamp(st.st_mtime).strftime("%d %b %Y %H:%M")}
#         is_file = True
#     return {"ref": s["ref"], "meta": m, "body": body[:200000],
#             "attachments": atts, "file": is_file}


# @app.get("/file/{i}")
# def file(i: int, dl: int = 0):
#     s = _get_item(i)
#     if s["source"] != "local":
#         raise HTTPException(404)
#     p = _local_path(s)
#     mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
#     return FileResponse(p, media_type=mime, headers=_disp(p.name, dl, mime))


# @app.get("/att/{i}/{j}")
# def att(i: int, j: int, dl: int = 0, text: int = 0):
#     s = _get_item(i)
#     atts = s.get("meta", {}).get("attachments", [])
#     if s["source"] != "gmail" or not 0 <= j < len(atts):
#         raise HTTPException(404)
#     a = atts[j]
#     bus.emit("Viewer", "opened", "gmail attachment")
#     data = orch._get("gmail").fetch_attachment(s["meta"]["id"], a["att_id"])
#     if text:
#         return PlainTextResponse(_bytes_to_text(a["name"], data)[:200000])
#     return Response(data, media_type=a["mime"], headers=_disp(a["name"], dl, a["mime"]))

# SUM_SYSTEM = """Summarize the document below for the user. Use ONLY the text given.
# Format: one short sentence saying what it is, then 3-5 bullets with the key facts:
# people, dates, deadlines, amounts and requested actions. Write in the third person.
# Never invent anything. If the text is short, one or two bullets are enough."""


# def _item_text(s):
#     if s["source"] == "local":
#         from agents.local_retriever import read_file
#         return read_file(_local_path(s))
#     m = s.get("meta", {})
#     body = s.get("full") or s["text"]
#     if s["source"] == "gmail":
#         return (f"From: {m.get('from','')}\nTo: {m.get('to','')}\n"
#                 f"Date: {m.get('date','')}\nSubject: {m.get('subject','')}\n\n{body}")
#     return body


# @app.get("/summary/{i}")
# def summary(i: int, att: int = -1):
#     s = _get_item(i)
#     label = "item"
#     if att >= 0:
#         atts = s.get("meta", {}).get("attachments", [])
#         if s["source"] != "gmail" or not 0 <= att < len(atts):
#             raise HTTPException(404)
#         a = atts[att]
#         data = orch._get("gmail").fetch_attachment(s["meta"]["id"], a["att_id"])
#         text, label = _bytes_to_text(a["name"], data), "attachment"
#     else:
#         try:
#             text = _item_text(s)
#         except HTTPException:
#             raise
#         except Exception:
#             text = ""
#     bus.emit("Viewer", "summarized", f"{s['source']} {label}")
#     if not (text or "").strip():
#         return PlainTextResponse("No readable text to summarize (it may be a scanned or image file).")
#     limit = 6000
#     note = "\n\n(Only the first part of a long document is shown to you.)" if len(text) > limit else ""
#     user = f"Document:\n{text[:limit]}{note}"

#     def gen():
#         try:
#             for t in orch.llm.chat_stream(SUM_SYSTEM, user):
#                 yield t
#         except Exception:
#             yield "Could not summarize: the local LLM (Ollama) isn't responding."
#     return StreamingResponse(gen(), media_type="text/plain")

# # ---------- chat ----------
# @app.post("/reset")
# def reset():
#     orch.reset()
#     STATE["items"] = []
#     return {"ok": True}


# @app.post("/ask")
# def ask(body: Ask):
#     def work():
#         try:
#             out = orch.run(body.question, body.sources,
#                            on_token=lambda t: bus.emit("System", "token", t))
#             STATE["items"] = out["sources"]
#             payload = {"answer": out["answer"],
#                        "sources": [_lite(s) for s in out["sources"]]}
#             bus.emit("System", "result", json.dumps(payload))
#         except Exception as e:
#             bus.emit("System", "error", str(e))
#     threading.Thread(target=work, daemon=True).start()
#     return {"ok": True}


# @app.get("/events")
# def events():
#     q = queue.Queue()
#     subs.append(q)

#     def gen():
#         try:
#             while True:
#                 try:
#                     yield f"data: {json.dumps(q.get(timeout=15))}\n\n"
#                 except queue.Empty:
#                     yield ": ping\n\n"
#         finally:
#             subs.remove(q)
#     return StreamingResponse(gen(), media_type="text/event-stream")


# # ---------- startup ----------
# def check_ollama():
#     import requests
#     try:
#         requests.get(orch.cfg["ollama_url"], timeout=3)
#         print("Ollama: connected")
#     except Exception:
#         print("WARNING: Ollama is not running. Start it (ollama serve) for planning and summaries.")


# def open_chrome():
#     import webbrowser
#     url = "http://127.0.0.1:8000"
#     for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
#                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
#         if os.path.exists(path):
#             webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(path))
#             webbrowser.get("chrome").open(url)
#             return
#     webbrowser.open(url)


# check_ollama()

# if __name__ == "__main__":
#     import uvicorn
#     threading.Timer(1.5, open_chrome).start()
#     uvicorn.run(app, host="127.0.0.1", port=8000)   # localhost only
import json, queue, threading, mimetypes, pathlib, os, tempfile, time, uuid, re
from datetime import datetime
from agents.composer import ComposerAgent, COMPOSE
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (HTMLResponse, StreamingResponse, Response,
                               PlainTextResponse, FileResponse)
from pydantic import BaseModel
from events import bus, ctx

DEMO = os.getenv("DEMO") == "1"
if os.getenv("PORT") and not DEMO:      # public host + real accounts = never
    raise SystemExit("Refusing to run non-demo mode on a public host. Set DEMO=1.")

if DEMO:
    from demo import DemoOrchestrator
    orch = DemoOrchestrator()
    tail = lambda n=60: []
else:
    from audit import tail
    from orchestrator import Orchestrator
    orch = Orchestrator()

app = FastAPI()
subs, STATE, HITS = [], {}, {}      # event listeners, per-session results, rate limit

bus.subscribe(lambda ev: [q.put(ev) for s, q in list(subs) if ev.get("sid") in (None, s)])

INLINE_OK = ("application/pdf", "text/plain", "image/png", "image/jpeg",
             "image/gif", "image/webp")
PREVIEW_EXT = {".pdf", ".docx", ".txt", ".md", ".csv", ".log", ".json"}


class Ask(BaseModel):
    question: str
    sources: list[str] | None = None


# ---------- helpers ----------
def sid_of(request): return request.cookies.get("sid", "")


def _human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def _lite(s):
    m = s.get("meta", {})
    return {"source": s["source"], "ref": s["ref"],
            "meta": {k: m[k] for k in ("from", "to", "date") if k in m}}


def _get_item(i, request):
    items = STATE.get(sid_of(request), [])
    if not 0 <= i < len(items):
        raise HTTPException(404)
    return items[i]


def _local_path(s):
    p = pathlib.Path(s["ref"]).resolve()
    roots = [pathlib.Path(d).expanduser().resolve() for d in orch.cfg["allowed_dirs"]]
    if not p.is_file() or not any(r == p or r in p.parents for r in roots):
        raise HTTPException(403)
    return p


def _disp(name, dl, mime):
    kind = "inline" if (not dl and mime in INLINE_OK) else "attachment"
    return {"Content-Disposition": f"{kind}; filename*=UTF-8''{quote(name)}",
            "X-Content-Type-Options": "nosniff"}


def _bytes_to_text(name, data):
    from agents.local_retriever import read_file
    with tempfile.NamedTemporaryFile(delete=False, suffix=pathlib.Path(name).suffix) as f:
        f.write(data)
        tmp = f.name
    try:
        return read_file(pathlib.Path(tmp))
    except Exception:
        return ""
    finally:
        os.unlink(tmp)


def _limited(request):
    if not DEMO:
        return False
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    now = time.time()
    h = [t for t in HITS.get(ip, []) if now - t < 60] + [now]
    HITS[ip] = h
    return len(h) > 10


# ---------- pages and info ----------
@app.get("/")
def index(request: Request):
    resp = HTMLResponse(open("static/index.html", encoding="utf-8").read())
    if not request.cookies.get("sid"):
        resp.set_cookie("sid", uuid.uuid4().hex, httponly=True, samesite="lax")
    return resp


@app.get("/config")
def config_view():
    return {"sources": orch.cfg["allowed_sources"], "model": orch.cfg["llm_model"]}


@app.get("/audit")
def audit_view():
    return tail(60)


@app.get("/health")
def health():
    if DEMO:
        return {"demo": True}
    import requests
    cfg = orch.cfg
    out = {"ollama": False, "llm_model": False, "embed_model": False}
    try:
        r = requests.get(cfg["ollama_url"] + "/api/tags", timeout=2)
        names = [m["name"] for m in r.json().get("models", [])]
        out["ollama"] = True
        out["llm_model"] = any(n.startswith(cfg["llm_model"]) for n in names)
        out["embed_model"] = any(n.startswith(cfg.get("embed_model", "nomic-embed-text"))
                                 for n in names)
    except Exception:
        pass
    out["google_token"] = os.path.exists("token.json")
    out["missing_dirs"] = [d for d in cfg["allowed_dirs"]
                           if not pathlib.Path(d).expanduser().exists()]
    return out


# ---------- viewer ----------
@app.get("/item/{i}")
def item(i: int, request: Request):
    s = _get_item(i, request)
    bus.emit("Viewer", "opened", f"{s['source']} item")
    m = dict(s.get("meta", {}))
    atts = [{"name": a["name"], "size_h": _human(a["size"]),
             "previewable": pathlib.Path(a["name"]).suffix.lower() in PREVIEW_EXT,
             "inline": a["mime"] in INLINE_OK} for a in m.pop("attachments", [])]
    m.pop("id", None)
    body, is_file = s.get("full") or s["text"], False
    if s["source"] == "local" and not s.get("demo"):
        from agents.local_retriever import read_file
        p = _local_path(s)
        try:
            body = read_file(p) or "(No readable text. Use Open original.)"
        except Exception:
            body = "(Could not read this file. Use Open original.)"
        st = p.stat()
        m = {"path": str(p), "size": _human(st.st_size),
             "modified": datetime.fromtimestamp(st.st_mtime).strftime("%d %b %Y %H:%M")}
        is_file = True
    return {"source": s["source"], "ref": s["ref"], "meta": m,
            "body": body[:200000], "attachments": atts, "file": is_file}

@app.get("/file/{i}")
def file(i: int, request: Request, dl: int = 0):
    s = _get_item(i, request)
    if s["source"] != "local" or s.get("demo"):
        raise HTTPException(404)
    p = _local_path(s)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=mime, headers=_disp(p.name, dl, mime))


@app.get("/att/{i}/{j}")
def att(i: int, j: int, request: Request, dl: int = 0, text: int = 0):
    s = _get_item(i, request)
    atts = s.get("meta", {}).get("attachments", [])
    if s["source"] != "gmail" or not 0 <= j < len(atts):
        raise HTTPException(404)
    a = atts[j]
    bus.emit("Viewer", "opened", "gmail attachment")
    data = orch._get("gmail").fetch_attachment(s["meta"]["id"], a["att_id"])
    if text:
        return PlainTextResponse(_bytes_to_text(a["name"], data)[:200000])
    return Response(data, media_type=a["mime"], headers=_disp(a["name"], dl, a["mime"]))


SUM_SYSTEM = """Summarize the document below for the user. Use ONLY the text given.
Format: one short sentence saying what it is, then 3-5 bullets with the key facts:
people, dates, deadlines, amounts and requested actions. Write in the third person.
Never invent anything. If the text is short, one or two bullets are enough."""


def _item_text(s):
    if s.get("demo"):
        return s["full"]
    if s["source"] == "local":
        from agents.local_retriever import read_file
        return read_file(_local_path(s))
    m = s.get("meta", {})
    body = s.get("full") or s["text"]
    if s["source"] == "gmail":
        return (f"From: {m.get('from','')}\nTo: {m.get('to','')}\n"
                f"Date: {m.get('date','')}\nSubject: {m.get('subject','')}\n\n{body}")
    return body


@app.get("/summary/{i}")
def summary(i: int, request: Request, att: int = -1):
    s = _get_item(i, request)
    label = "item"
    if att >= 0:
        atts = s.get("meta", {}).get("attachments", [])
        if s["source"] != "gmail" or not 0 <= att < len(atts):
            raise HTTPException(404)
        a = atts[att]
        data = orch._get("gmail").fetch_attachment(s["meta"]["id"], a["att_id"])
        text, label = _bytes_to_text(a["name"], data), "attachment"
    else:
        try:
            text = _item_text(s)
        except HTTPException:
            raise
        except Exception:
            text = ""
    bus.emit("Viewer", "summarized", f"{s['source']} {label}")
    if not (text or "").strip():
        return PlainTextResponse("No readable text to summarize (it may be a scanned or image file).")
    if DEMO:                                   # no LLM on the public demo
        sents = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
        pts = "\n".join("* " + x for x in sents[:3] if x.strip())
        return PlainTextResponse("Key points (demo summary, no LLM):\n" + pts)
    limit = 6000
    note = "\n\n(Only the first part of a long document is shown to you.)" if len(text) > limit else ""
    user = f"Document:\n{text[:limit]}{note}"

    def gen():
        try:
            for t in orch.llm.chat_stream(SUM_SYSTEM, user):
                yield t
        except Exception:
            yield "Could not summarize: the local LLM (Ollama) isn't responding."
    return StreamingResponse(gen(), media_type="text/plain")

# ---------- compose and send (human-in-the-loop) ----------
DRAFTS, SENT = {}, {}


def _guard(request):
    h = request.headers
    if h.get("x-requested-with") != "localagent":
        raise HTTPException(403, "Blocked")
    if not DEMO and h.get("host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "Blocked")
    o = h.get("origin")
    if o and o.split("://", 1)[-1] != h.get("host"):
        raise HTTPException(403, "Blocked")


def do_compose(sid, instruction, item=None):
    reply, items = None, STATE.get(sid, [])
    if item is not None and 0 <= item < len(items) and items[item]["source"] == "gmail":
        s = items[item]
        m = s.get("meta", {})
        reply = {"from": m.get("from", ""), "subject": m.get("subject", ""),
                 "body": s.get("full") or s["text"]}
    if DEMO:
        bus.emit("Composer", "running", "Drafting email (demo template)")
        d = ComposerAgent({}, None).template(instruction)
        if reply:
            from email.utils import parseaddr
            d["to"] = parseaddr(reply["from"])[1]
            d["subject"] = "Re: " + reply["subject"]
        bus.emit("Composer", "done", "Draft ready")
    else:
        d = ComposerAgent(orch.cfg, orch.llm).draft(instruction, orch.history[-2:], reply)
    did = uuid.uuid4().hex
    DRAFTS.setdefault(sid, {})[did] = time.time()
    bus.emit("System", "draft", json.dumps({**d, "draft_id": did}))


class Comp(BaseModel):
    instruction: str = "Reply to this email"
    item: int | None = None


@app.post("/compose")
def compose_ep(b: Comp, request: Request):
    _guard(request)
    sid = sid_of(request)

    def work():
        ctx.sid = sid
        try:
            do_compose(sid, b.instruction[:500], b.item)
        except Exception as e:
            bus.emit("System", "error", str(e))
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


class Send(BaseModel):
    to: str
    subject: str
    body: str
    draft_id: str
    confirm: bool = False


@app.post("/send")
def send_ep(b: Send, request: Request):
    _guard(request)
    sid, now = sid_of(request), time.time()
    made = DRAFTS.get(sid, {}).get(b.draft_id)
    if not b.confirm or not made or now - made > 1800:
        raise HTTPException(400, "Draft expired or not confirmed. Create the draft again.")
    recent = [t for t in SENT.get(sid, []) if now - t < 3600]
    if len(recent) >= 5:
        raise HTTPException(429, "Send limit reached (5 per hour)")
    if len(b.body) > 10000 or len(b.subject) > 200:
        raise HTTPException(400, "Message or subject too long")
    from agents.mailer import MailerAgent, valid_address, clean_header, mask
    ctx.sid = sid
    try:
        to = clean_header(b.to)
        if not valid_address(to):
            raise ValueError("That is not a valid email address")
        if DEMO:
            bus.emit("Mailer", "done", "Demo mode: email NOT sent")
            return {"ok": True, "demo": True}
        MailerAgent(orch.cfg, None).send(to, b.subject, b.body)
        DRAFTS[sid].pop(b.draft_id, None)
        SENT[sid] = recent + [now]
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        bus.emit("Mailer", "error", "Sending failed")
        raise HTTPException(502, str(e)[:200])
    finally:
        ctx.sid = None
        
# ---------- chat ----------
@app.post("/reset")
def reset(request: Request):
    orch.reset()
    STATE.pop(sid_of(request), None)
    return {"ok": True}


@app.post("/ask")
def ask(body: Ask, request: Request):
    sid = sid_of(request)
    if _limited(request):
        ctx.sid = sid
        bus.emit("System", "error", "Too many requests. Please wait a minute.")
        ctx.sid = None
        return {"ok": False}

    def work():
        ctx.sid = sid
        try:
            if COMPOSE.search(body.question):
                do_compose(sid, body.question[:500])
                return
            out = orch.run(body.question, body.sources,
                           on_token=lambda t: bus.emit("System", "token", t))
            if len(STATE) > 200:
                STATE.pop(next(iter(STATE)))
            STATE[sid] = out["sources"]
            payload = {"answer": out["answer"],
                       "sources": [_lite(s) for s in out["sources"]]}
            bus.emit("System", "result", json.dumps(payload))
        except Exception as e:
            bus.emit("System", "error", str(e))
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.get("/events")
def events(request: Request):
    entry = (sid_of(request), queue.Queue())
    subs.append(entry)

    def gen():
        try:
            while True:
                try:
                    yield f"data: {json.dumps(entry[1].get(timeout=15))}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            subs.remove(entry)
    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- startup ----------
def check_ollama():
    import requests
    try:
        requests.get(orch.cfg["ollama_url"], timeout=3)
        print("Ollama: connected")
    except Exception:
        print("WARNING: Ollama is not running. Start it (ollama serve) for planning and summaries.")


def open_chrome():
    import webbrowser
    url = "http://127.0.0.1:8000"
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(path):
            webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(path))
            webbrowser.get("chrome").open(url)
            return
    webbrowser.open(url)


if __name__ == "__main__":
    import uvicorn
    public = bool(os.getenv("PORT"))
    if not DEMO:
        check_ollama()
    if not public:
        threading.Timer(1.5, open_chrome).start()
    uvicorn.run(app, host="0.0.0.0" if public else "127.0.0.1",
                port=int(os.getenv("PORT", 8000)))