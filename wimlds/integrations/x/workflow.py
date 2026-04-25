"""Internal orchestration helpers ported from the X command center backend."""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

from wimlds.config.settings import settings
from wimlds.integrations.x.ai_rewriter import rewrite_post
from wimlds.integrations.x.buffer_client import create_post
from wimlds.integrations.x.image_processor import pad_and_upload_image
from wimlds.integrations.x.link_generator import extract_post_link
from wimlds.integrations.x.validator import validate_post_text

SYSTEM_EVENT_COLUMNS = {"ai_draft", "processed_image", "link", "posterlink", "status"}
EXPECTED_EXCEL_COLUMNS = [
    "status",
    "event title",
    "time",
    "posterlink",
    "event description",
    "location",
    "speaker",
    "meetup link",
    "ai_draft",
    "processed_image",
    "link",
]


def build_event_payload(row: pd.Series) -> dict:
    payload = {}
    for column, value in row.items():
        if str(column).strip().lower() in SYSTEM_EVENT_COLUMNS:
            continue
        text = str(value).strip()
        if text.lower() in {"", "nan", "none"}:
            continue
        payload[str(column)] = text
    return payload


def excel_cache_path() -> Path:
    return Path(settings.x_excel_cache_path).resolve()


def ensure_excel_cache_dir() -> None:
    excel_path = excel_cache_path()
    excel_path.parent.mkdir(parents=True, exist_ok=True)


def write_excel_cache(df: pd.DataFrame) -> None:
    ensure_excel_cache_dir()
    excel_path = excel_cache_path()
    root, ext = os.path.splitext(str(excel_path))
    tmp_path = f"{root}.tmp{ext or '.xlsx'}"
    df.to_excel(tmp_path, index=False, engine="openpyxl")
    os.replace(tmp_path, excel_path)


def read_excel_cache() -> pd.DataFrame:
    return pd.read_excel(excel_cache_path(), engine="openpyxl")


def perform_excel_sync() -> tuple[bool, str]:
    if not settings.remote_excel_url:
        return False, "REMOTE_EXCEL_URL is not configured."
    try:
        resp = requests.get(settings.remote_excel_url, allow_redirects=True, timeout=30)
        if resp.status_code != 200:
            return False, f"Remote download failed: {resp.status_code}"
        df = pd.read_excel(BytesIO(resp.content), engine="openpyxl")
        for col in EXPECTED_EXCEL_COLUMNS:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(str).replace("nan", "").replace("None", "")

        upcoming_events = df[df["status"].str.lower().str.strip() == "upcoming"].copy()
        if upcoming_events.empty:
            write_excel_cache(upcoming_events)
            return True, ""

        for index, row in upcoming_events.iterrows():
            try:
                event_data = build_event_payload(row)
                draft = rewrite_post(event_data)
                orig_image = str(row.get("posterlink", "")).strip()
                processed_url = ""
                if orig_image and orig_image.lower() not in {"", "nan", "none"}:
                    try:
                        processed_url = pad_and_upload_image(orig_image)
                    except Exception:
                        processed_url = ""
                upcoming_events.at[index, "status"] = "Review Required"
                upcoming_events.at[index, "ai_draft"] = draft
                upcoming_events.at[index, "link"] = ""
                upcoming_events.at[index, "processed_image"] = processed_url
            except Exception:
                continue
        write_excel_cache(upcoming_events)
        return True, ""
    except PermissionError:
        return False, f"Excel cache is locked: {excel_cache_path()}. Close any app using the cache file and try again."
    except Exception as exc:
        return False, f"Excel Sync Error: {exc}"


def get_review_required_events() -> list[dict]:
    if not excel_cache_path().exists():
        return []
    df = read_excel_cache()
    for col in EXPECTED_EXCEL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "").replace("None", "")
    review_required = df[df["status"] == "Review Required"]
    results = []
    for index, row in review_required.iterrows():
        results.append({
            "index": int(index),
            "event title": str(row.get("event title", "")),
            "event description": str(row.get("event description", "")),
            "location": str(row.get("location", "")),
            "time": str(row.get("time", "")),
            "speaker": str(row.get("speaker", "")),
            "meetup link": str(row.get("meetup link", "")),
            "posterlink": str(row.get("processed_image", "")),
            "ai_draft": str(row.get("ai_draft", "")),
        })
    return results


def confirm_excel_post(index: int, text: str, image_url: str | None = None) -> dict:
    validated = validate_post_text(text)
    response = create_post(validated, image_url)
    twitter_link = extract_post_link(response)
    df = read_excel_cache()
    df.at[index, "status"] = "Posted"
    df.at[index, "link"] = str(twitter_link)
    write_excel_cache(df)
    return {"success": True, "link": str(twitter_link), "raw_response": response}
