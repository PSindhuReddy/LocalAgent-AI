import os, re, pickle, pathlib
import numpy as np
from rank_bm25 import BM25Okapi
from agents.base import Agent
from utils import keywords
from utils import expand_terms

TEXT_EXT = {".txt", ".md", ".py", ".csv", ".json", ".log", ".html"}
SKIP = {"credentials.json", "token.json", "permissions.json", "audit_log.jsonl"}
CACHE = pathlib.Path("index_cache.pkl")
tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())

def read_file(p):
    ext = p.suffix.lower()
    if ext in TEXT_EXT:
        return p.read_text(errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    if ext == ".docx":
        import docx
        return "\n".join(x.text for x in docx.Document(str(p)).paragraphs)
    return ""

def chunk(text, size=120, overlap=30):
    w = text.split(); step = size - overlap
    return [" ".join(w[i:i + size]) for i in range(0, max(len(w), 1), step)]

def norm(a):
    a = np.asarray(a, dtype=float)
    return (a - a.min()) / (a.max() - a.min() + 1e-9) if len(a) else a

class LocalRetrievalAgent(Agent):
    name = "LocalFiles"
    SUPPORTED = TEXT_EXT | {".pdf", ".docx"}

    def __init__(self, cfg, llm=None):
        super().__init__(cfg, llm)
        self.chunks, self.meta, self.docs = [], [], []
        self.vecs, self.bm25 = None, None

    def _embed_all(self, texts):
        out = []
        for i in range(0, len(texts), 32):
            out += self.llm.embed(texts[i:i + 32])
        return out

    def _index(self):
        limit = self.cfg["max_file_mb"] * 1024 * 1024
        cache = pickle.loads(CACHE.read_bytes()) if CACHE.exists() else {}
        new_cache, all_vecs, semantic_ok = {}, [], True
        for d in self.cfg["allowed_dirs"]:
            for dp, _, files in os.walk(pathlib.Path(d).expanduser()):
                for f in files:
                    p = pathlib.Path(dp) / f
                    if f in SKIP or p.suffix.lower() not in self.SUPPORTED or p.stat().st_size > limit:
                        continue
                    key, mtime = str(p), p.stat().st_mtime
                    name = " ".join(tok(p.stem))
                    ent = cache.get(key)
                    if not ent or ent["mtime"] != mtime:        # new or changed file
                        try:
                            parts = [c for c in chunk(read_file(p)) if c.strip()]
                        except Exception:
                            parts = []
                        parts = parts or [name]
                        vecs = None
                        if semantic_ok:
                            try:
                                vecs = self._embed_all([f"{name}. {c}" for c in parts])
                            except Exception as e:
                                semantic_ok = False
                                self.log("warning", f"Embeddings unavailable ({e}); keyword search only")
                        ent = {"mtime": mtime, "chunks": parts, "vecs": vecs}
                    new_cache[key] = ent
                    for j, c in enumerate(ent["chunks"]):
                        self.chunks.append(c); self.meta.append(key)
                        self.docs.append(tok(f"{name} {name} {c}"))
                        all_vecs.append(ent["vecs"][j] if ent["vecs"] else None)
        CACHE.write_bytes(pickle.dumps(new_cache))
        if self.docs:
            self.bm25 = BM25Okapi(self.docs)
        if all_vecs and all(v is not None for v in all_vecs):
            m = np.array(all_vecs, dtype=float)
            self.vecs = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
        self.log("info", f"Indexed {len(self.chunks)} chunks "
                         f"({'hybrid' if self.vecs is not None else 'keyword-only'})")

    def retrieve(self, query):
        self.log("running", f"Searching local files: {query}")
        if self.bm25 is None:
            self._index()
        if not self.bm25:
            self.log("done", "No indexable files found"); return []
        qt = expand_terms(keywords(query) or tok(query))
        bm = np.array(self.bm25.get_scores(qt))
        bm_n = bm / (bm.max() + 1e-9)
        cos = np.zeros(len(bm))
        if self.vecs is not None:
            try:
                q = np.array(self.llm.embed([f"{query} {' '.join(qt)}"])[0], dtype=float)
                cos = self.vecs @ (q / (np.linalg.norm(q) + 1e-9))
            except Exception:
                pass
        name_hit = np.array([any(k in set(tok(pathlib.Path(m).stem)) for k in qt)
                             for m in self.meta], dtype=float)
        thr = self.cfg.get("sem_threshold", 0.5)
        sem = (0.5 * norm(cos) + 0.5 * bm_n) if self.vecs is not None else bm_n
        score = sem + 1.0 * name_hit
        best = score.max()
        only_named = bool(name_hit.any())          # a file-name match is a strong signal
        hits, seen = [], set()
        for i in np.argsort(-score):
            if self.meta[i] in seen or score[i] < 0.55 * best:
                continue
            if only_named and not name_hit[i]:
                continue
            is_sem = self.vecs is not None and cos[i] >= thr
            if not (is_sem or bm_n[i] >= 0.3 or name_hit[i]):
                continue
            seen.add(self.meta[i])
            hits.append({"source": "local", "ref": self.meta[i], "text": self.chunks[i],
                         "score": float(score[i]),
                         "semantic": bool(is_sem or name_hit[i])})
            if len(hits) >= self.cfg["top_k"]:
                break
        self.log("done", f"{len(hits)} hit(s)")
        return hits