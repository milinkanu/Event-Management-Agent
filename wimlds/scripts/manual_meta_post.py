#!/usr/bin/env python3
"""Simple test entry point for the Meta social posting graph."""
from __future__ import annotations

from pprint import pprint

from wimlds.graph import build_graph
from wimlds.integrations.meta.meta_api import validate_page_token


def main() -> None:
    token_check = validate_page_token()
    print("Page token validation:")
    pprint(token_check)

    agent = build_graph()
    input_data = {
        "event": "Test Post by AI Agent",
        "description": (
            "This is a test post created by an AI agent using the Meta Graph API. "
            "The agent is designed to create engaging content and post it on "
            "Facebook and Instagram."
        ),
        "poster": "https://testomat.io/wp-content/uploads/2025/07/AI-Agent-Testing-Level-Up-Your-QA-Process.png",
    }

    result = agent.invoke(input_data)
    pprint(result)

    facebook_url = result.get("facebook_post_url")
    instagram_url = result.get("instagram_post_url")
    if facebook_url or instagram_url:
        print("\nPost successfully published")
        if facebook_url:
            print(f"Facebook: {facebook_url}")
        if instagram_url:
            print(f"Instagram: {instagram_url}")


if __name__ == "__main__":
    main()


