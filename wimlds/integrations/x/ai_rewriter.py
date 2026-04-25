"""X-focused AI rewrite and analysis helpers."""
from __future__ import annotations

from wimlds.config.settings import settings

CORE_FIELD_LABELS = {
    "event title": "Event Name",
    "speaker": "Speaker",
    "location": "Venue",
    "event description": "Description",
    "time": "Time",
    "meetup link": "Link",
}


def _normalize_event_data(event_data) -> dict:
    if isinstance(event_data, dict):
        normalized = {}
        for key, value in event_data.items():
            text = str(value).strip()
            if text.lower() in {"", "nan", "none"}:
                continue
            normalized[str(key)] = text
        return normalized
    text = str(event_data).strip()
    return {"draft text": text} if text else {}


def _build_event_details(event_data: dict) -> str:
    lines = []
    seen = set()
    for key, label in CORE_FIELD_LABELS.items():
        value = event_data.get(key)
        if value:
            lines.append(f"{label}: {value}")
            seen.add(key)
    for key, value in event_data.items():
        if key in seen:
            continue
        label = str(key).replace("_", " ").strip().title()
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def rewrite_post(event_data) -> str:
    normalized_data = _normalize_event_data(event_data)
    if not normalized_data:
        raise ValueError("No event details provided for rewriting.")

    api_key = settings.nvidia_api_key
    if not api_key:
        title = normalized_data.get("event title") or normalized_data.get("draft text") or "Untitled event"
        location = normalized_data.get("location")
        return f"Event: {title}" + (f" @ {location}" if location else "")

    try:
        from openai import APIStatusError, OpenAI

        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
        prompt_text = (
            "You are an expert social media manager. Rewrite the provided event details into a high-impact X post.\n\n"
            "STRICT REQUIREMENTS:\n"
            "1. MUST be under 280 characters.\n"
            "2. Use the most important event details provided below and add extra columns only when useful.\n"
            "3. Format it cleanly with emojis or bullets.\n"
            "4. Make it exciting and professional.\n"
            "5. Output ONLY the post content."
        )
        event_details = _build_event_details(normalized_data)
        rewritten = ""
        for _ in range(3):
            response = client.chat.completions.create(
                model="meta/llama-3.1-405b-instruct",
                messages=[
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": f"Event Details:\n{event_details}"},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            rewritten = response.choices[0].message.content.strip()
            if rewritten.startswith('"') and rewritten.endswith('"'):
                rewritten = rewritten[1:-1]
            if len(rewritten) <= 280:
                return rewritten
        return rewritten[:277] + "..."
    except Exception:
        title = normalized_data.get("event title") or normalized_data.get("draft text") or "our next event"
        return f"Join us for {title}!"


def generate_qa_insights(posts: list[dict]) -> str:
    api_key = settings.nvidia_api_key
    if not api_key:
        return "Warning: NVIDIA_API_KEY is not configured. Cannot perform AI analysis."
    if not posts:
        return "No posts to analyze."

    combined_tweets = "\n".join(f"- {p['text']}" for p in posts)
    try:
        from openai import OpenAI

        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
        prompt_text = (
            "You are an expert social media data analyst. Analyze the provided X posts and return:\n\n"
            "🧠 KEY TAKEAWAYS\n"
            "- 2-3 sentence summary of sentiment, topic clusters, and overall vibe.\n\n"
            "❓ AUDIENCE Q&A & PROBLEM SOLVING\n"
            "- Identify 2 to 4 user questions or pain points.\n"
            "- For each, give a concise answer or solution.\n\n"
            "Be concise and format cleanly."
        )
        response = client.chat.completions.create(
            model="meta/llama-3.1-405b-instruct",
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": f"Here are the tweets:\n{combined_tweets}"},
            ],
            temperature=0.3,
            top_p=1,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"Error during AI data analysis: {exc}"
