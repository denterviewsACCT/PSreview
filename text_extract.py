"""
Pull plain-text paragraphs out of a submitted personal statement, whether
it arrived as a .docx or a .pdf. Empty paragraphs (blank lines) are dropped.
"""

import io
import re

from docx import Document
from pypdf import PdfReader

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"


def extract_paragraphs_from_docx(docx_bytes: bytes) -> list[str]:
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _reflow_wrapped_lines(lines: list[str]) -> list[str]:
    """
    Merge PDF line-wrap artifacts back into real paragraphs.

    Many PDFs (especially ones exported from Word docs using "space after"
    paragraph formatting instead of literal blank lines) don't preserve a
    blank line between paragraphs at all -- pypdf's extract_text() then
    just gives us one line per *wrapped* line of text, not one per
    paragraph. Treating every such line as its own paragraph (the old
    behavior) shreds a normal essay into dozens of fragment "paragraphs",
    which both looks wrong in the output docx and breaks anchor/tracked-
    change text matching whenever a comment's exact wording happens to
    straddle one of those artificial line breaks.

    Heuristic: a line that's close to the document's max observed line
    width is almost certainly a mid-paragraph wrap (the renderer just ran
    out of horizontal space), not an intentional paragraph break. A line
    noticeably shorter than that is either the last line of the document
    or an actual paragraph end. We merge lines into a paragraph until we
    hit one of the "short" (real end) lines.
    """
    if not lines:
        return []

    max_width = max(len(l) for l in lines)
    # Lines within 85% of the widest observed line are treated as
    # mid-paragraph wraps rather than paragraph ends.
    threshold = max_width * 0.85

    paragraphs = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if len(line) < threshold:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def extract_paragraphs_from_pdf(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Most PS PDFs (exported from Word/Docs) keep a blank line between
    # paragraphs -- split on that first.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", full_text) if p.strip()]

    # Some PDF exports collapse paragraph breaks entirely, leaving one
    # giant blob with only line-wrap newlines. If splitting on blank lines
    # didn't actually separate anything, fall back to reflowing wrapped
    # lines back into real paragraphs (see _reflow_wrapped_lines) rather
    # than treating every wrapped line as its own paragraph.
    if len(paragraphs) <= 1:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        paragraphs = _reflow_wrapped_lines(lines)

    return paragraphs


def extract_paragraphs(content_bytes: bytes, mime_type: str = DOCX_MIME) -> list[str]:
    """Dispatch to the right extractor based on the (effective) mime type."""
    if mime_type == PDF_MIME:
        return extract_paragraphs_from_pdf(content_bytes)
    return extract_paragraphs_from_docx(content_bytes)


def parse_student_name(filename: str) -> tuple[str, str]:
    """
    Best-effort parse of 'FirstName_LastName' or 'FirstName Lastname - PS...'
    out of an intake filename. Falls back to ('Student', 'Unknown') so the
    pipeline never crashes on a weird filename -- worth checking those by hand.
    """
    stem = re.sub(r"\.(docx|pdf|doc)$", "", filename, flags=re.IGNORECASE)
    stem = re.split(r"[-_]?\s*(PS|Personal Statement)\b", stem, flags=re.IGNORECASE)[0]
    stem = stem.replace("_", " ").strip(" -_")
    parts = stem.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if len(parts) == 1:
        return parts[0], "Unknown"
    return "Student", "Unknown"
