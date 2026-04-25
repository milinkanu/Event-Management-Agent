"""
Dedicated internal X/Twitter agent.

This is the native repo-integrated version of the previous external
X command center logic.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.sheets_client import sheets_client
from wimlds.integrations.x.ai_rewriter import rewrite_post
from wimlds.integrations.x.buffer_client import create_post
from wimlds.integrations.x.image_processor import pad_and_upload_image
from wimlds.integrations.x.link_generator import extract_post_link
from wimlds.integrations.x.scraper import run_scraper_api
from wimlds.integrations.x.validator import validate_post_text
from wimlds.integrations.x.workflow import (
    confirm_excel_post,
    get_review_required_events,
    perform_excel_sync,
)

logger = get_logger("x_agent")


class XAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def rewrite_text(self, event_data) -> str:
        if self.dry_run and isinstance(event_data, str):
            logger.debug("rewrite_text: dry_run mode, returning input text as-is")
            return event_data
        logger.debug("rewrite_text: delegating to rewrite_post()")
        return rewrite_post(event_data)

    def publish(
        self,
        text: str,
        image_url: Optional[str] = None,
        rewrite: bool = False,
    ) -> dict:
        logger.info(
            "X publish starting: text_length=%d, image_present=%s, dry_run=%s",
            len(text),
            bool(image_url and image_url.strip()),
            self.dry_run,
        )

        if rewrite:
            original_length = len(text)
            final_text = self.rewrite_text(text)
            logger.debug(
                "Rewrite enabled: original_length=%d, rewritten_length=%d",
                original_length,
                len(final_text),
            )
        else:
            final_text = text
            logger.debug("Rewrite disabled, using text as-is: length=%d", len(final_text))

        final_text = self.truncate_tweet(final_text)
        validated = validate_post_text(final_text)
        image_error = ""

        if self.dry_run:
            logger.info("X publish skipped (dry_run=True): returning mock result")
            dry_image = image_url or ""
            return {
                "success": True,
                "tweet_id": "dry_run_tweet_id",
                "post_url": "https://x.com/i/status/dry_run_tweet_id",
                "provider": "internal_dry_run",
                "final_text": validated,
                "raw_response": {"dry_run": True, "image_url": dry_image},
                "error": None,
            }

        final_image_url = None
        if image_url and image_url.strip():
            logger.debug("Processing image: url=%s", image_url.strip())
            try:
                final_image_url = pad_and_upload_image(image_url.strip())
            except Exception as exc:
                image_error = f"Image processing skipped: {exc}"
                logger.warning(image_error)
                final_image_url = None
        else:
            logger.debug("No image URL provided, proceeding without image")

        if self._has_direct_twitter_credentials():
            logger.info("Direct Twitter credentials found, attempting direct publish")
            direct_result = self._publish_direct_twitter(validated, final_image_url)
            if image_error:
                direct_result["error"] = image_error
            return direct_result

        logger.info("No direct Twitter credentials, publishing via Buffer")
        response = create_post(validated, final_image_url)
        post_url = extract_post_link(response)
        tweet_id = self._extract_tweet_id(post_url)
        logger.info(
            "X post published via Buffer: tweet_id=%s, post_url=%s",
            tweet_id,
            post_url,
        )
        logger.debug("Buffer raw_response: %s", response)
        return {
            "success": True,
            "tweet_id": tweet_id,
            "post_url": post_url,
            "provider": "buffer",
            "final_text": validated,
            "raw_response": response,
            "error": image_error,
        }

    def publish_event_from_master_sheet(
        self,
        row_number: int,
        rewrite: bool = True,
        force: bool = False,
    ) -> dict:
        logger.info(
            "publish_event_from_master_sheet starting: row_number=%d, rewrite=%s, force=%s",
            int(row_number),
            rewrite,
            force,
        )
        event_data = sheets_client.get_event(int(row_number))
        event_status = str(event_data.get("event_status", "")).strip()

        if event_status.lower() != "upcoming":
            logger.warning(
                "X publish blocked: event_status='%s', expected 'Upcoming', "
                "row_number=%d, event_title='%s'",
                event_status or "blank",
                int(row_number),
                event_data.get("event_title", ""),
            )
            result = {
                "success": False,
                "tweet_id": "",
                "post_url": "",
                "provider": "",
                "final_text": "",
                "raw_response": {},
                "error": f"Posting blocked: event_status is '{event_status or 'blank'}', not 'Upcoming'.",
                "row_number": int(row_number),
                "event_title": event_data.get("event_title", ""),
            }
            return result

        if not force and str(event_data.get("promote_x", "Y")).upper() != "Y":
            logger.warning(
                "X publish skipped: promote_x not enabled for row_number=%d",
                int(row_number),
            )
            result = {
                "success": False,
                "tweet_id": "",
                "post_url": "",
                "provider": "buffer",
                "final_text": "",
                "raw_response": {},
                "error": "promote_x is not enabled for this event row.",
                "row_number": int(row_number),
            }
            self._write_publish_back(row_number, result)
            return result

        payload = self._event_data_to_rewrite_payload(event_data)
        final_text = self.rewrite_text(payload) if rewrite else self._build_basic_post(payload)
        image_url = self._resolve_master_sheet_image_url(event_data)
        logger.debug(
            "Resolved image_url=%s for row_number=%d",
            image_url or "None",
            int(row_number),
        )
        allow_link_preview = str(event_data.get("_twitter_allow_link_preview", "N")).upper() == "Y"
        if not image_url and not allow_link_preview:
            logger.debug(
                "URL stripping applied (no image and link preview disabled): row_number=%d",
                int(row_number),
            )
            final_text = self._strip_urls(final_text)
        publish_result = self.publish(text=final_text, image_url=image_url, rewrite=False)
        logger.debug(
            "publish() result: success=%s, provider=%s, tweet_id=%s, post_url=%s",
            publish_result.get("success"),
            publish_result.get("provider"),
            publish_result.get("tweet_id"),
            publish_result.get("post_url"),
        )
        publish_result["row_number"] = int(row_number)
        publish_result["event_title"] = event_data.get("event_title", "")
        writeback = self._write_publish_back(row_number, publish_result)
        publish_result["writeback_success"] = writeback["success"]
        publish_result["writeback_error"] = writeback["error"]
        return publish_result

    def scrape(self, query: str, headless: bool = True) -> dict:
        if self.dry_run:
            logger.info("X scrape skipped (dry_run=True): returning mock analytics")
            sample_posts = [
                {"text": "Alice\nExcited for #WiMLDS Pune event tomorrow? Can't wait! pic.twitter.com/test", "url": "https://x.com/i/status/1", "analytics": {"replies": 1, "reposts": 2, "likes": 10, "views": 100}},
                {"text": "Bob\nAnyone attending the WiMLDS meetup? Looking forward to the speaker session.", "url": "https://x.com/i/status/2", "analytics": {"replies": 3, "reposts": 1, "likes": 7, "views": 80}},
            ]
            return {
                "posts": sample_posts,
                "analytics": {
                    "buzz": {"title": "Event Buzz Summary", "total_posts": 2, "unique_contributors": 2},
                    "attendees": {"title": "Potential Attendees", "count": 2, "items": []},
                    "trending": {"title": "Trending Topics", "items": [{"word": "wimlds", "count": 2}]},
                    "best_tweets": {"title": "Longest Event Tweets", "items": []},
                    "top_engaged": {"title": "Top Engaged Tweets", "items": []},
                    "questions": {"title": "Questions From Audience", "count": 2, "items": []},
                    "sentiment": {"title": "Sentiment Summary", "positive": 100.0, "negative": 0.0, "neutral": 0.0},
                    "photos": {"title": "Posts With Photos", "count": 1, "items": []},
                    "feedback": {"title": "Event Feedback Summary", "categories": {"content": 0, "venue": 0, "speaker": 1, "networking": 0}},
                    "advocates": {"title": "Event Advocates", "items": [{"user": "Alice", "count": 1}]},
                    "impact": {"title": "Event Impact Report", "total_tweets": 2, "unique_contributors": 2},
                },
                "ai_insights": "Dry-run insight summary for X analytics.",
            }
        logger.info("X scrape starting: query='%s', headless=%s", query, headless)
        return run_scraper_api(query, headless=headless)

    def sync_excel_queue(self) -> dict:
        if self.dry_run:
            logger.info("sync_excel_queue skipped (dry_run=True): returning mock data")
            return {
                "success": True,
                "events": [{
                    "index": 0,
                    "event title": "Dry Run Event",
                    "event description": "Internal X agent sync test",
                    "location": "Pune",
                    "time": "Tomorrow 6 PM",
                    "speaker": "Test Speaker",
                    "meetup link": "https://meetup.com/test",
                    "posterlink": "https://example.com/poster.png",
                    "ai_draft": "Dry-run draft for internal X workflow.",
                }],
                "error": "",
            }
        logger.info("sync_excel_queue starting")
        success, error = perform_excel_sync()
        result = {
            "success": success,
            "events": get_review_required_events() if success else [],
            "error": error,
        }
        logger.debug(
            "sync_excel_queue result: success=%s, event_count=%d, error='%s'",
            result["success"],
            len(result["events"]),
            result["error"] or "",
        )
        return result

    def confirm_excel_publish(self, index: int, text: str, image_url: Optional[str] = None) -> dict:
        if self.dry_run:
            logger.info("confirm_excel_publish skipped (dry_run=True): returning mock result")
            return {"success": True, "link": "https://x.com/i/status/dry_run_excel_publish", "raw_response": {"dry_run": True}}
        logger.info(
            "confirm_excel_publish starting: index=%d, text_length=%d, image_present=%s",
            index,
            len(text),
            bool(image_url and image_url.strip()),
        )
        return confirm_excel_post(index=index, text=text, image_url=image_url)

    def truncate_tweet(self, text: str, limit: int = 280) -> str:
        if len(text) <= limit:
            return text
        original_length = len(text)
        lines = text.strip().split("\n")
        hashtag_line = ""
        body_lines = lines.copy()
        if lines and lines[-1].strip().startswith("#"):
            hashtag_line = lines[-1]
            body_lines = lines[:-1]
        body = "\n".join(body_lines).strip()
        reserve = len(hashtag_line) + 5
        body = body[: max(limit - reserve, 1)] + "..."
        truncated = (body + "\n\n" + hashtag_line).strip() if hashtag_line else body
        logger.warning(
            "Tweet truncated: original_length=%d → final_length=%d (limit=%d)",
            original_length,
            len(truncated),
            limit,
        )
        return truncated

    @staticmethod
    def _extract_tweet_id(post_url: str) -> str:
        if "/status/" not in post_url:
            return ""
        return post_url.rsplit("/status/", 1)[-1].split("?", 1)[0].strip("/")

    @staticmethod
    def _event_data_to_rewrite_payload(event_data: dict) -> dict:
        time_value = " ".join(
            part for part in [
                str(event_data.get("date", "")).strip(),
                str(event_data.get("start_time_ist", "")).strip(),
                str(event_data.get("end_time_ist", "")).strip(),
            ] if part
        ).strip()
        description = event_data.get("subtitle") or event_data.get("_scope_one_liner") or event_data.get("session_type", "")
        location = event_data.get("venue_name") or event_data.get("venue_address") or event_data.get("location", "")
        meetup_link = event_data.get("meetup_event_url") or event_data.get("meetup link") or ""
        speaker = event_data.get("speaker_name") or event_data.get("speaker") or ""
        return {
            "event title": event_data.get("event_title", ""),
            "speaker": speaker,
            "location": location,
            "event description": description,
            "time": time_value,
            "meetup link": meetup_link,
            "series": event_data.get("series", ""),
            "mode": event_data.get("mode", ""),
        }

    @staticmethod
    def _build_basic_post(payload: dict) -> str:
        parts = [str(payload.get("event title", "")).strip()]
        if payload.get("speaker"):
            parts.append(f"with {payload['speaker']}")
        if payload.get("time"):
            parts.append(payload["time"])
        if payload.get("location"):
            parts.append(f"at {payload['location']}")
        return " | ".join(part for part in parts if part).strip()

    @staticmethod
    def _resolve_master_sheet_image_url(event_data: dict) -> Optional[str]:
        candidates = [
            event_data.get("_twitter_image_url"),
            event_data.get("poster_drive_url"),
            event_data.get("posterlink"),
            event_data.get("poster_meetup_url"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        return None

    @staticmethod
    def _strip_urls(text: str) -> str:
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _write_publish_back(self, row_number: int, publish_result: dict) -> dict:
        success = bool(publish_result.get("success"))
        logger.debug(
            "Writing publish result back to sheet: row_number=%d, success=%s",
            int(row_number),
            success,
        )
        timestamp = datetime.now().isoformat(timespec="seconds")
        fields = {
            "_twitter_tweet_id": publish_result.get("tweet_id", ""),
            "_twitter_post_url": publish_result.get("post_url", ""),
            "x_post_status": "Posted" if success else "Failed",
            "x_post_text": publish_result.get("final_text", ""),
            "x_posted_at": timestamp if success else "",
            "x_error": publish_result.get("error", "") or "",
        }
        if publish_result.get("post_url"):
            fields["link"] = publish_result.get("post_url", "")
        try:
            write_ok = sheets_client.write_fields(int(row_number), fields)
            if write_ok:
                logger.info("Metadata write-back succeeded: row_number=%d", int(row_number))
                return {"success": True, "error": ""}
            logger.warning(
                "Metadata write-back failed (workbook locked?): row_number=%d",
                int(row_number),
            )
            return {
                "success": False,
                "error": (
                    "Workbook write failed. The Excel file may be open or locked. "
                    "Close WiMLDS_Master_Sheet.xlsx and rerun."
                ),
            }
        except Exception as exc:
            logger.warning(f"Could not write X publish metadata back to sheet row {row_number}: {exc}")
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _has_direct_twitter_credentials() -> bool:
        return all([
            settings.twitter_api_key,
            settings.twitter_api_secret,
            settings.twitter_access_token,
            settings.twitter_access_token_secret,
        ])

    def _publish_direct_twitter(self, text: str, image_url: Optional[str] = None) -> dict:
        logger.info(
            "Attempting direct X publish via Tweepy: text_length=%d, image_present=%s",
            len(text),
            bool(image_url),
        )
        try:
            import tweepy

            client = tweepy.Client(
                consumer_key=settings.twitter_api_key,
                consumer_secret=settings.twitter_api_secret,
                access_token=settings.twitter_access_token,
                access_token_secret=settings.twitter_access_token_secret,
            )
            response = client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            post_url = f"https://x.com/i/status/{tweet_id}"
            logger.info(
                "X post published: provider=direct_tweepy, tweet_id=%s, post_url=%s",
                tweet_id,
                post_url,
            )
            logger.debug("Tweepy raw_response: %s", getattr(response, "data", {}))
            error = ""
            if image_url:
                error = "Image ignored for direct X publish because media upload is not implemented in this flow."
                logger.warning(
                    "Image ignored for direct X publish: media upload not implemented in this flow"
                )
            return {
                "success": True,
                "tweet_id": tweet_id,
                "post_url": post_url,
                "provider": "direct_tweepy",
                "final_text": text,
                "raw_response": getattr(response, "data", {}) or {},
                "error": error,
            }
        except Exception as exc:
            logger.warning("Direct X publish failed, falling back to Buffer: %s", exc)
            response = create_post(text, None)
            post_url = extract_post_link(response)
            tweet_id = self._extract_tweet_id(post_url)
            logger.info(
                "X post published via fallback Buffer: tweet_id=%s, post_url=%s",
                tweet_id,
                post_url,
            )
            logger.debug("Buffer fallback raw_response: %s", response)
            return {
                "success": True,
                "tweet_id": tweet_id,
                "post_url": post_url,
                "provider": "buffer_fallback",
                "final_text": text,
                "raw_response": response,
                "error": str(exc),
            }
