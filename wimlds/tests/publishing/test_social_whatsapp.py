"""
Tests for Social Agent and WhatsApp Agent.
All tests use dry_run=True — no real API calls are made.
Run with:  pytest tests/test_social_whatsapp.py -v
"""
import pytest

# ── Shared fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_event():
    return {
        "event_title":        "RAG Systems in Production",
        "subtitle":           "Vector DBs, Chunking & Evaluation",
        "day":                "Saturday",
        "date":               "12 Apr 2025",
        "start_time_ist":     "2:00 PM",
        "end_time_ist":       "5:30 PM",
        "venue_name":         "Thoughtworks Pune",
        "venue_address":      "5th Floor, Panchshil Tech Park, Yerwada",
        "entrance_note":      "Show Meetup RSVP at reception",
        "parking_info":       "B2 basement — free",
        "laptop_required":    "Yes",
        "wifi_note":          "TW-Guest / ask host for password",
        "host_name":          "Priya Sharma",
        "host_phone":         "+91 98765 43210",
        "speaker_name":       "Aditya Kulkarni",
        "speaker_title":      "Senior ML Engineer",
        "speaker_org":        "Persistent Systems",
        "speaker_special_achievements": "NeurIPS 2024 paper;AWS ML Hero",
        "_learn_bullets":     ["RAG pipeline design", "RAGAS evaluation", "Chunking strategies"],
        "_scope_one_liner":   "Build production RAG systems from scratch",
        "meetup_event_url":   "https://www.meetup.com/wimlds-pune/events/12345/",
        "conference_link":    "",
        "mode":               "In-Person",
        "series":             "Deep Dive",
        "meetup_event_id":    "test_4",
        "promote_linkedin":   "Y",
        "promote_facebook":   "Y",
        "promote_x":          "Y",
        "promote_instagram":  "N",
        "promote_whatsapp":   "Y",
        "promote_meetup":     "N",
        "wa_group_names":     "WiMLDS Pune,Pune ML Community",
        "wa_individual_numbers": "+919876543210,9123456789",
        "promote_wa_individual": "Y",
        "_poster_local_path": None,
        "_drive_folder_map":  {},
    }


class TestWhatsAppAgentDryRun:
    def test_send_announcement_dry_run(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        wa = WhatsAppAgent(dry_run=True)
        result = wa.send_announcement(sample_event)
        assert result.success is True
        assert result.data["dry_run"] is True

    def test_send_spotlight_dry_run(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        result = WhatsAppAgent(dry_run=True).send_spotlight(sample_event)
        assert result.success is True

    def test_send_logistics_dry_run(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        result = WhatsAppAgent(dry_run=True).send_logistics(sample_event)
        assert result.success is True

    def test_send_final_bump_dry_run(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        result = WhatsAppAgent(dry_run=True).send_final_bump(sample_event)
        assert result.success is True

    def test_group_names_parsed(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        groups = WhatsAppAgent._get_group_names(sample_event)
        assert groups == ["WiMLDS Pune", "Pune ML Community"]

    def test_numbers_normalized(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        nums = WhatsAppAgent._get_individual_numbers(sample_event)
        assert "+919876543210" in nums
        assert "+919123456789" in nums

    def test_empty_groups_success(self, sample_event):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        ev = {**sample_event, "wa_group_names": "", "wa_individual_numbers": ""}
        result = WhatsAppAgent(dry_run=True).send_announcement(ev)
        assert result.success is True

    def test_number_normalization_edge_cases(self):
        from wimlds.agents.publishing.whatsapp_agent import WhatsAppAgent
        ev = {"wa_individual_numbers": "9876543210,+911234567890,09111222333"}
        nums = WhatsAppAgent._get_individual_numbers(ev)
        assert "+919876543210" in nums
        assert "+911234567890" in nums
        assert "+919111222333" in nums


class TestSocialAgentDryRun:
    def test_post_announcement(self, sample_event):
        from wimlds.agents.publishing.social_agent import SocialAgent
        result = SocialAgent(dry_run=True).post_announcement(sample_event)
        assert result.success is True

    def test_post_spotlight(self, sample_event):
        from wimlds.agents.publishing.social_agent import SocialAgent
        result = SocialAgent(dry_run=True).post_spotlight(sample_event)
        assert result.success is True

    def test_post_logistics(self, sample_event):
        from wimlds.agents.publishing.social_agent import SocialAgent
        result = SocialAgent(dry_run=True).post_logistics(sample_event)
        assert result.success is True

    def test_post_final_bump(self, sample_event):
        from wimlds.agents.publishing.social_agent import SocialAgent
        result = SocialAgent(dry_run=True).post_final_bump(sample_event)
        assert result.success is True

    def test_twitter_truncation_short(self):
        from wimlds.agents.publishing.social_agent import SocialAgent
        text = "Short text\n\n#WiMLDS #Pune #AI"
        result = SocialAgent._truncate_tweet(text)
        assert result == text

    def test_twitter_truncation_long(self):
        from wimlds.agents.publishing.social_agent import SocialAgent
        long_text = "A" * 300 + "\n#WiMLDS #Pune #AI"
        truncated = SocialAgent._truncate_tweet(long_text)
        assert len(truncated) <= 280
        assert "#WiMLDS" in truncated


class TestMessageTemplates:
    def test_announcement_content(self, sample_event):
        from wimlds.agents.publishing.social_agent import _event_to_context
        from wimlds.config.message_templates import render_announcement
        ctx = _event_to_context(sample_event)
        msg = render_announcement(ctx)
        assert "RAG Systems in Production" in msg
        assert "Aditya Kulkarni" in msg
        assert "Thoughtworks Pune" in msg

    def test_spotlight_contains_achievements(self, sample_event):
        from wimlds.agents.publishing.social_agent import _event_to_context
        from wimlds.config.message_templates import render_spotlight
        ctx = _event_to_context(sample_event)
        msg = render_spotlight(ctx)
        assert "NeurIPS 2024 paper" in msg

    def test_logistics_contains_host(self, sample_event):
        from wimlds.agents.publishing.social_agent import _event_to_context
        from wimlds.config.message_templates import render_logistics
        ctx = _event_to_context(sample_event)
        msg = render_logistics(ctx)
        assert "Priya Sharma" in msg


