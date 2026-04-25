"""
Tests for the Post-Event Agent.
Run:  pytest tests/ -v
All network calls are mocked — tests pass with zero credentials.
"""
from __future__ import annotations

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from dataclasses import dataclass
from typing import Optional

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from wimlds.agents.post_event.post_event_agent import PostEventAgent, _event_context, _fallback_summary
from wimlds.integrations.processing.transcript_processor import (
    TranscriptProcessor, TranscriptFormat, transcript_processor
)
from wimlds.integrations.meeting.zoom_client import ZoomMeeting, ZoomRecording, _build_iso_datetime, _calc_duration_minutes


# ─── Fixtures ─────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def event_data():
    return json.loads((FIXTURE_DIR / "sample_event.json").read_text())


@pytest.fixture
def vtt_path():
    return str(FIXTURE_DIR / "sample_transcript.vtt")


@pytest.fixture
def agent_dry(monkeypatch):
    """PostEventAgent in dry-run mode — no real I/O."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return PostEventAgent(dry_run=True)


@pytest.fixture
def agent_live(monkeypatch):
    """PostEventAgent with all external calls mocked."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return PostEventAgent(dry_run=False)


# ─── TranscriptProcessor tests ────────────────────────────────────────────────

class TestTranscriptProcessor:

    def test_vtt_parse(self, vtt_path):
        parsed = transcript_processor.process_file(vtt_path)
        assert parsed.format_detected == TranscriptFormat.VTT
        assert parsed.word_count > 100
        assert len(parsed.segments) >= 6
        # Speaker should be extracted
        speakers = {s.speaker for s in parsed.segments if s.speaker}
        assert "Aditya Kulkarni" in speakers

    def test_vtt_clean_text(self, vtt_path):
        parsed = transcript_processor.process_file(vtt_path)
        assert "Aditya Kulkarni:" in parsed.clean_text
        assert "chunking" in parsed.clean_text.lower()
        assert "WEBVTT" not in parsed.clean_text  # markup stripped

    def test_duration_estimated(self, vtt_path):
        parsed = transcript_processor.process_file(vtt_path)
        assert parsed.duration_hint != "unknown"
        assert "min" in parsed.duration_hint

    def test_srt_format(self):
        srt = """1
00:00:03,000 --> 00:00:07,000
Jane Smith: Good morning everyone!

2
00:00:08,000 --> 00:00:15,000
Jane Smith: Today we discuss vector databases.
"""
        parsed = transcript_processor.process_text(srt, "test.srt")
        assert parsed.format_detected == TranscriptFormat.SRT
        assert len(parsed.segments) == 2
        assert parsed.segments[0].speaker == "Jane Smith"

    def test_zoom_txt_format(self):
        zoom_txt = """[00:00:03]
Aditya Kulkarni: Welcome to the session.

[00:01:30]
Attendee: Can you explain chunking?

[00:01:45]
Aditya Kulkarni: Sure. Semantic chunking splits on topic boundaries.
"""
        parsed = transcript_processor.process_text(zoom_txt, "test.txt")
        assert parsed.format_detected == TranscriptFormat.ZOOM
        assert len(parsed.segments) == 3
        assert parsed.segments[0].start_time == "00:00:03"

    def test_sbv_format(self):
        sbv = """0:00:03.000,0:00:07.000
Priya Desai: Hello and welcome!

0:00:08.500,0:00:15.000
Priya Desai: Let's start with transformers.
"""
        parsed = transcript_processor.process_text(sbv, "test.sbv")
        assert parsed.format_detected == TranscriptFormat.SBV
        assert parsed.segments[0].speaker == "Priya Desai"

    def test_plain_fallback(self):
        plain = "This is some plain text about machine learning.\n\nSecond paragraph."
        parsed = transcript_processor.process_text(plain, "notes.txt")
        assert parsed.format_detected == TranscriptFormat.PLAIN
        assert len(parsed.segments) == 2

    def test_speaker_split(self):
        from wimlds.integrations.processing.transcript_processor import _split_speaker
        speaker, body = _split_speaker("John Doe: Hello world")
        assert speaker == "John Doe"
        assert body    == "Hello world"

    def test_speaker_split_no_match(self):
        from wimlds.integrations.processing.transcript_processor import _split_speaker
        speaker, body = _split_speaker("https://example.com/link")
        assert speaker is None
        assert body == "https://example.com/link"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            transcript_processor.process_file("/nonexistent/path.vtt")


