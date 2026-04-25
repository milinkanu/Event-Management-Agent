"""
Caption Agent - generates short social captions using Ollama with a safe fallback.
"""
from __future__ import annotations

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("caption_agent")


def generate_caption(state: dict) -> dict:
    event = state["event"]
    description = state["description"]

    prompt = (
        "Write a concise social media caption for Facebook and Instagram.\n"
        f"Event: {event}\n"
        f"Description: {description}\n"
        "Requirements:\n"
        "- Keep it clear and promotional\n"
        "- Include a call to action\n"
        "- End with 3 relevant hashtags\n"
        "- Return only the final caption text"
    )

    try:
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.4,
        )
        response = llm.invoke(prompt)
        caption = response.content.strip()
    except Exception as exc:
        logger.warning(f"Falling back to static caption: {exc}")
        caption = f"""{event}

{description}

Join us and spread the word.

#events #community #joinus"""

    return {"caption": caption}


class CaptionAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def generate(self, event: str, description: str) -> dict:
        return generate_caption({"event": event, "description": description})




