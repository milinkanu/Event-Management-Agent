"""
Settings for the Post-Event Agent.
Drop-in compatible with the main WiMLDS settings; only the fields
relevant to this agent are declared here so it can run standalone.
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


SETTINGS_FILE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SETTINGS_FILE_DIR.parent.parent


class Settings(BaseSettings):
    # ── Google ─────────────────────────────────────────────────────────────
    google_service_account_json: str = Field("config/service-account.json")
    google_sheets_id: str = Field("")
    google_drive_root_folder_id: str = Field("")
    google_calendar_id: str = Field("primary")

    # ── Zoom Server-to-Server OAuth ─────────────────────────────────────────
    # Get from: marketplace.zoom.us → Build App → Server-to-Server OAuth
    # This is the current free-developer approach (JWT is deprecated)
    zoom_account_id: str = Field("")
    zoom_client_id: str = Field("")
    zoom_client_secret: str = Field("")

    # ── Social — full credentials ────────────────────────────────
    linkedin_access_token:       str = Field('')
    facebook_page_token:         str = Field('')
    facebook_page_id:            str = Field('')   # numeric Page ID
    twitter_api_key:             str = Field('')
    twitter_api_secret:          str = Field('')
    twitter_access_token:        str = Field('')
    twitter_access_token_secret: str = Field('')
    instagram_access_token:      str = Field('')
    instagram_user_id:           str = Field('')   # numeric IG Business ID
    buffer_api_key:              str = Field('')
    buffer_channel_id:           str = Field('')
    buffer_graphql_url:          str = Field('')
    nvidia_api_key:              str = Field('')
    remote_excel_url:            str = Field('')
    x_excel_cache_path:          str = Field('runtime/posts_cache.xlsx')
    x_selenium_profile_dir:      str = Field(r'D:\selenium_profile')
    x_scrape_max_posts:          int = Field(20)
    use_external_x_agent:        bool = Field(False)
    external_x_agent_base_url:   str = Field("")
    external_x_agent_timeout_seconds: int = Field(30)
    external_x_agent_enable_rewrite: bool = Field(True)

    # ── WhatsApp — Twilio ─────────────────────────────────────────
    twilio_account_sid:      str = Field('')

    twilio_auth_token:       str = Field('')
    twilio_whatsapp_number:  str = Field('')   # e.g. +14155238886
    wa_media_base_url:       str = Field('')   # optional public image URL base


    # ── Microsoft Teams ─────────────────────────────────────────────────────
    teams_tenant_id:     str = Field("")
    teams_client_id:     str = Field("")
    teams_client_secret: str = Field("")
    teams_user_id:       str = Field("")

    # ── LLM ────────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field("")
    openai_api_key: str = Field("")
    llm_provider: str = Field("anthropic")        # "anthropic" | "openai"
    llm_model: str = Field("claude-haiku-4-5-20251001")  # free-tier friendly default

    # ── Email (optional — organiser notifications) ──────────────────────────
    sendgrid_api_key: str = Field("")
    notification_email: str = Field("organizer@wimlds.org")

    # ── Meetup OAuth ───────────────────────────────────────────────────────────
    meetup_client_id:      str = Field("")
    meetup_client_secret:  str = Field("")
    meetup_refresh_token:  str = Field("")
    meetup_group_urlname:  str = Field("WiMLDS-Pune")
    meetup_use_headless:   bool = Field(False)

    # ── Asset paths ────────────────────────────────────────────────────────────
    wimlds_logo_path:      str = Field("config/assets/wimlds_logo.png")
    partner_logos_dir:     str = Field("config/assets/partner_logos")

    # ── App ────────────────────────────────────────────────────────────────
    log_level: str = Field("INFO")
    dry_run: bool = Field(False)
    timezone: str = Field("Asia/Kolkata")

    class Config:
        env_file = (
            str(SETTINGS_FILE_DIR / ".env"),
            str(ROOT_DIR / "config" / ".env"),
        )
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()

