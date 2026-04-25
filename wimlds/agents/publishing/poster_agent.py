"""
Poster Agent — Blueprint v9.0
==============================
Composes a brand-safe WiMLDS event poster and handles the approval loop.

Layout zones (exact Blueprint v9.0 spec):
  Top-Right   : WiMLDS Logo
  Top-Left    : Registration QR code (from QRAgent)
  Center      : Event Title / Subtitle / Session Type
  Speaker Block: Photo placeholder + Name + Designation + Organisation + Quals
  Timing Row  : Day · Date · Start–End IST  (pink pill)
  Venue (lower-left): Venue Logo + Address  (no LinkedIn, no Mode printed)
  Bottom-Center: Gift Sponsor (conditional on gift_sponsor == "Yes")
  Footer       : Partner logos — ABI Group · PKC · GPU Community · Startup Prime

NOT printed on poster (Blueprint §1.4):
  Mode, Host contact, Series block, LinkedIn page

Pipeline:
  1. create_poster()      Compose PNG → upload to Drive → return poster_drive_url
  2. send_for_approval()  Email Drive link to speaker(s) + venue sponsor + organiser
  3. Orchestrator reads poster_status from Sheet:
       "Approved" → proceed to upload_poster (MeetupAgent)
       "Rework"   → loop back to create_poster (max 5 attempts)
       "Draft"    → still waiting (workflow suspended)

File placement: agents/poster_agent.py  (REPLACE existing file)

New .env variables needed: none
New pip packages needed: none  (Pillow already in requirements.txt)

Optional: place a PNG logo at config/assets/wimlds_logo.png
          and partner logo PNGs at config/assets/partner_logos/
"""

import io
import os
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger
from wimlds.core.drive_client import drive_client
from wimlds.core.notifier import Notifier
from wimlds.core.orchestrator import AgentResult

logger = get_logger("poster_agent")

# ── Canvas & colours ──────────────────────────────────────────────────────────
POSTER_W      = 1080
POSTER_H      = 1350
BRAND_PURPLE  = (76,  29, 149)    # #4C1D95
BRAND_PURPLE2 = (124, 58, 237)    # #7C3AED  (lighter)
BRAND_PINK    = (236, 72, 153)    # #EC4899
WHITE         = (255, 255, 255)
DARK          = (31,  41,  55)    # #1F2937
GRAY          = (107, 114, 128)   # #6B7280
LIGHT_BG      = (249, 250, 251)   # #F9FAFB

# Fixed partner logos (text fallback)
PARTNER_NAMES = ["ABI Group", "PKC", "GPU Community", "Startup Prime"]

