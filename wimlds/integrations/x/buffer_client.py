"""Buffer GraphQL integration for X publishing."""
from __future__ import annotations

import json

import requests

from wimlds.config.settings import settings


def create_post(text: str, image_url: str | None = None) -> dict:
    assets_section = ""
    if image_url:
        assets_section = f""",
        assets: {{
            images: [
                {{
                    url: "{image_url}"
                }}
            ]
        }}
        """

    escaped_text = json.dumps(text)
    query = f"""
    mutation CreatePost {{
      createPost(input: {{
        text: {escaped_text},
        channelId: "{settings.buffer_channel_id}",
        schedulingType: automatic,
        mode: shareNow
        {assets_section}
      }}) {{
        ... on PostActionSuccess {{
          post {{
            id
            text
            externalLink
          }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    """
    headers = {
        "Authorization": f"Bearer {settings.buffer_api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        settings.buffer_graphql_url,
        json={"query": query},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
