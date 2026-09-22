"""
auth_youtube.py - Interactive one-time authorization helper for YouTube Data API v3.
Starts local server on port 8090, opens default browser, and saves token.json.
"""

import os
import sys
import subprocess
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

class UrlHook:
    def format(self, **kwargs):
        url = kwargs.get("url", "")
        os.makedirs("outputs", exist_ok=True)
        with open("outputs/auth_url.txt", "w", encoding="utf-8") as f:
            f.write(url)
        try:
            subprocess.Popen(f'cmd /c start "" "{url}"', shell=True)
        except Exception as e:
            print(f"Browser launch warning: {e}")
        return f"\n{'='*70}\nACTIVE AUTHORIZATION LINK:\n{url}\n{'='*70}\n"

def main():
    secrets_file = "client_secrets.json"
    if not os.path.exists(secrets_file):
        print(f"ERROR: {secrets_file} not found.")
        sys.exit(1)

    print("Initializing Google OAuth flow...")
    flow = InstalledAppFlow.from_client_secrets_file(
        secrets_file,
        scopes=SCOPES
    )

    print("Starting local server on port 8090...")
    try:
        creds = flow.run_local_server(
            port=8090,
            prompt="consent",
            access_type="offline",
            authorization_prompt_message=UrlHook(),
            open_browser=False
        )

        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        # Test YouTube API call
        yt = build("youtube", "v3", credentials=creds)
        resp = yt.channels().list(mine=True, part="snippet").execute()
        items = resp.get("items", [])
        channel_name = items[0]["snippet"]["title"] if items else "Unknown"

        print(f"\nSUCCESS! Authorized YouTube Channel: {channel_name}")
        print("Saved credentials to token.json!")
    except Exception as e:
        print(f"OAuth server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
