"""
WhatsApp Agent — Semi-automated posting to WA Groups.

Strategy: Uses Twilio WhatsApp API (most reliable for India) with a
fallback to WhatsApp Web + Selenium (for groups where direct API isn't available).

Twilio approach:
  - Sends messages to individual numbers (approved templates or session messages)
  - Works for WhatsApp Business numbers and personal numbers that opt-in
  - Supports images/media

WhatsApp Web (Selenium) approach:
  - Used for posting to named groups (where you are already a member)
  - Semi-manual: browser opens, message is typed, human presses Send
  - Session is persisted so QR scan is only needed once
"""

import time
import os
from typing import Optional
from pathlib import Path

from wimlds.config.settings import settings
from wimlds.config.message_templates import (
    EventContext, render_announcement, render_spotlight,
    render_logistics, render_final_bump,
)
from wimlds.core.logger import get_logger
from wimlds.core.orchestrator import AgentResult

logger = get_logger("whatsapp_agent")


def _event_to_context(event_data: dict) -> EventContext:
    from wimlds.agents.publishing.social_agent import _event_to_context as _ctx
    return _ctx(event_data)


# ─────────────────────────────────────────────────────────────────────────────
# Main Agent Class
# ─────────────────────────────────────────────────────────────────────────────

class WhatsAppAgent:
    """
    Two-mode WhatsApp agent:
      mode="twilio" — API-based, sends to individual numbers (no manual action needed)
      mode="web"    — Selenium WhatsApp Web, for named groups (human clicks Send)
    """

    def __init__(self, dry_run: bool = False, mode: str = "auto"):
        self.dry_run = dry_run
        # auto = use Twilio if credentials are set, else fall back to web
        if mode == "auto":
            self.mode = "twilio" if settings.twilio_account_sid else "web"
        else:
            self.mode = mode
        self._driver = None
        logger.info(f"WhatsAppAgent ready (mode={self.mode}, dry_run={dry_run})")

    # ── Public message senders ───────────────────────────────────────────────

    def send_announcement(self, event_data: dict) -> AgentResult:
        """Called at event publish time — sends announcement + poster."""
        ctx = _event_to_context(event_data)
        message = render_announcement(ctx)
        poster_path = event_data.get("_poster_local_path")
        groups   = self._get_group_names(event_data)
        numbers  = self._get_individual_numbers(event_data)
        return self._dispatch(message, groups, numbers, media_path=poster_path, stage="announcement")

    def send_spotlight(self, event_data: dict) -> AgentResult:
        """T-2 days — speaker spotlight with poster."""
        ctx = _event_to_context(event_data)
        message = render_spotlight(ctx)
        poster_path = event_data.get("_poster_local_path")
        groups  = self._get_group_names(event_data)
        numbers = self._get_individual_numbers(event_data)
        return self._dispatch(message, groups, numbers, media_path=poster_path, stage="spotlight")

    def send_logistics(self, event_data: dict) -> AgentResult:
        """T-1 day — logistics + venue details."""
        ctx = _event_to_context(event_data)
        message = render_logistics(ctx)
        groups  = self._get_group_names(event_data)
        numbers = self._get_individual_numbers(event_data)
        return self._dispatch(message, groups, numbers, stage="logistics")

    def send_final_bump(self, event_data: dict) -> AgentResult:
        """T-2 hours — final reminder."""
        ctx = _event_to_context(event_data)
        message = render_final_bump(ctx)
        groups   = self._get_group_names(event_data)
        numbers  = self._get_individual_numbers(event_data)
        # Also include individual recipients for final bump if configured
        if event_data.get("promote_wa_individual", "N").upper() == "Y":
            extra = self._get_individual_numbers(event_data, field="individual_wa_recipients")
            numbers = list(set(numbers + extra))
        return self._dispatch(message, groups, numbers, stage="final_bump")

    # ── Core dispatcher ──────────────────────────────────────────────────────

    def _dispatch(
        self,
        message: str,
        groups: list[str],
        numbers: list[str],
        media_path: Optional[str] = None,
        stage: str = "post",
    ) -> AgentResult:
        if self.dry_run:
            logger.info(
                f"[DRY-RUN] WA {stage}: would send to {len(groups)} groups "
                f"and {len(numbers)} numbers"
            )
            logger.info(f"[DRY-RUN] Message preview:\n{message[:300]}")
            return AgentResult(
                success=True,
                data={"groups": groups, "numbers": numbers, "stage": stage, "dry_run": True},
            )

        results = {"groups_sent": 0, "groups_failed": 0, "numbers_sent": 0, "numbers_failed": 0}

        # ── Twilio path (individual numbers) ────────────────────────────────
        if self.mode == "twilio" and numbers:
            for number in numbers:
                ok = self._send_via_twilio(message, number, media_path)
                if ok:
                    results["numbers_sent"] += 1
                else:
                    results["numbers_failed"] += 1
                time.sleep(1)

        # ── WhatsApp Web path (named groups) ─────────────────────────────────
        if groups:
            sent, failed = self._send_to_web_groups(message, groups, media_path)
            results["groups_sent"]   = sent
            results["groups_failed"] = failed

        total_ok = results["groups_sent"] + results["numbers_sent"]
        total    = len(groups) + len(numbers)
        success  = total == 0 or total_ok > 0

        logger.info(
            f"WA {stage}: groups {results['groups_sent']}/{len(groups)}, "
            f"numbers {results['numbers_sent']}/{len(numbers)}"
        )
        return AgentResult(success=success, data=results)

    # ── Twilio API ────────────────────────────────────────────────────────────

    def _send_via_twilio(
        self, message: str, to_number: str, media_path: Optional[str] = None
    ) -> bool:
        """
        Send a WhatsApp message via Twilio API.
        to_number must be in E.164 format: +91XXXXXXXXXX
        """
        try:
            from twilio.rest import Client

            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            from_wa = f"whatsapp:{settings.twilio_whatsapp_number}"
            to_wa   = f"whatsapp:{to_number}"

            kwargs: dict = {
                "from_": from_wa,
                "to":    to_wa,
                "body":  message,
            }

            # Attach media if provided and publicly accessible via URL
            # Twilio requires a publicly accessible URL, not a local file path
            media_url = getattr(settings, "wa_media_base_url", "")
            if media_path and media_url and Path(media_path).exists():
                filename = Path(media_path).name
                kwargs["media_url"] = [f"{media_url.rstrip('/')}/{filename}"]

            msg = client.messages.create(**kwargs)
            logger.info(f"  ✓ Twilio WA sent to {to_number} — SID: {msg.sid}")
            return True

        except Exception as e:
            logger.error(f"  ✗ Twilio WA failed for {to_number}: {e}")
            return False

    # ── WhatsApp Web / Selenium ───────────────────────────────────────────────

    def _send_to_web_groups(
        self,
        message: str,
        groups: list[str],
        media_path: Optional[str] = None,
    ) -> tuple[int, int]:
        """
        Opens WhatsApp Web for each group. Types the message.
        User must click Send in the browser (policy-safe for group messages).
        Returns (sent_count, failed_count).
        """
        sent, failed = 0, 0

        print(f"\n{'='*62}")
        print("  WhatsApp Group Posting — Semi-Manual Mode")
        print(f"  Sending to {len(groups)} group(s)")
        print(f"{'='*62}")
        print("\n📋 Message preview:")
        print("─" * 50)
        print(message[:400] + ("..." if len(message) > 400 else ""))
        print("─" * 50)

        for group_name in groups:
            try:
                ok = self._open_web_group(message, group_name, media_path)
                if ok:
                    sent += 1
                    logger.info(f"  ✓ WA group posted: {group_name}")
                else:
                    failed += 1
                    logger.warning(f"  ✗ WA group skipped: {group_name}")
                time.sleep(2)

            except KeyboardInterrupt:
                print("\n⚠  Posting interrupted. Remaining groups skipped.")
                break
            except Exception as e:
                failed += 1
                logger.error(f"  ✗ WA group error for {group_name}: {e}")

        return sent, failed

    def _open_web_group(
        self, message: str, group_name: str, media_path: Optional[str] = None
    ) -> bool:
        """
        Opens WhatsApp Web to a specific group by name and pre-fills the message.
        User clicks Send manually.
        """
        try:
            driver = self._get_driver()
            import urllib.parse
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # Build URL — WhatsApp Web search approach
            # For groups we search by group name; for numbers we use ?phone=
            encoded_msg = urllib.parse.quote(message)
            url = f"https://web.whatsapp.com"
            driver.get(url)
            time.sleep(3)  # Wait for WhatsApp Web to load

            # Find the search box and type the group name
            wait = WebDriverWait(driver, 15)
            search_box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')
                )
            )
            search_box.clear()
            search_box.send_keys(group_name)
            time.sleep(2)

            # Click the first result
            first_result = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, f'//span[@title="{group_name}"]')
                )
            )
            first_result.click()
            time.sleep(1)

            # Type the message in the chat input
            msg_box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                )
            )
            # Clear and type the message
            import pyperclip
            pyperclip.copy(message)
            msg_box.click()
            import platform as _plt
            if _plt.system() == "Darwin":
                from selenium.webdriver.common.keys import Keys
                msg_box.send_keys(Keys.COMMAND, "v")
            else:
                from selenium.webdriver.common.keys import Keys
                msg_box.send_keys(Keys.CONTROL, "v")
            time.sleep(1)

            # Prompt user to click send
            print(f"\n→ Group: {group_name}")
            print("  ✅ Message typed in WhatsApp Web.")
            if media_path:
                print(f"  📎 Media note: attach '{Path(media_path).name}' manually if needed.")
            print("  Please click  SEND  (➤) in the browser window.")
            confirm = input("  Type 'y' when sent, 's' to skip this group: ").strip().lower()
            return confirm == "y"

        except Exception as e:
            logger.error(f"WhatsApp Web error for group '{group_name}': {e}")
            print(f"  ⚠ Error opening group '{group_name}'. Skipping. (Error: {e})")
            return False

    def _get_driver(self):
        """Lazy-init Chrome WebDriver. Persists session so QR code is scanned only once."""
        if self._driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            opts = Options()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            # Persist WhatsApp Web session — avoids re-scanning QR code
            profile_dir = Path.home() / ".wimlds_wa_profile"
            profile_dir.mkdir(exist_ok=True)
            opts.add_argument(f"--user-data-dir={str(profile_dir)}")

            self._driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=opts,
            )
            self._driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            logger.info(f"Chrome WebDriver started. Profile: {profile_dir}")
            print("\n📱 WhatsApp Web opening...")
            print("   First time: scan the QR code with your phone.")
            print("   After that: your session is saved — no QR needed again.\n")
            time.sleep(4)

        return self._driver

    def close(self):
        """Call this at end of script to cleanly close browser."""
        if self._driver:
            self._driver.quit()
            self._driver = None
            logger.info("WhatsApp Web browser closed.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_group_names(event_data: dict) -> list[str]:
        """Parse WA group names from Master Sheet field 'wa_group_names'."""
        raw = event_data.get("wa_group_names", "") or event_data.get("meetup_groups_list", "")
        return [g.strip() for g in raw.split(",") if g.strip()]

    @staticmethod
    def _get_individual_numbers(
        event_data: dict, field: str = "wa_individual_numbers"
    ) -> list[str]:
        """Parse E.164 phone numbers from Master Sheet field."""
        raw = event_data.get(field, "")
        nums = []
        for n in raw.split(","):
            n = n.strip().replace(" ", "").replace("-", "")
            if n:
                # Ensure E.164 format — add +91 if bare 10-digit Indian number
                if n.isdigit() and len(n) == 10:
                    n = "+91" + n
                elif n.startswith("0") and len(n) == 11:
                    n = "+91" + n[1:]
                nums.append(n)
        return nums


