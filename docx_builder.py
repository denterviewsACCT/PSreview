"""
Takes the paragraphs of a personal statement + Claude's structured review
JSON, and produces a complete, valid .docx (as bytes) with:
  - a red bold intro paragraph
  - inline Word comments pinned to sentences
  - tracked changes (w:ins/w:del) for suggested edits
  - a red bold closing paragraph

Anchors are matched with exact-substring search first, then a light
whitespace-normalized fallback. Anything that still can't be found is
NOT silently dropped -- it's collected in `unmatched` and surfaced to
Matthew so nothing gets lost quietly.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

TEMPLATE_PATH = Path(__file__).parent / "templates" / "base_template.docx"

RED_BOLD_PPR = (
    '<w:pPr><w:spacing w:after="200"/><w:rPr><w:b/><w:color w:val="FF0000"/></w:rPr></w:pPr>'
)


def _red_bold_paragraph(text: str) -> str:
    return (
        f"<w:p>{RED_BOLD_PPR}"
        f'<w:r><w:rPr><w:b/><w:color w:val="FF0000"/></w:rPr>'
        f"<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"
    )


def _plain_run(text: str) -> str:
    if not text:
        return ""
    return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class MatchedComment:
    comment_id: int
    author_comment: str
    start: int
    end: int
    old_text: str | None = None
    new_text: str | None = None


@dataclass
class BuildResult:
    docx_bytes: bytes
    unmatched: list[dict] = field(default_factory=list)


def _find_anchor(full_text: str, anchor: str) -> tuple[int, int] | None:
    """Try exact match first, then whitespace-normalized match."""
    idx = full_text.find(anchor)
    if idx != -1:
        return idx, idx + len(anchor)

    norm_anchor = _normalize(anchor)
    norm_full = _normalize(full_text)
    idx = norm_full.find(norm_anchor)
    if idx == -1:
        return None

    # Map the normalized-string offset back to the original string.
    # Walk the original text counting normalized characters consumed.
    orig_pos = 0
    norm_pos = 0
    start = None
    end = None
    i = 0
    while i < len(full_text) and norm_pos <= idx + len(norm_anchor):
        if norm_pos == idx and start is None:
            start = i
        if full_text[i].isspace():
            # collapse runs of whitespace to one, matching _normalize
            if i == 0 or not full_text[i - 1].isspace():
                norm_pos += 1
        else:
            norm_pos += 1
        i += 1
        if norm_pos >= idx + len(norm_anchor) and end is None:
            end = i
            break
    if start is None or end is None:
        return None
    return start, end


def build_reviewed_docx(
    paragraphs: list[str],
    review: dict,
    author: str = "Reviewer",
    initials: str = "R",
    date: str = "2026-01-01T00:00:00Z",
) -> BuildResult:
    full_text = "\n".join(paragraphs)
    # offsets marking where each paragraph starts/ends within full_text
    para_spans = []
    pos = 0
    for p in paragraphs:
        para_spans.append((pos, pos + len(p)))
        pos += len(p) + 1  # +1 for the '\n' joiner

    comments = review.get("comments", [])
    unmatched = []
    matches: list[MatchedComment] = []

    for i, c in enumerate(comments):
        anchor = c.get("anchor", "")
        span = _find_anchor(full_text, anchor)
        if span is None:
            unmatched.append(c)
            continue
        start, end = span
        tracked = c.get("tracked_change")
        old_text, new_text = None, None
        if tracked:
            old = tracked.get("old", "")
            new = tracked.get("new", "")
            old_idx = full_text.find(old, start, end + 1)
            if old_idx == -1:
                # couldn't place the tracked change precisely -- keep the
                # comment anchored to the whole span, but skip the edit
                # rather than risk corrupting the wrong text.
                old_text, new_text = None, None
            else:
                old_text, new_text = old, new
        matches.append(
            MatchedComment(
                comment_id=i,
                author_comment=c.get("comment", ""),
                start=start,
                end=end,
                old_text=old_text,
                new_text=new_text,
            )
        )

    matches.sort(key=lambda m: m.start)

    # Build paragraph XML, splitting each paragraph's plain text around any
    # comment/tracked-change boundaries that fall inside it.
    body_parts = [_red_bold_paragraph(review.get("intro", ""))]

    for p_start, p_end in para_spans:
        para_text = full_text[p_start:p_end]
        # collect boundary cut points local to this paragraph
        cuts = set()
        relevant = [m for m in matches if m.start < p_end and m.end > p_start]
        for m in relevant:
            cuts.add(max(0, m.start - p_start))
            cuts.add(min(len(para_text), m.end - p_start))
            if m.old_text:
                old_local_start = full_text.find(m.old_text, m.start, m.end) - p_start
                if 0 <= old_local_start <= len(para_text):
                    cuts.add(old_local_start)
                    cuts.add(min(len(para_text), old_local_start + len(m.old_text)))
        cut_points = sorted(cuts | {0, len(para_text)})

        runs_xml = []
        for a, b in zip(cut_points, cut_points[1:]):
            segment = para_text[a:b]
            if not segment:
                continue
            # is this segment the exact "old_text" of a tracked change?
            owner = next(
                (
                    m
                    for m in relevant
                    if m.old_text
                    and (full_text.find(m.old_text, m.start, m.end) - p_start) == a
                    and len(m.old_text) == (b - a)
                ),
                None,
            )
            if owner:
                runs_xml.append(
                    f'<w:del w:id="{9000 + owner.comment_id}" w:author="{escape(author)}" w:date="{date}">'
                    f'<w:r><w:delText xml:space="preserve">{escape(segment)}</w:delText></w:r></w:del>'
                )
                runs_xml.append(
                    f'<w:ins w:id="{9500 + owner.comment_id}" w:author="{escape(author)}" w:date="{date}">'
                    f'<w:r><w:t xml:space="preserve">{escape(owner.new_text)}</w:t></w:r></w:ins>'
                )
                continue

            # does a comment range start or end exactly at this segment?
            starts_here = [m for m in relevant if max(0, m.start - p_start) == a]
            ends_here = [m for m in relevant if min(len(para_text), m.end - p_start) == b]

            prefix = "".join(f'<w:commentRangeStart w:id="{m.comment_id}"/>' for m in starts_here)
            suffix = ""
            for m in ends_here:
                suffix += f'<w:commentRangeEnd w:id="{m.comment_id}"/>'
                suffix += (
                    f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
                    f'<w:commentReference w:id="{m.comment_id}"/></w:r>'
                )

            runs_xml.append(prefix + _plain_run(segment) + suffix)

        body_parts.append(f"<w:p><w:pPr><w:spacing w:after=\"200\"/></w:pPr>{''.join(runs_xml)}</w:p>")

    body_parts.append(_red_bold_paragraph(review.get("closing", "")))

    document_xml = _wrap_document(body_parts)
    comments_xml, comments_ext_xml = _build_comments_xml(matches, author, initials, date)

    docx_bytes = _package_docx(document_xml, comments_xml, comments_ext_xml)
    return BuildResult(docx_bytes=docx_bytes, unmatched=unmatched)


def _wrap_document(body_parts: list[str]) -> str:
    header = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
        'xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid" '
        'mc:Ignorable="w14 w15 w16cid" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
        "<w:body>"
    )
    footer = (
        "<w:sectPr>"
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:cols w:space="720"/>'
        '<w:docGrid w:linePitch="360"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return header + "".join(body_parts) + footer


def _build_comments_xml(
    matches: list[MatchedComment], author: str, initials: str, date: str
) -> tuple[str, str]:
    comments_body = []
    ext_body = []
    for m in matches:
        comments_body.append(
            f'<w:comment w:id="{m.comment_id}" w:author="{escape(author)}" '
            f'w:date="{date}" w:initials="{escape(initials)}">'
            f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(m.author_comment)}</w:t></w:r></w:p>"
            "</w:comment>"
        )
        ext_body.append(f'<w15:commentEx w15:paraId="{m.comment_id:08X}" w15:done="0"/>')

    comments_ns = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + "".join(comments_body)
        + "</w:comments>"
    )
    ext_ns = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        '<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
        + "".join(ext_body)
        + "</w15:commentsEx>"
    )
    return comments_ns, ext_ns


def _package_docx(document_xml: str, comments_xml: str, comments_ext_xml: str) -> bytes:
    out_buf = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE_PATH, "r") as template_zip:
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out_zip:
            for item in template_zip.infolist():
                data = template_zip.read(item.filename)
                if item.filename == "word/document.xml":
                    data = document_xml.encode("utf-8")
                elif item.filename == "word/comments.xml":
                    data = comments_xml.encode("utf-8")
                elif item.filename == "word/commentsExtended.xml":
                    data = comments_ext_xml.encode("utf-8")
                out_zip.writestr(item, data)
    return out_buf.getvalue()
