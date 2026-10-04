# from googleapiclient.discovery import build
# from agents.base import Agent
# from google_auth import get_credentials
# from utils import keywords

# class DriveRetrievalAgent(Agent):
#     name = "Drive"

#     def __init__(self, cfg, llm=None):
#         super().__init__(cfg, llm)
#         # self.svc = build("drive", "v3", credentials=get_credentials())
#         self.creds = get_credentials()
#         self.svc = build("drive", "v3", credentials=self.creds, cache_discovery=False)

#     def _text(self, f):
#         mt = f["mimeType"]
#         try:
#             if mt == "application/vnd.google-apps.document":
#                 data = self.svc.files().export(fileId=f["id"], mimeType="text/plain").execute()
#             elif mt.startswith("text/"):
#                 data = self.svc.files().get_media(fileId=f["id"]).execute()
#             else:
#                 return ""
#             return data.decode("utf-8", "ignore")[:1500]
#         except Exception:
#             return ""

#     def retrieve(self, query):
#         self.log("running", f"Searching Drive: {query}")
#         cond = " or ".join(f"fullText contains '{k}'" for k in keywords(query))
#         res = self.svc.files().list(
#             q=f"({cond}) and trashed=false", pageSize=self.cfg["top_k"],
#             fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
#         hits = []
#         for i, f in enumerate(res.get("files", [])):
#             hits.append({"source": "drive",
#                          "ref": f"{f['name']} | {f.get('webViewLink','')}",
#                          "text": self._text(f) or f"(File: {f['name']}, type {f['mimeType']})",
#                          "score": round(1.0 - 0.1 * i, 2)})
#         self.log("done", f"{len(hits)} file(s)")
#         return hits
from googleapiclient.discovery import build
from agents.base import Agent
from google_auth import get_credentials
from utils import keywords

class DriveRetrievalAgent(Agent):
    name = "Drive"

    def __init__(self, cfg, llm=None):
        super().__init__(cfg, llm)
        self.creds = get_credentials()

    def _text(self, svc, f):
        mt = f["mimeType"]
        try:
            if mt == "application/vnd.google-apps.document":
                data = svc.files().export(fileId=f["id"], mimeType="text/plain").execute()
            elif mt.startswith("text/"):
                data = svc.files().get_media(fileId=f["id"]).execute()
            else:
                return ""
            return data.decode("utf-8", "ignore")[:50000]
        except Exception:
            return ""

    def retrieve(self, query):
        self.log("running", f"Searching Drive: {query}")
        svc = build("drive", "v3", credentials=self.creds, cache_discovery=False)
        cond = " or ".join(f"fullText contains '{k}'" for k in keywords(query))
        res = svc.files().list(
            q=f"({cond}) and trashed=false", pageSize=self.cfg["top_k"],
            fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
        hits = []
        for i, f in enumerate(res.get("files", [])):
            full = self._text(svc, f)
            hits.append({"source": "drive", "ref": f"{f['name']} | {f.get('webViewLink','')}",
                         "text": (full or f"(File: {f['name']}, type {f['mimeType']})")[:1500],
                         "full": full,
                         "meta": {"link": f.get("webViewLink", ""),
                                  "modified": f.get("modifiedTime", ""), "type": f["mimeType"]},
                         "score": round(1.0 - 0.1 * i, 2)})
        self.log("done", f"{len(hits)} file(s)")
        return hits