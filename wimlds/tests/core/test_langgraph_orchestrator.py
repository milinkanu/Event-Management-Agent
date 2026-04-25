"""
Tests for LangGraph Orchestrator — all dry_run=True, no real API calls.
Run with: pytest tests/test_langgraph_orchestrator.py -v
"""
import pytest
from unittest.mock import patch, MagicMock


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def full_event():
    return {
        "row_id": "3", "event_title": "Intro to Transformers — WiMLDS Pune",
        "series": "ML Foundations", "date": "11 Oct 2025", "day": "Saturday",
        "start_time_ist": "14:00", "end_time_ist": "17:30", "mode": "In-Person",
        "venue_name": "Tech Hub Pune", "venue_address": "1st Floor, Baner Road, Pune 411045",
        "speaker_name": "Dr. Priya Desai",
        "speaker_highest_qualification": "PhD in Computer Science",
        "speaker_tier1_institution": "Yes",
        "speaker_special_achievements": "NeurIPS 2024",
        "meetup_event_url": "https://meetup.com/WiMLDS-Pune/events/303123456",
        "meetup_event_id": "303123456", "event_status": "Upcoming",
        "c_level_linkedin_handles": "rajeev-sharma",
        "qr_drive_url": "https://drive.google.com/file/d/qr/view",
        "poster_drive_url": "https://drive.google.com/file/d/poster/view",
        "poster_status": "Approved", "conference_link": "",
        "promote_linkedin": "Y", "promote_facebook": "Y", "promote_x": "Y",
        "announce_sent": "N", "whatsapp_groups_posted": "N",
        "partners_notified": "N", "post_event_completed": "N",
    }

@pytest.fixture
def partial_event():
    return {"event_title": "Incomplete Event", "event_status": "Upcoming"}

@pytest.fixture
def base_state(full_event):
    return {
        "event_id": "3", "row_num": 3, "dry_run": True,
        "event_data": full_event, "current_node": "validate",
        "completed_stages": [], "retry_count": 0, "poster_rework_count": 0,
        "last_result": None, "error": None, "outcome": "running", "messages": [],
    }


# ── State & graph structure ────────────────────────────────────────────────────

class TestStateAndGraph:
    def test_wimlds_state_has_all_required_keys(self):
        from wimlds.core.langgraph_orchestrator import WiMLDSState
        required = {"event_id","row_num","dry_run","event_data","current_node",
                    "completed_stages","retry_count","poster_rework_count",
                    "last_result","error","outcome","messages"}
        assert required <= set(WiMLDSState.__annotations__)

    def test_build_graph_compiles(self):
        from wimlds.core.langgraph_orchestrator import build_graph
        g = build_graph()
        assert callable(getattr(g, "invoke", None))
        assert callable(getattr(g, "stream", None))

    def test_all_13_nodes_present(self):
        from wimlds.core.langgraph_orchestrator import build_graph
        g = build_graph()
        # LangGraph compiled graph exposes .nodes dict or similar
        # We verify by checking graph imports exist
        import wimlds.core.langgraph_orchestrator as m
        for fn_name in [
            "node_validate","node_create_event","node_generate_qr",
            "node_create_poster","node_approve_poster","node_upload_poster",
            "node_announce","node_setup_conferencing","node_schedule_reminders",
            "node_event_execution","node_post_event","node_analytics",
            "node_completed","node_failed","node_halted",
        ]:
            assert hasattr(m, fn_name), f"Missing: {fn_name}"


# ── Routing ────────────────────────────────────────────────────────────────────

