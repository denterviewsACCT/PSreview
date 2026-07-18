"""
Pull plain-text paragraphs out of a .docx file's bytes.
Empty paragraphs (blank lines) are dropped.
"""

import io
import re

from docx import Document


def extract_paragraphs(docx_bytes: bytes) -> list[str]:
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            paragraphs.append(text)
    return paragraphs


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
