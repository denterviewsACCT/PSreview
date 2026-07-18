"""
Calls Claude with the Denterview review prompt and asks for a structured
JSON review instead of free-text -- that's what makes the output mechanically
assemble-able into a docx with real Word comments and tracked changes.
"""

import json
from pathlib import Path

import anthropic

import config

PROMPT_PATH = Path(__file__).parent / "review_prompt.md"
MASTER_PROMPT = PROMPT_PATH.read_text()

# Strip the "how to use this prompt" header and the trailing placeholder --
# we only want the actual instructions, since we're calling the API directly
# rather than pasting into chat.
_START_MARKER = "## THE PROMPT"
_END_MARKER = "### NOW REVIEW THIS PERSONAL STATEMENT:"
_start = MASTER_PROMPT.index(_START_MARKER)
_end = MASTER_PROMPT.index(_END_MARKER)
REVIEW_INSTRUCTIONS = MASTER_PROMPT[_start:_end].strip()

JSON_SCHEMA_INSTRUCTIONS = """
IMPORTANT -- output format:

You must respond with ONLY a JSON object, no preamble, no markdown fences,
nothing before or after it. It must match this shape exactly:

{
  "intro": "the red bold intro paragraph, 4-6 sentences, as one string",
  "comments": [
    {
      "anchor": "the EXACT substring from the student's statement this comment is pinned to, copied verbatim, character for character, including punctuation",
      "comment": "the comment text, in your normal Denterview voice",
      "tracked_change": {
        "old": "exact substring to delete, must be contained within or equal to the anchor",
        "new": "the replacement text"
      }
    }
  ],
  "closing": "the red bold closing paragraph, ending with the second-edits link and sign-off, as one string"
}

Rules for "anchor":
- It must be copied EXACTLY from the statement text below -- same spelling,
  same punctuation, same capitalization. It will be used for an exact
  substring search, so if it doesn't match character-for-character the
  comment will be silently dropped.
- Keep each anchor as short as possible while still being unique in the
  document -- ideally a single sentence, never a whole paragraph.
- Do not let two anchors overlap each other.

Rules for "tracked_change":
- Omit this field entirely (do not include the key) if the comment is
  purely observational and doesn't involve an actual text edit.
- When present, "old" must be an exact substring of "anchor" (or equal to
  it), and "new" is what it should become.

Be as thorough as the statement requires -- there is no fixed number of
comments. Follow the full review framework above for what to look for.
"""


def review_statement(statement_text: str) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    system_prompt = REVIEW_INSTRUCTIONS + "\n\n" + JSON_SCHEMA_INSTRUCTIONS

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Here is the personal statement to review:\n\n{statement_text}",
            }
        ],
    )

    raw = "".join(block.text for block in message.content if block.type == "text")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)
