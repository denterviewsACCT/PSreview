"""
Environment configuration for the PS review service.

Required Railway environment variables:
  GOOGLE_SERVICE_ACCOUNT_JSON  - the full contents of the service account JSON key
  ANTHROPIC_API_KEY            - your Anthropic API key
  UPLOADS_FOLDER_ID            - Drive folder ID for "Finished Statements" (intake)
  RETURNED_FOLDER_ID           - Drive folder ID for "Returned Statements" (output)
  POLL_SECRET                  - a random string; the /poll endpoint requires this
                                  as a query param so randos can't trigger it
"""

import os

GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
UPLOADS_FOLDER_ID = os.environ["UPLOADS_FOLDER_ID"]
RETURNED_FOLDER_ID = os.environ["RETURNED_FOLDER_ID"]
POLL_SECRET = os.environ.get("POLL_SECRET", "")

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
