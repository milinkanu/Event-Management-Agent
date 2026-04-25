#!/usr/bin/env python3
"""Test script for the native in-repo X agent integration.

Safe by default:
  - dry-run mode
  - no real Buffer posts
  - no real scraping
  - no remote Excel calls

Examples:
  python -m wimlds.scripts.test_x_agent_integration
  python -m wimlds.scripts.test_x_agent_integration --mode rewrite
  python -m wimlds.scripts.test_x_agent_integration --mode publish --live
  python -m wimlds.scripts.test_x_agent_integration --mode scrape
  python -m wimlds.scripts.test_x_agent_integration --mode excel
"""
from __future__ import annotations

import argparse
import json

from wimlds.agents.publishing.social_agent import SocialAgent
from wimlds.agents.publishing.x_agent import XAgent
from wimlds.tests.fixtures.sample_event import SAMPLE_EVENT


def _print_json(label: str, payload: dict) -> None:
    print(f"\n{label}:")
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def test_rewrite(agent: XAgent) -> None:
    payload = {
        "event title": "WiMLDS Pune GenAI Meetup",
        "speaker": "Jane Doe",
        "location": "Pune",
        "event description": "A practical session on GenAI workflows for teams.",
        "time": "Saturday 5 PM",
        "meetup link": "https://meetup.com/example",
    }
    rewritten = agent.rewrite_text(payload)
    _print_json("rewrite_result", {"rewritten": rewritten, "length": len(rewritten)})


def test_publish(agent: XAgent) -> None:
    result = agent.publish(
        text="Testing the internal WiMLDS X agent publish flow.\n\n#WiMLDS #Pune #AI",
        image_url=None,
        rewrite=False,
    )
    _print_json("publish_result", result)


def test_scrape(agent: XAgent) -> None:
    result = agent.scrape("#WiMLDS", headless=True)
    _print_json("scrape_result_summary", {
        "post_count": len(result.get("posts", [])),
        "analytics_keys": sorted((result.get("analytics") or {}).keys()),
        "ai_insights": result.get("ai_insights", ""),
    })


def test_excel(agent: XAgent) -> None:
    sync_result = agent.sync_excel_queue()
    _print_json("excel_sync_result", sync_result)
    if sync_result.get("events"):
        first = sync_result["events"][0]
        confirm_result = agent.confirm_excel_publish(
            index=first["index"],
            text=first["ai_draft"],
            image_url=first.get("posterlink"),
        )
        _print_json("excel_confirm_result", confirm_result)


def test_social(agent_dry_run: bool) -> None:
    event_data = dict(SAMPLE_EVENT)
    event_data["promote_linkedin"] = "N"
    event_data["promote_facebook"] = "N"
    event_data["promote_instagram"] = "N"
    event_data["promote_meetup"] = "N"
    event_data["promote_whatsapp"] = "N"
    event_data["promote_x"] = "Y"
    event_data["poster_drive_url"] = "https://example.com/poster.png"

    result = SocialAgent(dry_run=agent_dry_run).post_announcement(event_data)
    _print_json("social_agent_result", {
        "success": result.success,
        "data": result.data,
        "error": result.error,
    })
    _print_json("event_data_x_fields", {
        "_twitter_tweet_id": event_data.get("_twitter_tweet_id", ""),
        "_twitter_post_url": event_data.get("_twitter_post_url", ""),
        "_twitter_provider": event_data.get("_twitter_provider", ""),
        "_twitter_final_text": event_data.get("_twitter_final_text", ""),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Test native X integration")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "rewrite", "publish", "scrape", "excel", "social"],
        help="Which integration slice to test",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run without dry-run where supported",
    )
    args = parser.parse_args()

    dry_run = not args.live
    agent = XAgent(dry_run=dry_run)

    if args.mode in {"all", "rewrite"}:
        test_rewrite(agent)
    if args.mode in {"all", "publish"}:
        test_publish(agent)
    if args.mode in {"all", "scrape"}:
        test_scrape(agent)
    if args.mode in {"all", "excel"}:
        test_excel(agent)
    if args.mode in {"all", "social"}:
        test_social(dry_run)


if __name__ == "__main__":
    main()
