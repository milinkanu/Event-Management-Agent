"""
Event data validation — checks all required fields before any agent runs.
"""
from dataclasses import dataclass, field
from typing import Optional
from wimlds.core.logger import get_logger

logger = get_logger("validator")

# All required fields per Blueprint v9.0
REQUIRED_FIELDS = [
    # Core Info
    "series", "event_title", "date", "day", "start_time_ist", "end_time_ist", "mode",
    # Venue
    "venue_name", "venue_address",
    # Speakers
    "speaker_name", "speaker_highest_qualification", "speaker_tier1_institution",
    "speaker_special_achievements",
    # Links
    "meetup_event_url",   # filled by Meetup Agent after creation
    # Status
    "event_status",
    # Partner
    "c_level_linkedin_handles",
]

# Fields that may be missing at the start but must exist before specific stages
STAGE_REQUIRED_FIELDS = {
    "qr_generation": ["meetup_event_url", "meetup_event_id"],
    "poster_creation": ["qr_drive_url", "meetup_event_url"],
    "social_announcement": ["poster_drive_url", "meetup_event_url"],
    "conferencing": ["mode"],
    "reminders_t2h": ["conference_link"],   # only if Online/Hybrid
    "post_event": ["recording_link", "transcript_link"],
}


@dataclass
class ValidationResult:
    valid: bool
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_event(event_data: dict, stage: Optional[str] = None) -> ValidationResult:
    """
    Validate event data for required fields.
    If stage is provided, also check stage-specific required fields.
    """
    missing = []
    warnings = []

    # Base required fields
    check_fields = list(REQUIRED_FIELDS)

    # Stage-specific additions
    if stage and stage in STAGE_REQUIRED_FIELDS:
        # For online/hybrid events, conference_link is required at T-2h
        if stage == "reminders_t2h":
            mode = event_data.get("mode", "")
            if mode in ("Online", "Hybrid"):
                check_fields.extend(STAGE_REQUIRED_FIELDS[stage])
        else:
            check_fields.extend(STAGE_REQUIRED_FIELDS[stage])

    for f in check_fields:
        val = event_data.get(f)
        if val is None or str(val).strip() == "" or str(val).strip() == "REPLACE_ME":
            missing.append(f)

    # Soft warnings
    optional_nice = ["subtitle", "google_maps_url", "parking_info", "wifi_note", "laptop_required"]
    for f in optional_nice:
        if not event_data.get(f):
            warnings.append(f"Optional field empty: {f}")

    if missing:
        logger.warning(f"Validation failed — missing: {missing}")
    else:
        logger.info("Validation passed ✓")

    return ValidationResult(valid=len(missing) == 0, missing_fields=missing, warnings=warnings)




