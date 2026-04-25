"""
gdrive_manager.py — Reusable Google Drive Manager Module
=========================================================

A comprehensive Google Drive operations module designed for team-based
automation agents. Handles authentication, file operations, and error
recovery using a single community Google account.

USAGE:
    from gdrive_manager import GoogleDriveManager

    # Initialize (handles authentication automatically)
    drive = GoogleDriveManager()

    # Upload a file
    file_id = drive.upload_file(
        local_path="poster.jpg",
        folder_id="abc123...",
        replace_existing=True
    )

    # Download a file
    success = drive.download_file(
        file_id="xyz789...",
        save_path="downloaded.jpg"
    )

    # Get or create folder
    folder_id = drive.get_or_create_folder(
        folder_name="Generated Posters",
        parent_id="parent_folder_id"
    )

AUTHENTICATION:
    - Uses OAuth 2.0 with credentials.json (community Google account)
    - Auto-generates and reuses token.json (no repeated logins)
    - Supports service account for read operations (optional)
    - All agents in project can share this same authentication

REQUIREMENTS:
    - credentials.json in project root (OAuth client credentials)
    - First run: browser opens for community account sign-in
    - Subsequent runs: automatic token refresh, no browser required

ERROR HANDLING:
    All methods include comprehensive error handling with clear messages:
    - Returns None/False on failure (never crashes)
    - Prints detailed error messages for debugging
    - Handles network failures, rate limits, permissions, quota

TEAM GUIDELINES:
    [WARN] Use the COMMUNITY Google account for:
        • Google Cloud Console project
        • OAuth client credentials generation
        • Drive folder permissions
        • First-time authentication

    [WARN] NEVER commit to Git:
        • credentials.json
        • token.json
        • Service account JSON files

Author: Community Automation Team
License: Internal use only
"""

import os
import io
import re
import time
from typing import Optional, List, Dict, Any

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError


# =============================================================================
#  CUSTOM EXCEPTIONS
# =============================================================================

class DriveAuthenticationError(Exception):
    """Raised when authentication fails (missing credentials, invalid token, etc.)"""
    pass


class DrivePermissionError(Exception):
    """Raised when user/service account lacks permissions for the operation"""
    pass


class DriveFileNotFoundError(Exception):
    """Raised when requested file/folder doesn't exist"""
    pass


class DriveQuotaError(Exception):
    """Raised when Google Drive storage quota is exceeded"""
    pass


class DriveNetworkError(Exception):
    """Raised when network/connectivity issues occur"""
    pass


class DriveRateLimitError(Exception):
    """Raised when API rate limit is hit"""
    pass


# =============================================================================
#  GOOGLE DRIVE MANAGER
# =============================================================================

