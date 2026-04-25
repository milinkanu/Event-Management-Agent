#!/usr/bin/env python3
"""Test publishing one selected master-sheet row to X.

Examples:
  python -m wimlds.scripts.test_x_master_sheet_publish --event-id 4
  python -m wimlds.scripts.test_x_master_sheet_publish --event-id 4 --live
  python -m wimlds.scripts.test_x_master_sheet_publish --first-upcoming --live
  python -m wimlds.scripts.test_x_master_sheet_publish --event-id 4 --live --no-rewrite
  python -m wimlds.scripts.test_x_master_sheet_publish --event-id 4 --live --force
"""
from __future__ import annotations

import argparse
import json

from wimlds.agents.publishing.x_agent import XAgent
from wimlds.core.sheets_client import sheets_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish one master-sheet event row to X")
    parser.add_argument("--event-id", type=int, help="Master sheet Excel row number")
    parser.add_argument(
        "--first-upcoming",
        action="store_true",
        help="Automatically find and publish the first row whose event_status is Upcoming",
    )
    parser.add_argument("--live", action="store_true", help="Run live publish instead of dry-run")
    parser.add_argument("--no-rewrite", action="store_true", help="Skip AI rewrite and build a basic post")
    parser.add_argument("--force", action="store_true", help="Publish even if promote_x is not Y")
    args = parser.parse_args()

    if args.first_upcoming and args.event_id is not None:
        parser.error("Use either --event-id or --first-upcoming, not both.")
    if not args.first_upcoming and args.event_id is None:
        parser.error("Provide --event-id or use --first-upcoming.")

    dry_run = not args.live
    agent = XAgent(dry_run=dry_run)

    if args.first_upcoming:
        upcoming_events = sheets_client.get_all_upcoming()
        if not upcoming_events:
            print("\nNo rows with event_status = Upcoming were found.")
            return
        event_data = upcoming_events[0]
        target_row = int(event_data["_row_number"])
    else:
        target_row = int(args.event_id)
        event_data = sheets_client.get_event(target_row)

    preview = {
        "_row_number": event_data.get("_row_number"),
        "row_id": event_data.get("_row_id", ""),
        "event_status": event_data.get("event_status", ""),
        "event_title": event_data.get("event_title", ""),
        "speaker_name": event_data.get("speaker_name", ""),
        "venue_name": event_data.get("venue_name", ""),
        "date": event_data.get("date", ""),
        "start_time_ist": event_data.get("start_time_ist", ""),
        "meetup_event_url": event_data.get("meetup_event_url", ""),
        "promote_x": event_data.get("promote_x", ""),
        "resolved_image_url": agent._resolve_master_sheet_image_url(event_data),
    }

    print("\nSelected master-sheet row:")
    print(json.dumps(preview, indent=2, ensure_ascii=True))

    result = agent.publish_event_from_master_sheet(
        row_number=target_row,
        rewrite=not args.no_rewrite,
        force=args.force,
    )

    print("\nPublish result:")
    print(json.dumps(result, indent=2, ensure_ascii=True))

    if not result.get("writeback_success", True):
        print("\nSheet write-back fields:")
        print(json.dumps({
            "writeback_success": False,
            "writeback_error": result.get("writeback_error", ""),
            "note": "Excel was not updated. If the workbook is open in Excel, close it and rerun.",
        }, indent=2, ensure_ascii=True))
        return

    refreshed = sheets_client.get_event(target_row)
    print("\nSheet write-back fields:")
    print(json.dumps({
        "_twitter_tweet_id": refreshed.get("_twitter_tweet_id", ""),
        "_twitter_post_url": refreshed.get("_twitter_post_url", ""),
        "x_post_status": refreshed.get("x_post_status", ""),
        "x_post_text": refreshed.get("x_post_text", ""),
        "x_posted_at": refreshed.get("x_posted_at", ""),
        "x_error": refreshed.get("x_error", ""),
        "link": refreshed.get("link", ""),
    }, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
