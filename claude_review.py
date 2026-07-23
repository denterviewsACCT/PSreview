"""
Calls Claude with the Denterview review prompt and gets back a structured
review via native tool-calling -- that's what makes the output mechanically
assemble-able into a docx with real Word comments and tracked changes.

We use a forced tool call (rather than asking Claude to hand-write a JSON
object as text) so the response is guaranteed well-formed, already-parsed
JSON -- no manual json.loads(), no risk of a stray unescaped quote inside
a comment (e.g. from quoting the student's own text) silently breaking the
whole parse partway through a long response.
"""

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

ANCHOR_RULES = """
IMPORTANT -- rules for submitting your review:

- "anchor" must be copied EXACTLY from the statement text below -- same
  spelling, same punctuation, same capitalization. It will be used for an
  exact substring search, so if it doesn't match character-for-character
  the comment will be silently dropped.
- Keep each anchor as short as possible while still being unique in the
  document -- ideally a single sentence, never a whole paragraph.
- Do not let two anchors overlap each other.
- Omit "tracked_change" entirely if the comment is purely observational
  and doesn't involve an actual text edit.
- When present, tracked_change.old must be an exact substring of the
  anchor (or equal to it), and tracked_change.new is what it should become.
- Be as thorough as the statement requires -- there is no fixed number of
  comments. Follow the full review framework above for what to look for.
"""

SUBMIT_REVIEW_TOOL = {
    "name": "submit_review",
    "description": (
        "Submit the completed structured review of the student's personal "
        "statement: the intro paragraph, the pinned inline comments (with "
        "optional tracked-change edits), and the closing paragraph."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intro": {
                "type": "string",
                "description": "The red bold intro paragraph, 4-6 sentences.",
            },
            "comments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "anchor": {
                            "type": "string",
                            "description": (
                                "Exact verbatim substring from the student's "
                                "statement this comment is pinned to."
                            ),
                        },
                        "comment": {
                            "type": "string",
                            "description": "The comment text, in the normal Denterview voice.",
                        },
                        "tracked_change": {
                            "type": "object",
                            "description": "Optional suggested text edit within the anchor.",
                            "properties": {
                                "old": {
                                    "type": "string",
                                    "description": "Exact substring to delete, within the anchor.",
                                },
                                "new": {
                                    "type": "string",
                                    "description": "The replacement text.",
                                },
                            },
                            "required": ["old", "new"],
                        },
                    },
                    "required": ["anchor", "comment"],
                },
            },
            "closing": {
                "type": "string",
                "description": (
                    "The red bold closing paragraph, ending with the "
                    "second-edits link and sign-off."
                ),
            },
        },
        "required": ["intro", "comments", "closing"],
    },
}


def review_statement(statement_text: str) -> dict:
    # Long timeout + max_retries=1: with streaming, tokens arrive continuously
    # so we should never actually hit this timeout waiting on a big blocking
    # read. It's a safety net for a truly dead connection, not the normal
    # path. Capping retries at 1 (SDK default is 2) limits how many times a
    # single slow-but-legitimate request can be re-sent -- each retry after
    # Claude has already started/finished generating is a second paid call.
    client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=600.0,
        max_retries=1,
    )

    system_prompt = REVIEW_INSTRUCTIONS + "\n\n" + ANCHOR_RULES

    # Non-streaming client.messages.create() waits for Claude to fully
    # finish generating (can take a while for a thorough review) before
    # sending anything back. If our client-side read times out during that
    # wait, Claude has *already finished and been billed for* the
    # generation -- we just failed to receive it, and the caller would have
    # to pay for the whole thing again on retry. Streaming avoids this: we
    # receive tokens as they're produced, so we never sit on one long
    # blocking read.
    with client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=32000,
        # Claude Sonnet 5 runs with adaptive thinking on by default, and
        # max_tokens is a hard cap on thinking + response combined. We don't
        # need reasoning exposed for this task, and forced tool_choice
        # (below) isn't compatible with thinking left on anyway -- disabling
        # it means the whole max_tokens budget goes to the review itself.
        thinking={"type": "disabled"},
        system=system_prompt,
        tools=[SUBMIT_REVIEW_TOOL],
        # Force the tool call rather than leaving it optional -- guarantees
        # we get back a submit_review call with schema-valid, already-parsed
        # JSON instead of free-text that might not even attempt the tool.
        tool_choice={"type": "tool", "name": "submit_review"},
        messages=[
            {
                "role": "user",
                "content": f"Here is the personal statement to review:\n\n{statement_text}",
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude's response was cut off before finishing (hit the max_tokens "
            "limit). Try raising max_tokens further in claude_review.py."
        )

    tool_use_blocks = [b for b in message.content if b.type == "tool_use"]
    if not tool_use_blocks:
        raise RuntimeError(
            "Claude did not return a submit_review tool call. "
            f"stop_reason={message.stop_reason!r}"
        )

    # .input is already a parsed dict -- guaranteed valid against the
    # input_schema above, no json.loads() and no manual escaping to get wrong.
    return tool_use_blocks[0].input