# ─── ZoomClient helpers ───────────────────────────────────────────────────────

class TestZoomHelpers:

    def test_build_iso_datetime(self, event_data):
        iso = _build_iso_datetime(event_data)
        assert "2025-11-15" in iso
        assert "+05:30" in iso

    def test_calc_duration(self, event_data):
        dur = _calc_duration_minutes(event_data)
        assert dur == 210  # 10:00 → 13:30 = 210 min

    def test_calc_duration_fallback(self):
        assert _calc_duration_minutes({}) >= 30


# ─── PostEventAgent dry-run tests ─────────────────────────────────────────────

class TestPostEventAgentDryRun:

    def test_full_pipeline_dry_run(self, agent_dry, event_data):
        """Full pipeline with dry_run=True should complete without errors."""
        result = agent_dry.run(event_data)
        assert result.success is True
        assert result.errors == []

    def test_dry_run_does_not_call_zoom(self, agent_dry, event_data):
        with patch("integrations.zoom_client.zoom_client.get_recording") as mock_zoom:
            agent_dry.run(event_data, meeting_id="999888")
            mock_zoom.assert_not_called()

    def test_dry_run_does_not_call_drive(self, agent_dry, event_data):
        with patch("integrations.drive_client.drive_client.upload_file") as mock_drive:
            agent_dry.run(event_data)
            mock_drive.assert_not_called()

    def test_dry_run_skips_sheet_write(self, agent_dry, event_data):
        with patch("core.sheets_client.sheets_client.write_fields") as mock_sheets:
            agent_dry.run(event_data)
            mock_sheets.assert_not_called()


# ─── LLM integration tests (mocked) ──────────────────────────────────────────

class TestLLMGeneration:

    def _make_agent_with_mock_llm(self, response_text: str, dry_run: bool = False):
        agent = PostEventAgent(dry_run=dry_run)
        agent.llm = MagicMock()
        agent.llm.dry_run = dry_run
        agent.llm.generate.return_value = response_text
        agent.llm.generate_json.return_value = json.loads(response_text) if response_text.startswith("{") else {}
        return agent

    def test_generate_summary_with_transcript(self, event_data, vtt_path):
        parsed = transcript_processor.process_file(vtt_path)
        mock_summary = {
            "one_liner": "Attendees learned to build production RAG pipelines.",
            "session_overview": "The session covered chunking, vector DBs, and evaluation.",
            "key_takeaways": ["Semantic chunking improves recall", "Use RAGAS for evaluation",
                              "Re-ranker reduces hallucinations", "Multi-hop needs agent loop",
                              "Choose vector DB carefully"],
            "key_insights": ["RAG is an engineering problem", "Evaluation is often skipped"],
            "notable_quotes": [],
            "topics_covered": ["RAG", "chunking", "RAGAS", "vector databases"],
            "audience_level": "Intermediate",
            "highlights_for_linkedin": "• Production RAG techniques\n• RAGAS evaluation\n• Vector DB trade-offs",
        }
        agent = self._make_agent_with_mock_llm(json.dumps(mock_summary))
        result = agent._generate_summary(event_data, parsed)
        assert result["one_liner"] != ""
        assert len(result["key_takeaways"]) == 5
        agent.llm.generate_json.assert_called_once()

    def test_generate_summary_fallback_on_failure(self, event_data):
        agent = PostEventAgent(dry_run=False)
        agent.llm = MagicMock()
        agent.llm.generate_json.side_effect = Exception("LLM unavailable")
        result = agent._generate_summary(event_data, None)
        # Should return fallback, not raise
        assert "one_liner" in result
        assert result["one_liner"] != ""

    def test_generate_blog_with_transcript(self, event_data, vtt_path):
        parsed = transcript_processor.process_file(vtt_path)
        mock_blog = "# RAG Systems in Production\n\n## Summary\n\nExcellent session.\n\n## Takeaways\n\n1. Chunk well."
        agent = self._make_agent_with_mock_llm(mock_blog)
        summary = {"key_takeaways": ["Chunk well"], "key_insights": ["RAG is engineering"]}
        blog = agent._generate_blog(event_data, parsed, summary)
        assert "RAG" in blog
        agent.llm.generate.assert_called_once()
        # Transcript should be in the prompt
        call_args = agent.llm.generate.call_args[0][0]
        assert "chunking" in call_args.lower() or "transcript" in call_args.lower()

    def test_generate_blog_without_transcript(self, event_data):
        mock_blog = "# RAG Systems\n\nNo transcript available but event was great."
        agent = self._make_agent_with_mock_llm(mock_blog)
        blog = agent._generate_blog(event_data, None, {})
        assert len(blog) > 10
        agent.llm.generate.assert_called_once()


