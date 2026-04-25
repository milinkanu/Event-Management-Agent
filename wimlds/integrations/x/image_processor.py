"""Image padding and upload helpers for X-compatible media."""
from __future__ import annotations

import io
import re

import requests
from PIL import Image


def parse_gdrive_url(url: str) -> str:
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)/?", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    match_id = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if "drive.google.com" in url and match_id:
        file_id = match_id.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url


def pad_and_upload_image(image_url: str) -> str:
    if "drive.google.com/drive/folders" in image_url or "drive.google.com/drive/u" in image_url:
        raise ValueError("Provided URL is a Google Drive folder, not a direct image file link.")

    direct_url = parse_gdrive_url(image_url)
    resp = requests.get(direct_url, timeout=15)
    resp.raise_for_status()

    image = Image.open(io.BytesIO(resp.content)).convert("RGB")
    target_width, target_height = 1200, 675
    original_width, original_height = image.size
    ratio = min(target_width / original_width, target_height / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)
    resized_img = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (target_width, target_height), (0, 0, 0))
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    canvas.paste(resized_img, (x_offset, y_offset))

    byte_arr = io.BytesIO()
    canvas.save(byte_arr, format="JPEG", quality=90)
    byte_arr.seek(0)

    upload_resp = requests.post(
        "https://uguu.se/upload.php",
        files={"files[]": ("padded.jpg", byte_arr, "image/jpeg")},
        timeout=30,
    )
    if upload_resp.status_code != 200:
        raise ValueError(
            f"Failed to upload image. Status code: {upload_resp.status_code}, Response: {upload_resp.text}"
        )
    resp_json = upload_resp.json()
    if not resp_json.get("success"):
        raise ValueError(f"Image host returned failure: {resp_json}")
    return resp_json["files"][0]["url"]
