"""Helpers for deriving a useful X link from Buffer responses."""


def extract_post_link(response: dict) -> str:
    try:
        if not response or "errors" in response:
            return "https://x.com"
        data = response.get("data") or {}
        create_post_data = data.get("createPost", {}) or {}
        post_data = create_post_data.get("post") or {}
        post_id = post_data.get("id", "")
        post_link = post_data.get("externalLink")
        if not post_link or str(post_link) == "None":
            return f"https://publish.buffer.com/profile/{post_id}" if post_id else "https://x.com"
        return str(post_link)
    except Exception:
        return "https://x.com"
