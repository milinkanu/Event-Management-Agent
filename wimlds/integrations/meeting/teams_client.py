"""
Microsoft Teams client for the WiMLDS Post-Event Agent.
Drop-in replacement for zoom_client.py.

Uses Microsoft Graph API to:
  1. Find the online meeting by join URL or meeting ID
  2. Wait for and download the recording (.mp4)
  3. Download the transcript (.vtt)

Authentication: Azure App Registration (Client Credentials flow)
  - No user login required — works headlessly as a background agent
  - Requires: TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET
  - Requires: TEAMS_USER_ID (the organiser's Azure object ID)

Graph API endpoints used:
  GET /users/{userId}/onlineMeetings?$filter=joinWebUrl eq '{url}'
  GET /users/{userId}/onlineMeetings/{meetingId}/recordings
  GET /users/{userId}/onlineMeetings/{meetingId}/recordings/{recordingId}/content
  GET /users/{userId}/onlineMeetings/{meetingId}/transcripts
  GET /users/{userId}/onlineMeetings/{meetingId}/transcripts/{transcriptId}/content

Required Azure App permissions (Application, not Delegated):
  OnlineMeetings.Read.All
  OnlineMeetingRecording.Read.All
  OnlineMeetingTranscript.Read.All

These are Application permissions — grant admin consent in Azure portal.
"""
from __future__ import annotations

import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from wimlds.core.logger import get_logger

logger = get_logger("teams_client")

# Graph API base URL
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# How long to wait for recording to appear after meeting ends (seconds)
RECORDING_POLL_INTERVAL = 30   # check every 30 seconds
RECORDING_MAX_WAIT      = 1800  # give up after 30 minutes


@dataclass
class TeamsRecording:
    """Represents a Teams meeting recording fetched via Graph API."""
    recording_id:    str
    meeting_id:      str
    created_at:      str
    download_url:    str          # direct download URL (expires in ~1 hour)
    file_size_bytes: int = 0
    duration_seconds: int = 0


