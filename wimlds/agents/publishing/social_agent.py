"""
Social Syndication Agent — Multi-platform posting.
Channels: LinkedIn, Facebook (Page), X/Twitter, Instagram, Meetup.com, WhatsApp.
Stages: Announcement → T-2d Spotlight → T-1d Logistics → T-2h Final Bump.

New in this version:
  - Twitter/X uses tweepy v4 (OAuth 2 PKCE / app-only bearer token)
  - Facebook and Instagram share the same Graph API token (Meta Business Suite)
  - LinkedIn uses the official UGC Posts API (v2)
  - WhatsApp is delegated to WhatsAppAgent
  - _event_to_context is fully self-contained (no circular imports)
"""

import os
import time
from pathlib import Path
from typing import Optional
import requests

from wimlds.agents.publishing.x_agent import XAgent
from wimlds.config.settings import settings
from wimlds.config.message_templates import (
    EventContext, render_announcement, render_spotlight,
    render_logistics, render_final_bump,
)
from wimlds.core.logger import get_logger
from wimlds.core.drive_client import drive_client
from wimlds.core.orchestrator import AgentResult

logger = get_logger("social_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Event → context mapper (shared with WhatsApp agent)
# ─────────────────────────────────────────────────────────────────────────────

def _event_to_context(event_data: dict) -> EventContext:
    return EventContext(
        event_title   = event_data.get("event_title", ""),
        subtitle      = event_data.get("subtitle", ""),
        day           = event_data.get("day", ""),
        date          = event_data.get("date", ""),
        start_time    = event_data.get("start_time_ist", ""),
        end_time      = event_data.get("end_time_ist", ""),
        venue_name    = event_data.get("venue_name", ""),
        venue_address = event_data.get("venue_address", ""),
        entrance_note = event_data.get("entrance_note", ""),
        parking_info  = event_data.get("parking_info", ""),
        laptop_required     = event_data.get("laptop_required", "No"),
        wifi_note           = event_data.get("wifi_note", ""),
        host_name           = event_data.get("host_name", ""),
        host_phone          = event_data.get("host_phone", ""),
        speaker_name        = event_data.get("speaker_name", ""),
        speaker_title       = event_data.get("speaker_title", ""),
        speaker_org         = event_data.get("speaker_org", ""),
        speaker_achievements= (
            event_data.get("speaker_special_achievements", "").split(";")
            if event_data.get("speaker_special_achievements") else []
        ),
        learn_bullets       = event_data.get("_learn_bullets", []),
        scope_one_liner     = event_data.get("_scope_one_liner", ""),
        meetup_url          = event_data.get("meetup_event_url", ""),
        conference_link     = event_data.get("conference_link", ""),
        mode                = event_data.get("mode", "In-Person"),
        series              = event_data.get("series", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Social Agent
# ─────────────────────────────────────────────────────────────────────────────

class SocialAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    # ── Stage methods ─────────────────────────────────────────────────────────

    def post_announcement(self, event_data: dict) -> AgentResult:
        ctx    = _event_to_context(event_data)
        text   = render_announcement(ctx)
        poster = event_data.get("_poster_local_path")
        return self._broadcast(text, event_data, image_path=poster, stage="announcement")

    def post_spotlight(self, event_data: dict) -> AgentResult:
        ctx    = _event_to_context(event_data)
        text   = render_spotlight(ctx)
        poster = event_data.get("_poster_local_path")
        return self._broadcast(text, event_data, image_path=poster, stage="t2d_spotlight")

    def post_logistics(self, event_data: dict) -> AgentResult:
        ctx  = _event_to_context(event_data)
        text = render_logistics(ctx)
        return self._broadcast(text, event_data, stage="t1d_logistics")

    def post_final_bump(self, event_data: dict) -> AgentResult:
        ctx  = _event_to_context(event_data)
        text = render_final_bump(ctx)
        return self._broadcast(text, event_data, stage="t2h_final_bump")

    # ── Core broadcast ────────────────────────────────────────────────────────

    def _broadcast(
        self,
        text: str,
        event_data: dict,
        image_path: Optional[str] = None,
        stage: str = "post",
    ) -> AgentResult:
        """Post to all enabled channels and collect results."""
        results: dict = {}
        errors:  list = []

        # Always save draft to Drive first (never blocks other channels)
        self._save_draft(text, event_data, stage)

        # ── LinkedIn ──────────────────────────────────────────────────────────
        if event_data.get("promote_linkedin", "Y").upper() == "Y":
            ok = self._post_linkedin(text, image_path)
            results["linkedin"] = ok
            if not ok:
                errors.append("linkedin")

        # ── Facebook Page ─────────────────────────────────────────────────────
        if event_data.get("promote_facebook", "Y").upper() == "Y":
            ok = self._post_facebook(text, image_path)
            results["facebook"] = ok
            if not ok:
                errors.append("facebook")

        # ── X / Twitter ───────────────────────────────────────────────────────
        if event_data.get("promote_x", "Y").upper() == "Y":
            x_result = self._post_twitter(text, event_data, image_path)
            ok = x_result.get("success", False)
            results["twitter"] = ok
            if x_result.get("tweet_id") or x_result.get("post_url"):
                results["twitter_meta"] = {
                    "tweet_id": x_result.get("tweet_id", ""),
                    "post_url": x_result.get("post_url", ""),
                    "provider": x_result.get("provider", ""),
                }
            if not ok:
                errors.append("twitter")

        # ── Instagram ─────────────────────────────────────────────────────────
        if event_data.get("promote_instagram", "Y").upper() == "Y":
            ok = self._post_instagram(text, image_path)
            results["instagram"] = ok
            if not ok:
                errors.append("instagram")

        # ── Meetup.com groups ─────────────────────────────────────────────────
        if event_data.get("promote_meetup", "Y").upper() == "Y":
            ok = self._post_meetup_groups(text, event_data)
            results["meetup_groups"] = ok
            if not ok:
                errors.append("meetup_groups")

        # ── WhatsApp (delegated to WhatsAppAgent) ─────────────────────────────
        if event_data.get("promote_whatsapp", "Y").upper() == "Y":
            ok = self._post_whatsapp(text, event_data, image_path, stage)
            results["whatsapp"] = ok
            if not ok:
                errors.append("whatsapp")

        success = len(errors) < max(len(results), 1)   # partial success is OK
        if errors:
            logger.warning(f"Channels with errors: {errors}")

        return AgentResult(
            success=success,
            data=results,
            error=f"Failed channels: {errors}" if errors else None,
        )

    # ── Platform: LinkedIn ────────────────────────────────────────────────────

    def _post_linkedin(self, text: str, image_path: Optional[str]) -> bool:
        if self.dry_run:
            logger.info(f"[DRY-RUN] LinkedIn: {text[:80]}...")
            return True
        try:
            token   = settings.linkedin_access_token
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            }
            # Get authenticated person URN
            me_resp = requests.get(
                "https://api.linkedin.com/v2/me", headers=headers, timeout=10
            )
            me_resp.raise_for_status()
            person_urn = f"urn:li:person:{me_resp.json()['id']}"

            payload: dict = {
                "author":         person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary":    {"text": text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }

            resp = requests.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers=headers, json=payload, timeout=15,
            )
            resp.raise_for_status()
            logger.info(f"LinkedIn post published — ID: {resp.headers.get('x-restli-id', '?')}")
            return True

        except Exception as e:
            logger.error(f"LinkedIn post failed: {e}")
            return False

    # ── Platform: Facebook Page ───────────────────────────────────────────────

    def _post_facebook(self, text: str, image_path: Optional[str]) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Facebook post")
            return True
        try:
            token    = settings.facebook_page_token
            page_id  = settings.facebook_page_id

            if not page_id:
                # Auto-detect page ID from token
                r = requests.get(
                    f"https://graph.facebook.com/me?access_token={token}", timeout=10
                )
                r.raise_for_status()
                page_id = r.json()["id"]

            if image_path and Path(image_path).exists():
                # Post with image
                with open(image_path, "rb") as f:
                    resp = requests.post(
                        f"https://graph.facebook.com/v18.0/{page_id}/photos",
                        data={"message": text, "access_token": token},
                        files={"source": f},
                        timeout=30,
                    )
            else:
                # Text-only post
                resp = requests.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/feed",
                    data={"message": text, "access_token": token},
                    timeout=15,
                )
            resp.raise_for_status()
            logger.info(f"Facebook post published — ID: {resp.json().get('id', '?')}")
            return True

        except Exception as e:
            logger.error(f"Facebook post failed: {e}")
            return False

    # ── Platform: X / Twitter ─────────────────────────────────────────────────

    def _post_twitter(
        self,
        text: str,
        event_data: dict,
        image_path: Optional[str] = None,
    ) -> dict:
        image_url = self._resolve_x_image_url(event_data, image_path)
        result = XAgent(dry_run=self.dry_run).publish(text=text, image_url=image_url)
        if result.get("success"):
            event_data["_twitter_tweet_id"] = result.get("tweet_id", "")
            event_data["_twitter_post_url"] = result.get("post_url", "")
            event_data["_twitter_provider"] = result.get("provider", "")
            event_data["_twitter_final_text"] = result.get("final_text", text)
        return result

    @staticmethod
    def _truncate_tweet(text: str, limit: int = 280) -> str:
        """Truncate tweet text preserving hashtags at end."""
        return XAgent.truncate_tweet(text, limit)

    # ── Platform: Instagram ───────────────────────────────────────────────────

    def _post_instagram(self, text: str, image_path: Optional[str]) -> bool:
        """
        Instagram posting via Meta Graph API.
        Requires: Instagram Business/Creator account linked to a Facebook Page.
        Image must be hosted at a public URL (uploaded to Drive CDN or similar).
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Instagram post")
            return True
        try:
            token      = settings.instagram_access_token
            ig_user_id = settings.instagram_user_id

            if not ig_user_id:
                logger.warning("INSTAGRAM_USER_ID not set — skipping Instagram")
                return False

            media_url = getattr(settings, "wa_media_base_url", "")

            if image_path and media_url:
                # Step 1 — create container
                img_filename = Path(image_path).name
                public_url   = f"{media_url.rstrip('/')}/{img_filename}"
                container_resp = requests.post(
                    f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
                    data={
                        "image_url":   public_url,
                        "caption":     text,
                        "access_token": token,
                    },
                    timeout=20,
                )
                container_resp.raise_for_status()
                container_id = container_resp.json()["id"]
                time.sleep(3)  # Wait for container to be ready

                # Step 2 — publish container
                pub_resp = requests.post(
                    f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish",
                    data={"creation_id": container_id, "access_token": token},
                    timeout=15,
                )
                pub_resp.raise_for_status()
                logger.info(f"Instagram post published — ID: {pub_resp.json().get('id', '?')}")
            else:
                logger.warning(
                    "Instagram skipped: no public image URL available "
                    "(set WA_MEDIA_BASE_URL in .env)"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Instagram post failed: {e}")
            return False

    # ── Platform: Meetup.com ──────────────────────────────────────────────────

    def _post_meetup_groups(self, text: str, event_data: dict) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Meetup Groups post")
            return True
        try:
            from wimlds.agents.publishing.meetup_agent import MeetupAgent
            ma     = MeetupAgent(dry_run=self.dry_run)
            result = ma.post_attendee_message(event_data, text)
            return result.success
        except Exception as e:
            logger.error(f"Meetup groups post failed: {e}")
            return False

    # ── Platform: WhatsApp ────────────────────────────────────────────────────

    def _post_whatsapp(
        self,
        text: str,
        event_data: dict,
        image_path: Optional[str],
        stage: str,
    ) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] WhatsApp post")
            return True
        try:
            from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
            wa = WhatsAppAgent(dry_run=self.dry_run)
            # Call the stage-specific method
            stage_method = {
                "announcement":  wa.send_announcement,
                "t2d_spotlight": wa.send_spotlight,
                "t1d_logistics": wa.send_logistics,
                "t2h_final_bump": wa.send_final_bump,
            }.get(stage, wa.send_announcement)
            result = stage_method(event_data)
            wa.close()
            return result.success
        except Exception as e:
            logger.error(f"WhatsApp post failed: {e}")
            return False

    # ── Save draft to Drive ───────────────────────────────────────────────────

    def _save_draft(self, text: str, event_data: dict, stage: str) -> None:
        try:
            folder_map = event_data.get("_drive_folder_map", {})
            folder_id  = folder_map.get("02_output/03_social_copies")
            if not folder_id:
                return
            filename = f"social_{stage}_{event_data.get('meetup_event_id', 'draft')}.txt"
            drive_client.upload_bytes(
                data      = text.encode("utf-8"),
                filename  = filename,
                folder_id = folder_id,
                mime_type = "text/plain",
            )
            logger.info(f"Social draft saved to Drive: {filename}")
        except Exception as e:
            logger.warning(f"Could not save social draft to Drive: {e}")

    @staticmethod
    def _resolve_x_image_url(event_data: dict, image_path: Optional[str] = None) -> Optional[str]:
        candidates = [
            event_data.get("_twitter_image_url"),
            event_data.get("poster_drive_url"),
            event_data.get("poster_meetup_url"),
            event_data.get("qr_drive_url"),
        ]
        if image_path and str(image_path).startswith(("http://", "https://")):
            candidates.insert(0, image_path)
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        return None

