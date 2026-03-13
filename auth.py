"""
Run this script ONCE to authenticate with Google/YouTube.
It will open a browser, ask you to log in, and save token.json.
After that, Claude Desktop will use the saved token automatically.

Usage:
    python auth.py
"""

from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

BASE_DIR = Path(r"C:\youtube-mcp")
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"


def main():
    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: client_secret.json not found in {BASE_DIR}")
        print("Please download it from Google Cloud Console first.")
        return

    print("Opening browser for Google authentication...")
    print("If the browser doesn't open, copy the URL that appears and paste it manually.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)

    # Try to open browser; fall back to console copy-paste if it fails
    try:
        creds = flow.run_local_server(port=0, open_browser=True)
    except Exception:
        creds = flow.run_console()

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅ Success! token.json saved to {TOKEN_FILE}")
    print("You can now restart Claude Desktop and use the YouTube tools.")


if __name__ == "__main__":
    main()
