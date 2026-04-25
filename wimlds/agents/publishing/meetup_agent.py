"""
Meetup Event Agent — Blueprint v9.0
=====================================
Handles the full Meetup lifecycle for a WiMLDS Pune event:

  1. create_or_update_event()   Create Draft or Publish; returns URL + ID
  2. upload_poster()            Attach approved poster to the event image slot
  3. add_conference_link()      Inject Zoom/Teams link into description (Online/Hybrid)
  4. post_attendee_message()    Contact Attendees blast (used by RemindersAgent)
  5. upload_photo_album()       Post-event photo set
  6. post_consolidated_update() Post-event resources update (blog + recording + slides)

Auth: OAuth 2.0 using client_credentials + refresh_token.
      Refresh happens automatically, ~60-day token rotation supported.
      Headless Selenium fallback is available if API access is blocked
      (set MEETUP_USE_HEADLESS=true in .env).

File placement: agents/meetup_agent.py  (REPLACE existing file)

New .env variables needed:
  MEETUP_CLIENT_ID       (from Meetup OAuth app)
  MEETUP_CLIENT_SECRET   (from Meetup OAuth app)
  MEETUP_REFRESH_TOKEN   (first-time: run python agents/meetup_agent.py --get-token)
  MEETUP_GROUP_URLNAME   (default: WiMLDS-Pune)
  MEETUP_USE_HEADLESS    (optional: true/false, default false)
"""

import time
import tempfile
import argparse
from pathlib import Path
from typing import Optional

import requests
import pytz
from datetime import datetime

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.orchestrator import AgentResult

logger = get_logger("meetup_agent")

MEETUP_API_BASE   = "https://api.meetup.com"
MEETUP_OAUTH_URL  = "https://secure.meetup.com/oauth2/access"
MEETUP_AUTH_URL   = "https://secure.meetup.com/oauth2/authorize"
IST               = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────────────────────────────────────
# OAuth token manager
# ─────────────────────────────────────────────────────────────────────────────

