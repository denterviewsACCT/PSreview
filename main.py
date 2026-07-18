"""
Entry point for the ps-review service.

GET/POST /poll?secret=...  -- checks the intake folder for new files,
                              reviews any that don't already have output,
                              uploads results to the returned folder.

Meant to be hit on a schedule (Railway Cron, or an external cron pinging
the URL) rather than run as a constantly-looping worker -- simpler to
reason about and cheaper to run.
"""

import logging
import traceback

from flask import Flask, jsonify, request

import config
import drive_client
from claude_review import review_statement
from docx_builder import build_reviewed_docx
from text_extract import extract_paragraphs, parse_student_name

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ps-review")

app = Flask(__name__)


@app.route("/")
def health():
    return jsonify({"status": "ok"})


@app.route("/poll", methods=["GET", "POST"])
def poll():
    if request.args.get("secret") != config.POLL_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    results = {"processed": [], "skipped": [], "errors": []}

    try:
        intake_files = drive_client.list_folder(config.UPLOADS_FOLDER_ID)
    except Exception as e:
        log.exception("Failed to list intake folder")
        return jsonify({"error": f"could not list intake folder: {e}"}), 500

    for f in intake_files:
        file_id = f["id"]
        filename = f["name"]
        mime_type = f["mimeType"]

        try:
            first, last = parse_student_name(filename)
            output_name = f"{first}_{last}_PS_TO_RETURN.docx"

            if drive_client.file_exists_in_folder(config.RETURNED_FOLDER_ID, output_name):
                results["skipped"].append(filename)
                continue

            log.info("Processing %s", filename)
            docx_bytes = drive_client.download_as_docx_bytes(file_id, mime_type)
            paragraphs = extract_paragraphs(docx_bytes)

            if not paragraphs:
                results["errors"].append(
                    {"file": filename, "error": "no extractable text"}
                )
                continue

            statement_text = "\n".join(paragraphs)
            review = review_statement(statement_text)

            build_result = build_reviewed_docx(paragraphs, review)
            drive_client.upload_docx(
                config.RETURNED_FOLDER_ID, output_name, build_result.docx_bytes
            )

            entry = {"file": filename, "output": output_name}
            if build_result.unmatched:
                entry["unmatched_comments"] = [
                    c.get("comment", "")[:120] for c in build_result.unmatched
                ]
            results["processed"].append(entry)

        except Exception as e:
            log.exception("Failed processing %s", filename)
            results["errors"].append({"file": filename, "error": str(e), "trace": traceback.format_exc()})

    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