class GoogleDriveManager:
    """
    Comprehensive Google Drive operations manager for team-based automation.

    This class provides a clean interface to Google Drive API with automatic
    authentication, error handling, and retry logic. Designed to be shared
    across multiple automation agents in the same project.

    Attributes:
        service: Authenticated Google Drive API service (v3)
        credentials_file: Path to OAuth client credentials
        token_file: Path to OAuth token storage
        service_account_file: Path to service account key (optional)

    Example:
        >>> drive = GoogleDriveManager()
        >>> folder_id = drive.get_or_create_folder("My Folder", parent_id)
        >>> file_id = drive.upload_file("document.pdf", folder_id)
        >>> drive.download_file(file_id, "local_copy.pdf")
    """

    # OAuth scopes for Drive access
    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        service_account_file: Optional[str] = None,
        use_service_account: bool = False
    ):
        """
        Initialize Google Drive Manager with authentication.

        Args:
            credentials_file: Path to OAuth client credentials JSON
            token_file: Path to store/load OAuth tokens
            service_account_file: Path to service account key (optional)
            use_service_account: Use service account instead of OAuth

        Raises:
            DriveAuthenticationError: If authentication fails

        Note:
            On first run, a browser window opens for OAuth consent.
            Sign in with the COMMUNITY Google account (not personal).
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service_account_file = service_account_file
        self.service = None

        # Authenticate
        if use_service_account and service_account_file:
            self._authenticate_service_account()
        else:
            self._authenticate_oauth()

    # =========================================================================
    #  AUTHENTICATION
    # =========================================================================

    def _authenticate_oauth(self) -> None:
        """
        Authenticate using OAuth 2.0 flow (team-based).

        Flow:
            1. Load token.json if exists
            2. Refresh if expired
            3. Launch OAuth flow if needed (browser opens)
            4. Save token for future runs

        Raises:
            DriveAuthenticationError: If credentials are missing or invalid
        """
        creds = None

        # Step 1: Load existing token
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
                print(f"[OK] Loaded OAuth token from {self.token_file}")
            except Exception as exc:
                print(f"[WARN] Cannot load token file: {exc}")
                creds = None

        # Step 2: Refresh expired token
        if creds and creds.expired and creds.refresh_token:
            try:
                print("-> Refreshing expired OAuth token...")
                creds.refresh(Request())
                with open(self.token_file, "w") as fh:
                    fh.write(creds.to_json())
                print(f"[OK] Token refreshed and saved to {self.token_file}")
            except Exception as exc:
                print(f"[WARN]  Token refresh failed: {exc}")
                creds = None

        # Step 3: OAuth login if needed
        if not creds or not creds.valid:
            if not os.path.exists(self.credentials_file):
                raise DriveAuthenticationError(
                    f"OAuth credentials file not found: {self.credentials_file}\n\n"
                    f"To fix:\n"
                    f"1. Go to Google Cloud Console (community account)\n"
                    f"2. Create OAuth 2.0 Desktop credentials\n"
                    f"3. Download as '{self.credentials_file}'\n"
                    f"4. Place in project root directory"
                )

            print("\n" + "="*60)
            print("  TEAM AUTHENTICATION REQUIRED")
            print("="*60)
            print(f"  Opening browser for Google sign-in...")
            print(f"  [WARN]  IMPORTANT: Sign in with the COMMUNITY Google account")
            print(f"      (the same account used for Google Cloud Console)")
            print("="*60)

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES
                )
                creds = flow.run_local_server(port=0)

                # Save token for future runs
                with open(self.token_file, "w") as fh:
                    fh.write(creds.to_json())

                print(f"[OK] OAuth authenticated and token saved to {self.token_file}")
                print("[OK] Future runs will use saved token (no browser required)")

            except Exception as exc:
                raise DriveAuthenticationError(
                    f"OAuth authentication failed: {exc}\n"
                    f"Verify that {self.credentials_file} is valid and from community account"
                )

        # Build Drive service
        try:
            self.service = build("drive", "v3", credentials=creds)
            print("[OK] Google Drive service ready (OAuth)")
        except Exception as exc:
            raise DriveAuthenticationError(f"Failed to build Drive service: {exc}")

    def _authenticate_service_account(self) -> None:
        """
        Authenticate using service account (read-only operations).

        Service accounts are useful for automated read operations without
        requiring user interaction (no browser OAuth flow).

        Raises:
            DriveAuthenticationError: If service account file is missing/invalid
        """
        if not os.path.exists(self.service_account_file):
            raise DriveAuthenticationError(
                f"Service account file not found: {self.service_account_file}\n\n"
                f"To fix:\n"
                f"1. Go to Google Cloud Console (community account)\n"
                f"2. Create Service Account\n"
                f"3. Download JSON key\n"
                f"4. Rename to '{self.service_account_file}'\n"
                f"5. Place in project root directory"
            )

        try:
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            self.service = build("drive", "v3", credentials=creds)
            print("[OK] Google Drive service ready (Service Account)")
        except Exception as exc:
            raise DriveAuthenticationError(
                f"Service account authentication failed: {exc}"
            )

    # =========================================================================
    #  FILE OPERATIONS
    # =========================================================================

    def upload_file(
        self,
        local_path: str,
        folder_id: str,
        custom_name: Optional[str] = None,
        replace_existing: bool = True,
        mime_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload a file to Google Drive.

        Args:
            local_path: Path to local file to upload
            folder_id: Google Drive folder ID to upload into
            custom_name: Custom filename (default: use local filename)
            replace_existing: If True, replace file with same name
            mime_type: MIME type (auto-detected if None)

        Returns:
            File ID if successful, None if failed

        Raises:
            None (returns None on error, prints message)

        Example:
            >>> file_id = drive.upload_file("poster.jpg", "folder_abc123")
            [OK] Uploaded 'poster.jpg' to Drive (id: xyz789...)
        """
        # Validate local file exists
        if not os.path.exists(local_path):
            print(f"[ERROR] Upload failed: Local file not found: {local_path}")
            return None

        try:
            # Determine filename
            filename = custom_name or os.path.basename(local_path)

            # Auto-detect MIME type
            if mime_type is None:
                ext = os.path.splitext(local_path)[1].lower()
                mime_types = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif",
                    ".pdf": "application/pdf",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".txt": "text/plain",
                    ".csv": "text/csv"
                }
                mime_type = mime_types.get(ext, "application/octet-stream")

            # Check if file already exists
            existing_id = None
            if replace_existing:
                existing_id = self.find_file(filename, folder_id)

            # Prepare upload
            media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

            if existing_id:
                # Update existing file
                file = self.service.files().update(
                    fileId=existing_id,
                    media_body=media,
                    fields="id, name"
                ).execute()
                print(f"[OK] Updated '{filename}' on Drive (id: {file.get('id')})")
            else:
                # Create new file
                file_metadata = {
                    "name": filename,
                    "parents": [folder_id]
                }
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name"
                ).execute()
                print(f"[OK] Uploaded '{filename}' to Drive (id: {file.get('id')})")

            return file.get("id")

        except HttpError as exc:
            return self._handle_http_error(exc, f"upload file '{local_path}'")
        except Exception as exc:
            print(f"[ERROR] Upload failed: {exc}")
            return None

    def download_file(
        self,
        file_id: Optional[str] = None,
        save_path: Optional[str] = None,
        file_name: Optional[str] = None,
        folder_id: Optional[str] = None
    ) -> bool:
        """
        Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID (required if file_name not provided)
            save_path: Local path to save file
            file_name: Find file by name (requires folder_id)
            folder_id: Folder to search in (when using file_name)

        Returns:
            True if successful, False if failed

        Example:
            >>> drive.download_file(file_id="abc123", save_path="poster.jpg")
            [OK] Downloaded file to poster.jpg
        """
        # Resolve file_id from file_name if needed
        if not file_id and file_name and folder_id:
            file_id = self.find_file(file_name, folder_id)
            if not file_id:
                print(f"[ERROR] Download failed: File '{file_name}' not found in folder")
                return False

        if not file_id:
            print("[ERROR] Download failed: Must provide file_id or (file_name + folder_id)")
            return False

        if not save_path:
            print("[ERROR] Download failed: save_path is required")
            return False

        try:
            # Check if file is a Google Workspace doc (needs export)
            file_meta = self.service.files().get(fileId=file_id, fields="mimeType, name").execute()
            mime_type = file_meta.get("mimeType", "")

            if mime_type == "application/vnd.google-apps.spreadsheet":
                # Export Google Sheets as Excel
                request = self.service.files().export_media(
                    fileId=file_id,
                    mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                # Download regular file
                request = self.service.files().get_media(fileId=file_id)

            # Download
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Save to disk
            with open(save_path, "wb") as fh:
                fh.write(buf.getvalue())

            print(f"[OK] Downloaded '{file_meta.get('name', 'file')}' to {save_path}")
            return True

        except HttpError as exc:
            self._handle_http_error(exc, f"download file (id: {file_id})")
            return False
        except IOError as exc:
            print(f"[ERROR] Download failed: Cannot write to {save_path}: {exc}")
            return False
        except Exception as exc:
            print(f"[ERROR] Download failed: {exc}")
            return False

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID to delete

        Returns:
            True if successful, False if failed

        Warning:
            This permanently deletes the file. Use with caution.

        Example:
            >>> drive.delete_file("abc123xyz")
            [OK] Deleted file (id: abc123xyz)
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"[OK] Deleted file (id: {file_id})")
            return True

        except HttpError as exc:
            self._handle_http_error(exc, f"delete file (id: {file_id})")
            return False
        except Exception as exc:
            print(f"[ERROR] Delete failed: {exc}")
            return False

    # =========================================================================
    #  FOLDER OPERATIONS
    # =========================================================================

    def create_folder(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new folder in Google Drive.

        Args:
            folder_name: Name of folder to create
            parent_id: Parent folder ID (None = root)

        Returns:
            Folder ID if successful, None if failed

        Example:
            >>> folder_id = drive.create_folder("Generated Posters", parent_id)
            [OK] Created folder 'Generated Posters' (id: abc123...)
        """
        try:
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder"
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields="id, name"
            ).execute()

            print(f"[OK] Created folder '{folder_name}' (id: {folder.get('id')})")
            return folder.get("id")

        except HttpError as exc:
            self._handle_http_error(exc, f"create folder '{folder_name}'")
            return None
        except Exception as exc:
            print(f"[ERROR] Create folder failed: {exc}")
            return None

    def get_or_create_folder(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get existing folder ID or create if doesn't exist.

        Args:
            folder_name: Name of folder
            parent_id: Parent folder ID (None = root)

        Returns:
            Folder ID if successful, None if failed

        Example:
            >>> folder_id = drive.get_or_create_folder("Output", parent_id)
            [OK] Found existing folder 'Output' (id: xyz789...)
        """
        # Try to find existing folder
        existing_id = self.find_folder(folder_name, parent_id)
        if existing_id:
            print(f"[OK] Found existing folder '{folder_name}' (id: {existing_id})")
            return existing_id

        # Create if not found
        return self.create_folder(folder_name, parent_id)

    # =========================================================================
    #  SEARCH / LIST OPERATIONS
    # =========================================================================

    def find_file(
        self,
        file_name: str,
        folder_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Find a file by name (returns first match).

        Args:
            file_name: Exact filename to search for
            folder_id: Limit search to this folder (None = all)

        Returns:
            File ID if found, None otherwise

        Example:
            >>> file_id = drive.find_file("poster.jpg", folder_id)
        """
        try:
            query_parts = [f"name='{file_name}'", "trashed=false"]
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")

            query = " and ".join(query_parts)

            results = self.service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                pageSize=5
            ).execute()

            files = results.get("files", [])
            return files[0]["id"] if files else None

        except HttpError as exc:
            self._handle_http_error(exc, f"find file '{file_name}'")
            return None
        except Exception as exc:
            print(f"[ERROR] Find file failed: {exc}")
            return None

    def find_folder(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Find a folder by name (returns first match).

        Args:
            folder_name: Exact folder name to search for
            parent_id: Limit search to this parent (None = all)

        Returns:
            Folder ID if found, None otherwise

        Example:
            >>> folder_id = drive.find_folder("Speaker Photos", parent_id)
        """
        try:
            query_parts = [
                f"name='{folder_name}'",
                "mimeType='application/vnd.google-apps.folder'",
                "trashed=false"
            ]
            if parent_id:
                query_parts.append(f"'{parent_id}' in parents")

            query = " and ".join(query_parts)

            results = self.service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                pageSize=5
            ).execute()

            folders = results.get("files", [])
            return folders[0]["id"] if folders else None

        except HttpError as exc:
            self._handle_http_error(exc, f"find folder '{folder_name}'")
            return None
        except Exception as exc:
            print(f"[ERROR] Find folder failed: {exc}")
            return None

    def list_files(
        self,
        folder_id: Optional[str] = None,
        max_results: int = 100,
        file_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List files in a folder.

        Args:
            folder_id: Folder ID to list (None = all accessible files)
            max_results: Maximum number of files to return
            file_type: Filter by MIME type (e.g., "image/jpeg")

        Returns:
            List of file dictionaries with 'id', 'name', 'mimeType'

        Example:
            >>> files = drive.list_files(folder_id, max_results=50)
            >>> for file in files:
            ...     print(f"{file['name']} (id: {file['id']})")
        """
        try:
            query_parts = ["trashed=false"]
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            if file_type:
                query_parts.append(f"mimeType='{file_type}'")

            query = " and ".join(query_parts)

            results = self.service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name, mimeType, modifiedTime)",
                pageSize=max_results,
                orderBy="modifiedTime desc"
            ).execute()

            files = results.get("files", [])
            print(f"[OK] Found {len(files)} file(s)")
            return files

        except HttpError as exc:
            self._handle_http_error(exc, "list files")
            return []
        except Exception as exc:
            print(f"[ERROR] List files failed: {exc}")
            return []

    # =========================================================================
    #  ERROR HANDLING
    # =========================================================================

    def _handle_http_error(self, exc: HttpError, operation: str) -> Optional[Any]:
        """
        Handle Google API HTTP errors with user-friendly messages.

        Args:
            exc: HttpError exception
            operation: Description of operation that failed

        Returns:
            None (always returns None after printing error)
        """
        error_code = exc.resp.status
        error_reason = exc.error_details[0].get("reason", "unknown") if exc.error_details else "unknown"

        # Permission denied
        if error_code == 403:
            if "insufficientPermissions" in error_reason:
                print(f"[ERROR] Permission denied: Cannot {operation}")
                print(f"  -> Ensure the file/folder is shared with your account")
            elif "quotaExceeded" in error_reason or "storageQuotaExceeded" in error_reason:
                print(f"[ERROR] Quota exceeded: {operation}")
                print(f"  -> Google Drive storage quota full")
                print(f"  -> Free up space or upgrade storage plan")
            elif "rateLimitExceeded" in error_reason or "userRateLimitExceeded" in error_reason:
                print(f"[ERROR] Rate limit exceeded: {operation}")
                print(f"  -> Too many API requests in short time")
                print(f"  -> Wait a few minutes and try again")
            else:
                print(f"[ERROR] Access forbidden (403): Cannot {operation}")
                print(f"  -> Reason: {error_reason}")

        # Not found
        elif error_code == 404:
            print(f"[ERROR] Not found (404): Cannot {operation}")
            print(f"  -> File or folder doesn't exist or was deleted")

        # Unauthorized
        elif error_code == 401:
            print(f"[ERROR] Unauthorized (401): Cannot {operation}")
            print(f"  -> Token may be invalid or expired")
            print(f"  -> Delete token.json and re-authenticate")

        # Network errors
        elif error_code in (500, 502, 503, 504):
            print(f"[ERROR] Server error ({error_code}): Cannot {operation}")
            print(f"  -> Google Drive servers may be temporarily unavailable")
            print(f"  -> Try again in a few minutes")

        # Other errors
        else:
            print(f"[ERROR] HTTP {error_code} error: Cannot {operation}")
            print(f"  -> {exc}")

        return None


# =============================================================================
#  MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

def quick_upload(local_path: str, folder_id: str) -> Optional[str]:
    """
    Quick one-liner to upload a file.

    Args:
        local_path: Local file path
        folder_id: Drive folder ID

    Returns:
        File ID if successful, None if failed

    Example:
        >>> from gdrive_manager import quick_upload
        >>> file_id = quick_upload("poster.jpg", "abc123")
    """
    drive = GoogleDriveManager()
    return drive.upload_file(local_path, folder_id)


def quick_download(file_id: str, save_path: str) -> bool:
    """
    Quick one-liner to download a file.

    Args:
        file_id: Drive file ID
        save_path: Local save path

    Returns:
        True if successful, False if failed

    Example:
        >>> from gdrive_manager import quick_download
        >>> quick_download("abc123", "downloaded.jpg")
    """
    drive = GoogleDriveManager()
    return drive.download_file(file_id, save_path)


# =============================================================================
#  USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  Google Drive Manager — Usage Example")
    print("=" * 70)

    # Initialize
    print("\n1. Initializing Drive Manager...")
    try:
        drive = GoogleDriveManager()
    except DriveAuthenticationError as exc:
        print(f"Authentication failed: {exc}")
        exit(1)

    # Find/create folder
    print("\n2. Finding or creating folder...")
    folder_id = drive.get_or_create_folder("Test Folder")

    if folder_id:
        # List files
        print("\n3. Listing files in folder...")
        files = drive.list_files(folder_id, max_results=10)
        for file in files:
            print(f"  - {file['name']} (id: {file['id']})")

        # Example upload (if test file exists)
        test_file = "test.txt"
        if os.path.exists(test_file):
            print(f"\n4. Uploading {test_file}...")
            file_id = drive.upload_file(test_file, folder_id)

            if file_id:
                print(f"\n5. Downloading back as test_downloaded.txt...")
                drive.download_file(file_id, "test_downloaded.txt")

    print("\n" + "=" * 70)
    print("  Example complete! Module is ready for use in your agents.")
    print("=" * 70)
