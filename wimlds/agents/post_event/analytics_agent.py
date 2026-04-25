"""
Analytics Agent — Full KPI aggregation, Analytics tab write-back,
Looker Studio / Metabase dashboard layer, completion email with
KPI snapshot, and month-over-month growth tracking toward the
10,000 Meetup members goal (March 2026).

Called by Orchestrator at Stage.ANALYTICS, or standalone via `python run.py analytics`.

Architecture:
  _collect_kpis()          — pulls from Meetup API, LinkedIn, Facebook, Twitter, Sheet fields
  _collect_growth()        — Meetup member count, MoM growth, goal gap, daily pace needed
  _write_analytics_tab()   — upserts a row in the "Analytics" Sheet tab (Looker Studio data source)
  _write_master_flags()    — sets event_status=Completed on the Master Event Sheet row
  _refresh_dashboard()     — Looker Studio auto-refreshes; Metabase pinged if configured
  _send_completion_email() — KPI snapshot + growth summary via SendGrid
"""

from __future__ import annotations

import time
from datetime import datetime, date
from typing import Optional
import pytz
import requests

from wimlds.config.settings    import settings
from wimlds.core.logger        import get_logger
from wimlds.core.sheets_client import sheets_client
from wimlds.core.orchestrator  import AgentResult

logger = get_logger("analytics_agent")
IST    = pytz.timezone("Asia/Kolkata")

# ── Constants ─────────────────────────────────────────────────────────────────
MEMBER_GOAL   = 10_000
GOAL_DATE     = date(2026, 3, 31)
ANALYTICS_TAB = "Analytics"        # name of the second Sheet tab
MASTER_TAB    = "Master Event Sheet"

# ── Analytics tab column map (field_key → column letter) ─────────────────────
# Row 2 = header labels, row 3+ = one row per event (matching Master Sheet row number)
ANALYTICS_COL: dict[str, str] = {
    # ── Identity ──────────────────────────────────────────────────────────────
    "row_id":           "A",
    "event_title":      "B",
    "date":             "C",
    "series":           "D",
    "mode":             "E",
    "session_type":     "F",
    "venue_name":       "G",
    "speaker_org":      "H",
    "speaker_tier1":    "I",
    # ── Funnel ────────────────────────────────────────────────────────────────
    "capacity":         "J",
    "rsvps":            "K",
    "showups":          "L",
    "showup_rate_pct":  "M",
    "waitlisted":       "N",
    # ── Community growth ──────────────────────────────────────────────────────
    "meetup_members":   "O",
    "new_members_30d":  "P",
    "mom_growth_pct":   "Q",
    "goal_gap":         "R",
    "members_needed_per_day": "S",
    # ── Social engagement ─────────────────────────────────────────────────────
    "linkedin_reactions": "T",
    "linkedin_comments":  "U",
    "linkedin_shares":    "V",
    "facebook_reactions": "W",
    "facebook_comments":  "X",
    "twitter_impressions":"Y",
    "twitter_likes":      "Z",
    "twitter_retweets":   "AA",
    "wa_groups_count":    "AB",
    "wa_individuals_count":"AC",
    # ── Ops cadence (Y/N) ─────────────────────────────────────────────────────
    "announce_sent":      "AD",
    "t2d_sent":           "AE",
    "t1d_sent":           "AF",
    "t2h_sent":           "AG",
    "wa_groups_posted":   "AH",
    "partners_notified":  "AI",
    "post_event_completed":"AJ",
    # ── Content delivered ─────────────────────────────────────────────────────
    "blog_link":          "AK",
    "recording_link":     "AL",
    "transcript_link":    "AM",
    "ppt_link":           "AN",
    # ── Meta ──────────────────────────────────────────────────────────────────
    "collected_at":       "AO",
}

