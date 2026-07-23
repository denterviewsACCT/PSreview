"""
One-time LOCAL script to get a Google OAuth refresh token for the
PSreview service's Drive access.

Run this once on your own machine (NOT on Railway) as the actual Google
account that owns "Finished Statements" / "Returned Statements". It opens
a browser consent screen, then prints a refresh token you paste into
Railway's env vars.

Usage (client secret is passed as an env var so it's never typed into a
file or a chat -- only your own terminal history, which you control):

    GOOGLE_OAUTH_CLIENT_SECRET=paste_it_here python3 get_refresh_token.py

Requires: pip install google-auth-oauthlib --break-system-packages
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

CLIENT_ID = "710736851057-1radocp88lshftmu0fsr0hkf4a32itvk.apps.googleusercontent.com"

CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
if not CLIENT_SECRET:
    sys.exit(
        "Set GOOGLE_OAUTH_CLIENT_SECRET before running this script, e.g.:\n"
        "  GOOGLE_OAUTH_CLIENT_SECRET=your_secret_here python3 get_refresh_token.py"
    )

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
# Opens your default browser, asks you to log in as the account that owns
# the Drive folders, then redirects to a localhost port this script is
# listening on.
creds = flow.run_local_server(port=0)

print("\n--- Save these to Railway env vars ---")
print("GOOGLE_OAUTH_CLIENT_ID:", CLIENT_ID)
print("GOOGLE_OAUTH_CLIENT_SECRET:", CLIENT_SECRET)
print("GOOGLE_OAUTH_REFRESH_TOKEN:", creds.refresh_token)
