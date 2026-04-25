"""
Community Partner & Media Agent — Personalized email outreach with UTM tracking.
"""
import csv
import uuid
from pathlib import Path
from urllib.parse import urlencode

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.notifier import Notifier
from wimlds.core.orchestrator import AgentResult

logger = get_logger("partner_agent")


class PartnerAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.notifier = Notifier(dry_run=dry_run)

    def send_outreach(self, event_data: dict) -> AgentResult:
        """Send personalized email + poster + UTM RSVP link to all partners."""
        partners = self._load_partner_list()
        if not partners:
            logger.warning("No partner list found — skipping partner outreach")
            return AgentResult(success=True, data={"partners_emailed": 0})

        event_title = event_data.get("event_title", "WiMLDS Pune Meetup")
        meetup_url  = event_data.get("meetup_event_url", "")

        sent, failed = 0, 0
        for partner in partners:
            utm_url = self._build_utm_url(meetup_url, partner)
            subject, body = self._compose_email(event_data, partner, utm_url)
            ok = self._send_email(partner["email"], subject, body,
                                  poster_url=event_data.get("poster_drive_url"))
            if ok:
                sent += 1
                logger.info(f"Partner email sent: {partner.get('name', partner['email'])}")
            else:
                failed += 1

        logger.info(f"Partner outreach: {sent} sent, {failed} failed")
        return AgentResult(
            success=sent > 0,
            data={"partners_emailed": sent, "partners_failed": failed},
        )

    def _load_partner_list(self) -> list[dict]:
        path = Path(settings.partner_email_list)
        if not path.exists():
            logger.warning(f"Partner list not found: {path}")
            return []
        partners = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("email"):
                    partners.append(row)
        return partners

    def _build_utm_url(self, base_url: str, partner: dict) -> str:
        if not base_url:
            return base_url
        org = partner.get("org", "partner").lower().replace(" ", "_")[:20]
        params = {
            "utm_source":   org,
            "utm_medium":   "email",
            "utm_campaign": "partner_outreach",
            "utm_content":  "rsvp_button",
        }
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{urlencode(params)}"

    def _compose_email(self, event_data: dict, partner: dict, utm_url: str) -> tuple[str, str]:
        name = partner.get("name", "there")
        org  = partner.get("org", "your organisation")
        event_title = event_data.get("event_title", "WiMLDS Pune Meetup")
        date = event_data.get("date", "")
        day  = event_data.get("day", "")
        start= event_data.get("start_time_ist", "")
        end  = event_data.get("end_time_ist", "")
        venue= event_data.get("venue_name", "")

        subject = f"You're invited: WiMLDS Pune — {event_title}"

        body = f"""Hi {name},

I'm reaching out from WiMLDS Pune to invite you and the {org} community to our upcoming meetup!

📅 {event_title}
🗓️  {day}, {date} | {start}–{end} IST
📍 {venue}

We'd love to have members from {org} join us. It's a fantastic opportunity to connect with women in ML/AI across Pune.

🎟️ Free RSVP: {utm_url}

We would also be delighted to reciprocate by sharing your upcoming events with our community (~{self._community_size()} members).

The event poster is attached. Please feel free to share it with your network!

Looking forward to seeing you there.

Warm regards,
WiMLDS Pune Organising Team

--
WiMLDS (Women in Machine Learning & Data Science) Pune Chapter
Meetup: https://meetup.com/WiMLDS-Pune
"""
        return subject, body

    def _send_email(
        self, to_email: str, subject: str, body: str, poster_url: Optional[str] = None
    ) -> bool:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Partner email to {to_email}: {subject}")
            return True
        return self.notifier._send(to_email=to_email, subject=subject, body=body)

    @staticmethod
    def _community_size() -> str:
        return "9,000+"


from typing import Optional




