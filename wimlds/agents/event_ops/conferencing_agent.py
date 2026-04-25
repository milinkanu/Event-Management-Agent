"""
Conferencing Agent — Create Zoom/Teams/GMeet meetings with full recording setup.
Applies Appendix C checklist automatically.
"""
import time
import hmac
import hashlib
import base64
import requests
from typing import Optional

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.orchestrator import AgentResult

logger = get_logger("conferencing_agent")


class ConferencingAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def create_meeting(self, event_data: dict) -> AgentResult:
        """Create meeting on the appropriate platform based on preference/availability."""
        mode = event_data.get("mode", "In-Person")

        if mode == "In-Person":
            logger.info("In-Person event — no conferencing setup needed")
            return AgentResult(success=True, data={"conference_link": ""})

        # Try Zoom first, fall back to Teams, then GMeet
        if settings.zoom_api_key:
            return self._create_zoom(event_data)
        elif settings.teams_client_id:
            return self._create_teams(event_data)
        else:
            return self._create_gmeet_placeholder(event_data)

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _create_zoom(self, event_data: dict) -> AgentResult:
        if self.dry_run:
            logger.info("[DRY-RUN] Would create Zoom meeting")
            return AgentResult(success=True, data={"conference_link": "https://zoom.us/j/DRY_RUN"})

        try:
            token = self._generate_zoom_jwt()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            payload = {
                "topic": event_data.get("event_title", "WiMLDS Pune Meetup"),
                "type": 2,   # Scheduled meeting
                "start_time": self._iso_datetime(event_data),
                "duration": self._duration_minutes(event_data),
                "timezone": "Asia/Kolkata",
                "agenda": event_data.get("subtitle", ""),
                "settings": {
                    # Appendix C checklist
                    "waiting_room":                True,
                    "password_required":           True,
                    "auto_recording":              "cloud",
                    "recording_authentication":    False,
                    "host_video":                  True,
                    "participant_video":           True,
                    "mute_upon_entry":             False,
                    "registrants_email_notification": True,
                    "auto_recording_cloud":        True,
                    # Transcription
                    "automated_recording_cloud_participant_audio_type": "cloud_plus",
                },
            }

            resp = requests.post(
                "https://api.zoom.us/v2/users/me/meetings",
                headers=headers, json=payload, timeout=20
            )
            resp.raise_for_status()
            data = resp.json()
            join_url = data.get("join_url", "")
            logger.info(f"Zoom meeting created: {join_url}")

            return AgentResult(success=True, data={
                "conference_link": join_url,
                "meeting_id": str(data.get("id", "")),
                "meeting_password": data.get("password", ""),
                "platform": "zoom",
            })
        except Exception as e:
            logger.error(f"Zoom creation failed: {e}")
            return AgentResult(success=False, error=str(e))

    def _generate_zoom_jwt(self) -> str:
        """Generate Zoom JWT token."""
        import json
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()

        exp = int(time.time()) + 5400
        payload = base64.urlsafe_b64encode(
            json.dumps({"iss": settings.zoom_api_key, "exp": exp}).encode()
        ).rstrip(b"=").decode()

        sig_input = f"{header}.{payload}".encode()
        sig = hmac.new(settings.zoom_api_secret.encode(), sig_input, hashlib.sha256).digest()
        signature = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

        return f"{header}.{payload}.{signature}"

    # ── MS Teams ──────────────────────────────────────────────────────────────

    def _create_teams(self, event_data: dict) -> AgentResult:
        if self.dry_run:
            logger.info("[DRY-RUN] Would create Teams meeting")
            return AgentResult(success=True, data={"conference_link": "https://teams.microsoft.com/DRY_RUN"})

        try:
            token = self._get_teams_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            payload = {
                "subject": event_data.get("event_title", "WiMLDS Meetup"),
                "startDateTime": self._iso_datetime(event_data),
                "endDateTime":   self._iso_datetime_end(event_data),
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "teamsForBusiness",
                "recordAutomatically": True,
            }

            resp = requests.post(
                f"https://graph.microsoft.com/v1.0/me/events",
                headers=headers, json=payload, timeout=20
            )
            resp.raise_for_status()
            data = resp.json()
            join_url = data.get("onlineMeeting", {}).get("joinUrl", "")
            logger.info(f"Teams meeting created: {join_url}")

            return AgentResult(success=True, data={
                "conference_link": join_url,
                "platform": "teams",
            })
        except Exception as e:
            logger.error(f"Teams creation failed: {e}")
            return AgentResult(success=False, error=str(e))

    def _get_teams_token(self) -> str:
        resp = requests.post(
            f"https://login.microsoftonline.com/{settings.teams_tenant_id}/oauth2/v2.0/token",
            data={
                "client_id":     settings.teams_client_id,
                "client_secret": settings.teams_client_secret,
                "scope":         "https://graph.microsoft.com/.default",
                "grant_type":    "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ── GMeet placeholder ─────────────────────────────────────────────────────

    def _create_gmeet_placeholder(self, event_data: dict) -> AgentResult:
        """
        GMeet creation requires Google Calendar API with a service account.
        Placeholder — implement via Google Calendar API if needed.
        """
        logger.warning("No conferencing credentials configured — manual GMeet link required")
        return AgentResult(
            success=False,
            error="No conferencing API credentials. Please create meeting manually and add link to sheet."
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _iso_datetime(event_data: dict) -> str:
        try:
            import pytz
            from datetime import datetime
            date  = event_data.get("date", "01 Jan 2025")
            start = event_data.get("start_time_ist", "14:00")
            dt_str = f"{date} {start}"
            ist = pytz.timezone("Asia/Kolkata")
            dt = ist.localize(datetime.strptime(dt_str, "%d %b %Y %H:%M"))
            return dt.isoformat()
        except Exception:
            return ""

    @staticmethod
    def _iso_datetime_end(event_data: dict) -> str:
        try:
            import pytz
            from datetime import datetime
            date = event_data.get("date", "01 Jan 2025")
            end  = event_data.get("end_time_ist", "17:00")
            dt_str = f"{date} {end}"
            ist = pytz.timezone("Asia/Kolkata")
            dt = ist.localize(datetime.strptime(dt_str, "%d %b %Y %H:%M"))
            return dt.isoformat()
        except Exception:
            return ""

    @staticmethod
    def _duration_minutes(event_data: dict) -> int:
        try:
            sh, sm = map(int, event_data.get("start_time_ist", "14:00").split(":"))
            eh, em = map(int, event_data.get("end_time_ist", "17:00").split(":"))
            return (eh * 60 + em) - (sh * 60 + sm)
        except Exception:
            return 180