# Human-readable header labels for the Analytics tab (matches key order above)
ANALYTICS_HEADERS: list[str] = [
    "Row ID", "Event Title", "Date", "Series", "Mode", "Session Type",
    "Venue", "Speaker Org", "Tier-1 Speaker",
    "Capacity", "RSVPs", "Show-ups", "Show-up Rate %", "Waitlisted",
    "Meetup Members", "New Members (30d)", "MoM Growth %", "Goal Gap", "Members/Day Needed",
    "LI Reactions", "LI Comments", "LI Shares",
    "FB Reactions", "FB Comments",
    "TW Impressions", "TW Likes", "TW Retweets",
    "WA Groups", "WA Individuals",
    "Announce Sent", "T-2d Sent", "T-1d Sent", "T-2h Sent",
    "WA Groups Posted", "Partners Notified", "Post-Event Done",
    "Blog Link", "Recording Link", "Transcript Link", "Slides Link",
    "Collected At",
]


# ─────────────────────────────────────────────────────────────────────────────
class AnalyticsAgent:
    """
    Collects all KPIs from APIs + Sheet, writes them to the Analytics tab,
    updates dashboards, tracks 10k-member growth goal, and sends the
    organizer a completion email.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run       = dry_run
        self._meetup_auth  = None   # lazy-initialised

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point — called by Orchestrator
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, event_data: dict, row_num: int) -> AgentResult:
        """Full analytics pipeline for one completed event."""
        title = event_data.get("event_title", f"row {row_num}")
        logger.info(f"Analytics starting: {title}")

        # 1 — Collect per-event KPIs
        kpis = self._collect_kpis(event_data, row_num)

        # 2 — Community growth snapshot
        growth = self._collect_growth()
        kpis.update(growth)

        # 3 — Write to Analytics tab
        self._write_analytics_tab(row_num, kpis)

        # 4 — Flag event as Completed on Master Sheet
        self._write_master_flags(row_num)

        # 5 — Trigger dashboard refresh
        self._refresh_dashboard()

        # 6 — Send completion email with KPI snapshot
        self._send_completion_email(event_data, kpis, growth)

        logger.info(f"Analytics complete: {title}")
        return AgentResult(success=True, data={"kpis": kpis, "growth": growth})

    # ─────────────────────────────────────────────────────────────────────────
    # Standalone helpers (called by the analytics CLI command directly)
    # ─────────────────────────────────────────────────────────────────────────

    def run_standalone(self, event_data: dict, row_num: int) -> AgentResult:
        """Re-run analytics for an already-completed event (e.g. back-fill engagement)."""
        return self.run(event_data, row_num)

    def growth_report_only(self) -> dict:
        """Return a growth snapshot with no event context. Used by --growth-only flag."""
        growth = self._collect_growth()
        logger.info(f"Growth snapshot: {growth}")
        return growth

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1 — Per-event KPI collection
    # ─────────────────────────────────────────────────────────────────────────

    def _collect_kpis(self, event_data: dict, row_num: int) -> dict:
        kpis: dict = {}

        # Identity
        kpis["row_id"]       = str(event_data.get("row_id", row_num))
        kpis["event_title"]  = event_data.get("event_title", "")
        kpis["date"]         = event_data.get("date", "")
        kpis["series"]       = event_data.get("series", "")
        kpis["mode"]         = event_data.get("mode", "")
        kpis["session_type"] = event_data.get("session_type", "")
        kpis["venue_name"]   = event_data.get("venue_name", "")
        kpis["speaker_org"]  = event_data.get("speaker_org", "")
        kpis["speaker_tier1"]= event_data.get("tier_1_institution", "N")

        # Funnel
        capacity  = _safe_int(event_data.get("capacity", 0))
        rsvps     = self._fetch_rsvps(event_data)
        showups   = _safe_int(
            event_data.get("showup_count") or event_data.get("_showup_count", 0)
        )
        waitlisted = _safe_int(event_data.get("waitlisted", 0))
        kpis["capacity"]        = capacity
        kpis["rsvps"]           = rsvps
        kpis["showups"]         = showups
        kpis["waitlisted"]      = waitlisted
        kpis["showup_rate_pct"] = round(showups / rsvps * 100, 1) if rsvps > 0 else 0.0

        # Social engagement — each returns a sub-dict
        kpis.update(self._fetch_linkedin_engagement(event_data))
        kpis.update(self._fetch_facebook_engagement(event_data))
        kpis.update(self._fetch_twitter_engagement(event_data))

        # WhatsApp reach (derived from Master Sheet fields)
        groups_raw = event_data.get("meetup_groups_list", "")
        kpis["wa_groups_count"]      = _safe_int(
            event_data.get("wa_groups_count") or
            len([g for g in groups_raw.split(",") if g.strip()])
        )
        kpis["wa_individuals_count"] = _safe_int(
            event_data.get("wa_individuals_count", 0)
        )

        # Ops cadence — Y/N flags straight from the sheet
        kpis["announce_sent"]       = event_data.get("announce_sent", "N")
        kpis["t2d_sent"]            = event_data.get("tminus2_sent", "N")
        kpis["t1d_sent"]            = event_data.get("tminus1_sent", "N")
        kpis["t2h_sent"]            = event_data.get("tminus2h_sent", "N")
        kpis["wa_groups_posted"]    = event_data.get("whatsapp_groups_posted", "N")
        kpis["partners_notified"]   = event_data.get("partners_notified", "N")
        kpis["post_event_completed"]= event_data.get("post_event_completed", "N")

        # Content links
        kpis["blog_link"]       = event_data.get("blog_link", "")
        kpis["recording_link"]  = event_data.get("recording_link", "")
        kpis["transcript_link"] = event_data.get("transcript_link", "")
        kpis["ppt_link"]        = event_data.get("ppt_link", "")

        kpis["collected_at"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
        return kpis

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2 — Community growth snapshot
    # ─────────────────────────────────────────────────────────────────────────

    def _collect_growth(self) -> dict:
        """
        Fetch Meetup member count and compute:
          - New members in last 30 days
          - Month-over-month growth %
          - Gap to 10,000-member goal
          - Members/day needed to reach goal by March 31 2026
        """
        growth: dict = {
            "meetup_members":         0,
            "new_members_30d":        0,
            "mom_growth_pct":         0.0,
            "goal_gap":               MEMBER_GOAL,
            "members_needed_per_day": 0.0,
        }

        if self.dry_run:
            current = 8_450
            new30   = 120
            growth.update({
                "meetup_members":         current,
                "new_members_30d":        new30,
                "mom_growth_pct":         round(new30 / max(current - new30, 1) * 100, 2),
                "goal_gap":               MEMBER_GOAL - current,
                "members_needed_per_day": round(
                    (MEMBER_GOAL - current) / max((GOAL_DATE - date.today()).days, 1), 1
                ),
            })
            return growth

        try:
            auth  = self._get_meetup_auth()
            group = settings.meetup_group_urlname

            # Meetup GraphQL: member count + recently joined
            gql = """
            query($urlname: String!) {
              groupByUrlname(urlname: $urlname) {
                memberships          { count }
                recentlyJoined: memberships(filter: { joinedAfterDays: 30 }) { count }
              }
            }"""
            resp = requests.post(
                "https://api.meetup.com/gql",
                json={"query": gql, "variables": {"urlname": group}},
                headers={"Authorization": f"Bearer {auth.get_token()}"},
                timeout=15,
            )
            resp.raise_for_status()
            grp     = resp.json().get("data", {}).get("groupByUrlname", {})
            current = _safe_int(grp.get("memberships", {}).get("count", 0))
            new30   = _safe_int(grp.get("recentlyJoined", {}).get("count", 0))
            prior   = max(current - new30, 1)
            mom_pct = round(new30 / prior * 100, 2)
            gap     = max(MEMBER_GOAL - current, 0)
            today   = date.today()
            days_left = max((GOAL_DATE - today).days, 1)

            growth.update({
                "meetup_members":         current,
                "new_members_30d":        new30,
                "mom_growth_pct":         mom_pct,
                "goal_gap":               gap,
                "members_needed_per_day": round(gap / days_left, 1),
            })
            logger.info(
                f"Members: {current} | +{new30}/30d | MoM: {mom_pct}% | "
                f"Gap: {gap} | Needed/day: {growth['members_needed_per_day']}"
            )
        except Exception as exc:
            logger.warning(f"Meetup growth fetch failed (non-fatal): {exc}")

        return growth

    # ─────────────────────────────────────────────────────────────────────────
    # Step 3 — Write Analytics tab
    # ─────────────────────────────────────────────────────────────────────────

    def _write_analytics_tab(self, row_num: int, kpis: dict) -> None:
        """
        Write (or overwrite) the Analytics row that corresponds to this event.
        Row number is intentionally the same as the Master Sheet row so that
        Looker Studio JOIN queries work without a separate lookup.
        """
        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Would write {len(kpis)} KPI fields "
                f"to {ANALYTICS_TAB} tab row {row_num}"
            )
            return

        try:
            svc   = sheets_client._get_service()
            sid   = settings.google_sheets_id

            # Create the Analytics tab if it does not yet exist
            self._ensure_analytics_tab(svc, sid)

            # Write header row once (row 2 — row 1 is a title banner)
            self._ensure_analytics_headers(svc, sid)

            # Build the ordered value list
            ordered = sorted(ANALYTICS_COL.items(), key=lambda x: _col_index(x[1]))
            values  = [str(kpis.get(field, "")) for field, _ in ordered]
            last_col = _col_letter(len(values))
            rng     = f"{ANALYTICS_TAB}!A{row_num}:{last_col}{row_num}"

            svc.spreadsheets().values().update(
                spreadsheetId    = sid,
                range            = rng,
                valueInputOption = "USER_ENTERED",
                body             = {"values": [values]},
            ).execute()
            logger.info(f"Analytics tab written: {rng}")

        except Exception as exc:
            logger.error(f"Analytics tab write failed: {exc}")

    def _ensure_analytics_tab(self, svc, sid: str) -> None:
        """Add the Analytics sheet tab if missing."""
        try:
            meta     = svc.spreadsheets().get(spreadsheetId=sid).execute()
            existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
            if ANALYTICS_TAB not in existing:
                svc.spreadsheets().batchUpdate(
                    spreadsheetId=sid,
                    body={"requests": [{
                        "addSheet": {"properties": {"title": ANALYTICS_TAB, "index": 1}}
                    }]},
                ).execute()
                logger.info("Analytics tab created in Master Sheet")
        except Exception as exc:
            logger.warning(f"Could not ensure Analytics tab: {exc}")

    def _ensure_analytics_headers(self, svc, sid: str) -> None:
        """Write column headers to row 2 of the Analytics tab (idempotent)."""
        try:
            check = svc.spreadsheets().values().get(
                spreadsheetId=sid, range=f"{ANALYTICS_TAB}!A2:A2"
            ).execute()
            if check.get("values"):
                return  # headers already present
            last_col = _col_letter(len(ANALYTICS_HEADERS))
            svc.spreadsheets().values().update(
                spreadsheetId    = sid,
                range            = f"{ANALYTICS_TAB}!A2:{last_col}2",
                valueInputOption = "USER_ENTERED",
                body             = {"values": [ANALYTICS_HEADERS]},
            ).execute()
            logger.info("Analytics tab headers written")
        except Exception as exc:
            logger.warning(f"Analytics header write failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Step 4 — Master Sheet flag
    # ─────────────────────────────────────────────────────────────────────────

    def _write_master_flags(self, row_num: int) -> None:
        if self.dry_run:
            logger.info("[DRY-RUN] Would set event_status=Completed on Master Sheet")
            return
        try:
            sheets_client.write_fields(row_num, {"event_status": "Completed"})
        except Exception as exc:
            logger.warning(f"Master flag write-back failed (non-fatal): {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Step 5 — Dashboard refresh
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_dashboard(self) -> None:
        """
        Looker Studio:  auto-refreshes on next open from the Sheet — no action.
        Metabase:       ping the API to bust the question cache if configured.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would trigger dashboard refresh")
            return

        mb_url   = getattr(settings, "metabase_url", "")
        mb_token = getattr(settings, "metabase_session_token", "")
        mb_dash  = getattr(settings, "metabase_dashboard_id", "")

        if mb_url and mb_token and mb_dash:
            try:
                resp = requests.post(
                    f"{mb_url.rstrip('/')}/api/card/{mb_dash}/query",
                    headers={"X-Metabase-Session": mb_token,
                             "Content-Type": "application/json"},
                    json={},
                    timeout=15,
                )
                if resp.status_code in (200, 202):
                    logger.info("Metabase dashboard cache refreshed")
                else:
                    logger.warning(f"Metabase refresh HTTP {resp.status_code}")
            except Exception as exc:
                logger.warning(f"Metabase refresh failed (non-fatal): {exc}")
        else:
            logger.info("Looker Studio dashboard: auto-refreshes from Sheet — no action needed")

    # ─────────────────────────────────────────────────────────────────────────
    # Step 6 — Completion email
    # ─────────────────────────────────────────────────────────────────────────

    def _send_completion_email(
        self, event_data: dict, kpis: dict, growth: dict
    ) -> None:
        if self.dry_run:
            logger.info("[DRY-RUN] Would send completion email")
            return
        try:
            from wimlds.core.notifier import Notifier
            notifier         = Notifier(dry_run=False)
            subject, body    = _build_completion_email(event_data, kpis, growth)
            ok = notifier.send_raw(
                to_email=settings.notification_email,
                subject =subject,
                body    =body,
            )
            if ok:
                logger.info(f"Completion email sent → {settings.notification_email}")
            else:
                logger.warning("Completion email failed (non-fatal)")
        except Exception as exc:
            logger.warning(f"Completion email error (non-fatal): {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Platform engagement fetchers
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_rsvps(self, event_data: dict) -> int:
        if self.dry_run:
            return _safe_int(event_data.get("rsvps") or event_data.get("_rsvp_count", 45))
        try:
            auth     = self._get_meetup_auth()
            event_id = event_data.get("meetup_event_id", "").strip()
            group    = settings.meetup_group_urlname
            if not event_id:
                return _safe_int(event_data.get("rsvps", 0))
            resp = requests.get(
                f"https://api.meetup.com/{group}/events/{event_id}",
                headers={"Authorization": f"Bearer {auth.get_token()}"},
                timeout=10,
            )
            if resp.ok:
                return _safe_int(resp.json().get("yes_rsvp_count", 0))
        except Exception as exc:
            logger.warning(f"RSVP fetch failed: {exc}")
        return _safe_int(event_data.get("rsvps", 0))

    def _fetch_linkedin_engagement(self, event_data: dict) -> dict:
        defaults = {"linkedin_reactions": 0, "linkedin_comments": 0, "linkedin_shares": 0}
        if self.dry_run:
            return {"linkedin_reactions": 42, "linkedin_comments": 8, "linkedin_shares": 5}
        post_urn = event_data.get("_linkedin_post_urn", "")
        token    = getattr(settings, "linkedin_access_token", "")
        if not post_urn or not token:
            return defaults
        try:
            hdrs = {
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
            }
            r = requests.get(
                f"https://api.linkedin.com/v2/socialActions/{post_urn}",
                headers=hdrs, timeout=10,
            )
            if r.ok:
                d = r.json()
                return {
                    "linkedin_reactions": d.get("likesSummary", {}).get("totalLikes", 0),
                    "linkedin_comments":  d.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
                    "linkedin_shares":    d.get("sharesSummary", {}).get("totalShares", 0),
                }
        except Exception as exc:
            logger.warning(f"LinkedIn engagement fetch failed: {exc}")
        return defaults

    def _fetch_facebook_engagement(self, event_data: dict) -> dict:
        defaults = {"facebook_reactions": 0, "facebook_comments": 0}
        if self.dry_run:
            return {"facebook_reactions": 31, "facebook_comments": 6}
        post_id = event_data.get("_facebook_post_id", "")
        token   = getattr(settings, "facebook_page_token", "")
        if not post_id or not token:
            return defaults
        try:
            r = requests.get(
                f"https://graph.facebook.com/v18.0/{post_id}",
                params={
                    "fields":       "reactions.summary(true),comments.summary(true)",
                    "access_token": token,
                },
                timeout=10,
            )
            if r.ok:
                d = r.json()
                return {
                    "facebook_reactions": d.get("reactions", {}).get("summary", {}).get("total_count", 0),
                    "facebook_comments":  d.get("comments",  {}).get("summary", {}).get("total_count", 0),
                }
        except Exception as exc:
            logger.warning(f"Facebook engagement fetch failed: {exc}")
        return defaults

    def _fetch_twitter_engagement(self, event_data: dict) -> dict:
        defaults = {"twitter_impressions": 0, "twitter_likes": 0, "twitter_retweets": 0}
        if self.dry_run:
            return {"twitter_impressions": 1_240, "twitter_likes": 38, "twitter_retweets": 12}
        tweet_id = event_data.get("_twitter_tweet_id", "")
        if not tweet_id:
            return defaults
        try:
            import tweepy
            client = tweepy.Client(
                consumer_key        = getattr(settings, "twitter_api_key", ""),
                consumer_secret     = getattr(settings, "twitter_api_secret", ""),
                access_token        = getattr(settings, "twitter_access_token", ""),
                access_token_secret = getattr(settings, "twitter_access_token_secret", ""),
            )
            resp = client.get_tweet(tweet_id, tweet_fields=["public_metrics"])
            if resp.data:
                m = resp.data.public_metrics or {}
                return {
                    "twitter_impressions": m.get("impression_count", 0),
                    "twitter_likes":       m.get("like_count", 0),
                    "twitter_retweets":    m.get("retweet_count", 0),
                }
        except Exception as exc:
            logger.warning(f"Twitter engagement fetch failed: {exc}")
        return defaults

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_meetup_auth(self):
        if self._meetup_auth is None:
            from wimlds.agents.publishing.meetup_agent import MeetupAuth
            self._meetup_auth = MeetupAuth()
        return self._meetup_auth


# ─────────────────────────────────────────────────────────────────────────────
# Completion email
# ─────────────────────────────────────────────────────────────────────────────

def _build_completion_email(
    event_data: dict, kpis: dict, growth: dict
) -> tuple[str, str]:
    title     = event_data.get("event_title", "Event")
    subject   = f"✅ WiMLDS Post-Event Analytics — {title}"

    rsvps     = kpis.get("rsvps", 0)
    showups   = kpis.get("showups", 0)
    rate      = kpis.get("showup_rate_pct", 0)
    members   = growth.get("meetup_members", 0)
    new30     = growth.get("new_members_30d", 0)
    mom       = growth.get("mom_growth_pct", 0)
    gap       = growth.get("goal_gap", MEMBER_GOAL)
    npd       = growth.get("members_needed_per_day", 0)
    today     = date.today()
    days_left = max((GOAL_DATE - today).days, 0)

    flags     = ["announce_sent","t2d_sent","t1d_sent","t2h_sent",
                 "wa_groups_posted","partners_notified","post_event_completed"]
    done      = sum(1 for f in flags if kpis.get(f,"N").upper() == "Y")

    goal_line = (
        "  🏆  GOAL ACHIEVED — 10,000 members reached!\n"
        if gap == 0 else
        f"  Gap to goal  : {gap:,} members still needed\n"
        f"  Required pace: {npd} new members/day to hit goal by {GOAL_DATE}\n"
        f"  Days remaining: {days_left}\n"
    )

    body = f"""WiMLDS Pune — Post-Event Analytics Complete
{"=" * 62}
Event  : {title}
Date   : {event_data.get('date', '?')}   |   Series : {event_data.get('series', '?')}
Mode   : {event_data.get('mode', '?')}   |   Venue  : {event_data.get('venue_name', '?')}

──── ATTENDANCE FUNNEL ─────────────────────────────────────────
  Capacity        : {kpis.get('capacity', 0)}
  RSVPs           : {rsvps}
  Show-ups        : {showups}
  Show-up rate    : {rate}%
  Waitlisted      : {kpis.get('waitlisted', 0)}

──── SOCIAL ENGAGEMENT ─────────────────────────────────────────
  LinkedIn   : {kpis.get('linkedin_reactions', 0)} reactions  |  {kpis.get('linkedin_comments', 0)} comments  |  {kpis.get('linkedin_shares', 0)} shares
  Facebook   : {kpis.get('facebook_reactions', 0)} reactions  |  {kpis.get('facebook_comments', 0)} comments
  Twitter/X  : {kpis.get('twitter_impressions', 0):,} impressions  |  {kpis.get('twitter_likes', 0)} likes  |  {kpis.get('twitter_retweets', 0)} RTs
  WhatsApp   : {kpis.get('wa_groups_count', 0)} groups  |  {kpis.get('wa_individuals_count', 0)} individual sends

──── OPS CADENCE  ({done}/{len(flags)} tasks complete) ──────────────────────────
  Announcement sent     : {kpis.get('announce_sent','N')}
  T-2d spotlight        : {kpis.get('t2d_sent','N')}
  T-1d logistics        : {kpis.get('t1d_sent','N')}
  T-2h final bump       : {kpis.get('t2h_sent','N')}
  WA groups posted      : {kpis.get('wa_groups_posted','N')}
  Partners notified     : {kpis.get('partners_notified','N')}
  Post-event pipeline   : {kpis.get('post_event_completed','N')}

──── CONTENT DELIVERED ─────────────────────────────────────────
  Blog post   : {kpis.get('blog_link','') or '(not yet)'}
  Recording   : {kpis.get('recording_link','') or '(not yet)'}
  Transcript  : {kpis.get('transcript_link','') or '(not yet)'}
  Slides      : {kpis.get('ppt_link','') or '(not yet)'}

══════════════════════════════════════════════════════════════════
  🎯  10,000-MEMBER GOAL TRACKER  (Target: March 31 2026)
══════════════════════════════════════════════════════════════════
  Current members     : {members:,}
  New in last 30 days : +{new30:,}
  Month-over-month    : +{mom}%
{goal_line}
──── DASHBOARD ─────────────────────────────────────────────────
  All KPIs written to: Master Sheet → Analytics tab
  Looker Studio will auto-refresh on next open.
  Collected at: {kpis.get('collected_at','?')}

{"=" * 62}
WiMLDS Automation Orchestrator
"""
    return subject, body


# ─────────────────────────────────────────────────────────────────────────────
# Column helpers
# ─────────────────────────────────────────────────────────────────────────────

def _col_index(col: str) -> int:
    """Convert column letter (A, B … AA, AB …) to 0-based integer."""
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - 64)
    return result - 1

def _col_letter(n: int) -> str:
    """Convert 1-based column number to letter(s)."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result

def _safe_int(val) -> int:
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0



