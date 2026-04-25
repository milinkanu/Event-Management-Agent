"""
QR Agent — Blueprint v9.0
==========================
Generates a brand-safe WiMLDS QR code from the Meetup event URL,
uploads it to the correct Google Drive folder, and writes the URL
back to the Master Sheet.

Pipeline position: CREATE_EVENT → GENERATE_QR → CREATE_POSTER
The QR PNG is embedded top-left on the poster by PosterAgent.

Output:
  /02_Output/02_QR/QR_<EventID>.png   (in the event's Drive folder)
  event_data['qr_drive_url']          written back to Master Sheet col AO

Naming convention (Blueprint Appendix D):  QR_<EventID>.png

File placement: agents/qr_agent.py  (REPLACE existing file)

No new .env variables needed — uses existing Google Drive credentials.

pip packages already in requirements.txt:
  qrcode[pil]==7.4.2
  Pillow==10.3.0
"""

import io
import tempfile
from pathlib import Path
from typing import Optional

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.drive_client import drive_client
from wimlds.core.orchestrator import AgentResult

logger = get_logger("qr_agent")

# WiMLDS brand colours
BRAND_PURPLE = "#4C1D95"
BRAND_PINK   = "#EC4899"
WHITE        = "white"

# QR code settings
QR_BOX_SIZE     = 12   # pixels per module
QR_BORDER       = 3    # quiet zone in modules
QR_ERROR_LEVEL  = "H"  # High error correction — 30% damage recoverable


class QRAgent:
    """
    Generates a styled WiMLDS QR code PNG and uploads it to Google Drive.
    Pass dry_run=True to test without any Drive uploads.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    # ── Main entry point ──────────────────────────────────────────────────────

    def generate_qr(self, event_data: dict) -> AgentResult:
        """
        Full pipeline:
          1. Validate inputs
          2. Generate styled QR PNG in memory
          3. Add WiMLDS branding frame (label + border)
          4. Save to temp file
          5. Upload to Drive → /02_Output/02_QR/
          6. Return { qr_drive_url, _qr_local_path }

        _qr_local_path is also stored in event_data for PosterAgent to use.
        """
        meetup_url = (event_data.get("meetup_event_url") or "").strip()
        event_id   = (event_data.get("meetup_event_id")  or "unknown").strip()

        if not meetup_url:
            return AgentResult(
                success=False,
                error="meetup_event_url is empty — run CREATE_EVENT stage first"
            )

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would generate QR for: {meetup_url}")
            return AgentResult(success=True, data={
                "qr_drive_url":   "https://drive.google.com/file/d/DRY_RUN/view",
                "_qr_local_path": "",
            })

        try:
            # Step 1: Make the QR image
            qr_img = self._make_qr(meetup_url)

            # Step 2: Add branding frame
            branded = self._add_branding(qr_img)

            # Step 3: Save to temp file (keep alive for PosterAgent)
            filename = _qr_filename(event_id)
            tmp_path = _save_to_temp(branded, filename)

            # Step 4: Upload to Drive
            folder_id = _get_qr_folder_id(event_data)
            drive_url = drive_client.upload_file(
                local_path=tmp_path,
                folder_id=folder_id,
                filename=filename,
                mime_type="image/png",
            )

            logger.info(f"QR generated and uploaded: {drive_url}")
            return AgentResult(success=True, data={
                "qr_drive_url":   drive_url,
                "_qr_local_path": tmp_path,
            })

        except Exception as exc:
            logger.error(f"QR generation failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    # ── QR image generation ───────────────────────────────────────────────────

    def _make_qr(self, url: str):
        """
        Generate a styled QR code with rounded modules in WiMLDS brand purple.
        Falls back to plain square modules if the styled library is unavailable.
        """
        try:
            import qrcode
            from qrcode.image.styledpil import StyledPilImage
            from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
        except ImportError:
            raise ImportError(
                "qrcode[pil] not installed. Run:  pip install 'qrcode[pil]'"
            )

        qr = qrcode.QRCode(
            version=None,                              # auto-size
            error_correction=_error_level(QR_ERROR_LEVEL),
            box_size=QR_BOX_SIZE,
            border=QR_BORDER,
        )
        qr.add_data(url)
        qr.make(fit=True)

        try:
            # Styled: rounded modules in brand purple
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
                fill_color=BRAND_PURPLE,
                back_color=WHITE,
            )
        except Exception:
            # Plain fallback
            img = qr.make_image(fill_color=BRAND_PURPLE, back_color=WHITE)

        return img

    def _add_branding(self, qr_img) -> "Image":
        """
        Add a WiMLDS label strip below the QR code.
        Canvas: white background, QR centred, purple label at bottom.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise ImportError("Pillow not installed. Run:  pip install Pillow")

        # Convert to PIL Image if it is a qrcode wrapper
        if not isinstance(qr_img, Image.Image):
            buf = io.BytesIO()
            qr_img.save(buf)
            buf.seek(0)
            qr_pil = Image.open(buf).convert("RGBA")
        else:
            qr_pil = qr_img.convert("RGBA")

        qw, qh   = qr_pil.size
        label_h  = 36                     # pixels for the WiMLDS label strip
        pad      = 10                     # white padding around QR
        canvas_w = qw + pad * 2
        canvas_h = qh + pad * 2 + label_h

        canvas = Image.new("RGB", (canvas_w, canvas_h), WHITE)

        # Paste QR onto white canvas
        if qr_pil.mode == "RGBA":
            canvas.paste(qr_pil, (pad, pad), qr_pil)
        else:
            canvas.paste(qr_pil, (pad, pad))

        # Purple label strip at bottom
        draw = ImageDraw.Draw(canvas)
        label_y = qh + pad * 2
        draw.rectangle(
            [(0, label_y), (canvas_w, canvas_h)],
            fill=BRAND_PURPLE,
        )

        # "WiMLDS Pune" text centred in label
        label_text = "WiMLDS Pune — RSVP"
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
            )
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label_text, font=font)
        tx   = (canvas_w - (bbox[2] - bbox[0])) // 2
        ty   = label_y + (label_h - (bbox[3] - bbox[1])) // 2
        draw.text((tx, ty), label_text, fill=WHITE, font=font)

        return canvas


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _qr_filename(event_id: str) -> str:
    """Appendix D naming convention: QR_<EventID>.png"""
    safe_id = event_id.replace("/", "_").replace(" ", "_")
    return f"QR_{safe_id}.png"


