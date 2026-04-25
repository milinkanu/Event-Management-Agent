"""
Zoom Server-to-Server OAuth client.

Setup (free):
  1. Go to marketplace.zoom.us → Build App → Server-to-Server OAuth
  2. Add scopes: meeting:read:admin, meeting:write:admin,
                 recording:read:admin, cloud_recording:read:admin
  3. Set ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET in config/.env

This uses the modern Server-to-Server OAuth — JWT auth is deprecated
and no longer accepted for new apps.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("zoom_client")

_ZOOM_API  = "https://api.zoom.us/v2"
_TOKEN_URL = "https://zoom.us/oauth/token"

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class ZoomMeeting:
    meeting_id: str
    join_url: str
    password: str
    start_url: str          # host-only link
    recording_auto: bool    # whether cloud recording is enabled
    platform: str = "zoom"


@dataclass
class ZoomRecording:
    meeting_id: str
    topic: str
    start_time: str
    download_url: str       # mp4 download
    play_url: str           # in-browser playback
    transcript_download_url: Optional[str]  # VTT/plain-text transcript
    duration_minutes: int
    file_size_mb: float


class ZoomClient:
    """
    Zoom Server-to-Server OAuth client.
    Token is cached in-process and refreshed before expiry.
    """

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if within 60 s of expiry."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        if not all([settings.zoom_account_id, settings.zoom_client_id, settings.zoom_client_secret]):
            raise RuntimeError(
                "Zoom credentials missing. Set ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, "
                "ZOOM_CLIENT_SECRET in config/.env"
            )

        creds = base64.b64encode(
            f"{settings.zoom_client_id}:{settings.zoom_client_secret}".encode()
        ).decode()

        resp = requests.post(
            _TOKEN_URL,
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":  "account_credentials",
                "account_id":  settings.zoom_account_id,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()

        self._access_token = payload["access_token"]
        self._token_expiry  = time.time() + payload.get("expires_in", 3600)
        logger.debug("Zoom access token refreshed")
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json",
        }

    # ── Meeting creation ──────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10),
        retry=retry_if_exception_type(requests.HTTPError),
    )
    def create_meeting(self, event_data: dict) -> ZoomMeeting:
        """
        Create a scheduled Zoom meeting with the full Appendix C checklist
        (waiting room, cloud recording, auto-transcription, passcode).
        """
        title     = event_data.get("event_title", "WiMLDS Pune Meetup")
        start_iso = _build_iso_datetime(event_data)
        duration  = _calc_duration_minutes(event_data)

        payload = {
            "topic":      title,
            "type":       2,          # scheduled
            "start_time": start_iso,
            "duration":   duration,
            "timezone":   "Asia/Kolkata",
            "agenda":     event_data.get("subtitle", ""),
            "settings": {
                # ── Appendix C checklist ──────────────────────────────────
                "waiting_room":               True,
                "passcode":                   _generate_passcode(),
                "host_video":                 True,
                "participant_video":          True,
                "mute_upon_entry":            False,
                "auto_recording":             "cloud",   # cloud recording ON
                "recording_authentication":   False,     # attendees can view
                "allow_multiple_devices":     True,
                # Transcription (requires Business/Enterprise plan)
                # On free plan this silently no-ops — recording still works
                "cloud_recording_transcription": True,
                "audio_type":                 "both",    # VoIP + phone
                "approval_type":              0,         # auto-approve registrants
                "registrants_email_notification": True,
            },
        }

        resp = requests.post(
            f"{_ZOOM_API}/users/me/meetings",
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        meeting = ZoomMeeting(
            meeting_id   = str(data["id"]),
            join_url     = data["join_url"],
            password     = data.get("password", ""),
            start_url    = data.get("start_url", ""),
            recording_auto = True,
        )
        logger.info(f"Zoom meeting created — ID {meeting.meeting_id} | {meeting.join_url}")
        return meeting

    # ── Recording retrieval ───────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=60))
    def get_recording(self, meeting_id: str) -> Optional[ZoomRecording]:
        """
        Fetch the cloud recording for a completed meeting.
        Zoom takes 5-30 minutes to process recordings after the meeting ends.
        The retry decorator handles the wait transparently.
        """
        resp = requests.get(
            f"{_ZOOM_API}/meetings/{meeting_id}/recordings",
            headers=self._headers(),
            timeout=20,
        )

        if resp.status_code == 404:
            logger.info(f"Recording not ready yet for meeting {meeting_id} — will retry")
            raise requests.HTTPError("404 — recording not yet available", response=resp)

        resp.raise_for_status()
        data = resp.json()

        if not data.get("recording_files"):
            raise requests.HTTPError("No recording files yet", response=resp)

        files = data["recording_files"]

        # Find the mp4 (shared_screen_with_speaker_view is best for events)
        mp4 = next(
            (f for f in files if f.get("file_type") == "MP4"
             and f.get("recording_type") == "shared_screen_with_speaker_view"),
            next((f for f in files if f.get("file_type") == "MP4"), None),
        )

        # Transcript: Zoom produces a .vtt and a .transcript file
        transcript_file = next(
            (f for f in files if f.get("file_type") in ("TRANSCRIPT", "VTT")), None
        )

        if not mp4:
            logger.warning("No MP4 found in recording files")
            return None

        size_mb = round(mp4.get("file_size", 0) / (1024 * 1024), 1)

        recording = ZoomRecording(
            meeting_id              = meeting_id,
            topic                   = data.get("topic", ""),
            start_time              = data.get("start_time", ""),
            download_url            = mp4["download_url"],
            play_url                = mp4.get("play_url", ""),
            transcript_download_url = transcript_file["download_url"] if transcript_file else None,
            duration_minutes        = data.get("duration", 0),
            file_size_mb            = size_mb,
        )
        logger.info(
            f"Recording ready — {size_mb} MB | "
            f"transcript: {'yes' if transcript_file else 'no'}"
        )
        return recording

    def download_recording(self, download_url: str, dest_path: str, token: Optional[str] = None) -> str:
        """
        Download a recording file to disk.
        Returns the local path.
        Zoom download URLs require the Bearer token for private recordings.
        """
        tok = token or self._get_token()
        headers = {"Authorization": f"Bearer {tok}"}
        logger.info(f"Downloading recording to {dest_path} ...")

        with requests.get(download_url, headers=headers, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        logger.info(f"Download complete: {dest_path}")
        return dest_path

    def download_transcript(self, transcript_url: str, dest_path: str) -> str:
        """Download the Zoom auto-transcript (VTT or plain text)."""
        tok = self._get_token()
        headers = {"Authorization": f"Bearer {tok}"}
        resp = requests.get(transcript_url, headers=headers, timeout=60)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"Transcript downloaded: {dest_path}")
        return dest_path

    def delete_recording(self, meeting_id: str):
        """Delete cloud recording to free Zoom storage (call after uploading to Drive)."""
        resp = requests.delete(
            f"{_ZOOM_API}/meetings/{meeting_id}/recordings",
            headers=self._headers(),
            params={"action": "trash"},
            timeout=20,
        )
        if resp.status_code == 204:
            logger.info(f"Recording deleted from Zoom cloud: {meeting_id}")
        else:
            logger.warning(f"Could not delete recording: {resp.status_code}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_iso_datetime(event_data: dict) -> str:
    """Convert sheet date + time → ISO 8601 with IST offset."""
    try:
        from dateutil import parser as dtp
        date_str = event_data.get("date", "01 Jan 2025")
        time_str = event_data.get("start_time_ist", "14:00")
        naive = dtp.parse(f"{date_str} {time_str}")
        aware = naive.replace(tzinfo=IST)
        return aware.isoformat()
    except Exception as e:
        logger.warning(f"Could not parse event datetime: {e}")
        return datetime.now(IST).isoformat()


def _calc_duration_minutes(event_data: dict) -> int:
    try:
        sh, sm = map(int, event_data.get("start_time_ist", "14:00").split(":"))
        eh, em = map(int, event_data.get("end_time_ist", "17:00").split(":"))
        return max(30, (eh * 60 + em) - (sh * 60 + sm))
    except Exception:
        return 180


def _generate_passcode() -> str:
    """Generate a 6-char alphanumeric passcode Zoom accepts."""
    import random, string
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


# ── Singleton ─────────────────────────────────────────────────────────────────
zoom_client = ZoomClient()


