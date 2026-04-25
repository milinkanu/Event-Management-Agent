"""
core/drive_client.py
====================
Re-exports DriveClient from wimlds.integrations.storage.drive_client so that both:
  from wimlds.core.drive_client import drive_client       (used by poster_agent, qr_agent, social_agent)
  from wimlds.integrations.storage.drive_client import drive_client  (used by post_event_agent)
resolve to the same singleton.
"""
from wimlds.integrations.storage.drive_client import drive_client, DriveClient

__all__ = ["drive_client", "DriveClient"]


