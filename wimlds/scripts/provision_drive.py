#!/usr/bin/env python3
"""Provision Google Drive folder structure for a new event."""

from datetime import datetime
import re

import click

from wimlds.core.drive_client import drive_client
from wimlds.core.logger import get_logger
from wimlds.core.sheets_client import sheets_client

logger = get_logger("provision_drive")


def provision_event_folders(event_id: str) -> str:
    row_num = int(event_id)
    event_data = sheets_client.get_event(row_num)

    date = event_data.get("date", "01 Jan 2025")
    series = event_data.get("series", "")
    title = event_data.get("event_title", "Meetup")

    try:
        dt = datetime.strptime(date, "%d %b %Y")
        date_slug = dt.strftime("%Y-%m-%d")
    except Exception:
        date_slug = date.replace(" ", "-")

    short_title = re.sub(r"[^a-zA-Z0-9\s]", "", title)[:30].strip().replace(" ", "_")
    event_slug = f"{date_slug}_{series}_{short_title}"

    root_url, folder_map = drive_client.provision_event_folders(event_slug)
    event_data["_drive_folder_map"] = folder_map

    logger.info(f"Drive folders provisioned: {root_url}")
    print(f"\nEvent folder created: {root_url}")
    return root_url


@click.command()
@click.option("--event-id", required=True)
def main(event_id):
    provision_event_folders(event_id)


if __name__ == "__main__":
    main()