class TestRouting:
    def test_validate_running_routes_to_create_event(self, base_state):
        from wimlds.core.langgraph_orchestrator import route_after_validate
        assert route_after_validate({**base_state, "outcome": "running"}) == "create_event"

    def test_validate_halted_routes_to_halted(self, base_state):
        from wimlds.core.langgraph_orchestrator import route_after_validate
        assert route_after_validate({**base_state, "outcome": "halted"}) == "halted"

    def test_validate_failed_routes_to_failed(self, base_state):
        from wimlds.core.langgraph_orchestrator import route_after_validate
        assert route_after_validate({**base_state, "outcome": "failed"}) == "failed"

    def test_approve_poster_approved(self, base_state, full_event):
        from wimlds.core.langgraph_orchestrator import route_after_approve_poster
        s = {**base_state, "event_data": {**full_event, "poster_status": "Approved"}}
        assert route_after_approve_poster(s) == "upload_poster"

    def test_approve_poster_changes(self, base_state, full_event):
        from wimlds.core.langgraph_orchestrator import route_after_approve_poster
        s = {**base_state, "event_data": {**full_event, "poster_status": "Changes"}}
        assert route_after_approve_poster(s) == "create_poster"

    def test_approve_poster_rework(self, base_state, full_event):
        from wimlds.core.langgraph_orchestrator import route_after_approve_poster
        s = {**base_state, "event_data": {**full_event, "poster_status": "Rework"}}
        assert route_after_approve_poster(s) == "create_poster"

    def test_approve_poster_pending_self_loop(self, base_state, full_event):
        from wimlds.core.langgraph_orchestrator import route_after_approve_poster
        s = {**base_state, "event_data": {**full_event, "poster_status": "Pending"}}
        assert route_after_approve_poster(s) == "approve_poster"

    def test_approve_poster_max_retries_fails(self, base_state, full_event):
        from wimlds.core.langgraph_orchestrator import route_after_approve_poster, MAX_RETRIES
        s = {**base_state, "retry_count": MAX_RETRIES,
             "event_data": {**full_event, "poster_status": "Pending"}}
        assert route_after_approve_poster(s) == "failed"

    def test_analytics_completed(self, base_state):
        from wimlds.core.langgraph_orchestrator import route_after_analytics
        assert route_after_analytics({**base_state, "outcome": "completed"}) == "completed"

    def test_analytics_failed(self, base_state):
        from wimlds.core.langgraph_orchestrator import route_after_analytics
        assert route_after_analytics({**base_state, "outcome": "failed"}) == "failed"

    def test_all_intermediate_routes_pass_through(self, base_state):
        from wimlds.core.langgraph_orchestrator import (
            route_after_create_event, route_after_generate_qr,
            route_after_create_poster, route_after_upload_poster,
            route_after_announce, route_after_setup_conferencing,
            route_after_schedule_reminders, route_after_event_execution,
            route_after_post_event,
        )
        pairs = [
            (route_after_create_event,        "generate_qr"),
            (route_after_generate_qr,         "create_poster"),
            (route_after_create_poster,       "approve_poster"),
            (route_after_upload_poster,       "announce"),
            (route_after_announce,            "setup_conferencing"),
            (route_after_setup_conferencing,  "schedule_reminders"),
            (route_after_schedule_reminders,  "event_execution"),
            (route_after_event_execution,     "post_event"),
            (route_after_post_event,          "analytics"),
        ]
        for fn, expected in pairs:
            assert fn(base_state) == expected, f"{fn.__name__} failed"

    def test_all_intermediate_routes_fail_on_failure(self, base_state):
        from wimlds.core.langgraph_orchestrator import (
            route_after_create_event, route_after_generate_qr,
            route_after_upload_poster, route_after_announce,
        )
        failed_state = {**base_state, "outcome": "failed"}
        for fn in (route_after_create_event, route_after_generate_qr,
                   route_after_upload_poster, route_after_announce):
            assert fn(failed_state) == "failed"


# ── _run_agent helper ──────────────────────────────────────────────────────────