def _save_to_temp(img, filename: str) -> str:
    """Save PIL image to a named temp file. Caller must delete when done."""
    import tempfile, os
    tmp_dir  = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, filename)
    img.save(tmp_path, "PNG", optimize=True)
    logger.debug(f"QR saved locally: {tmp_path}")
    return tmp_path


def _get_qr_folder_id(event_data: dict) -> str:
    """
    Return the Drive folder ID for QR files.
    Priority: event folder map → fallback to root folder.
    """
    folder_map = event_data.get("_drive_folder_map", {})

    # Try multiple key variants (drive_client.provision_event_folders creates these)
    for key in ("02_output/02_qr", "02_output_02_qr", "02_QR"):
        fid = folder_map.get(key)
        if fid:
            return fid

    # Fallback: root folder (file will land in root, not ideal but not fatal)
    logger.warning(
        "QR Drive folder not found in _drive_folder_map — uploading to root folder. "
        "Run provision_drive.py first to set up folder structure."
    )
    return settings.google_drive_root_folder_id or ""


def _error_level(level: str):
    """Convert string error level to qrcode constant."""
    import qrcode
    return {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }.get(level.upper(), qrcode.constants.ERROR_CORRECT_H)


# ─────────────────────────────────────────────────────────────────────────────
# Quick test — run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    parser = argparse.ArgumentParser(description="QR Agent quick test")
    parser.add_argument("--event-id", default="3", help="Master Sheet row number")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--url",      default="", help="Override Meetup URL for testing")
    args = parser.parse_args()

    if args.url:
        event_data = {
            "meetup_event_url": args.url,
            "meetup_event_id":  "TEST",
            "_drive_folder_map": {},
        }
    else:
        from wimlds.core.sheets_client import sheets_client
        event_data = sheets_client.get_event(int(args.event_id))

    agent  = QRAgent(dry_run=args.dry_run)
    result = agent.generate_qr(event_data)

    print(f"\nSuccess: {result.success}")
    print(f"Data:    {json.dumps(result.data, indent=2)}")
    if result.error:
        print(f"Error:   {result.error}")


