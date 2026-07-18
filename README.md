# Denterview PS Review Automation

Watches your **Personal Statement Uploads / Finished Statements** Drive folder
for new submissions, runs the same review Claude has been doing by hand in
chat (same prompt, same checklist, same voice), and drops a fully marked-up
`_TO_RETURN.docx` (real Word comments + tracked changes, red bold intro/
closing) into **Returned Statements** for you to check before sending.

Nothing auto-sends to students. You still review and send yourself.

## How it works

1. Tally form -> Zapier -> file lands in "Finished Statements" (unchanged,
   already working).
2. Something pings `GET /poll?secret=...` on this service (Railway Cron,
   or any external scheduler -- see below).
3. For every file in "Finished Statements" that doesn't already have a
   matching output in "Returned Statements", the service:
   - downloads it and pulls out the plain text
   - calls Claude with the same review prompt from
     `Denterview_AI_Review_Prompt.md`, asking for a structured JSON review
     instead of free text
   - builds a real .docx with comments/tracked changes from that JSON
   - uploads it to "Returned Statements" as `FirstName_LastName_PS_TO_RETURN.docx`
4. You open "Returned Statements", check it, and send it however you
   already do.

If a comment's anchor text can't be matched back into the document (should
be rare), it's not silently dropped -- it shows up in the `/poll` response
under `unmatched_comments` so you know to check that file by hand.

## Files

- `main.py` -- Flask app, the `/poll` endpoint
- `drive_client.py` -- Google Drive read/write
- `claude_review.py` -- calls Claude, gets structured JSON back
- `docx_builder.py` -- turns that JSON into a real .docx with comments/tracked changes
- `text_extract.py` -- pulls paragraphs out of the downloaded file, parses student name from filename
- `templates/base_template.docx` -- a blank docx shell with the comments infrastructure pre-wired in (don't edit by hand)
- `review_prompt.md` -- your master review prompt (copy this over any time you update it in your own docs -- the service reads it fresh on each deploy)

## Deploying to Railway

1. Push this folder to a new GitHub repo (e.g. `denterview-ps-review`).
2. In Railway, **New Project -> Deploy from GitHub repo**, pick it. I'd keep
   it as its own Railway service/project rather than adding it to
   denterview-ai, so a slow or failed review run never touches your
   production app.
3. Set the **Start Command** to:
   ```
   gunicorn -w 2 -b 0.0.0.0:$PORT main:app
   ```
4. Add these environment variables in Railway:

   | Variable | Value |
   |---|---|
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | paste the entire contents of the service account JSON key file |
   | `ANTHROPIC_API_KEY` | your Anthropic API key |
   | `UPLOADS_FOLDER_ID` | `1lkrREU1dz0R63HA6uICp6Dl5Mentz4O7` (Finished Statements) |
   | `RETURNED_FOLDER_ID` | `1oKMqg6VHnZ0Lft3pmPqCNf7v4O-FXxwe` (Returned Statements) |
   | `POLL_SECRET` | any random string you make up, e.g. output of `openssl rand -hex 16` |

5. Deploy. Once it's live, Railway gives you a public URL like
   `https://denterview-ps-review-production.up.railway.app`.
6. Set up the schedule -- easiest option is **Railway's Cron Schedule**
   (Settings -> Cron Schedule on the service) set to something like every
   10 minutes (`*/10 * * * *`), with the command:
   ```
   curl "https://<your-railway-url>/poll?secret=<your POLL_SECRET>"
   ```
   Alternatively, a free external cron pinger (e.g. cron-job.org) hitting
   that same URL on a schedule works just as well and doesn't need Railway's
   cron feature at all.

## Testing it

Hit the URL yourself once it's deployed:
```
curl "https://<your-railway-url>/poll?secret=<your POLL_SECRET>"
```
It returns JSON: which files were processed, which were skipped (already
had output), and any errors. Drop a test PS into "Finished Statements"
first and confirm a `_TO_RETURN.docx` shows up in "Returned Statements"
after hitting `/poll`.

## What's still manual (by design)

- Sending the reviewed file to the student -- you review it in "Returned
  Statements" first, always.
- Updating the review prompt/checklist as your style evolves -- edit
  `review_prompt.md` and redeploy.

## If quality drifts over time

Right now the "memory" of your past reviews is baked into
`review_prompt.md` as fixed example comments. If after a few dozen more
reviews you notice the automated output starting to feel generic compared
to what you'd do by hand, that's the signal to add more real examples into
the prompt (or move to a retrieval-based system that pulls a similar past
fix on the fly) -- not something to build preemptively.
