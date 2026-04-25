"""Validation helpers for X post text."""


def validate_post_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Post text cannot be empty.")
    if len(text) > 280:
        raise ValueError("Post exceeds X character limit (280).")
    return text
