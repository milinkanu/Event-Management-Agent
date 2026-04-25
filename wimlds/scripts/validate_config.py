#!/usr/bin/env python3
"""Pre-flight configuration validator."""

import sys
from pathlib import Path

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("validate_config")

CHECKS = []


def check(label):
    def decorator(fn):
        CHECKS.append((label, fn))
        return fn

    return decorator


@check("Google Service Account JSON exists")
def check_sa():
    path = Path(settings.google_service_account_json)
    if not path.exists():
        return f"Not found: {path}"


@check("Google Sheets ID configured")
def check_sheets():
    if not settings.google_sheets_id or "REPLACE" in settings.google_sheets_id:
        return "GOOGLE_SHEETS_ID not set"


@check("Google Drive Root Folder ID configured")
def check_drive():
    if not settings.google_drive_root_folder_id or "REPLACE" in settings.google_drive_root_folder_id:
        return "GOOGLE_DRIVE_ROOT_FOLDER_ID not set"


@check("Meetup credentials present")
def check_meetup():
    if not settings.meetup_client_id or "REPLACE" in settings.meetup_client_id:
        return "Meetup OAuth credentials not set"


@check("LLM API key present")
def check_llm():
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key or "REPLACE" in settings.anthropic_api_key:
            return "ANTHROPIC_API_KEY not set"
    elif not settings.openai_api_key or "REPLACE" in settings.openai_api_key:
        return "OPENAI_API_KEY not set"


@check("SendGrid API key present")
def check_sendgrid():
    if not settings.sendgrid_api_key or "REPLACE" in settings.sendgrid_api_key:
        return "SENDGRID_API_KEY not set"


@check("Redis connection")
def check_redis():
    try:
        import redis

        redis.from_url(settings.redis_url).ping()
    except Exception as exc:
        return f"Redis not reachable: {exc}"


@check("Partner email list file")
def check_partner_list():
    path = Path(settings.partner_email_list)
    if not path.exists():
        return f"Partner list not found: {path}. Create CSV with columns: name,email,org"



def validate_all() -> list[str]:
    errors = []
    print("\nWiMLDS Automation - Configuration Validation\n" + "-" * 50)
    for label, fn in CHECKS:
        result = fn()
        if result:
            print(f"  x {label}")
            print(f"    -> {result}")
            errors.append(f"{label}: {result}")
        else:
            print(f"  OK {label}")

    print("\n" + "-" * 50)
    if errors:
        print(f"\nFAILED: {len(errors)} check(s) failed. Fix the above before running.\n")
    else:
        print("\nAll checks passed. Ready to run.\n")
    return errors


if __name__ == "__main__":
    validation_errors = validate_all()
    sys.exit(1 if validation_errors else 0)


