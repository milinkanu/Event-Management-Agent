"""
Event Execution Agent — Day-of checklist verification and material archival.
"""
from pathlib import Path
from wimlds.core.logger import get_logger
from wimlds.core.orchestrator import AgentResult
from wimlds.core.drive_client import drive_client
from wimlds.config.settings import settings

logger = get_logger("event_exec_agent")

# Appendix C checklist items
CHECKLIST = [
    "Meeting created with correct date/time",
    "Waiting room ON",
    "Passcode ON",
    "Cloud recording ON — Auto-start ON",
    "Live transcription/captions ON",
    "Save chat ON",
    "Host + Co-host assigned",
    "Conference link in Master Sheet",
]


class EventExecAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def run_checklist(self, event_data: dict, row_num: int) -> AgentResult:
        """
        Print the Appendix C checklist and verify required flags before the event.
        This is partially manual — the agent verifies what it can automatically.
        """
        logger.info("▶ Event Execution Checklist")
        mode = event_data.get("mode", "In-Person")

        issues = []

        # Auto-checks
        if mode in ("Online", "Hybrid"):
            if not event_data.get("conference_link", "").strip():
                issues.append("Conference link missing in sheet!")
            else:
                logger.info("  ✓ Conference link present")

        logger.info(f"\n  Mode: {mode}")
        logger.info(f"  Event: {event_data.get('event_title', '')}")
        logger.info(f"  Date: {event_data.get('date', '')} @ {event_data.get('start_time_ist', '')}")

        # Print checklist for human verification
        print("\n" + "="*60)
        print("  EVENT DAY CHECKLIST (Appendix C)")
        print("="*60)
        for item in CHECKLIST:
            if mode == "In-Person" and "record" in item.lower():
                continue   # Skip recording checks for in-person
            print(f"  [ ] {item}")
        print("="*60)

        if issues:
            for issue in issues:
                logger.error(f"  ✗ {issue}")
            return AgentResult(success=False, error="; ".join(issues))

        return AgentResult(success=True, data={"checklist_items": len(CHECKLIST)})

    def archive_speaker_materials(self, event_data: dict, file_paths: list[str]) -> AgentResult:
        """Archive PPT/code/links to /04_PostEvent/04_Presentations/"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would archive {len(file_paths)} speaker files")
            return AgentResult(success=True)

        folder_map = event_data.get("_drive_folder_map", {})
        folder_id = folder_map.get("04_postevent/04_presentations") or settings.google_drive_root_folder_id

        uploaded = []
        for path in file_paths:
            p = Path(path)
            if not p.exists():
                logger.warning(f"File not found: {path}")
                continue
            try:
                url = drive_client.upload_file(
                    local_path=str(p),
                    folder_id=folder_id,
                    filename=p.name,
                )
                uploaded.append(url)
                logger.info(f"Archived: {p.name} → {url}")
            except Exception as e:
                logger.error(f"Archive failed for {p.name}: {e}")

        return AgentResult(success=True, data={"archived_files": uploaded})

    def create_speaker_form(self, event_data: dict) -> str:
        """
        Returns the URL of a Google Form for speakers to upload materials pre-event.
        In production: create via Google Forms API or use a pre-made template.
        """
        # Placeholder — in production, use Google Forms API to create form
        form_url = (
            "https://docs.google.com/forms/d/e/PLACEHOLDER/viewform"
            f"?usp=pp_url&entry.event={event_data.get('meetup_event_id', '')}"
        )
        logger.info(f"Speaker form URL: {form_url}")
        return form_url




