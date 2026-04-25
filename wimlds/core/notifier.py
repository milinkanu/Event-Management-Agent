"""
Email notifications — missing field alerts, completion summaries.

Changes from original:
  - Added send_raw() method used by AnalyticsAgent to send its own pre-built email body.
  - Made sendgrid import lazy so the module loads even without credentials.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from wimlds.config.settings import settings
from wimlds.config.message_templates import render_missing_info_email
from wimlds.core.logger import get_logger

logger = get_logger("notifier")


class Notifier:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._sg = None   # lazy-init so missing sendgrid doesn't break imports

    def _get_sg(self):
        if self._sg is None:
            import sendgrid
            self._sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        return self._sg

    def send_missing_fields_alert(
        self,
        owner_name: str,
        owner_email: str,
        event_title: str,
        missing_fields: list[str],
    ) -> bool:
        subject, body = render_missing_info_email(owner_name, event_title, missing_fields)
        return self._send(to_email=owner_email, subject=subject, body=body)

    def send_completion_summary(
        self,
        event_title: str,
        kpis: dict,
    ) -> bool:
        subject = f"✅ WiMLDS Automation Complete — {event_title}"
        body = self._format_completion_email(event_title, kpis)
        return self._send(
            to_email=settings.notification_email,
            subject=subject,
            body=body,
        )

    def send_poster_approval_request(
        self,
        recipients: list[str],
        event_title: str,
        poster_drive_url: str,
    ) -> bool:
        subject = f"Poster Approval Needed — WiMLDS {event_title}"
        body = f"""Hi,

Please review and approve the poster for the upcoming WiMLDS Pune meetup:
"{event_title}"

Poster link: {poster_drive_url}

Please reply with:
  ✅ APPROVED — to proceed with posting
  ❌ CHANGES: <your notes> — to request revisions

Thank you!
WiMLDS Automation System
"""
        success = True
        for email in recipients:
            ok = self._send(to_email=email, subject=subject, body=body)
            success = success and ok
        return success

    # ── NEW METHOD — used by AnalyticsAgent ───────────────────────────────────
    def send_raw(self, to_email: str, subject: str, body: str) -> bool:
        """
        Send a pre-built plain-text email.
        Called by AnalyticsAgent which builds its own detailed KPI email body.
        """
        return self._send(to_email=to_email, subject=subject, body=body)
    # ── END NEW METHOD ────────────────────────────────────────────────────────

    def _send(self, to_email: str, subject: str, body: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Email to {to_email}: {subject}")
            return True

        try:
            from sendgrid.helpers.mail import Mail
            message = Mail(
                from_email="automation@wimlds-pune.org",
                to_emails=to_email,
                subject=subject,
                plain_text_content=body,
            )
            response = self._get_sg().send(message)
            if response.status_code in (200, 202):
                logger.info(f"Email sent to {to_email}: {subject}")
                return True
            else:
                logger.error(f"Email failed ({response.status_code}): {to_email}")
                return False
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False

    def _format_completion_email(self, event_title: str, kpis: dict) -> str:
        lines = [
            f"WiMLDS Automation — Event Complete: {event_title}",
            "=" * 60,
            "",
            "📊 KPI Summary:",
        ]
        for k, v in kpis.items():
            lines.append(f"  {k}: {v}")
        lines += ["", "All tasks completed successfully.", "WiMLDS Automation Orchestrator"]
        return "\n".join(lines)


