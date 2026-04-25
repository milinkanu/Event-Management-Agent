"""
Google Drive client — uploads transcript, blog, recording.
Copy of core/drive_client.py from the main codebase, 
self-contained here so the post-event agent can run standalone.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from tenacity import retry, stop_after_attempt, wait_exponential

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("drive_client")

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

POST_EVENT_FOLDERS = {
    "01_Photos":        None,
    "02_Recording":     None,
    "03_Transcript":    None,
    "04_Presentations": None,
    "05_Blogs_Drafts":  None,
    "06_Social_Posts":  None,
}


class DriveClient:

    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        sa_path = Path(settings.google_service_account_json)
        if not sa_path.exists():
            raise FileNotFoundError(
                f"Service account JSON not found: {sa_path}\n"
                "Create a Google service account, download the JSON, "
                "and set GOOGLE_SERVICE_ACCOUNT_JSON in config/.env"
            )
        creds = service_account.Credentials.from_service_account_file(
            str(sa_path), scopes=SCOPES
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    # ── Folder management ─────────────────────────────────────────────────────

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        svc   = self._get_service()
        query = (
            f"name=\'{name}\' and "
            "mimeType=\'application/vnd.google-apps.folder\' "
            f"and \'{parent_id}\' in parents and trashed=false"
        )
        res   = svc.files().list(q=query, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name":     name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents":  [parent_id],
        }
        f = svc.files().create(body=meta, fields="id").execute()
        logger.debug(f"Created Drive folder: {name}")
        return f["id"]

    def provision_post_event_folders(
        self,
        event_slug: str,
        root_folder_id: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Create (or reuse) the 04_PostEvent subfolder hierarchy.
        Returns a dict mapping short names → Drive folder IDs.
        e.g. {"02_Recording": "1AbC...", "03_Transcript": "1xYz...", ...}
        """
        root = root_folder_id or settings.google_drive_root_folder_id
        if not root:
            raise RuntimeError(
                "GOOGLE_DRIVE_ROOT_FOLDER_ID not set. "
                "Create a root folder in Drive, share it with the service account, "
                "and set the folder ID in config/.env"
            )

        # Top-level event folder
        event_folder = self._get_or_create_folder(event_slug, root)
        # 04_PostEvent container
        post_event   = self._get_or_create_folder("04_PostEvent", event_folder)

        folder_map: dict[str, str] = {"root": event_folder, "04_PostEvent": post_event}
        for name in POST_EVENT_FOLDERS:
            fid = self._get_or_create_folder(name, post_event)
            folder_map[name] = fid
            logger.debug(f"  Drive folder ready: 04_PostEvent/{name}")

        logger.info(f"Drive folder hierarchy ready for {event_slug}")
        return folder_map

    # ── File upload ───────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def upload_file(
        self,
        local_path: str,
        folder_id: str,
        filename: Optional[str] = None,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Upload a local file to Drive. Returns the shareable view URL."""
        svc   = self._get_service()
        local = Path(local_path)
        name  = filename or local.name

        logger.info(f"Uploading {name} ({local.stat().st_size // 1024} KB) to Drive ...")
        meta  = {"name": name, "parents": [folder_id]}
        media = MediaFileUpload(str(local), mimetype=mime_type, resumable=True)
        f     = svc.files().create(body=meta, media_body=media, fields="id").execute()
        fid   = f["id"]

        self._make_public(svc, fid)
        url = f"https://drive.google.com/file/d/{fid}/view"
        logger.info(f"Uploaded → {url}")
        return url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        folder_id: str,
        mime_type: str = "text/plain",
    ) -> str:
        """Upload raw bytes to Drive. Returns the shareable view URL."""
        svc  = self._get_service()
        meta = {"name": filename, "parents": [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
        f    = svc.files().create(body=meta, media_body=media, fields="id").execute()
        fid  = f["id"]
        self._make_public(svc, fid)
        url = f"https://drive.google.com/file/d/{fid}/view"
        logger.info(f"Bytes uploaded → {url}")
        return url

    @staticmethod
    def _make_public(svc, file_id: str):
        """Grant public read access (anyone with link can view)."""
        svc.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()


drive_client = DriveClient()


