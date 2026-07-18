"""
Thin wrapper around the Drive v3 API for the two folders we care about.
"""

import io
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

import config

SCOPES = ["https://www.googleapis.com/auth/drive"]

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


def _get_service():
    info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def list_folder(folder_id: str) -> list[dict]:
    """List all non-trashed files directly inside a folder."""
    service = _get_service()
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, createdTime)",
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def file_exists_in_folder(folder_id: str, filename: str) -> bool:
    service = _get_service()
    safe_name = filename.replace("'", "\\'")
    query = f"'{folder_id}' in parents and trashed = false and name = '{safe_name}'"
    resp = service.files().list(q=query, fields="files(id)").execute()
    return len(resp.get("files", [])) > 0


def download_as_docx_bytes(file_id: str, mime_type: str) -> bytes:
    """
    Download a file's content as .docx bytes.
    Native Google Docs are exported to docx; already-docx files are
    downloaded directly.
    """
    service = _get_service()
    if mime_type == GOOGLE_DOC_MIME:
        request = service.files().export_media(fileId=file_id, mimeType=DOCX_MIME)
    else:
        request = service.files().get_media(fileId=file_id)

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def upload_docx(folder_id: str, filename: str, content_bytes: bytes) -> str:
    """Upload a .docx file to a folder. Returns the new file's ID."""
    service = _get_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(content_bytes),
        mimetype=DOCX_MIME,
        resumable=True,
    )
    result = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    return result["id"]
