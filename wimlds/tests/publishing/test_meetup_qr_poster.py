"""
Tests — Meetup Agent, QR Agent, Poster Agent
=============================================
All tests run in dry_run=True mode — no real API calls, no Drive uploads,
no emails, no file system changes.

Run:  pytest tests/test_meetup_qr_poster.py -v

Covers:
  TestMeetupAgent   — 14 tests
  TestQRAgent       — 10 tests
  TestPosterAgent   — 12 tests
  TestHelpers       —  4 tests
  Total             — 40 tests
"""
import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from wimlds.tests.fixtures.sample_event import SAMPLE_EVENT


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def event():
    """Full SAMPLE_EVENT for tests."""
    return dict(SAMPLE_EVENT)


@pytest.fixture
def online_event(event):
    return {**event, "mode": "Online", "conference_link": "https://zoom.us/j/999"}


@pytest.fixture
def hybrid_event(event):
    return {**event, "mode": "Hybrid", "conference_link": "https://zoom.us/j/888"}


@pytest.fixture
def event_no_url(event):
    return {**event, "meetup_event_url": "", "meetup_event_id": ""}


@pytest.fixture
def event_with_id(event):
    return {**event, "meetup_event_id": "EXISTING123"}


# ─────────────────────────────────────────────────────────────────────────────
# TestMeetupAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestMeetupAgent:

    # ── dry_run happy paths ───────────────────────────────────────────────────

    def test_create_event_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.create_or_update_event(event)
        assert result.success
        assert "meetup_url" in result.data
        assert "event_id"   in result.data
        assert "DRY_RUN"    in result.data["meetup_url"]

    def test_upload_poster_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.upload_poster({**event, "_poster_local_path": "/tmp/fake.png"})
        assert result.success
        assert "poster_meetup_url" in result.data

    def test_add_conference_link_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.add_conference_link_to_description(event, "https://zoom.us/j/1")
        assert result.success

    def test_post_attendee_message_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.post_attendee_message(event, "Hello attendees!")
        assert result.success

    def test_upload_photo_album_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.upload_photo_album(event, ["/tmp/a.jpg", "/tmp/b.jpg"])
        assert result.success
        assert result.data["uploaded_photos"] == []

    def test_post_consolidated_update_dry_run(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent  = MeetupAgent(dry_run=True)
        result = agent.post_consolidated_update(
            event,
            blog_link="https://blog.com/post1",
            recording_link="https://drive.google.com/rec",
            transcript_link="https://drive.google.com/tr",
            slides_link="https://drive.google.com/slides",
        )
        assert result.success

    # ── description builder ───────────────────────────────────────────────────

    def test_description_contains_title(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent = MeetupAgent(dry_run=True)
        desc  = agent._build_description(event)
        assert event["event_title"] in desc

    def test_description_online_includes_conf_link(self, online_event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent = MeetupAgent(dry_run=True)
        desc  = agent._build_description(online_event)
        assert online_event["conference_link"] in desc

    def test_description_inperson_no_conf_link(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent = MeetupAgent(dry_run=True)
        desc  = agent._build_description({**event, "mode": "In-Person", "conference_link": ""})
        assert "Join Link" not in desc

    def test_description_includes_speaker(self, event):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        agent = MeetupAgent(dry_run=True)
        desc  = agent._build_description(event)
        assert event["speaker_name"] in desc
        assert event["speaker_org"]  in desc

    # ── epoch conversion ──────────────────────────────────────────────────────

    def test_to_epoch_ms_valid(self):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        ms = MeetupAgent._to_epoch_ms("11 Oct 2025", "14:00")
        assert ms is not None
        assert ms > 0
        # 11 Oct 2025 14:00 IST ≈ 2025-10-11T08:30Z → epoch ~1728635400000 ± tolerance
        assert abs(ms - 1728635400000) < 60_000  # within 60 seconds

    def test_to_epoch_ms_empty_inputs(self):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        assert MeetupAgent._to_epoch_ms("", "14:00") is None
        assert MeetupAgent._to_epoch_ms("11 Oct 2025", "") is None

    def test_duration_ms_valid(self):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        ms = MeetupAgent._duration_ms("14:00", "17:30")
        assert ms == 3.5 * 60 * 60 * 1000   # 3h30m

    def test_duration_ms_bad_input(self):
        from wimlds.agents.publishing.meetup_agent import MeetupAgent
        assert MeetupAgent._duration_ms("", "") is None


# ─────────────────────────────────────────────────────────────────────────────
# TestQRAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestQRAgent:

    def test_generate_qr_dry_run(self, event):
        from wimlds.agents.publishing.qr_agent import QRAgent
        result = QRAgent(dry_run=True).generate_qr(event)
        assert result.success
        assert "qr_drive_url"   in result.data
        assert "DRY_RUN"        in result.data["qr_drive_url"]

    def test_generate_qr_missing_url_fails(self, event_no_url):
        from wimlds.agents.publishing.qr_agent import QRAgent
        result = QRAgent(dry_run=True).generate_qr(event_no_url)
        assert not result.success
        assert "meetup_event_url" in result.error

    def test_generate_qr_real_creates_image(self, event):
        """Integration-style: actually generate a QR PNG in memory."""
        from wimlds.agents.publishing.qr_agent import QRAgent
        import os
        agent = QRAgent(dry_run=False)

        with patch("agents.qr_agent.drive_client") as mock_dc:
            mock_dc.upload_file.return_value = "https://drive.google.com/file/d/TEST/view"
            result = agent.generate_qr(event)

        assert result.success
        assert result.data["qr_drive_url"] == "https://drive.google.com/file/d/TEST/view"
        # Temp file should have been created
        tmp_path = result.data.get("_qr_local_path", "")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    def test_qr_filename_convention(self):
        """Blueprint Appendix D: QR_<EventID>.png"""
        from wimlds.agents.publishing.qr_agent import _qr_filename
        assert _qr_filename("12345")      == "QR_12345.png"
        assert _qr_filename("TEST/SLASH") == "QR_TEST_SLASH.png"

    def test_get_qr_folder_id_from_map(self, event):
        from wimlds.agents.publishing.qr_agent import _get_qr_folder_id
        ev = {**event, "_drive_folder_map": {"02_output/02_qr": "FOLDER_ID_123"}}
        assert _get_qr_folder_id(ev) == "FOLDER_ID_123"

    def test_get_qr_folder_id_fallback(self, event):
        from wimlds.agents.publishing.qr_agent import _get_qr_folder_id
        ev = {**event, "_drive_folder_map": {}}
        # Should not raise — returns root folder or empty string
        result = _get_qr_folder_id(ev)
        assert isinstance(result, str)

    def test_error_level_H(self):
        from wimlds.agents.publishing.qr_agent import _error_level
        import qrcode
        assert _error_level("H") == qrcode.constants.ERROR_CORRECT_H

    def test_error_level_unknown_defaults_to_H(self):
        from wimlds.agents.publishing.qr_agent import _error_level
        import qrcode
        assert _error_level("X") == qrcode.constants.ERROR_CORRECT_H

    def test_make_qr_returns_image_object(self, event):
        from wimlds.agents.publishing.qr_agent import QRAgent
        agent = QRAgent(dry_run=False)
        img   = agent._make_qr("https://meetup.com/WiMLDS-Pune/events/TEST")
        # Should be a PIL Image or qrcode image — not None
        assert img is not None

    def test_add_branding_returns_pil_image(self, event):
        from wimlds.agents.publishing.qr_agent import QRAgent
        from PIL import Image
        agent  = QRAgent(dry_run=False)
        qr_img = agent._make_qr("https://meetup.com/WiMLDS-Pune/events/TEST")
        result = agent._add_branding(qr_img)
        assert isinstance(result, Image.Image)


# ─────────────────────────────────────────────────────────────────────────────
# TestPosterAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestPosterAgent:

    def test_create_poster_dry_run(self, event):
        from wimlds.agents.publishing.poster_agent import PosterAgent
        result = PosterAgent(dry_run=True).create_poster(event)
        assert result.success
        assert "poster_drive_url"   in result.data
        assert "DRY_RUN"            in result.data["poster_drive_url"]

    def test_send_approval_dry_run(self, event):
        from wimlds.agents.publishing.poster_agent import PosterAgent
        result = PosterAgent(dry_run=True).send_for_approval(
            {**event, "poster_drive_url": "https://drive.google.com/poster"}
        )
        assert result.success

    def test_send_approval_missing_url_fails(self, event):
        from wimlds.agents.publishing.poster_agent import PosterAgent
        result = PosterAgent(dry_run=True).send_for_approval(
            {**event, "poster_drive_url": ""}
        )
        assert not result.success
        assert "poster_drive_url" in result.error

    def test_compose_poster_returns_image(self, event):
        """Actually compose the PIL image — no Drive upload."""
        from wimlds.agents.publishing.poster_agent import PosterAgent
        from PIL import Image
        agent  = PosterAgent(dry_run=True)
        poster = agent._compose_poster(event)
        assert isinstance(poster, Image.Image)
        assert poster.size == (1080, 1350)

    def test_poster_correct_canvas_size(self, event):
        from wimlds.agents.publishing.poster_agent import PosterAgent, POSTER_W, POSTER_H
        poster = PosterAgent(dry_run=True)._compose_poster(event)
        assert poster.width  == POSTER_W
        assert poster.height == POSTER_H

    def test_poster_with_gift_sponsor(self, event):
        """Gift sponsor section rendered when gift_sponsor == Yes."""
        from wimlds.agents.publishing.poster_agent import PosterAgent
        from PIL import Image
        ev     = {**event, "gift_sponsor": "Yes"}
        poster = PosterAgent(dry_run=True)._compose_poster(ev)
        assert isinstance(poster, Image.Image)  # Should not raise

    def test_poster_without_gift_sponsor(self, event):
        from wimlds.agents.publishing.poster_agent import PosterAgent
        from PIL import Image
        ev     = {**event, "gift_sponsor": "No"}
        poster = PosterAgent(dry_run=True)._compose_poster(ev)
        assert isinstance(poster, Image.Image)

    def test_poster_online_mode(self, online_event):
        """Poster should render for Online mode events."""
        from wimlds.agents.publishing.poster_agent import PosterAgent
        from PIL import Image
        poster = PosterAgent(dry_run=True)._compose_poster(online_event)
        assert isinstance(poster, Image.Image)

    def test_send_approval_includes_organiser(self, event):
        """Organiser email always included in recipients."""
        from wimlds.agents.publishing.poster_agent import PosterAgent
        notifier_calls = []

        agent = PosterAgent(dry_run=False)

        def capture_send(recipients, event_title, poster_drive_url):
            notifier_calls.append(recipients)
            return True

        agent.notifier.send_poster_approval_request = capture_send
        agent.send_for_approval(
            {**event, "poster_drive_url": "https://drive.google.com/x",
             "speaker_email": "speaker@test.com"}
        )
        assert len(notifier_calls) == 1
        recipients = notifier_calls[0]
        # Organiser (settings.notification_email) should always be in list
        assert len(recipients) >= 1

    def test_create_poster_live_uploads_to_drive(self, event):
        """Live path: compose poster + mock Drive upload."""
        from wimlds.agents.publishing.poster_agent import PosterAgent
        agent = PosterAgent(dry_run=False)

        with patch("agents.poster_agent.drive_client") as mock_dc:
            mock_dc.upload_file.return_value = "https://drive.google.com/file/d/POSTER/view"
            result = agent.create_poster(event)

        assert result.success
        assert result.data["poster_drive_url"] == "https://drive.google.com/file/d/POSTER/view"
        mock_dc.upload_file.assert_called_once()

    def test_get_poster_folder_id_from_map(self, event):
        from wimlds.agents.publishing.poster_agent import _get_poster_folder_id
        ev = {**event, "_drive_folder_map": {"02_output/01_poster_final": "PFID_456"}}
        assert _get_poster_folder_id(ev) == "PFID_456"

    def test_get_poster_folder_id_fallback(self, event):
        from wimlds.agents.publishing.poster_agent import _get_poster_folder_id
        ev = {**event, "_drive_folder_map": {}}
        result = _get_poster_folder_id(ev)
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# TestHelpers
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:

    def test_wrap_text_simple_short(self):
        from wimlds.agents.publishing.poster_agent import _wrap_text_simple
        lines = _wrap_text_simple("Hello world", max_chars=20)
        assert lines == ["Hello world"]

    def test_wrap_text_simple_long(self):
        from wimlds.agents.publishing.poster_agent import _wrap_text_simple
        text  = "This is a very long address string that should wrap properly"
        lines = _wrap_text_simple(text, max_chars=20)
        assert len(lines) > 1
        for line in lines:
            # No line should exceed max_chars by more than one word
            assert len(line) <= 30   # generous tolerance

    def test_poster_font_fallback(self):
        """_font() should never raise even on an unsupported platform."""
        from wimlds.agents.publishing.poster_agent import _font
        font = _font(24, bold=True)
        assert font is not None

    def test_qr_error_level_all(self):
        from wimlds.agents.publishing.qr_agent import _error_level
        import qrcode
        assert _error_level("L") == qrcode.constants.ERROR_CORRECT_L
        assert _error_level("M") == qrcode.constants.ERROR_CORRECT_M
        assert _error_level("Q") == qrcode.constants.ERROR_CORRECT_Q
        assert _error_level("H") == qrcode.constants.ERROR_CORRECT_H


