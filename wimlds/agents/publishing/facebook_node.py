"""
Facebook node for posting a generated poster and caption via the Meta API helper.
"""
from __future__ import annotations

from wimlds.integrations.meta.meta_api import build_facebook_post_url, post_to_facebook


def post_facebook(state: dict) -> dict:
    image = state["poster"]
    caption = state["caption"]

    result = post_to_facebook(image, caption)
    post_url = build_facebook_post_url(result)

    return {
        "facebook_posted": True,
        "facebook_result": result,
        "facebook_post_url": post_url,
    }




