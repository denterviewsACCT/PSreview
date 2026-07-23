"""
Environment configuration for the PS review service.

Required Railway environment variables:
  GOOGLE_OAUTH_CLIENT_ID      - OAuth client ID (Desktop app type)
  GOOGLE_OAUTH_CLIENT_SECRET  - OAuth client secret
  GOOGLE_OAUTH_REFRESH_TOKEN  - refresh token from get_refresh_token.py,
                                run once locally as the account that owns
                                "Finished Statements" / "Returned Statements"
  ANTHROPIC_API_KEY           - your Anthropic API key
  UPLOADS_FOLDER_ID           - Drive folder ID for "Finished Statements" (intake)
  RETURNED_FOLDER_ID          - Drive folder ID for "Returned Statements" (output)
  POLL_SECRET                 - a random string; the /poll endpoint requires this
                                 as a query param so randos can't trigger it
"""

import os

GOOGLE_OAUTH_CLIENT_ID = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
GOOGLE_OAUTH_CLIENT_SECRET = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
GOOGLE_OAUTH_REFRESH_TOKEN = os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
UPLOADS_FOLDER_ID = os.environ["UPLOADS_FOLDER_ID"]
RETURNED_FOLDER_ID = os.environ["RETURNED_FOLDER_ID"]
POLL_SECRET = os.environ.get("POLL_SECRET", "")

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
