"""
Instagram node for publishing a poster and caption through the Meta API helper.
"""
from __future__ import annotations

from wimlds.integrations.meta.meta_api import create_instagram_container, get_instagram_permalink, publish_instagram


def post_instagram(state: dict) -> dict:
    image = state["poster"]
    caption = state["caption"]

    container_id = create_instagram_container(image, caption)
    result = publish_instagram(container_id)
    post_url = get_instagram_permalink(result["id"])

    return {
        "instagram_posted": True,
        "instagram_result": result,
        "instagram_post_url": post_url,
    }




