"""
Post-Event Agent — Production-ready, end-to-end.

Full pipeline:
  1.  Conferencing teardown  — fetch Zoom/GMeet recording URL
  2.  Recording download     — save mp4 locally
  3.  Transcript retrieval   — pull Zoom auto-transcript or external file
  4.  Transcript parsing     — VTT / SRT / SBV / Zoom-txt → clean speaker-attributed text
  5.  LLM summarisation      — Claude generates structured summary (JSON)
  6.  LLM blog generation    — full markdown blog post from transcript
  7.  Drive upload           — transcript, recording, blog → 04_PostEvent/
  8.  Sheet write-back       — all links + flags → Google Sheets
  9.  LinkedIn post          — gratitude post (NO closed-share links)
  10. Meetup post            — all resources (attendees only)
  11. WhatsApp closed share  — recording + transcript + slides → WA groups
  12. Organiser notification — completion email via SendGrid

Usage:
    agent = PostEventAgent(dry_run=False)
    result = agent.run(event_data, meeting_id="123456789", platform="zoom")

    # Or, if conferencing was created by the Conferencing Agent earlier:
    result = agent.run(event_data)   # reads meeting_id from event_data["_meeting_id"]
"""
from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.result import AgentResult
from wimlds.integrations.llm.llm_client import LLMClient
from wimlds.integrations.processing.transcript_processor import transcript_processor, ParsedTranscript
from wimlds.integrations.storage.drive_client import drive_client

logger = get_logger("post_event_agent")

# ─── Closed-sharing rule ──────────────────────────────────────────────────────
# These links NEVER appear on public social channels (LinkedIn/FB/X/IG).
# They go to: Meetup Contact Attendees, closed WA groups only.
CLOSED_SHARE_FIELDS = {"recording_link", "transcript_link", "ppt_link"}


@dataclass
class PostEventResult:
    """Detailed result of the full post-event pipeline."""
    success:         bool
    transcript_url:  str = ""
    recording_url:   str = ""
    summary:         dict = field(default_factory=dict)   # LLM-generated structured summary
    blog_url:        str = ""
    blog_markdown:   str = ""
    linkedin_posted: bool = False
    meetup_posted:   bool = False
    wa_groups_sent:  int = 0
    errors:          list[str] = field(default_factory=list)
    data:            dict = field(default_factory=dict)   # all write-backs for sheets


