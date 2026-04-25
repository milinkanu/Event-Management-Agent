"""
Meta Graph API helpers for Facebook and Instagram publishing.
"""
from __future__ import annotations

import requests
from requests import Response

from wimlds.config.settings import settings

ACCESS_TOKEN = settings.meta_access_token
GRAPH_VERSION = settings.meta_graph_version
INSTAGRAM_ID = settings.instagram_business_account_id
PAGE_ID = settings.facebook_page_id
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _ensure_config() -> None:
    missing = []
    if not PAGE_ID:
        missing.append("FACEBOOK_PAGE_ID")
    if not INSTAGRAM_ID:
        missing.append("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not ACCESS_TOKEN:
        missing.append("META_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def _raise_for_error(response: Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Meta API request failed with {response.status_code}: {response.text}"
        ) from exc


def validate_page_token() -> dict:
    _ensure_config()

    url = f"{BASE_URL}/{PAGE_ID}"
    params = {"access_token": ACCESS_TOKEN}

    response = requests.get(url, params=params, timeout=30)
    _raise_for_error(response)
    return response.json()


def post_to_facebook(image_url: str, caption: str) -> dict:
    _ensure_config()

    url = f"{BASE_URL}/{PAGE_ID}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }

    response = requests.post(url, data=payload, timeout=60)
    _raise_for_error(response)
    return response.json()


def build_facebook_post_url(post_result: dict) -> str:
    post_id = post_result.get("post_id") or post_result.get("id")
    if not post_id:
        raise RuntimeError(f"Facebook post result missing post identifier: {post_result}")
    return f"https://www.facebook.com/{post_id}"


def create_instagram_container(image_url: str, caption: str) -> str:
    _ensure_config()

    url = f"{BASE_URL}/{INSTAGRAM_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }

    response = requests.post(url, data=payload, timeout=60)
    _raise_for_error(response)
    data = response.json()
    if "id" not in data:
        raise RuntimeError(f"Instagram container creation failed: {data}")
    return data["id"]


def publish_instagram(container_id: str) -> dict:
    _ensure_config()

    url = f"{BASE_URL}/{INSTAGRAM_ID}/media_publish"
    payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }

    response = requests.post(url, data=payload, timeout=60)
    _raise_for_error(response)
    return response.json()


def get_instagram_permalink(media_id: str) -> str:
    _ensure_config()

    url = f"{BASE_URL}/{media_id}"
    params = {
        "fields": "permalink",
        "access_token": ACCESS_TOKEN,
    }

    response = requests.get(url, params=params, timeout=30)
    _raise_for_error(response)
    data = response.json()
    permalink = data.get("permalink")
    if not permalink:
        raise RuntimeError(f"Instagram permalink lookup failed: {data}")
    return permalink