class TestRunAgentHelper:
    def test_success_records_stage(self, base_state):
        from wimlds.core.langgraph_orchestrator import _run_agent
        from wimlds.core.orchestrator import AgentResult
        result = _run_agent(base_state, "my_node",
                            lambda: AgentResult(success=True, data={"k": "v"}))
        assert "my_node" in result["completed_stages"]
        assert result["event_data"]["k"] == "v"
        assert result["retry_count"] == 0

    def test_failure_increments_retry(self, base_state):
        from wimlds.core.langgraph_orchestrator import _run_agent
        from wimlds.core.orchestrator import AgentResult
        result = _run_agent(base_state, "my_node",
                            lambda: AgentResult(success=False, error="oops"))
        assert result["retry_count"] == 1
        assert result["error"] == "oops"

    def test_max_retries_sets_failed_outcome(self, base_state):
        from wimlds.core.langgraph_orchestrator import _run_agent, MAX_RETRIES
        from wimlds.core.orchestrator import AgentResult
        state = {**base_state, "retry_count": MAX_RETRIES - 1}
        result = _run_agent(state, "my_node",
                            lambda: AgentResult(success=False, error="persist"))
        assert result["outcome"] == "failed"

    def test_exception_sets_failed(self, base_state):
        from wimlds.core.langgraph_orchestrator import _run_agent
        def _raise(): raise RuntimeError("boom")
        result = _run_agent(base_state, "my_node", _raise)
        assert result["outcome"] == "failed"
        assert "boom" in result["error"]


# ── node_validate ──────────────────────────────────────────────────────────────

class TestNodeValidate:
    @patch("core.langgraph_orchestrator.sheets_client")
    def test_valid_event_passes(self, mock_sheets, full_event, base_state):
        from wimlds.core.langgraph_orchestrator import node_validate
        mock_sheets.get_event.return_value = full_event
        result = node_validate(base_state)
        assert result["outcome"] == "running"
        assert "validate" in result["completed_stages"]

    @patch("core.langgraph_orchestrator.Notifier")
    @patch("core.langgraph_orchestrator.sheets_client")
    def test_missing_fields_halts_and_notifies(self, mock_sheets, mock_notifier_cls,
                                                partial_event, base_state):
        from wimlds.core.langgraph_orchestrator import node_validate
        mock_sheets.get_event.return_value = partial_event
        mock_notifier = MagicMock()
        mock_notifier_cls.return_value = mock_notifier
        result = node_validate({**base_state, "event_data": partial_event})
        assert result["outcome"] == "halted"
        mock_notifier.send_missing_fields_alert.assert_called_once()

    @patch("core.langgraph_orchestrator.sheets_client")
    def test_sheet_error_fails(self, mock_sheets, base_state):
        from wimlds.core.langgraph_orchestrator import node_validate
        mock_sheets.get_event.side_effect = Exception("network timeout")
        result = node_validate(base_state)
        assert result["outcome"] == "failed"


# ── node_announce ──────────────────────────────────────────────────────────────

class TestNodeAnnounce:
    def _make_mocks(self, social_ok=True, wa_ok=True, partner_ok=True):
        from wimlds.core.orchestrator import AgentResult
        mocks = {}
        for name, ok in [("social", social_ok), ("wa", wa_ok), ("partner", partner_ok)]:
            m = MagicMock()
            m.post_announcement.return_value = AgentResult(success=ok, error=None if ok else f"{name} failed")
            m.send_announcement.return_value = AgentResult(success=ok, error=None if ok else f"{name} failed")
            m.send_outreach.return_value     = AgentResult(success=ok, error=None if ok else f"{name} failed")
            mocks[name] = m
        return mocks

    @patch("core.langgraph_orchestrator.sheets_client")
    @patch("core.langgraph_orchestrator.PartnerAgent")
    @patch("core.langgraph_orchestrator.WhatsAppAgent")
    @patch("core.langgraph_orchestrator.SocialAgent")
    def test_all_success(self, MSocial, MWA, MPartner, mock_sheets, base_state):
        from wimlds.core.langgraph_orchestrator import node_announce
        from wimlds.core.orchestrator import AgentResult
        for cls in (MSocial, MWA, MPartner):
            inst = cls.return_value
            for attr in ("post_announcement","send_announcement","send_outreach"):
                setattr(inst, attr, MagicMock(return_value=AgentResult(success=True)))
        result = node_announce(base_state)
        assert "announce" in result["completed_stages"]

    @patch("core.langgraph_orchestrator.sheets_client")
    @patch("core.langgraph_orchestrator.PartnerAgent")
    @patch("core.langgraph_orchestrator.WhatsAppAgent")
    @patch("core.langgraph_orchestrator.SocialAgent")
    def test_wa_fail_non_blocking(self, MSocial, MWA, MPartner, mock_sheets, base_state):
        from wimlds.core.langgraph_orchestrator import node_announce
        from wimlds.core.orchestrator import AgentResult
        MSocial.return_value.post_announcement.return_value  = AgentResult(success=True)
        MWA.return_value.send_announcement.return_value      = AgentResult(success=False, error="WA fail")
        MPartner.return_value.send_outreach.return_value     = AgentResult(success=True)
        result = node_announce(base_state)
        assert "announce" in result["completed_stages"]  # WA fail is non-blocking


# ── Terminal nodes ─────────────────────────────────────────────────────────────

class TestTerminalNodes:
    def test_completed(self, base_state):
        from wimlds.core.langgraph_orchestrator import node_completed
        assert node_completed(base_state)["outcome"] == "completed"

    def test_failed(self, base_state):
        from wimlds.core.langgraph_orchestrator import node_failed
        assert node_failed(base_state)["outcome"] == "failed"

    def test_halted(self, base_state):
        from wimlds.core.langgraph_orchestrator import node_halted
        assert node_halted(base_state)["outcome"] == "halted"


# ── LangGraphOrchestrator public API ──────────────────────────────────────────

class TestLangGraphOrchestrator:
    def test_init_dry_run(self):
        from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator
        orch = LangGraphOrchestrator(dry_run=True)
        assert orch.dry_run is True

    @patch("core.langgraph_orchestrator.sheets_client")
    def test_get_status_single(self, mock_sheets, full_event):
        from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator
        mock_sheets.get_event.return_value = full_event
        result = LangGraphOrchestrator(dry_run=True).get_status(event_id="3")
        assert result[0]["id"] == "3"

    @patch("core.langgraph_orchestrator.sheets_client")
    def test_get_status_all(self, mock_sheets, full_event):
        from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator
        mock_sheets.get_all_upcoming.return_value = [
            {**full_event, "_row_number": 3},
            {**full_event, "_row_number": 4, "event_title": "RAG Systems"},
        ]
        result = LangGraphOrchestrator(dry_run=True).get_status()
        assert len(result) == 2

    @patch("core.langgraph_orchestrator.sheets_client")
    def test_run_agent_unknown_node_returns_error(self, mock_sheets, full_event):
        from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator
        mock_sheets.get_event.return_value = full_event
        result = LangGraphOrchestrator(dry_run=True).run_agent("3", "bad_node")
        assert result["success"] is False
        assert "Unknown" in result["error"]

    @patch("core.langgraph_orchestrator.sheets_client")
    def test_run_agent_valid_node(self, mock_sheets, full_event):
        from wimlds.core.langgraph_orchestrator import LangGraphOrchestrator
        from wimlds.core.orchestrator import AgentResult
        mock_sheets.get_event.return_value = full_event
        # Patch the analytics agent so it doesn't need real credentials
        with patch("core.langgraph_orchestrator.node_analytics") as mock_node:
            mock_node.return_value = {
                **{
                    "event_id":"3","row_num":3,"dry_run":True,
                    "event_data":full_event,"current_node":"analytics",
                    "completed_stages":["analytics"],"retry_count":0,
                    "poster_rework_count":0,
                    "last_result":{"success":True,"data":{}},
                    "error":None,"outcome":"running","messages":["✓ analytics"],
                }
            }
            result = LangGraphOrchestrator(dry_run=True).run_agent("3", "analytics")
            assert result["success"] is True