class PostEventAgent:
    """
    Complete post-event pipeline.

    Designed to be called by the Orchestrator after the event concludes,
    or standalone via the CLI:
        python run.py post-event-agent --event-id 3 --meeting-id 123456789
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.llm = LLMClient(dry_run=dry_run)

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════════

    def run(
        self,
        event_data: dict,
        meeting_id: Optional[str] = None,
        platform: Optional[str] = None,
        transcript_path: Optional[str] = None,
    ) -> PostEventResult:
        """
        Run the full post-event pipeline.

        Args:
            event_data:      Row from Google Sheets (as loaded by SheetsClient).
            meeting_id:      Zoom/Meet meeting ID. Falls back to event_data["_meeting_id"].
            platform:        "zoom" | "gmeet" | None (auto-detect from meeting_id).
            transcript_path: Local path to a pre-downloaded transcript file.
                             If None, the agent will try to fetch it from Zoom cloud.
        Returns:
            PostEventResult with all URLs, the LLM summary, and error list.
        """
        result = PostEventResult(success=False)
        row    = event_data.get("_row_number", 0)

        logger.info(
            "[bold cyan]Post-Event Pipeline starting[/] — "
            f"event: {event_data.get('event_title', '?')} "
            f"(row {row})"
        )

        # ── Step 1: Resolve meeting ID and platform ───────────────────────────
        mid      = meeting_id or event_data.get("_meeting_id") or event_data.get("meeting_id")
        platform = platform   or event_data.get("_platform", "zoom")

        # ── Step 2: Provision Drive folders ───────────────────────────────────
        folder_map = self._provision_folders(event_data)

        # ── Step 3: Fetch + download recording ────────────────────────────────
        recording_local, recording_url = self._handle_recording(
            event_data, mid, platform, folder_map
        )
        if recording_url:
            result.recording_url  = recording_url
            result.data["recording_link"] = recording_url

        # ── Step 4: Get transcript ─────────────────────────────────────────────
        transcript_local = self._resolve_transcript(
            event_data, mid, platform, transcript_path, recording_local
        )

        # ── Step 5: Parse transcript ───────────────────────────────────────────
        parsed: Optional[ParsedTranscript] = None
        if transcript_local and Path(transcript_local).exists():
            try:
                parsed = transcript_processor.process_file(transcript_local)
                logger.info(
                    f"Transcript parsed — {parsed.word_count} words, "
                    f"~{parsed.duration_hint}, format: {parsed.format_detected.value}"
                )
            except Exception as e:
                msg = f"Transcript parsing failed: {e}"
                logger.error(msg)
                result.errors.append(msg)
        else:
            logger.warning("No transcript available — LLM steps will use event metadata only")

        # ── Step 6: LLM structured summary ────────────────────────────────────
        summary = self._generate_summary(event_data, parsed)
        result.summary = summary
        logger.info(f"Summary generated — {len(summary.get('key_takeaways', []))} takeaways")

        # ── Step 7: LLM blog post ──────────────────────────────────────────────
        blog_md = self._generate_blog(event_data, parsed, summary)
        result.blog_markdown = blog_md

        # ── Step 8: Upload transcript to Drive ────────────────────────────────
        transcript_url = ""
        if transcript_local and Path(transcript_local).exists():
            transcript_url = self._upload_transcript(event_data, transcript_local, folder_map)
            result.transcript_url             = transcript_url
            result.data["transcript_link"]    = transcript_url

        # ── Step 9: Upload blog to Drive ──────────────────────────────────────
        blog_url = ""
        if blog_md:
            blog_url          = self._upload_blog(event_data, blog_md, folder_map)
            result.blog_url   = blog_url
            result.data["blog_link"] = blog_url

        # ── Step 10: Write all links back to Google Sheet ─────────────────────
        self._write_to_sheet(row, result)

        # ── Step 11: LinkedIn public gratitude post ────────────────────────────
        result.linkedin_posted = self._post_linkedin(event_data, summary, blog_url)

        # ── Step 12: Meetup attendee post (closed — with all resources) ────────
        result.meetup_posted = self._post_meetup_update(event_data, result)

        # ── Step 13: WhatsApp closed share ────────────────────────────────────
        result.wa_groups_sent = self._share_wa_closed(event_data, result)

        # ── Step 14: Mark event Completed in sheet ────────────────────────────
        self._finalise_sheet(row)

        # ── Step 15: Notify organiser ─────────────────────────────────────────
        self._notify_organiser(event_data, result)

        result.success = True
        logger.info(
            "[bold green]Post-Event Pipeline complete ✓[/] — "
            f"errors: {len(result.errors)}"
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # STEP IMPLEMENTATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Folder provisioning ───────────────────────────────────────────────────

    def _provision_folders(self, event_data: dict) -> dict:
        if self.dry_run:
            logger.info("[DRY-RUN] Would provision Drive folders")
            return {k: "dry-run-folder-id" for k in [
                "02_Recording","03_Transcript","05_Blogs_Drafts","04_Presentations"
            ]}
        try:
            date   = event_data.get("date", "").replace(" ", "-")
            series = event_data.get("series", "Event").replace(" ", "_")
            title  = event_data.get("event_title", "Untitled")[:30].replace(" ", "_")
            slug   = f"{date}_{series}_{title}"

            folder_map = drive_client.provision_post_event_folders(
                event_slug     = slug,
                root_folder_id = settings.google_drive_root_folder_id,
            )
            logger.info(f"Drive folders ready: {len(folder_map)} folders")
            return folder_map
        except Exception as e:
            logger.warning(f"Drive folder provisioning failed: {e} — uploads will go to root")
            return {}

    # ── Recording ─────────────────────────────────────────────────────────────

    def _handle_recording(
        self,
        event_data: dict,
        meeting_id: Optional[str],
        platform: str,
        folder_map: dict,
    ) -> tuple[str, str]:
        """
        Download recording from Zoom/GMeet and upload to Drive.
        Returns (local_tmp_path, drive_url).
        GMeet recordings require Workspace and are handled manually (link provided by organiser).
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would fetch and upload recording")
            return "", "https://drive.google.com/file/d/DRY_RUN/view"

        if platform == "zoom" and meeting_id:
            return self._handle_zoom_recording(event_data, meeting_id, folder_map)

        if platform == "teams" and meeting_id:
            return self._handle_teams_recording(event_data, meeting_id, folder_map)

        if platform == "gmeet":
            # GMeet recordings go to the organiser's Drive automatically (Workspace plan).
            # On the free tier the organiser provides the link manually.
            rec_url = event_data.get("_recording_manual_url", "")
            if rec_url:
                logger.info(f"Using manually provided recording URL: {rec_url}")
                return "", rec_url
            logger.info(
                "Google Meet recording: provide the Drive URL in event_data['_recording_manual_url']"
                " or upload manually and paste into the sheet."
            )
            return "", ""

        logger.info("No meeting_id / platform — skipping recording download")
        return "", ""

    def _handle_zoom_recording(
        self,
        event_data: dict,
        meeting_id: str,
        folder_map: dict,
    ) -> tuple[str, str]:
        from wimlds.integrations.meeting.zoom_client import zoom_client

        logger.info(f"Fetching Zoom recording for meeting {meeting_id} ...")
        try:
            recording = zoom_client.get_recording(meeting_id)
        except Exception as e:
            logger.error(f"Could not fetch Zoom recording: {e}")
            return "", ""

        if not recording:
            logger.warning("Recording not found on Zoom")
            return "", ""

        logger.info(
            f"Recording ready — {recording.file_size_mb} MB | "
            f"transcript available: {bool(recording.transcript_download_url)}"
        )

        # Download to temp file
        tmp_dir = tempfile.mkdtemp(prefix="wimlds_rec_")
        date    = event_data.get("date", "").replace(" ", "-")
        series  = event_data.get("series", "")
        rec_filename = f"{date}_{series}_Recording.mp4"
        local_path   = str(Path(tmp_dir) / rec_filename)

        zoom_client.download_recording(recording.download_url, local_path)

        # Upload to Drive
        rec_folder = (
            folder_map.get("02_Recording")
            or settings.google_drive_root_folder_id
        )
        rec_url = drive_client.upload_file(
            local_path = local_path,
            folder_id  = rec_folder,
            filename   = rec_filename,
            mime_type  = "video/mp4",
        )

        # Optionally delete from Zoom to free storage
        try:
            zoom_client.delete_recording(meeting_id)
        except Exception:
            pass   # non-fatal

        # Store transcript download URL for next step
        event_data["_zoom_transcript_url"] = recording.transcript_download_url or ""
        event_data["_zoom_token"]          = None  # token already in client

        return local_path, rec_url

    def _handle_teams_recording(
        self,
        event_data: dict,
        meeting_id: str,
        folder_map: dict,
    ) -> tuple[str, str]:
        """
        Fetch recording from Microsoft Teams via Graph API and upload to Drive.

        meeting_id here can be either:
          - The full Teams Graph meeting ID (long encoded string)
          - A Teams meeting join URL (https://teams.microsoft.com/l/meetup-join/...)
        """
        from wimlds.integrations.meeting.teams_client import teams_client

        logger.info(f"Fetching Teams recording for meeting {meeting_id[:40]}...")

        try:
            # Detect if it's a join URL or a meeting ID
            if meeting_id.startswith("http"):
                rec_path, transcript_path = teams_client.fetch_meeting_artifacts(
                    join_url=meeting_id
                )
            else:
                rec_path, transcript_path = teams_client.fetch_meeting_artifacts(
                    meeting_id=meeting_id
                )
        except Exception as e:
            logger.error(f"Could not fetch Teams recording: {e}")
            return "", ""

        if not rec_path:
            logger.warning("Teams recording not available")
            return "", ""

        # Rename to standard WiMLDS convention
        tmp_dir      = tempfile.mkdtemp(prefix="wimlds_teams_")
        date         = event_data.get("date", "").replace(" ", "-")
        series       = event_data.get("series", "")
        rec_filename = f"{date}_{series}_Recording.mp4"
        local_path   = str(Path(tmp_dir) / rec_filename)
        import shutil
        shutil.copy2(str(rec_path), local_path)

        # Upload to Drive
        rec_folder = (
            folder_map.get("02_Recording")
            or settings.google_drive_root_folder_id
        )
        rec_url = drive_client.upload_file(
            local_path = local_path,
            folder_id  = rec_folder,
            filename   = rec_filename,
            mime_type  = "video/mp4",
        )

        # Store transcript path for next step (Teams gives us the file directly)
        if transcript_path:
            event_data["_teams_transcript_path"] = str(transcript_path)

        return local_path, rec_url

    # ── Transcript ────────────────────────────────────────────────────────────

    def _resolve_transcript(
        self,
        event_data: dict,
        meeting_id: Optional[str],
        platform: str,
        transcript_path: Optional[str],
        recording_local: str,
    ) -> Optional[str]:
        """
        Find or download the transcript file.
        Priority: provided path > Zoom cloud auto-transcript > None.
        Returns local file path or None.
        """
        # Caller provided a path
        if transcript_path and Path(transcript_path).exists():
            logger.info(f"Using provided transcript: {transcript_path}")
            return transcript_path

        # Zoom auto-transcript URL was stored during recording download
        zoom_transcript_url = event_data.get("_zoom_transcript_url", "")
        if zoom_transcript_url and platform == "zoom" and not self.dry_run:
            return self._download_zoom_transcript(zoom_transcript_url, event_data)

        # Zoom — fetch via API (in case recording was handled separately)
        if platform == "zoom" and meeting_id and not self.dry_run:
            return self._fetch_zoom_transcript_via_api(meeting_id, event_data)

        # Teams — transcript was already downloaded alongside the recording
        teams_transcript_path = event_data.get("_teams_transcript_path", "")
        if teams_transcript_path and Path(teams_transcript_path).exists():
            logger.info(f"Using Teams transcript: {teams_transcript_path}")
            return teams_transcript_path

        logger.info("No transcript source available — continuing without transcript")
        return None

    def _download_zoom_transcript(self, url: str, event_data: dict) -> Optional[str]:
        from wimlds.integrations.meeting.zoom_client import zoom_client
        tmp_dir  = tempfile.mkdtemp(prefix="wimlds_tr_")
        date     = event_data.get("date", "").replace(" ", "-")
        series   = event_data.get("series", "")
        filename = f"{date}_{series}_Transcript.vtt"
        dest     = str(Path(tmp_dir) / filename)
        try:
            return zoom_client.download_transcript(url, dest)
        except Exception as e:
            logger.error(f"Failed to download Zoom transcript: {e}")
            return None

    def _fetch_zoom_transcript_via_api(self, meeting_id: str, event_data: dict) -> Optional[str]:
        """Attempt to retrieve transcript URL from Zoom API (separate from recording download)."""
        from wimlds.integrations.meeting.zoom_client import zoom_client
        try:
            recording = zoom_client.get_recording(meeting_id)
            if recording and recording.transcript_download_url:
                return self._download_zoom_transcript(
                    recording.transcript_download_url, event_data
                )
        except Exception as e:
            logger.warning(f"Transcript fetch via API failed: {e}")
        return None

    # ── LLM: Structured Summary ────────────────────────────────────────────────

    def _generate_summary(
        self, event_data: dict, parsed: Optional[ParsedTranscript]
    ) -> dict:
        """
        Ask Claude to produce a structured JSON summary from the transcript.
        Falls back gracefully if no transcript is available.
        """
        event_ctx = _event_context(event_data)
        transcript_section = (
            f"TRANSCRIPT (first 6000 chars):\n{parsed.clean_text[:6000]}"
            if parsed and parsed.clean_text
            else "TRANSCRIPT: Not available — use event metadata only."
        )

        prompt = f"""You are summarising a WiMLDS Pune community tech meetup.

EVENT CONTEXT:
{event_ctx}

{transcript_section}

Produce a structured summary. Return ONLY valid JSON with this exact schema:
{{
  "one_liner": "One sentence describing what attendees learned (max 25 words)",
  "session_overview": "2-3 sentences covering the main theme and approach",
  "key_takeaways": [
    "Takeaway 1 (specific, actionable, 15-20 words)",
    "Takeaway 2",
    "Takeaway 3",
    "Takeaway 4",
    "Takeaway 5"
  ],
  "key_insights": [
    "Insight 1 — a nuanced observation from the session",
    "Insight 2",
    "Insight 3"
  ],
  "notable_quotes": [
    "Direct quote if available from transcript, otherwise empty"
  ],
  "topics_covered": ["topic1", "topic2", "topic3"],
  "audience_level": "Beginner | Intermediate | Advanced | Mixed",
  "highlights_for_linkedin": "3-4 bullet points as a single string, each on a new line, starting with •"
}}"""

        logger.info("Calling LLM for structured summary ...")
        try:
            summary = self.llm.generate_json(prompt, max_tokens=1200)
            logger.info("Structured summary generated ✓")
            return summary
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return _fallback_summary(event_data)

    # ── LLM: Blog Post ────────────────────────────────────────────────────────

    def _generate_blog(
        self,
        event_data: dict,
        parsed: Optional[ParsedTranscript],
        summary: dict,
    ) -> str:
        """
        Generate a full markdown blog post from transcript + structured summary.
        The blog is ready to publish on the WiMLDS Pune website or Medium.
        """
        event_ctx  = _event_context(event_data)
        transcript_section = ""
        if parsed and parsed.clean_text:
            # Send first 8000 chars (roughly 60-90 min of conversation)
            transcript_section = (
                f"\n\nFULL TRANSCRIPT EXCERPT (first 8000 chars):\n"
                f"{parsed.clean_text[:8000]}"
            )

        summary_json = "\n".join(f"  {k}: {v}" for k, v in summary.items())

        prompt = f"""You are writing a high-quality blog post for the WiMLDS Pune community website.

EVENT CONTEXT:
{event_ctx}

STRUCTURED SUMMARY (already generated):
{summary_json}
{transcript_section}

Write a complete, polished blog post in Markdown. Requirements:
- Title: use the event title
- Subtitle / meta: date, speaker, WiMLDS Pune
- Introduction paragraph (engaging, sets context, ~100 words)
- "What We Covered" section (2-3 paragraphs from transcript/summary)
- "Top 5 Key Takeaways" as a numbered list (from summary.key_takeaways)
- "Deep Dive: Key Insights" section (from summary.key_insights)
- One notable quote block (> quote) if available
- "About the Speaker" section (1 paragraph using speaker metadata)
- "Join WiMLDS Pune" closing CTA (1 paragraph, mention Meetup group)
- Tags line at bottom: #WiMLDS #Pune #AI etc.

Tone: professional but warm, accessible to ML/tech practitioners.
Length: 600-900 words.
Format: valid Markdown only, no HTML."""

        logger.info("Calling LLM for blog post generation ...")
        blog = self.llm.generate(prompt, max_tokens=2000)
        logger.info(f"Blog generated — {len(blog.split())} words")
        return blog

    # ── Drive uploads ─────────────────────────────────────────────────────────

    def _upload_transcript(
        self, event_data: dict, local_path: str, folder_map: dict
    ) -> str:
        if self.dry_run:
            return "https://drive.google.com/file/d/DRY_RUN_TR/view"
        try:
            date   = event_data.get("date", "").replace(" ", "-")
            series = event_data.get("series", "")
            ext    = Path(local_path).suffix or ".txt"
            name   = f"{date}_{series}_Transcript{ext}"
            folder = folder_map.get("03_Transcript") or settings.google_drive_root_folder_id
            url    = drive_client.upload_file(local_path, folder, filename=name)
            logger.info(f"Transcript uploaded → {url}")
            return url
        except Exception as e:
            logger.error(f"Transcript upload failed: {e}")
            return ""

    def _upload_blog(self, event_data: dict, blog_md: str, folder_map: dict) -> str:
        if self.dry_run:
            return "https://drive.google.com/file/d/DRY_RUN_BLOG/view"
        try:
            date   = event_data.get("date", "").replace(" ", "-")
            series = event_data.get("series", "")
            name   = f"{date}_{series}_Blog.md"
            folder = folder_map.get("05_Blogs_Drafts") or settings.google_drive_root_folder_id
            url    = drive_client.upload_bytes(
                data      = blog_md.encode("utf-8"),
                filename  = name,
                folder_id = folder,
                mime_type = "text/markdown",
            )
            logger.info(f"Blog uploaded → {url}")
            return url
        except Exception as e:
            logger.error(f"Blog upload failed: {e}")
            return ""

    # ── Sheet write-back ──────────────────────────────────────────────────────

    def _write_to_sheet(self, row: int, result: PostEventResult):
        if not row or self.dry_run:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would write to sheet row {row}: {result.data}")
            return
        try:
            from wimlds.core.sheets_client import sheets_client
            if result.data:
                sheets_client.write_fields(row, result.data)
                logger.info(f"Sheet row {row} updated with {len(result.data)} fields")
        except Exception as e:
            logger.error(f"Sheet write-back failed: {e}")

    def _finalise_sheet(self, row: int):
        if not row or self.dry_run:
            return
        try:
            from wimlds.core.sheets_client import sheets_client
            sheets_client.write_fields(row, {
                "event_status":           "Completed",
                "post_event_update_sent": "Y",
                "post_event_completed":   "Y",
            })
            logger.info(f"Event marked Completed in sheet row {row}")
        except Exception as e:
            logger.error(f"Could not finalise sheet: {e}")

    # ── LinkedIn post ─────────────────────────────────────────────────────────

    def _post_linkedin(
        self, event_data: dict, summary: dict, blog_url: str
    ) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Would post LinkedIn gratitude post")
            return True
        try:
            from wimlds.config.message_templates import POST_EVENT_LINKEDIN_TEMPLATE
            highlights = summary.get("highlights_for_linkedin", "")
            c_tags     = _format_c_level_tags(event_data)

            post_text = POST_EVENT_LINKEDIN_TEMPLATE.format(
                event_title   = event_data.get("event_title", ""),
                venue_name    = event_data.get("venue_name", ""),
                series        = event_data.get("series", ""),
                speaker_name  = event_data.get("speaker_name", ""),
                speaker_title = event_data.get("speaker_title", ""),
                speaker_org   = event_data.get("speaker_org", ""),
                venue_sponsor = event_data.get("venue_sponsor_name", ""),
                gift_sponsor  = "Fragrance Stories"
                                if event_data.get("gift_sponsor", "").upper() == "YES" else "",
                highlights_block = highlights,
                blog_link     = blog_url or "Coming soon",
                meetup_url    = event_data.get("meetup_event_url", ""),
                c_level_tags  = c_tags,
            )

            token = settings.linkedin_access_token
            if not token:
                logger.warning("LINKEDIN_ACCESS_TOKEN not set — skipping LinkedIn post")
                return False

            from wimlds.agents.publishing.social_agent import SocialAgent
            sa = SocialAgent(dry_run=False)
            ok = sa._post_linkedin(post_text, image_path=None)
            if ok:
                logger.info("LinkedIn gratitude post published ✓")
            return ok
        except ImportError:
            logger.warning("SocialAgent / message_templates not available in standalone mode")
            return False
        except Exception as e:
            logger.error(f"LinkedIn post failed: {e}")
            return False

    # ── Meetup attendee message ────────────────────────────────────────────────

    def _post_meetup_update(self, event_data: dict, result: PostEventResult) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Would post Meetup attendee update")
            return True
        try:
            from wimlds.agents.publishing.meetup_agent import MeetupAgent
            lines = [f"📚 Resources from {event_data.get('event_title', '')}:\n"]
            if result.blog_url:
                lines.append(f"📝 Blog Recap: {result.blog_url}")
            if result.recording_url:
                lines.append(f"🎥 Recording: {result.recording_url}")
            if result.transcript_url:
                lines.append(f"📄 Transcript: {result.transcript_url}")
            if event_data.get("ppt_link"):
                lines.append(f"📊 Slides: {event_data['ppt_link']}")
            lines.append("\nThank you all for attending! See you at the next one. 🚀")

            msg = "\n".join(lines)
            ma  = MeetupAgent(dry_run=False)
            res = ma.post_attendee_message(event_data, msg)
            if res.success:
                logger.info("Meetup attendee update sent ✓")
            return res.success
        except ImportError:
            logger.warning("MeetupAgent not available in standalone mode")
            return False
        except Exception as e:
            logger.error(f"Meetup update failed: {e}")
            return False

    # ── WhatsApp closed sharing ───────────────────────────────────────────────

    def _share_wa_closed(self, event_data: dict, result: PostEventResult) -> int:
        """
        Send recording + transcript + blog to CLOSED WA groups only.
        NEVER send to individual contacts (closed-sharing rule).
        Returns number of groups messaged.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would share resources on closed WA groups")
            return 0
        try:
            lines = [
                f"📚 *{event_data.get('event_title', '')}* — Resources:",
            ]
            if result.blog_url:
                lines.append(f"📝 Blog: {result.blog_url}")
            if result.recording_url:
                lines.append(f"🎥 Recording: {result.recording_url}")
            if result.transcript_url:
                lines.append(f"📄 Transcript: {result.transcript_url}")
            if event_data.get("ppt_link"):
                lines.append(f"📊 Slides: {event_data['ppt_link']}")
            lines.append(
                "\n🔒 Shared with WiMLDS community — please do not redistribute publicly."
            )
            msg = "\n".join(lines)

            from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
            wa     = WhatsAppAgent(dry_run=False)
            groups = wa._get_groups(event_data, individual=False)
            wa._send_to_groups(msg, groups)
            logger.info(f"Resources shared to {len(groups)} WA groups ✓")
            return len(groups)
        except ImportError:
            logger.warning("WhatsAppAgent not available in standalone mode")
            return 0
        except Exception as e:
            logger.error(f"WA closed share failed: {e}")
            return 0

    # ── Organiser notification ────────────────────────────────────────────────

    def _notify_organiser(self, event_data: dict, result: PostEventResult):
        if self.dry_run or not settings.sendgrid_api_key:
            return
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail

            body_lines = [
                f"Post-event pipeline complete for: {event_data.get('event_title')}",
                "",
                f"✅ Recording:   {result.recording_url or 'N/A'}",
                f"✅ Transcript:  {result.transcript_url or 'N/A'}",
                f"✅ Blog:        {result.blog_url or 'N/A'}",
                f"✅ LinkedIn:    {'posted' if result.linkedin_posted else 'FAILED'}",
                f"✅ Meetup:      {'posted' if result.meetup_posted else 'FAILED'}",
                f"✅ WA groups:   {result.wa_groups_sent} messaged",
            ]
            if result.errors:
                body_lines += ["", "⚠ Errors:"] + [f"  • {e}" for e in result.errors]

            body_lines += [
                "",
                "Blog preview (first 500 chars):",
                result.blog_markdown[:500] + "...",
            ]

            mail = Mail(
                from_email    = settings.notification_email,
                to_emails     = settings.notification_email,
                subject       = f"[WiMLDS] Post-event pipeline done — {event_data.get('event_title', '')}",
                plain_text_content = "\n".join(body_lines),
            )
            sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
            sg.client.mail.send.post(request_body=mail.get())
            logger.info("Organiser notification sent ✓")
        except Exception as e:
            logger.warning(f"Could not send organiser notification: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _event_context(event_data: dict) -> str:
    return (
        f"Title:        {event_data.get('event_title', '')}\n"
        f"Series:       {event_data.get('series', '')}\n"
        f"Date:         {event_data.get('date', '')} ({event_data.get('day', '')})\n"
        f"Time:         {event_data.get('start_time_ist', '')}–{event_data.get('end_time_ist', '')} IST\n"
        f"Mode:         {event_data.get('mode', 'In-Person')}\n"
        f"Venue:        {event_data.get('venue_name', '')}, {event_data.get('venue_address', '')}\n"
        f"Speaker:      {event_data.get('speaker_name', '')} — "
        f"{event_data.get('speaker_title', '')} at {event_data.get('speaker_org', '')}\n"
        f"Qualification:{event_data.get('speaker_highest_qualification', '')}\n"
        f"Achievements: {event_data.get('speaker_special_achievements', '')}\n"
        f"Subtitle:     {event_data.get('subtitle', '')}\n"
        f"Session type: {event_data.get('session_type', '')}\n"
        f"RSVPs:        {event_data.get('_rsvp_count', 'N/A')}\n"
    )


def _fallback_summary(event_data: dict) -> dict:
    """Return a minimal summary when LLM call fails."""
    return {
        "one_liner":            f"WiMLDS Pune hosted {event_data.get('event_title', 'a session')}.",
        "session_overview":     "An insightful session for the WiMLDS Pune community.",
        "key_takeaways":        ["Session held successfully.", "Resources shared with community."],
        "key_insights":         ["Community engagement remains strong."],
        "notable_quotes":       [],
        "topics_covered":       [],
        "audience_level":       "Mixed",
        "highlights_for_linkedin": "• Insightful session\n• Great networking\n• Community building",
    }


def _format_c_level_tags(event_data: dict) -> str:
    handles = event_data.get("c_level_linkedin_handles", "")
    if not handles:
        return ""
    return " ".join(f"@{h.strip()}" for h in handles.split(",") if h.strip())