# ════════════════════════════════════════════════════════════════════════════
class TeamsClient:
    """
    Fetches recordings and transcripts from Microsoft Teams via Graph API.

    How to get your credentials (one-time setup):
      1. Go to portal.azure.com
      2. Azure Active Directory → App registrations → New registration
      3. Name: WiMLDS Post Event Agent  |  Account type: Single tenant
      4. Click Register
      5. Copy: Application (client) ID  → TEAMS_CLIENT_ID
      6. Copy: Directory (tenant) ID    → TEAMS_TENANT_ID
      7. Certificates & secrets → New client secret → Copy → TEAMS_CLIENT_SECRET
      8. API permissions → Add → Microsoft Graph → Application permissions:
           OnlineMeetings.Read.All
           OnlineMeetingRecording.Read.All
           OnlineMeetingTranscript.Read.All
      9. Click "Grant admin consent"
     10. TEAMS_USER_ID: your organiser's Azure object ID
           → Azure AD → Users → click your user → copy Object ID
    """

    def __init__(self):
        from wimlds.config.settings import settings
        self.tenant_id     = settings.teams_tenant_id
        self.client_id     = settings.teams_client_id
        self.client_secret = settings.teams_client_secret
        self.user_id       = settings.teams_user_id

        self._token:       Optional[str]  = None
        self._token_expiry: float         = 0.0

    # ── Authentication ────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Get or refresh the OAuth2 access token using client credentials flow."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = requests.post(url, data={
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "scope":         "https://graph.microsoft.com/.default",
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        self._token        = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        logger.debug("Teams OAuth token refreshed")
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json",
        }

    # ── Meeting lookup ────────────────────────────────────────────────────────

    def get_meeting_by_join_url(self, join_url: str) -> dict:
        """
        Look up a Teams meeting by its join URL.
        The join URL looks like: https://teams.microsoft.com/l/meetup-join/...

        Returns the onlineMeeting object which contains the meeting ID.
        """
        # URL-encode the join URL for the filter query
        from urllib.parse import quote
        encoded_url = quote(join_url, safe="")
        endpoint = (
            f"{GRAPH_BASE}/users/{self.user_id}/onlineMeetings"
            f"?$filter=joinWebUrl eq '{join_url}'"
        )
        resp = requests.get(endpoint, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        meetings = resp.json().get("value", [])
        if not meetings:
            raise ValueError(f"No meeting found for join URL: {join_url}")
        logger.info(f"Found meeting: {meetings[0].get('subject','?')}")
        return meetings[0]

    def get_meeting_by_id(self, meeting_id: str) -> dict:
        """Look up a meeting by its Graph meeting ID (the long encoded string)."""
        endpoint = f"{GRAPH_BASE}/users/{self.user_id}/onlineMeetings/{meeting_id}"
        resp = requests.get(endpoint, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Recording ─────────────────────────────────────────────────────────────

    def list_recordings(self, meeting_id: str) -> list:
        """List all recordings for a meeting. Returns empty list if none yet."""
        endpoint = (
            f"{GRAPH_BASE}/users/{self.user_id}"
            f"/onlineMeetings/{meeting_id}/recordings"
        )
        resp = requests.get(endpoint, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("value", [])

    @retry(
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=30, min=30, max=120),
        reraise=True,
    )
    def wait_for_recording(self, meeting_id: str) -> TeamsRecording:
        """
        Poll until the recording is available (Teams takes 5–20 min after meeting ends).
        Retries every 30 seconds for up to 30 minutes.
        """
        recordings = self.list_recordings(meeting_id)
        if not recordings:
            logger.info("Recording not yet available — waiting 30 seconds...")
            raise RuntimeError("Recording not yet available")

        rec = recordings[0]  # take the first/latest recording
        rec_id = rec["id"]

        # Get the download URL
        content_url = (
            f"{GRAPH_BASE}/users/{self.user_id}"
            f"/onlineMeetings/{meeting_id}/recordings/{rec_id}/content"
        )

        logger.info(f"Recording available: id={rec_id}")
        return TeamsRecording(
            recording_id  = rec_id,
            meeting_id    = meeting_id,
            created_at    = rec.get("createdDateTime", ""),
            download_url  = content_url,
        )

    def download_recording(self, recording: TeamsRecording) -> Path:
        """
        Download the recording .mp4 to a temp file.
        Returns the local file path.
        """
        logger.info("Downloading Teams recording...")
        headers = self._headers()

        resp = requests.get(recording.download_url, headers=headers,
                            stream=True, timeout=300)
        resp.raise_for_status()

        suffix = ".mp4"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        size = 0
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)
                size += len(chunk)
        tmp.close()

        recording.file_size_bytes = size
        logger.info(f"Recording downloaded: {size // (1024*1024)} MB → {tmp.name}")
        return Path(tmp.name)

    # ── Transcript ────────────────────────────────────────────────────────────

    def list_transcripts(self, meeting_id: str) -> list:
        """List all transcripts for a meeting. Returns empty list if none."""
        endpoint = (
            f"{GRAPH_BASE}/users/{self.user_id}"
            f"/onlineMeetings/{meeting_id}/transcripts"
        )
        resp = requests.get(endpoint, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("value", [])

    def download_transcript(self, meeting_id: str) -> Optional[Path]:
        """
        Download the .vtt transcript for a meeting.
        Returns local file path, or None if no transcript available.
        """
        transcripts = self.list_transcripts(meeting_id)
        if not transcripts:
            logger.warning("No transcript available for this meeting")
            return None

        transcript = transcripts[0]
        transcript_id = transcript["id"]

        content_url = (
            f"{GRAPH_BASE}/users/{self.user_id}"
            f"/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content"
            f"?$format=text/vtt"
        )

        resp = requests.get(content_url, headers=self._headers(), timeout=60)
        resp.raise_for_status()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".vtt",
                                          mode="wb")
        tmp.write(resp.content)
        tmp.close()

        logger.info(f"Transcript downloaded: {len(resp.content)} bytes → {tmp.name}")
        return Path(tmp.name)

    # ── Convenience: full fetch ───────────────────────────────────────────────

    def fetch_meeting_artifacts(
        self,
        join_url:   Optional[str] = None,
        meeting_id: Optional[str] = None,
    ) -> tuple[Optional[Path], Optional[Path]]:
        """
        High-level method: given a join URL or meeting ID, return:
          (recording_path, transcript_path)

        Either path may be None if the artifact is not available.
        """
        if not join_url and not meeting_id:
            raise ValueError("Provide either join_url or meeting_id")

        # Resolve meeting ID
        if meeting_id:
            meeting = self.get_meeting_by_id(meeting_id)
        else:
            meeting = self.get_meeting_by_join_url(join_url)
            meeting_id = meeting["id"]

        logger.info(f"Fetching artifacts for: {meeting.get('subject','?')}")

        # Recording
        recording_path = None
        try:
            recording = self.wait_for_recording(meeting_id)
            recording_path = self.download_recording(recording)
        except Exception as e:
            logger.warning(f"Could not fetch recording: {e}")

        # Transcript
        transcript_path = None
        try:
            transcript_path = self.download_transcript(meeting_id)
        except Exception as e:
            logger.warning(f"Could not fetch transcript: {e}")

        return recording_path, transcript_path


# Singleton
teams_client = TeamsClient()


