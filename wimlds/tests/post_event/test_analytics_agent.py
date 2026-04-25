"""
Tests for AnalyticsAgent — all use dry_run=True, no real API calls.
Run with:  pytest tests/test_analytics_agent.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date


# ── Shared fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def sample_event():
    return {
        "row_id":           "3",
        "event_title":      "Intro to Transformers — WiMLDS Pune",
        "date":             "11 Oct 2025",
        "series":           "ML Foundations",
        "mode":             "In-Person",
        "session_type":     "Hands-on Workshop",
        "venue_name":       "Tech Hub Pune",
        "speaker_org":      "IIT Pune AI Lab",
        "tier_1_institution": "Yes",
        "capacity":         "60",
        "rsvps":            "52",
        "showup_count":     "44",
        "waitlisted":       "8",
        "meetup_event_id":  "303123456",
        "meetup_groups_list": "WiMLDS-Pune,AI-Pune,DataScience-Pune",
        "wa_groups_count":  "",
        "wa_individuals_count": "12",
        # Ops flags
        "announce_sent":          "Y",
        "tminus2_sent":           "Y",
        "tminus1_sent":           "Y",
        "tminus2h_sent":          "Y",
        "whatsapp_groups_posted": "Y",
        "partners_notified":      "Y",
        "post_event_completed":   "Y",
        # Content
        "blog_link":       "https://drive.google.com/file/d/blog_oct/view",
        "recording_link":  "https://drive.google.com/file/d/recording_oct/view",
        "transcript_link": "https://drive.google.com/file/d/transcript_oct/view",
        "ppt_link":        "https://drive.google.com/file/d/slides_oct/view",
        # Post IDs for engagement
        "_linkedin_post_urn": "",
        "_facebook_post_id":  "",
        "_twitter_tweet_id":  "",
    }


@pytest.fixture
def agent():
    from wimlds.agents.post_event.analytics_agent import AnalyticsAgent
    return AnalyticsAgent(dry_run=True)


# ── KPI collection ──────────────────────────────────────────────────────────

class TestKPICollection:
    def test_collect_kpis_returns_dict(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        assert isinstance(kpis, dict)

    def test_identity_fields(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        assert kpis["event_title"] == "Intro to Transformers — WiMLDS Pune"
        assert kpis["series"]      == "ML Foundations"
        assert kpis["mode"]        == "In-Person"
        assert kpis["speaker_org"] == "IIT Pune AI Lab"

    def test_funnel_calculation(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        # dry_run returns 45 for RSVPs; showups from sheet = 44
        assert kpis["showups"]   == 44
        assert kpis["capacity"]  == 60
        assert kpis["waitlisted"]== 8

    def test_showup_rate_computed(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        rsvps  = kpis["rsvps"]
        showups= kpis["showups"]
        expected = round(showups / rsvps * 100, 1) if rsvps > 0 else 0.0
        assert kpis["showup_rate_pct"] == expected

    def test_wa_groups_derived_from_list(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        # meetup_groups_list has 3 groups
        assert kpis["wa_groups_count"] == 3

    def test_ops_cadence_all_yes(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        assert kpis["announce_sent"]       == "Y"
        assert kpis["t2d_sent"]            == "Y"
        assert kpis["t1d_sent"]            == "Y"
        assert kpis["t2h_sent"]            == "Y"
        assert kpis["wa_groups_posted"]    == "Y"
        assert kpis["partners_notified"]   == "Y"
        assert kpis["post_event_completed"]== "Y"

    def test_ops_cadence_partial(self, agent, sample_event):
        ev = {**sample_event, "tminus2_sent": "N", "partners_notified": "N"}
        kpis = agent._collect_kpis(ev, row_num=3)
        assert kpis["t2d_sent"]         == "N"
        assert kpis["partners_notified"]== "N"

    def test_content_links_present(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        assert "blog_oct" in kpis["blog_link"]
        assert "recording_oct" in kpis["recording_link"]

    def test_content_links_empty_when_missing(self, agent, sample_event):
        ev = {**sample_event, "blog_link": "", "recording_link": ""}
        kpis = agent._collect_kpis(ev, row_num=3)
        assert kpis["blog_link"] == ""

    def test_collected_at_timestamp_set(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        assert "IST" in kpis["collected_at"]

    def test_engagement_defaults_when_no_post_ids(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, row_num=3)
        # dry_run always returns mock values regardless
        assert kpis["linkedin_reactions"] >= 0
        assert kpis["facebook_reactions"] >= 0
        assert kpis["twitter_impressions"] >= 0


# ── Growth snapshot ─────────────────────────────────────────────────────────

class TestGrowthSnapshot:
    def test_returns_all_keys(self, agent):
        g = agent._collect_growth()
        for key in ["meetup_members","new_members_30d","mom_growth_pct",
                    "goal_gap","members_needed_per_day"]:
            assert key in g

    def test_dry_run_returns_plausible_values(self, agent):
        g = agent._collect_growth()
        assert g["meetup_members"] == 8_450
        assert g["new_members_30d"] == 120
        assert g["goal_gap"] == 10_000 - 8_450

    def test_goal_gap_is_non_negative(self, agent):
        g = agent._collect_growth()
        assert g["goal_gap"] >= 0

    def test_mom_growth_pct_is_float(self, agent):
        g = agent._collect_growth()
        assert isinstance(g["mom_growth_pct"], float)

    def test_members_needed_per_day_positive(self, agent):
        g = agent._collect_growth()
        # goal not yet reached in dry_run
        assert g["members_needed_per_day"] > 0


# ── Dry-run pipeline ────────────────────────────────────────────────────────

class TestDryRunPipeline:
    def test_run_returns_success(self, agent, sample_event):
        result = agent.run(sample_event, row_num=3)
        assert result.success is True

    def test_run_data_has_kpis_and_growth(self, agent, sample_event):
        result = agent.run(sample_event, row_num=3)
        assert "kpis"   in result.data
        assert "growth" in result.data

    def test_run_standalone_also_succeeds(self, agent, sample_event):
        result = agent.run_standalone(sample_event, row_num=3)
        assert result.success is True

    def test_growth_report_only(self, agent):
        g = agent.growth_report_only()
        assert "meetup_members" in g
        assert "goal_gap" in g

    def test_write_analytics_tab_dry_run_logs(self, agent, sample_event):
        kpis = agent._collect_kpis(sample_event, 3)
        # Should not raise
        agent._write_analytics_tab(3, kpis)

    def test_write_master_flags_dry_run_logs(self, agent):
        agent._write_master_flags(3)  # should not raise

    def test_refresh_dashboard_dry_run_logs(self, agent):
        agent._refresh_dashboard()  # should not raise

    def test_send_completion_email_dry_run_logs(self, agent, sample_event):
        kpis   = agent._collect_kpis(sample_event, 3)
        growth = agent._collect_growth()
        agent._send_completion_email(sample_event, kpis, growth)  # should not raise


# ── Completion email builder ────────────────────────────────────────────────

class TestCompletionEmail:
    def test_subject_contains_title(self, sample_event):
        from wimlds.agents.post_event.analytics_agent import _build_completion_email, AnalyticsAgent
        a = AnalyticsAgent(dry_run=True)
        kpis   = a._collect_kpis(sample_event, 3)
        growth = a._collect_growth()
        subject, body = _build_completion_email(sample_event, kpis, growth)
        assert "Intro to Transformers" in subject

    def test_body_contains_funnel_section(self, sample_event):
        from wimlds.agents.post_event.analytics_agent import _build_completion_email, AnalyticsAgent
        a = AnalyticsAgent(dry_run=True)
        kpis   = a._collect_kpis(sample_event, 3)
        growth = a._collect_growth()
        _, body = _build_completion_email(sample_event, kpis, growth)
        assert "ATTENDANCE FUNNEL" in body
        assert "Show-up rate" in body

    def test_body_contains_goal_tracker(self, sample_event):
        from wimlds.agents.post_event.analytics_agent import _build_completion_email, AnalyticsAgent
        a = AnalyticsAgent(dry_run=True)
        kpis   = a._collect_kpis(sample_event, 3)
        growth = a._collect_growth()
        _, body = _build_completion_email(sample_event, kpis, growth)
        assert "10,000" in body
        assert "GOAL TRACKER" in body

    def test_body_contains_ops_section(self, sample_event):
        from wimlds.agents.post_event.analytics_agent import _build_completion_email, AnalyticsAgent
        a = AnalyticsAgent(dry_run=True)
        kpis   = a._collect_kpis(sample_event, 3)
        growth = a._collect_growth()
        _, body = _build_completion_email(sample_event, kpis, growth)
        assert "OPS CADENCE" in body

    def test_goal_achieved_message_when_gap_zero(self, sample_event):
        from wimlds.agents.post_event.analytics_agent import _build_completion_email
        kpis   = {"rsvps":50,"showups":40,"showup_rate_pct":80,"capacity":60,"waitlisted":0,
                  "linkedin_reactions":0,"linkedin_comments":0,"linkedin_shares":0,
                  "facebook_reactions":0,"facebook_comments":0,
                  "twitter_impressions":0,"twitter_likes":0,"twitter_retweets":0,
                  "wa_groups_count":0,"wa_individuals_count":0,
                  "announce_sent":"Y","t2d_sent":"Y","t1d_sent":"Y","t2h_sent":"Y",
                  "wa_groups_posted":"Y","partners_notified":"Y","post_event_completed":"Y",
                  "blog_link":"","recording_link":"","transcript_link":"","ppt_link":"",
                  "collected_at":"2025-10-11 15:00 IST"}
        growth = {"meetup_members":10000,"new_members_30d":200,"mom_growth_pct":2.0,
                  "goal_gap":0,"members_needed_per_day":0}
        _, body = _build_completion_email(sample_event, kpis, growth)
        assert "GOAL ACHIEVED" in body


# ── Column helpers ──────────────────────────────────────────────────────────

class TestColumnHelpers:
    def test_col_index_A(self):
        from wimlds.agents.post_event.analytics_agent import _col_index
        assert _col_index("A") == 0

    def test_col_index_Z(self):
        from wimlds.agents.post_event.analytics_agent import _col_index
        assert _col_index("Z") == 25

    def test_col_index_AA(self):
        from wimlds.agents.post_event.analytics_agent import _col_index
        assert _col_index("AA") == 26

    def test_col_letter_1(self):
        from wimlds.agents.post_event.analytics_agent import _col_letter
        assert _col_letter(1) == "A"

    def test_col_letter_27(self):
        from wimlds.agents.post_event.analytics_agent import _col_letter
        assert _col_letter(27) == "AA"

    def test_safe_int_normal(self):
        from wimlds.agents.post_event.analytics_agent import _safe_int
        assert _safe_int("42") == 42
        assert _safe_int(60)   == 60
        assert _safe_int("1,200") == 1200

    def test_safe_int_garbage(self):
        from wimlds.agents.post_event.analytics_agent import _safe_int
        assert _safe_int("N/A") == 0
        assert _safe_int("")    == 0
        assert _safe_int(None)  == 0


