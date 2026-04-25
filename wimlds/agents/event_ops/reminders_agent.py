"""
Reminders Agent — Schedules T-2d / T-1d / T-2h blasts.
Each reminder fires on Social + WA + Meetup attendees simultaneously.
"""
from datetime import datetime, timedelta
from typing import Optional
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.date import DateTrigger

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.sheets_client import sheets_client
from wimlds.core.orchestrator import AgentResult

logger = get_logger("reminders_agent")

IST = pytz.timezone("Asia/Kolkata")


class RemindersAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._scheduler: Optional[BackgroundScheduler] = None

    def _get_scheduler(self) -> BackgroundScheduler:
        if self._scheduler is None:
            try:
                job_stores = {
                    "default": RedisJobStore(
                        jobs_key="wimlds:apscheduler:jobs",
                        run_times_key="wimlds:apscheduler:run_times",
                        host=settings.redis_url.replace("redis://", "").split(":")[0],
                        port=int(settings.redis_url.split(":")[-1].split("/")[0]),
                    )
                }
            except Exception:
                job_stores = {}   # In-memory fallback

            self._scheduler = BackgroundScheduler(
                jobstores=job_stores,
                executors={"default": ThreadPoolExecutor(max_workers=4)},
                timezone=IST,
            )
        return self._scheduler

    # ── Main entry ────────────────────────────────────────────────────────────

    def schedule_all(self, event_data: dict, row_num: int) -> AgentResult:
        """Schedule T-2d, T-1d, T-2h reminders for an event."""
        event_dt = self._parse_event_datetime(event_data)
        if event_dt is None:
            return AgentResult(success=False, error="Could not parse event date/time")

        event_id = str(row_num)
        jobs_scheduled = []

        # T-2 days (48h before)
        t2d_time = event_dt - timedelta(days=2)
        if t2d_time > datetime.now(IST):
            self._schedule_job(
                job_id=f"{event_id}_t2d",
                run_at=t2d_time,
                func=self._fire_t2d,
                args=[event_id],
            )
            jobs_scheduled.append(f"T-2d @ {t2d_time.strftime('%d %b %Y %H:%M IST')}")
        else:
            logger.warning(f"T-2d reminder time {t2d_time} is in the past — skipping")

        # T-1 day (24h before)
        t1d_time = event_dt - timedelta(days=1)
        if t1d_time > datetime.now(IST):
            self._schedule_job(
                job_id=f"{event_id}_t1d",
                run_at=t1d_time,
                func=self._fire_t1d,
                args=[event_id],
            )
            jobs_scheduled.append(f"T-1d @ {t1d_time.strftime('%d %b %Y %H:%M IST')}")

        # T-2 hours (2h before)
        t2h_time = event_dt - timedelta(hours=2)
        if t2h_time > datetime.now(IST):
            self._schedule_job(
                job_id=f"{event_id}_t2h",
                run_at=t2h_time,
                func=self._fire_t2h,
                args=[event_id],
            )
            jobs_scheduled.append(f"T-2h @ {t2h_time.strftime('%d %b %Y %H:%M IST')}")

        # Start scheduler if not running
        sched = self._get_scheduler()
        if not sched.running:
            sched.start()

        logger.info(f"Reminders scheduled: {jobs_scheduled}")
        return AgentResult(success=True, data={"jobs": jobs_scheduled})

    # ── Reminder firers ───────────────────────────────────────────────────────

    def _fire_t2d(self, event_id: str):
        """T-2 days: Speaker Spotlight blast."""
        logger.info(f"🔔 T-2d reminder firing for event {event_id}")
        try:
            event_data = sheets_client.get_event(int(event_id))

            # Guard: check if already sent
            if event_data.get("tminus2_sent", "").upper() == "Y":
                logger.info("T-2d already sent — skipping")
                return

            from wimlds.agents.publishing.social_agent import SocialAgent
            from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
            from wimlds.agents.publishing.meetup_agent import MeetupAgent
            from wimlds.config.message_templates import EventContext, render_spotlight
            from wimlds.agents.publishing.social_agent import _event_to_context

            ctx = _event_to_context(event_data)
            message = render_spotlight(ctx)

            SocialAgent(dry_run=self.dry_run).post_spotlight(event_data)
            WhatsAppAgent(dry_run=self.dry_run).send_spotlight(event_data)
            MeetupAgent(dry_run=self.dry_run).post_attendee_message(event_data, message)

            sheets_client.set_flag(int(event_id), "tminus2_sent")
            logger.info(f"T-2d reminder sent for event {event_id}")
        except Exception as e:
            logger.error(f"T-2d reminder failed for {event_id}: {e}")

    def _fire_t1d(self, event_id: str):
        """T-1 day: Logistics blast."""
        logger.info(f"🔔 T-1d reminder firing for event {event_id}")
        try:
            event_data = sheets_client.get_event(int(event_id))

            if event_data.get("tminus1_sent", "").upper() == "Y":
                logger.info("T-1d already sent — skipping")
                return

            from wimlds.agents.publishing.social_agent import SocialAgent
            from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
            from wimlds.agents.publishing.meetup_agent import MeetupAgent
            from wimlds.config.message_templates import render_logistics
            from wimlds.agents.publishing.social_agent import _event_to_context

            ctx = _event_to_context(event_data)
            message = render_logistics(ctx)

            SocialAgent(dry_run=self.dry_run).post_logistics(event_data)
            WhatsAppAgent(dry_run=self.dry_run).send_logistics(event_data)
            MeetupAgent(dry_run=self.dry_run).post_attendee_message(event_data, message)

            sheets_client.set_flag(int(event_id), "tminus1_sent")
            logger.info(f"T-1d reminder sent for event {event_id}")
        except Exception as e:
            logger.error(f"T-1d reminder failed for {event_id}: {e}")

    def _fire_t2h(self, event_id: str):
        """T-2 hours: Final bump (+ conference link if Online/Hybrid)."""
        logger.info(f"🔔 T-2h reminder firing for event {event_id}")
        try:
            event_data = sheets_client.get_event(int(event_id))

            if event_data.get("tminus2h_sent", "").upper() == "Y":
                logger.info("T-2h already sent — skipping")
                return

            from wimlds.agents.publishing.social_agent import SocialAgent
            from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
            from wimlds.agents.publishing.meetup_agent import MeetupAgent
            from wimlds.config.message_templates import render_final_bump
            from wimlds.agents.publishing.social_agent import _event_to_context

            ctx = _event_to_context(event_data)
            message = render_final_bump(ctx)

            SocialAgent(dry_run=self.dry_run).post_final_bump(event_data)
            WhatsAppAgent(dry_run=self.dry_run).send_final_bump(event_data)
            MeetupAgent(dry_run=self.dry_run).post_attendee_message(event_data, message)

            sheets_client.set_flag(int(event_id), "tminus2h_sent")
            logger.info(f"T-2h reminder sent for event {event_id}")
        except Exception as e:
            logger.error(f"T-2h reminder failed for {event_id}: {e}")

    # ── Scheduler controls ────────────────────────────────────────────────────

    def start_scheduler(self):
        sched = self._get_scheduler()
        if not sched.running:
            sched.start()
            logger.info("Reminder scheduler started")

    def stop_scheduler(self):
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()
            logger.info("Reminder scheduler stopped")

    def list_jobs(self) -> list[dict]:
        sched = self._get_scheduler()
        return [
            {"id": job.id, "next_run": str(job.next_run_time)}
            for job in sched.get_jobs()
        ]

    def _schedule_job(self, job_id: str, run_at: datetime, func, args: list):
        sched = self._get_scheduler()
        # Remove existing job with same ID (idempotent)
        try:
            sched.remove_job(job_id)
        except Exception:
            pass
        sched.add_job(
            func, trigger=DateTrigger(run_date=run_at, timezone=IST),
            id=job_id, args=args, replace_existing=True,
            misfire_grace_time=3600,   # 1h tolerance
        )
        logger.debug(f"Job scheduled: {job_id} @ {run_at}")

    @staticmethod
    def _parse_event_datetime(event_data: dict) -> Optional[datetime]:
        try:
            date   = event_data.get("date", "")
            start  = event_data.get("start_time_ist", "")
            dt_str = f"{date} {start}"
            dt     = datetime.strptime(dt_str, "%d %b %Y %H:%M")
            return IST.localize(dt)
        except Exception as e:
            logger.error(f"Could not parse event datetime: {e}")
            return None




