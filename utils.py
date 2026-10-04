import re
STOP = {"the","and","for","with","from","that","this","find","show","get","what","when",
        "where","which","about","my","me","any","all","did","does","are","was","have","has",
        "mail","mails","email","emails","subject","your","address","and","not","from","message"}

def keywords(q, n=5):
    words = re.findall(r"\w+", q.lower())
    kws = list(dict.fromkeys(w for w in words if len(w) > 2 and w not in STOP))
    return (kws or words)[:n]
SYNONYMS = {
    "cv": ["resume", "curriculum", "vitae"],
    "resume": ["cv"],
    "pic": ["photo", "image"],
    "photo": ["pic", "image"],
    "invoice": ["bill", "receipt"],
    "bill": ["invoice", "receipt"],
}

def expand_terms(kws):
    out = list(kws)
    for k in kws:
        out += [s for s in SYNONYMS.get(k, []) if s not in out]
    return out