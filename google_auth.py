import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/calendar.readonly",
          "https://www.googleapis.com/auth/tasks.readonly"]

def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            if not creds.has_scopes(SCOPES):          # old token missing a scope
                creds = None
                os.remove("token.json")
        except Exception:
            creds = None
            os.remove("token.json")
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json") or os.path.getsize("credentials.json") == 0:
                raise FileNotFoundError(
                    "credentials.json is missing or empty. Download the Desktop-app "
                    "OAuth client JSON from Google Cloud and save it in the project root.")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            # creds = flow.run_local_server(port=0)
            creds = flow.run_local_server(port=0, timeout_seconds=120)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds