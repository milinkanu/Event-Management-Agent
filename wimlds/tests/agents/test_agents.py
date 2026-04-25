"""Unit tests for individual agents (dry-run mode)."""
from unittest.mock import patch

from wimlds.tests.fixtures.sample_event import SAMPLE_EVENT


class TestQRAgent:
    def test_generate_qr_dry_run(self):
        from wimlds.agents.publishing.qr_agent import QRAgent

        agent = QRAgent(dry_run=True)
        result = agent.generate_qr(SAMPLE_EVENT)
        assert result.success
        assert "qr_drive_url" in result.data

    def test_generate_qr_missing_url(self):
        from wimlds.agents.publishing.qr_agent import QRAgent

        agent = QRAgent(dry_run=True)
        result = agent.generate_qr({**SAMPLE_EVENT, "meetup_event_url": ""})
        assert not result.success


class TestPosterAgent:
    def test_create_poster_dry_run(self):
        from wimlds.agents.publishing.poster_agent import PosterAgent

        agent = PosterAgent(dry_run=True)
        result = agent.create_poster(SAMPLE_EVENT)
        assert result.success

    def test_send_approval_dry_run(self):
        from wimlds.agents.publishing.poster_agent import PosterAgent

        agent = PosterAgent(dry_run=True)
        result = agent.send_for_approval({**SAMPLE_EVENT, "poster_drive_url": "https://drive.google.com/x"})
        assert result.success


class TestSocialAgent:
    def test_announcement_dry_run(self):
        from wimlds.agents.publishing.social_agent import SocialAgent

        agent = SocialAgent(dry_run=True)
        result = agent.post_announcement(SAMPLE_EVENT)
        assert result.success

    def test_spotlight_dry_run(self):
        from wimlds.agents.publishing.social_agent import SocialAgent

        agent = SocialAgent(dry_run=True)
        result = agent.post_spotlight(SAMPLE_EVENT)
        assert result.success


class TestConferencingAgent:
    def test_inperson_skips_meeting(self):
        from wimlds.agents.event_ops.conferencing_agent import ConferencingAgent

        agent = ConferencingAgent(dry_run=True)
        result = agent.create_meeting({**SAMPLE_EVENT, "mode": "In-Person"})
        assert result.success
        assert result.data.get("conference_link") == ""

    def test_online_dry_run(self):
        from wimlds.agents.event_ops.conferencing_agent import ConferencingAgent

        agent = ConferencingAgent(dry_run=True)
        result = agent.create_meeting({**SAMPLE_EVENT, "mode": "Online"})
        assert result.success
        assert "conference_link" in result.data


class TestMessageTemplates:
    def test_announcement_renders(self):
        from wimlds.config.message_templates import EventContext, render_announcement

        ctx = EventContext(
            event_title="Test Event",
            day="Saturday",
            date="11 Oct 2025",
            start_time="14:00",
            end_time="17:00",
            venue_name="Tech Hub",
            venue_address="Pune",
            speaker_name="Dr. Test",
            speaker_title="Prof",
            speaker_org="IIT",
            meetup_url="https://meetup.com/test",
            scope_one_liner="Great event!",
        )
        text = render_announcement(ctx)
        assert "Test Event" in text
        assert "Dr. Test" in text
        assert "https://meetup.com/test" in text

    def test_final_bump_includes_conf_link_for_online(self):
        from wimlds.config.message_templates import EventContext, render_final_bump

        ctx = EventContext(
            event_title="Online Event",
            day="Saturday",
            date="11 Oct 2025",
            start_time="14:00",
            end_time="17:00",
            venue_name="Virtual",
            venue_address="",
            host_name="Organizer",
            host_phone="1234",
            conference_link="https://zoom.us/test",
            mode="Online",
            meetup_url="https://meetup.com/test",
        )
        text = render_final_bump(ctx)
        assert "https://zoom.us/test" in text

    def test_final_bump_no_conf_link_for_inperson(self):
        from wimlds.config.message_templates import EventContext, render_final_bump

        ctx = EventContext(
            event_title="In-Person Event",
            day="Saturday",
            date="11 Oct 2025",
            start_time="14:00",
            end_time="17:00",
            venue_name="Office",
            venue_address="Pune",
            host_name="Organizer",
            host_phone="1234",
            conference_link="https://zoom.us/test",
            mode="In-Person",
            meetup_url="https://meetup.com/test",
        )
        text = render_final_bump(ctx)
        assert "zoom.us" not in text


class TestCaptionAgent:
    def test_generate_caption_fallback(self):
        from wimlds.agents.publishing.caption_agent import generate_caption

        result = generate_caption(
            {
                "event": "WiMLDS Pune Meetup",
                "description": "A community session on practical ML.",
            }
        )

        assert "caption" in result
        assert "WiMLDS Pune Meetup" in result["caption"]


class TestFacebookNode:
    @patch("wimlds.agents.facebook_node.build_facebook_post_url")
    @patch("wimlds.agents.facebook_node.post_to_facebook")
    def test_post_facebook_returns_result(self, mock_post, mock_build_url):
        from wimlds.agents.publishing.facebook_node import post_facebook

        mock_post.return_value = {"id": "fb_post_123"}
        mock_build_url.return_value = "https://www.facebook.com/fb_post_123"

        result = post_facebook(
            {
                "poster": "https://example.com/poster.png",
                "caption": "Join us this weekend! #ml #community #wimlds",
            }
        )

        assert result["facebook_posted"] is True
        assert "facebook_result" in result
        assert result["facebook_post_url"] == "https://www.facebook.com/fb_post_123"


class TestInstagramNode:
    @patch("wimlds.agents.instagram_node.get_instagram_permalink")
    @patch("wimlds.agents.instagram_node.publish_instagram")
    @patch("wimlds.agents.instagram_node.create_instagram_container")
    def test_post_instagram_returns_result(self, mock_container, mock_publish, mock_permalink):
        from wimlds.agents.publishing.instagram_node import post_instagram

        mock_container.return_value = "ig_container_123"
        mock_publish.return_value = {"id": "ig_post_123"}
        mock_permalink.return_value = "https://www.instagram.com/p/test123/"

        result = post_instagram(
            {
                "poster": "https://example.com/poster.png",
                "caption": "Join us this weekend! #ml #community #wimlds",
            }
        )

        assert result["instagram_posted"] is True
        assert "instagram_result" in result
        assert result["instagram_post_url"] == "https://www.instagram.com/p/test123/"


class TestSocialGraph:
    @patch("wimlds.graph.post_facebook")
    @patch("wimlds.graph.post_instagram")
    @patch("wimlds.graph.generate_caption")
    def test_build_graph_runs_all_nodes(self, mock_caption, mock_instagram, mock_facebook):
        from wimlds.graph import build_graph

        mock_caption.return_value = {"caption": "Test caption #ml #community #wimlds"}
        mock_instagram.return_value = {
            "instagram_posted": True,
            "instagram_result": {"id": "ig_post_123"},
            "instagram_post_url": "https://www.instagram.com/p/test123/",
        }
        mock_facebook.return_value = {
            "facebook_posted": True,
            "facebook_result": {"id": "fb_post_123"},
            "facebook_post_url": "https://www.facebook.com/fb_post_123",
        }

        graph = build_graph()
        result = graph.invoke(
            {
                "event": "Test Post by AI Agent",
                "description": "A test description",
                "poster": "https://example.com/poster.png",
            }
        )

        assert result["caption"] == "Test caption #ml #community #wimlds"
        assert result["instagram_posted"] is True
        assert result["facebook_posted"] is True
        assert result["instagram_post_url"] == "https://www.instagram.com/p/test123/"
        assert result["facebook_post_url"] == "https://www.facebook.com/fb_post_123"


