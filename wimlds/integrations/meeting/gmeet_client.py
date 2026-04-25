"""
Google Meet client via Google Calendar API.

Setup (free):
  1. Google Cloud Console → Enable "Google Calendar API"
  2. Create a Service Account, download JSON key
  3. Share your calendar with the service account email (give "Make changes to events")
  4. Set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_CALENDAR_ID in config/.env

Google Meet links are created by attaching conferenceData to a Calendar event.
This requires the conferenceDataVersion=1 query param.
Transcripts are produced via Google Meet's "Record meeting" feature (Workspace only).
For the free tier, Zoom is recommended for automatic transcripts.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timezone, timedelta
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("gmeet_client")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
IST    = timezone(timedelta(hours=5, minutes=30))


@dataclass
class GMeetMeeting:
    event_id:    str
    join_url:    str
    conference_id: str
    platform:    str = "gmeet"
    recording_auto: bool = False   # requires Workspace; False on free tier


class GMeetClient:

    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        sa_path = Path(settings.google_service_account_json)
        if not sa_path.exists():
            raise FileNotFoundError(
                f"Service account JSON not found: {sa_path}. "
                "See config/.env.example for setup instructions."
            )
        creds = service_account.Credentials.from_service_account_file(
            str(sa_path), scopes=SCOPES
        )
        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def create_meeting(self, event_data: dict) -> GMeetMeeting:
        """
        Create a Google Calendar event with an attached Meet conference link.
        Returns a GMeetMeeting with the join URL.
        """
        svc        = self._get_service()
        title      = event_data.get("event_title", "WiMLDS Pune Meetup")
        start_iso  = _build_iso_datetime(event_data, "start")
        end_iso    = _build_iso_datetime(event_data, "end")
        request_id = uuid.uuid4().hex   # idempotency key

        body = {
            "summary":     title,
            "description": event_data.get("subtitle", ""),
            "start":       {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
            "end":         {"dateTime": end_iso,   "timeZone": "Asia/Kolkata"},
            "conferenceData": {
                "createRequest": {
                    "requestId":             request_id,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                },
            },
            "attendees": [],   # add attendees if needed
            "reminders": {"useDefault": True},
        }

        try:
            event = svc.events().insert(
                calendarId=settings.google_calendar_id,
                body=body,
                conferenceDataVersion=1,   # required for Meet creation
                sendUpdates="none",
            ).execute()
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            raise

        conf = event.get("conferenceData", {})
        entry = conf.get("entryPoints", [{}])[0]
        join_url = entry.get("uri", "")
        conf_id  = conf.get("conferenceId", event["id"])

        meeting = GMeetMeeting(
            event_id     = event["id"],
            join_url     = join_url,
            conference_id = conf_id,
        )
        logger.info(f"Google Meet created — {join_url}")
        return meeting


def _build_iso_datetime(event_data: dict, which: str = "start") -> str:
    try:
        from dateutil import parser as dtp
        date_str = event_data.get("date", "01 Jan 2025")
        time_key = "start_time_ist" if which == "start" else "end_time_ist"
        time_str = event_data.get(time_key, "14:00")
        naive = dtp.parse(f"{date_str} {time_str}")
        return naive.replace(tzinfo=IST).isoformat()
    except Exception as e:
        from datetime import datetime
        logger.warning(f"Could not parse datetime: {e}")
        return datetime.now(IST).isoformat()


# Singleton
gmeet_client = GMeetClient()