# ─── Full pipeline with mocked externals ─────────────────────────────────────

class TestFullPipelineMocked:

    @pytest.fixture
    def mock_zoom_recording(self):
        return ZoomRecording(
            meeting_id              = "123456789",
            topic                   = "RAG Systems in Production",
            start_time              = "2025-11-15T10:00:00+05:30",
            download_url            = "https://zoom.us/rec/download/mock.mp4",
            play_url                = "https://zoom.us/rec/play/mock",
            transcript_download_url = "https://zoom.us/rec/download/mock.vtt",
            duration_minutes        = 210,
            file_size_mb            = 450.0,
        )

    def test_pipeline_with_zoom_transcript(
        self, event_data, vtt_path, mock_zoom_recording
    ):
        agent = PostEventAgent(dry_run=False)
        agent.llm = MagicMock()
        agent.llm.dry_run = False
        agent.llm.generate.return_value = "# Blog Post\n\nGreat session."
        agent.llm.generate_json.return_value = {
            "one_liner": "Attendees learned RAG.",
            "session_overview": "Great session.",
            "key_takeaways": ["A", "B", "C", "D", "E"],
            "key_insights": ["X", "Y"],
            "notable_quotes": [],
            "topics_covered": ["RAG"],
            "audience_level": "Intermediate",
            "highlights_for_linkedin": "• A\n• B",
        }

        with (
            patch("integrations.zoom_client.zoom_client.get_recording",
                  return_value=mock_zoom_recording),
            patch("integrations.zoom_client.zoom_client.download_recording",
                  return_value=vtt_path),
            patch("integrations.zoom_client.zoom_client.download_transcript",
                  return_value=vtt_path),
            patch("integrations.zoom_client.zoom_client.delete_recording"),
            patch("integrations.drive_client.drive_client.provision_post_event_folders",
                  return_value={"02_Recording": "fid1", "03_Transcript": "fid2",
                                "05_Blogs_Drafts": "fid3"}),
            patch("integrations.drive_client.drive_client.upload_file",
                  return_value="https://drive.google.com/file/d/MOCK/view"),
            patch("integrations.drive_client.drive_client.upload_bytes",
                  return_value="https://drive.google.com/file/d/MOCKBLOG/view"),
            patch.object(agent, "_post_linkedin", return_value=True),
            patch.object(agent, "_post_meetup_update", return_value=True),
            patch.object(agent, "_share_wa_closed", return_value=3),
            patch.object(agent, "_write_to_sheet"),
            patch.object(agent, "_finalise_sheet"),
            patch.object(agent, "_notify_organiser"),
        ):
            result = agent.run(
                event_data,
                meeting_id = "123456789",
                platform   = "zoom",
            )

        assert result.success is True
        assert result.blog_markdown  != ""
        assert result.recording_url  == "https://drive.google.com/file/d/MOCK/view"
        assert result.transcript_url == "https://drive.google.com/file/d/MOCK/view"
        assert result.blog_url       == "https://drive.google.com/file/d/MOCKBLOG/view"
        assert result.linkedin_posted is True
        assert result.meetup_posted   is True
        assert result.wa_groups_sent  == 3

    def test_pipeline_with_provided_transcript(
        self, event_data, vtt_path
    ):
        agent = PostEventAgent(dry_run=False)
        agent.llm = MagicMock()
        agent.llm.dry_run = False
        agent.llm.generate.return_value = "# Blog\n\nContent."
        agent.llm.generate_json.return_value = {
            "one_liner": "Session done.",
            "session_overview": "Good.",
            "key_takeaways": ["T1","T2","T3","T4","T5"],
            "key_insights": ["I1"],
            "notable_quotes": [],
            "topics_covered": [],
            "audience_level": "Mixed",
            "highlights_for_linkedin": "• T1\n• T2",
        }

        with (
            patch("integrations.drive_client.drive_client.provision_post_event_folders",
                  return_value={"03_Transcript": "fid2", "05_Blogs_Drafts": "fid3"}),
            patch("integrations.drive_client.drive_client.upload_file",
                  return_value="https://drive.google.com/file/d/TR/view"),
            patch("integrations.drive_client.drive_client.upload_bytes",
                  return_value="https://drive.google.com/file/d/BLOG/view"),
            patch.object(agent, "_post_linkedin",     return_value=True),
            patch.object(agent, "_post_meetup_update",return_value=True),
            patch.object(agent, "_share_wa_closed",   return_value=2),
            patch.object(agent, "_write_to_sheet"),
            patch.object(agent, "_finalise_sheet"),
            patch.object(agent, "_notify_organiser"),
        ):
            result = agent.run(
                event_data,
                transcript_path = vtt_path,
            )

        assert result.success is True
        assert result.transcript_url != ""
        assert result.blog_markdown  != ""

    def test_pipeline_survives_recording_failure(self, event_data, vtt_path):
        """Pipeline should continue even if recording download fails."""
        agent = PostEventAgent(dry_run=False)
        agent.llm = MagicMock()
        agent.llm.dry_run = False
        agent.llm.generate.return_value = "# Blog\n\nContent."
        agent.llm.generate_json.return_value = {
            "one_liner": "Session done.", "session_overview": "Good.",
            "key_takeaways": ["T1"], "key_insights": ["I1"],
            "notable_quotes": [], "topics_covered": [],
            "audience_level": "Mixed", "highlights_for_linkedin": "• T1",
        }

        with (
            patch("integrations.zoom_client.zoom_client.get_recording",
                  side_effect=Exception("Zoom API error")),
            patch("integrations.drive_client.drive_client.provision_post_event_folders",
                  return_value={}),
            patch("integrations.drive_client.drive_client.upload_file",
                  return_value="https://drive.google.com/file/d/TR/view"),
            patch("integrations.drive_client.drive_client.upload_bytes",
                  return_value="https://drive.google.com/file/d/BLOG/view"),
            patch.object(agent, "_post_linkedin",     return_value=True),
            patch.object(agent, "_post_meetup_update",return_value=True),
            patch.object(agent, "_share_wa_closed",   return_value=0),
            patch.object(agent, "_write_to_sheet"),
            patch.object(agent, "_finalise_sheet"),
            patch.object(agent, "_notify_organiser"),
        ):
            result = agent.run(
                event_data,
                meeting_id      = "123456789",
                platform        = "zoom",
                transcript_path = vtt_path,
            )

        assert result.success is True          # pipeline resilient
        assert result.recording_url == ""      # recording failed but continued
        assert result.blog_markdown != ""      # blog still generated


# ─── Helper function tests ────────────────────────────────────────────────────

class TestHelpers:

    def test_event_context_includes_key_fields(self, event_data):
        ctx = _event_context(event_data)
        assert "Aditya Kulkarni" in ctx
        assert "NLP Series"      in ctx
        assert "Pune Tech Park"  in ctx

    def test_fallback_summary_has_required_keys(self, event_data):
        fb = _fallback_summary(event_data)
        for k in ["one_liner","session_overview","key_takeaways","key_insights",
                  "notable_quotes","topics_covered","audience_level","highlights_for_linkedin"]:
            assert k in fb, f"Missing key: {k}"

    def test_closed_share_fields_are_correct(self):
        from wimlds.agents.post_event.post_event_agent import CLOSED_SHARE_FIELDS
        assert "recording_link"  in CLOSED_SHARE_FIELDS
        assert "transcript_link" in CLOSED_SHARE_FIELDS
        assert "ppt_link"        in CLOSED_SHARE_FIELDS
        # Blog is public
        assert "blog_link" not in CLOSED_SHARE_FIELDS


