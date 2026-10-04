import json, requests

class LocalLLM:
    def __init__(self, cfg):
        self.url, self.model = cfg["ollama_url"], cfg["llm_model"]
        self.embed_model = cfg.get("embed_model", "nomic-embed-text")

    def embed(self, texts):
        r = requests.post(f"{self.url}/api/embed",
                          json={"model": self.embed_model, "input": texts}, timeout=300)
        r.raise_for_status()
        return r.json()["embeddings"]

    def chat(self, system, user, json_mode=False):
        payload = {"model": self.model, "stream": False,
                   "options": {"num_ctx": 4096},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        if json_mode:
            payload["format"] = "json"
        r = requests.post(f"{self.url}/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def chat_json(self, system, user):
        return json.loads(self.chat(system, user, json_mode=True))
    def chat_stream(self, system, user):
        payload = {"model": self.model, "stream": True,
                   "options": {"num_ctx": 4096},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        with requests.post(f"{self.url}/api/chat", json=payload,
                           stream=True, timeout=300) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                tok = d.get("message", {}).get("content", "")
                if tok:
                    yield tok
                if d.get("done"):
                    break