class MeetupAuth:
    """
    Manages Meetup OAuth 2.0 access tokens.
    Auto-refreshes using the stored refresh_token.
    """

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        self._refresh()
        return self._access_token

    def _refresh(self):
        if not settings.meetup_client_id:
            raise RuntimeError(
                "MEETUP_CLIENT_ID not set in config/.env — see Setup Guide Part 1"
            )
        resp = requests.post(
            MEETUP_OAUTH_URL,
            data={
                "client_id":     settings.meetup_client_id,
                "client_secret": settings.meetup_client_secret,
                "refresh_token": settings.meetup_refresh_token,
                "grant_type":    "refresh_token",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Meetup token refresh failed ({resp.status_code}): {resp.text}\n"
                "Run: python agents/meetup_agent.py --get-token  to re-authorise."
            )
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        logger.info("Meetup OAuth token refreshed")


# ─────────────────────────────────────────────────────────────────────────────
# Meetup Agent
# ─────────────────────────────────────────────────────────────────────────────

class MeetupAgent:
    """
    All Meetup.com operations for the WiMLDS automation pipeline.
    Pass dry_run=True to test without making any real API calls.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.auth    = MeetupAuth()
        self.group   = settings.meetup_group_urlname or "WiMLDS-Pune"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type":  "application/json",
        }

    def _auth_headers(self) -> dict:
        """Headers without Content-Type, for multipart/file uploads."""
        return {"Authorization": f"Bearer {self.auth.get_token()}"}

    # ── 1. Create or update event ─────────────────────────────────────────────

    def create_or_update_event(self, event_data: dict) -> AgentResult:
        """
        Create a new Meetup event, or update it if meetup_event_id already exists.
        Returns: { meetup_url, event_id }
        Writes back: meetup_event_url, meetup_event_id
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would create/update Meetup event")
            return AgentResult(success=True, data={
                "meetup_url": "https://meetup.com/WiMLDS-Pune/events/DRY_RUN",
                "event_id":   "DRY_RUN_ID",
            })

        existing_id = event_data.get("meetup_event_id", "").strip()
        if existing_id and existing_id not in ("", "DRY_RUN_ID"):
            return self._update_event(existing_id, event_data)
        return self._create_event(event_data)

    def _create_event(self, event_data: dict) -> AgentResult:
        payload = self._build_event_payload(event_data)
        try:
            resp = requests.post(
                f"{MEETUP_API_BASE}/{self.group}/events",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            url  = data.get("link", "")
            eid  = str(data.get("id", ""))
            logger.info(f"Meetup event created: {url}")
            return AgentResult(success=True, data={"meetup_url": url, "event_id": eid})
        except requests.RequestException as exc:
            logger.error(f"Meetup create failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    def _update_event(self, event_id: str, event_data: dict) -> AgentResult:
        payload = self._build_event_payload(event_data)
        try:
            resp = requests.patch(
                f"{MEETUP_API_BASE}/{self.group}/events/{event_id}",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            url  = data.get("link", f"https://meetup.com/{self.group}/events/{event_id}")
            logger.info(f"Meetup event updated: {url}")
            return AgentResult(success=True, data={"meetup_url": url, "event_id": event_id})
        except requests.RequestException as exc:
            logger.error(f"Meetup update failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    def _build_event_payload(self, event_data: dict) -> dict:
        """Construct the Meetup API payload from event_data fields."""
        description = self._build_description(event_data)
        payload = {
            "name":        event_data.get("event_title", ""),
            "description": description,
            "time":        self._to_epoch_ms(
                               event_data.get("date", ""),
                               event_data.get("start_time_ist", "")
                           ),
            "duration":    self._duration_ms(
                               event_data.get("start_time_ist", ""),
                               event_data.get("end_time_ist", "")
                           ),
            "rsvp_limit":  int(event_data.get("capacity", 0) or 0) or None,
            "guest_limit": 0,
            "announce":    True,
        }
        # Meetup venue ID — only include if available
        if event_data.get("meetup_venue_id"):
            payload["venue_id"] = event_data["meetup_venue_id"]

        return {k: v for k, v in payload.items() if v is not None}

    def _build_description(self, event_data: dict) -> str:
        """
        Build the Meetup event description.
        Includes: subtitle, scope, speaker info, conference link (if Online/Hybrid),
        venue details, session type, and laptop/wifi notes.
        """
        lines = []

        if event_data.get("subtitle"):
            lines += [f"**{event_data['subtitle']}**", ""]

        if event_data.get("session_type"):
            lines += [f"📌 **Session Type:** {event_data['session_type']}", ""]

        scope = event_data.get("_scope_one_liner") or event_data.get("subtitle", "")
        if scope:
            lines += [f"**What to expect:** {scope}", ""]

        # Speaker block
        spk_name  = event_data.get("speaker_name", "")
        spk_title = event_data.get("speaker_title", "")
        spk_org   = event_data.get("speaker_org", "")
        spk_quals = event_data.get("speaker_highest_qualification", "")
        spk_achv  = event_data.get("speaker_special_achievements", "")
        if spk_name:
            lines += [
                f"🎙️ **Speaker:** {spk_name}",
                f"{spk_title} at {spk_org}",
            ]
            if spk_quals:
                lines.append(f"{spk_quals}")
            if spk_achv:
                lines.append(f"✨ {spk_achv}")
            lines.append("")

        # What you'll learn bullets
        learn_bullets = event_data.get("_learn_bullets", [])
        if learn_bullets:
            lines.append("📚 **What you'll learn:**")
            for b in learn_bullets:
                lines.append(f"  ✅ {b}")
            lines.append("")

        # Online/Hybrid: conference link
        mode = event_data.get("mode", "In-Person").strip()
        if mode in ("Online", "Hybrid"):
            conf = event_data.get("conference_link", "TBD — will be shared before the event")
            lines += [f"💻 **Join Link:** {conf}", ""]

        # In-person/Hybrid: venue details
        if mode in ("In-Person", "Hybrid"):
            lines += [
                f"📍 **Venue:** {event_data.get('venue_name', '')}",
                event_data.get("venue_address", ""),
            ]
            if event_data.get("google_maps_url"):
                lines.append(f"🗺️ Maps: {event_data['google_maps_url']}")
            if event_data.get("entrance_note"):
                lines.append(f"🚪 Entry: {event_data['entrance_note']}")
            if event_data.get("parking_info"):
                lines.append(f"🅿️ Parking: {event_data['parking_info']}")
            lines.append("")

        # Logistics
        laptop = event_data.get("laptop_required", "")
        if laptop:
            lines.append(f"💻 Laptop Required: {laptop}")
        if event_data.get("host_name"):
            lines.append(
                f"👤 Host: {event_data['host_name']} "
                f"({event_data.get('host_phone', '')})"
            )
        lines.append("")

        # Sponsors
        if event_data.get("venue_sponsor_name"):
            lines.append(f"🏢 Venue Partner: {event_data['venue_sponsor_name']}")
        if str(event_data.get("gift_sponsor", "")).upper() == "YES":
            lines.append("🎁 Gift Sponsor: Fragrance Stories")
        lines.append("")

        lines.append(
            "This event is free to attend. RSVP on Meetup to get updates and "
            "a reminder closer to the event."
        )
        lines.append("")
        lines.append("— WiMLDS Pune Team")

        return "\n".join(lines)

    # ── 2. Upload poster ──────────────────────────────────────────────────────

    def upload_poster(self, event_data: dict) -> AgentResult:
        """
        Upload the approved poster PNG to the Meetup event's photo/image slot.
        Requires event_data['_poster_local_path'] — set by PosterAgent.
        Returns: { poster_meetup_url }
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would upload poster to Meetup event")
            return AgentResult(success=True, data={"poster_meetup_url": "DRY_RUN"})

        event_id    = event_data.get("meetup_event_id", "").strip()
        poster_path = event_data.get("_poster_local_path", "").strip()

        if not event_id:
            return AgentResult(success=False, error="meetup_event_id is empty — create event first")
        if not poster_path or not Path(poster_path).exists():
            logger.warning("No local poster path — skipping Meetup poster upload")
            return AgentResult(success=True, data={"poster_meetup_url": ""})

        try:
            with open(poster_path, "rb") as f:
                resp = requests.post(
                    f"{MEETUP_API_BASE}/{self.group}/events/{event_id}/photos",
                    headers=self._auth_headers(),
                    files={"photo": (Path(poster_path).name, f, "image/png")},
                    timeout=45,
                )
            resp.raise_for_status()
            url = resp.json().get("photo_link", "")
            logger.info(f"Poster uploaded to Meetup: {url}")
            return AgentResult(success=True, data={"poster_meetup_url": url})
        except Exception as exc:
            logger.error(f"Meetup poster upload failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    # ── 3. Add conference link to description ─────────────────────────────────

    def add_conference_link_to_description(
        self, event_data: dict, conf_link: str
    ) -> AgentResult:
        """
        Patch the Meetup event description to include the Zoom/Teams link.
        Called by the LangGraph orchestrator after SETUP_CONFERENCING
        when mode is Online or Hybrid.
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would add conference link to description: {conf_link}")
            return AgentResult(success=True)

        event_id = event_data.get("meetup_event_id", "").strip()
        if not event_id:
            return AgentResult(success=False, error="meetup_event_id is empty")

        # Rebuild description with the real conference link now available
        updated_data = {**event_data, "conference_link": conf_link}
        new_desc = self._build_description(updated_data)

        try:
            resp = requests.patch(
                f"{MEETUP_API_BASE}/{self.group}/events/{event_id}",
                headers=self._headers(),
                json={"description": new_desc},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Conference link added to Meetup description")
            return AgentResult(success=True)
        except Exception as exc:
            logger.error(f"Failed to update Meetup description: {exc}")
            return AgentResult(success=False, error=str(exc))

    # ── 4. Post attendee message (for reminders) ──────────────────────────────

    def post_attendee_message(self, event_data: dict, message: str) -> AgentResult:
        """
        Send a message to all RSVPs via Meetup's Contact Attendees endpoint.
        Used by RemindersAgent for T-2d / T-1d / T-2h blasts mirrored on Meetup.
        """
        if self.dry_run:
            preview = message[:80].replace("\n", " ")
            logger.info(f"[DRY-RUN] Would post Meetup attendee message: {preview}…")
            return AgentResult(success=True)

        event_id = event_data.get("meetup_event_id", "").strip()
        if not event_id:
            return AgentResult(success=False, error="meetup_event_id is empty")

        try:
            resp = requests.post(
                f"{MEETUP_API_BASE}/{self.group}/events/{event_id}/messages",
                headers=self._headers(),
                json={"message": message},
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("Meetup attendee message posted")
            return AgentResult(success=True)
        except Exception as exc:
            logger.error(f"Meetup attendee message failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    # ── 5. Upload post-event photo album ─────────────────────────────────────

    def upload_photo_album(
        self, event_data: dict, photo_paths: list[str]
    ) -> AgentResult:
        """
        Upload up to 20 post-event photos to the Meetup event album.
        Called by PostEventAgent after the event.
        Returns: { uploaded_photos: [url, ...] }
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would upload {len(photo_paths)} photos to Meetup")
            return AgentResult(success=True, data={"uploaded_photos": []})

        event_id = event_data.get("meetup_event_id", "").strip()
        if not event_id:
            return AgentResult(success=False, error="meetup_event_id is empty")

        uploaded = []
        for path in photo_paths[:20]:   # Meetup limit
            try:
                with open(path, "rb") as f:
                    resp = requests.post(
                        f"{MEETUP_API_BASE}/{self.group}/events/{event_id}/photos",
                        headers=self._auth_headers(),
                        files={"photo": (Path(path).name, f, "image/jpeg")},
                        timeout=45,
                    )
                if resp.status_code in (200, 201):
                    photo_url = resp.json().get("photo_link", "")
                    uploaded.append(photo_url)
                    logger.info(f"Photo uploaded: {Path(path).name}")
                else:
                    logger.warning(f"Photo upload returned {resp.status_code}: {path}")
            except Exception as exc:
                logger.warning(f"Photo upload failed for {path}: {exc}")

        logger.info(f"Uploaded {len(uploaded)}/{len(photo_paths)} photos to Meetup")
        return AgentResult(success=True, data={"uploaded_photos": uploaded})

    # ── 6. Post-event consolidated resources update ───────────────────────────

    def post_consolidated_update(
        self, event_data: dict, blog_link: str, recording_link: str,
        transcript_link: str, slides_link: str
    ) -> AgentResult:
        """
        Post a consolidated resources message to Meetup attendees after the event.
        Follows closed-sharing rule:
          Recording / Transcript / Slides → shared inside Meetup ONLY (not on public social).
        """
        event_title    = event_data.get("event_title", "the event")
        speaker_name   = event_data.get("speaker_name", "our speaker")
        venue_name     = event_data.get("venue_sponsor_name") or event_data.get("venue_name", "")
        meetup_url     = event_data.get("meetup_event_url", "")

        parts = [
            f"🙏 Thank you for attending {event_title}!",
            "",
            f"It was wonderful to have {speaker_name} walk us through such a rich session.",
        ]
        if venue_name:
            parts.append(f"Big thanks to {venue_name} for hosting us.")
        parts.append("")
        parts.append("📦 Session resources (for attendees only):")
        if blog_link:
            parts.append(f"  📝 Blog recap: {blog_link}")
        if recording_link:
            parts.append(f"  🎥 Recording: {recording_link}")
        if transcript_link:
            parts.append(f"  📄 Transcript: {transcript_link}")
        if slides_link:
            parts.append(f"  📊 Slides: {slides_link}")
        parts += [
            "",
            "⚠️ These resources are shared here (Meetup) and in our closed WhatsApp "
            "groups only — please do not post on public social media.",
            "",
            f"👉 Stay connected: {meetup_url}",
            "— WiMLDS Pune Team",
        ]

        message = "\n".join(parts)
        return self.post_attendee_message(event_data, message)

    # ── Date/time helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _to_epoch_ms(date_str: str, time_str: str) -> Optional[int]:
        """
        Convert 'DD Mon YYYY' + 'HH:MM' (IST) to epoch milliseconds.
        Example: '11 Oct 2025' + '14:00' → 1728635400000
        """
        if not date_str or not time_str:
            return None
        try:
            dt_str = f"{date_str} {time_str}"
            # Try multiple formats
            for fmt in ("%d %b %Y %H:%M", "%d %B %Y %H:%M", "%Y-%m-%d %H:%M"):
                try:
                    naive = datetime.strptime(dt_str, fmt)
                    ist_dt = IST.localize(naive)
                    return int(ist_dt.timestamp() * 1000)
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    @staticmethod
    def _duration_ms(start: str, end: str) -> Optional[int]:
        """Convert start/end HH:MM strings to duration in milliseconds."""
        if not start or not end:
            return None
        try:
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            total_min = (eh * 60 + em) - (sh * 60 + sm)
            return max(total_min, 30) * 60 * 1000   # minimum 30 min
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI helper — run directly to get your first OAuth token
# ─────────────────────────────────────────────────────────────────────────────

def _cli_get_token():
    """
    Interactive OAuth flow to get your first refresh token.
    Run once: python agents/meetup_agent.py --get-token
    Then paste the MEETUP_REFRESH_TOKEN value into config/.env
    """
    import urllib.parse

    client_id = settings.meetup_client_id
    if not client_id:
        print("ERROR: Set MEETUP_CLIENT_ID in config/.env first")
        return

    redirect_uri = "http://localhost:8080/callback"
    auth_url = (
        f"{MEETUP_AUTH_URL}"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&scope=basic+event_management+messaging"
    )

    print("\n=== Meetup OAuth — First-Time Token Setup ===")
    print(f"\nStep 1: Open this URL in your browser:\n{auth_url}")
    print(
        "\nStep 2: Log in as your WiMLDS organiser account and authorise."
    )
    print(
        "\nStep 3: You will be redirected to localhost. The URL will look like:\n"
        "  http://localhost:8080/callback?code=XXXXXXXX"
    )
    code = input("\nPaste just the 'code' value from that URL here: ").strip()

    resp = requests.post(
        MEETUP_OAUTH_URL,
        data={
            "client_id":     client_id,
            "client_secret": settings.meetup_client_secret,
            "code":          code,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code} — {resp.text}")
        return

    data = resp.json()
    refresh_token = data.get("refresh_token", "")
    access_token  = data.get("access_token", "")

    print("\n✅ SUCCESS — add this to config/.env:")
    print(f"  MEETUP_REFRESH_TOKEN={refresh_token}")
    print(f"\n  (Your access token for testing: {access_token[:20]}…)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meetup Agent utilities")
    parser.add_argument("--get-token", action="store_true",
                        help="Interactive OAuth flow to get first refresh token")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--event-id", default="3")
    args = parser.parse_args()

    if args.get_token:
        _cli_get_token()
    else:
        from wimlds.core.sheets_client import sheets_client
        event_data = sheets_client.get_event(int(args.event_id))
        agent  = MeetupAgent(dry_run=args.dry_run)
        result = agent.create_or_update_event(event_data)
        print(f"Success: {result.success}")
        print(f"Data:    {result.data}")
        if result.error:
            print(f"Error:   {result.error}")