# Font paths — DejaVu is available on most Linux / Windows / Mac systems
_FONT_BOLD   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
# Windows fallback
_FONT_BOLD_WIN   = "C:/Windows/Fonts/arialbd.ttf"
_FONT_NORMAL_WIN = "C:/Windows/Fonts/arial.ttf"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load a font, with multiple fallbacks."""
    candidates = (
        [_FONT_BOLD, _FONT_BOLD_WIN] if bold
        else [_FONT_NORMAL, _FONT_NORMAL_WIN]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


class PosterAgent:
    """
    Brand-safe poster composition for WiMLDS Pune events.
    Pass dry_run=True to skip Drive upload and approval email.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run  = dry_run
        self.notifier = Notifier(dry_run=dry_run)

    # ── 1. Create poster ──────────────────────────────────────────────────────

    def create_poster(self, event_data: dict) -> AgentResult:
        """
        Compose the brand-safe poster PNG and upload to Drive.
        Returns: { poster_drive_url, _poster_local_path }
        _poster_local_path is kept alive for MeetupAgent.upload_poster().
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would compose and upload poster")
            return AgentResult(success=True, data={
                "poster_drive_url":   "https://drive.google.com/file/d/DRY_RUN/view",
                "_poster_local_path": "",
            })

        try:
            poster = self._compose_poster(event_data)

            # Save locally (persistent temp — not deleted, MeetupAgent needs it)
            event_id = (
                event_data.get("meetup_event_id")
                or event_data.get("event_title", "event")[:20]
                or "event"
            ).replace(" ", "_").replace("/", "_")
            filename  = "Poster_Final.png"   # Blueprint Appendix D
            tmp_path  = os.path.join(tempfile.gettempdir(), f"Poster_{event_id}.png")
            poster.save(tmp_path, "PNG", optimize=True)

            # Upload to Drive → /02_Output/01_Poster_Final/
            folder_id = _get_poster_folder_id(event_data)
            drive_url = drive_client.upload_file(
                local_path=tmp_path,
                folder_id=folder_id,
                filename=filename,
                mime_type="image/png",
            )

            logger.info(f"Poster uploaded: {drive_url}")
            return AgentResult(success=True, data={
                "poster_drive_url":   drive_url,
                "_poster_local_path": tmp_path,
            })

        except Exception as exc:
            logger.error(f"Poster creation failed: {exc}")
            return AgentResult(success=False, error=str(exc))

    # ── 2. Send for approval ──────────────────────────────────────────────────

    def send_for_approval(self, event_data: dict) -> AgentResult:
        """
        Email the poster Drive link to:
          • Speaker(s) — if speaker_email is in event_data
          • Venue sponsor — if venue_sponsor_email is in event_data
          • Organiser (always, via settings.notification_email)

        The organiser then updates poster_status in the Master Sheet:
          "Approved" → LangGraph routes to upload_poster
          "Rework"   → LangGraph loops back to create_poster
        """
        poster_url = (event_data.get("poster_drive_url") or "").strip()
        if not poster_url:
            return AgentResult(
                success=False,
                error="poster_drive_url is empty — run create_poster first"
            )

        recipients = []
        if event_data.get("speaker_email"):
            recipients.append(event_data["speaker_email"])
        if event_data.get("venue_sponsor_email"):
            recipients.append(event_data["venue_sponsor_email"])
        # Organiser is always CC'd
        recipients.append(settings.notification_email)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would send approval request to: {recipients}")
            logger.info(f"[DRY-RUN] Poster URL: {poster_url}")
            return AgentResult(success=True)

        ok = self.notifier.send_poster_approval_request(
            recipients      = recipients,
            event_title     = event_data.get("event_title", "WiMLDS Event"),
            poster_drive_url= poster_url,
        )
        if ok:
            logger.info(f"Approval request sent to {recipients}")
        else:
            logger.error("Approval email failed to send")

        return AgentResult(
            success=ok,
            error=None if ok else "Approval email failed — check SendGrid credentials"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # POSTER COMPOSITION
    # All drawing methods below; called only by create_poster() in live mode.
    # ─────────────────────────────────────────────────────────────────────────

    def _compose_poster(self, event_data: dict) -> Image.Image:
        poster = Image.new("RGB", (POSTER_W, POSTER_H), WHITE)
        draw   = ImageDraw.Draw(poster)

        # ── Background gradient: deep purple → near-white ─────────────────
        self._draw_gradient(draw, BRAND_PURPLE, LIGHT_BG)

        # ── Top bar (solid brand purple, 140px) ───────────────────────────
        draw.rectangle([(0, 0), (POSTER_W, 140)], fill=BRAND_PURPLE)

        # ── Top-Left: QR code ─────────────────────────────────────────────
        qr_path = (event_data.get("_qr_local_path") or "").strip()
        self._draw_qr(poster, qr_path, x=18, y=15, size=110)

        # ── Top-Right: WiMLDS logo ────────────────────────────────────────
        self._draw_logo(poster, x=POSTER_W - 155, y=18, width=135)

        # ── Event Title ───────────────────────────────────────────────────
        title = event_data.get("event_title") or "WiMLDS Pune Meetup"
        self._draw_text_centered(draw, title, y=158, font_size=38,
                                 color=BRAND_PURPLE, bold=True, max_width=980)

        subtitle = (event_data.get("subtitle") or "").strip()
        if subtitle:
            self._draw_text_centered(draw, subtitle, y=210, font_size=26,
                                     color=DARK, max_width=960)

        session_type = (event_data.get("session_type") or "").strip()
        if session_type:
            self._draw_pill_small(draw, f"[ {session_type} ]", y=252,
                                  bg=BRAND_PURPLE2, text_color=WHITE)

        # ── Timing Row: Day · Date · Start–End IST ────────────────────────
        day  = event_data.get("day", "")
        date = event_data.get("date", "")
        st   = event_data.get("start_time_ist", "")
        et   = event_data.get("end_time_ist", "")
        if day or date:
            timing = f"{day}  ·  {date}  ·  {st}–{et} IST"
            self._draw_timing_pill(draw, timing, y=296)

        # ── Speaker Block (y ≈ 370) ───────────────────────────────────────
        y_after_speaker = self._draw_speaker_block(poster, draw, event_data, y_start=370)

        # ── Venue Block (lower section) ───────────────────────────────────
        venue_y = max(y_after_speaker + 20, 840)
        self._draw_venue_block(draw, event_data, y_start=venue_y)

        # ── Gift Sponsor (conditional) ────────────────────────────────────
        gift = str(event_data.get("gift_sponsor", "")).strip().upper()
        if gift in ("YES", "Y"):
            self._draw_gift_sponsor(draw, y=max(venue_y + 110, 980))

        # ── Partner Logos / Labels (footer) ──────────────────────────────
        self._draw_partner_logos(poster, draw, event_data, y_start=1130)

        # ── Bottom accent line ────────────────────────────────────────────
        draw.rectangle(
            [(0, POSTER_H - 14), (POSTER_W, POSTER_H)],
            fill=BRAND_PINK,
        )

        return poster

    # ── Background ────────────────────────────────────────────────────────────

    def _draw_gradient(self, draw: ImageDraw.ImageDraw,
                       top_color: tuple, bottom_color: tuple):
        """Simple top-to-bottom gradient from top_color to bottom_color."""
        for y in range(POSTER_H):
            t = y / POSTER_H
            r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
            g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
            b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
            draw.line([(0, y), (POSTER_W, y)], fill=(r, g, b))

    # ── QR ────────────────────────────────────────────────────────────────────

    def _draw_qr(self, poster: Image.Image, qr_path: str,
                 x: int, y: int, size: int):
        """Paste the QR PNG; draw a placeholder box if file not found."""
        if qr_path and Path(qr_path).exists():
            try:
                qr_img = Image.open(qr_path).convert("RGBA").resize((size, size))
                # Paste with alpha mask so white background stays transparent over purple
                poster.paste(qr_img, (x, y), qr_img)
                return
            except Exception as exc:
                logger.warning(f"Could not load QR image: {exc}")

        # Placeholder
        draw = ImageDraw.Draw(poster)
        draw.rectangle([(x, y), (x + size, y + size)],
                       outline=WHITE, width=2)
        draw.text((x + 8, y + size // 2 - 10), "QR",
                  fill=WHITE, font=_font(18, bold=True))

    # ── WiMLDS Logo ───────────────────────────────────────────────────────────

    def _draw_logo(self, poster: Image.Image, x: int, y: int, width: int):
        """Paste the WiMLDS logo PNG; fall back to text label."""
        logo_path = Path(settings.wimlds_logo_path)
        if logo_path.exists():
            try:
                logo  = Image.open(logo_path).convert("RGBA")
                ratio = width / logo.width
                h     = int(logo.height * ratio)
                logo  = logo.resize((width, h), Image.LANCZOS)
                poster.paste(logo, (x, y), logo)
                return
            except Exception as exc:
                logger.warning(f"Could not load WiMLDS logo: {exc}")

        # Text fallback
        draw = ImageDraw.Draw(poster)
        draw.text((x, y + 20), "WiMLDS\nPune",
                  fill=WHITE, font=_font(22, bold=True))

    # ── Text utilities ────────────────────────────────────────────────────────

    def _draw_text_centered(self, draw: ImageDraw.ImageDraw, text: str,
                            y: int, font_size: int = 24,
                            color: tuple = DARK, bold: bool = False,
                            max_width: int = POSTER_W - 40):
        """Draw text centred horizontally, wrapping if needed."""
        font  = _font(font_size, bold)
        lines = _wrap_text(text, font, max_width, draw)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            w    = bbox[2] - bbox[0]
            draw.text(((POSTER_W - w) // 2, y + i * (font_size + 8)),
                      line, fill=color, font=font)

    def _draw_timing_pill(self, draw: ImageDraw.ImageDraw, text: str, y: int):
        """Pink rounded pill for the timing row."""
        font = _font(24, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw   = bbox[2] - bbox[0]
        pad  = 22
        rx   = (POSTER_W - tw - pad * 2) // 2
        draw.rounded_rectangle(
            [(rx, y), (rx + tw + pad * 2, y + 48)],
            radius=24, fill=BRAND_PINK
        )
        draw.text((rx + pad, y + 10), text, fill=WHITE, font=font)

    def _draw_pill_small(self, draw: ImageDraw.ImageDraw, text: str,
                         y: int, bg: tuple, text_color: tuple):
        """Small rounded pill for session type label."""
        font = _font(20)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw   = bbox[2] - bbox[0]
        pad  = 16
        rx   = (POSTER_W - tw - pad * 2) // 2
        draw.rounded_rectangle(
            [(rx, y), (rx + tw + pad * 2, y + 36)],
            radius=18, fill=bg
        )
        draw.text((rx + pad, y + 8), text, fill=text_color, font=font)

    # ── Speaker block ─────────────────────────────────────────────────────────

    def _draw_speaker_block(self, poster: Image.Image, draw: ImageDraw.ImageDraw,
                            event_data: dict, y_start: int) -> int:
        """
        Draws:
          • Circular photo placeholder (or real photo if _speaker_photo_path set)
          • Name (bold, large)
          • Designation
          • Organisation (purple)
          • Qualification (gray)

        Returns the y position after the last line drawn.
        """
        photo_size = 150
        cx = (POSTER_W - photo_size) // 2

        # Try to load real speaker photo
        photo_path = (event_data.get("_speaker_photo_path") or "").strip()
        if photo_path and Path(photo_path).exists():
            try:
                raw    = Image.open(photo_path).convert("RGBA")
                raw    = raw.resize((photo_size, photo_size), Image.LANCZOS)
                # Circular mask
                mask   = Image.new("L", (photo_size, photo_size), 0)
                ImageDraw.Draw(mask).ellipse(
                    [(0, 0), (photo_size, photo_size)], fill=255
                )
                circular = Image.new("RGBA", (photo_size, photo_size), (0, 0, 0, 0))
                circular.paste(raw, mask=mask)
                poster.paste(circular, (cx, y_start), circular)
            except Exception:
                self._draw_photo_placeholder(draw, cx, y_start, photo_size)
        else:
            self._draw_photo_placeholder(draw, cx, y_start, photo_size)

        ty = y_start + photo_size + 18

        speaker_name  = event_data.get("speaker_name", "")
        speaker_title = event_data.get("speaker_title", "")
        speaker_org   = event_data.get("speaker_org", "")
        quals         = event_data.get("speaker_highest_qualification", "")
        achievements  = event_data.get("speaker_special_achievements", "")

        if speaker_name:
            self._draw_text_centered(draw, speaker_name, ty,
                                     font_size=32, color=DARK, bold=True)
            ty += 44

        if speaker_title:
            self._draw_text_centered(draw, speaker_title, ty,
                                     font_size=22, color=GRAY)
            ty += 32

        if speaker_org:
            self._draw_text_centered(draw, speaker_org, ty,
                                     font_size=22, color=BRAND_PURPLE, bold=True)
            ty += 32

        if quals:
            self._draw_text_centered(draw, quals, ty,
                                     font_size=18, color=GRAY)
            ty += 28

        if achievements:
            # Truncate long achievements for poster
            ach = achievements if len(achievements) <= 60 else achievements[:57] + "…"
            self._draw_text_centered(draw, f"✨  {ach}", ty,
                                     font_size=17, color=BRAND_PURPLE2)
            ty += 28

        return ty

    def _draw_photo_placeholder(self, draw: ImageDraw.ImageDraw,
                                cx: int, y: int, size: int):
        """Purple circle placeholder for speaker photo."""
        draw.ellipse(
            [(cx, y), (cx + size, y + size)],
            fill=BRAND_PURPLE2
        )
        draw.text(
            (cx + size // 2 - 16, y + size // 2 - 14),
            "👤",
            fill=WHITE,
            font=_font(32)
        )

    # ── Venue block ───────────────────────────────────────────────────────────

    def _draw_venue_block(self, draw: ImageDraw.ImageDraw,
                          event_data: dict, y_start: int):
        """
        Blueprint §1.4: Venue Logo + Address.
        NOT printed: Mode, Host Contact, LinkedIn page.
        """
        venue_name = event_data.get("venue_name", "")
        venue_addr = event_data.get("venue_address", "")

        font_b = _font(24, bold=True)
        font   = _font(20)

        if venue_name:
            draw.text((40, y_start), f"📍  {venue_name}",
                      fill=DARK, font=font_b)
            y_start += 36

        if venue_addr:
            for line in _wrap_text_simple(venue_addr, max_chars=52):
                draw.text((40, y_start), line, fill=GRAY, font=font)
                y_start += 28

        # Google Maps URL as small label (not a clickable link, just text)
        if event_data.get("google_maps_url"):
            draw.text((40, y_start), "📌  google.com/maps — see Meetup page",
                      fill=GRAY, font=_font(16))

    # ── Gift sponsor ──────────────────────────────────────────────────────────

    def _draw_gift_sponsor(self, draw: ImageDraw.ImageDraw, y: int):
        """Conditional gift sponsor section (Blueprint §1.4 Bottom-Centre)."""
        self._draw_text_centered(
            draw,
            "🎁  Gift Sponsor: Fragrance Stories",
            y, font_size=20, color=BRAND_PURPLE2
        )

    # ── Partner logos (footer) ────────────────────────────────────────────────

    def _draw_partner_logos(self, poster: Image.Image, draw: ImageDraw.ImageDraw,
                            event_data: dict, y_start: int):
        """
        Footer row: ABI Group · PKC · GPU Community · Startup Prime.
        Tries to load PNGs from config/assets/partner_logos/.
        Falls back to text labels if images not present.
        """
        logos_dir = Path(settings.partner_logos_dir)
        x         = 30
        max_h     = 60

        for name in PARTNER_NAMES:
            # Try PNG file named after partner
            png = logos_dir / f"{name.replace(' ', '_')}.png"
            if logos_dir.exists() and png.exists():
                try:
                    logo  = Image.open(png).convert("RGBA")
                    ratio = max_h / logo.height
                    w     = int(logo.width * ratio)
                    logo  = logo.resize((w, max_h), Image.LANCZOS)
                    poster.paste(logo, (x, y_start + 10), logo)
                    x += w + 24
                    continue
                except Exception:
                    pass

            # Text label fallback
            font = _font(17)
            bbox = draw.textbbox((0, 0), name, font=font)
            tw   = bbox[2] - bbox[0]
            draw.text((x, y_start + 28), name, fill=GRAY, font=font)
            x += tw + 28


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_text(text: str, font: ImageFont.ImageFont,
               max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words  = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _wrap_text_simple(text: str, max_chars: int) -> list[str]:
    """Simple character-count word-wrap (no PIL needed)."""
    words  = text.split()
    lines, line = [], ""
    for w in words:
        if len(line) + len(w) + 1 <= max_chars:
            line += (" " if line else "") + w
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines or [text]


def _get_poster_folder_id(event_data: dict) -> str:
    """Return Drive folder ID for poster output."""
    folder_map = event_data.get("_drive_folder_map", {})
    for key in ("02_output/01_poster_final", "02_output_01_poster_final", "01_Poster_Final"):
        fid = folder_map.get(key)
        if fid:
            return fid
    logger.warning(
        "Poster Drive folder not found in _drive_folder_map — uploading to root folder."
    )
    return settings.google_drive_root_folder_id or ""


# ─────────────────────────────────────────────────────────────────────────────
# Quick test — run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    parser = argparse.ArgumentParser(description="Poster Agent quick test")
    parser.add_argument("--event-id",  default="3", help="Master Sheet row number")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--save-local", default="",
                        help="Save poster PNG to this local path (skips Drive upload)")
    args = parser.parse_args()

    from wimlds.core.sheets_client import sheets_client
    event_data = sheets_client.get_event(int(args.event_id))

    if args.save_local:
        # Quick visual preview — no Drive upload, no dry_run needed
        agent  = PosterAgent(dry_run=True)
        poster = agent._compose_poster(event_data)
        poster.save(args.save_local, "PNG")
        print(f"Poster saved locally: {args.save_local}")
    else:
        agent  = PosterAgent(dry_run=args.dry_run)
        result = agent.create_poster(event_data)
        print(f"Success: {result.success}")
        print(f"Data:    {result.data}")
        if result.error:
            print(f"Error:   {result.error}")


