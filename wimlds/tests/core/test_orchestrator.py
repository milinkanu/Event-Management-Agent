"""
Unit tests for the Orchestrator and state machine.
"""
import pytest
from unittest.mock import patch
from wimlds.core.state_machine import WorkflowState, Stage
from wimlds.core.orchestrator import Orchestrator, AgentResult


# ── State Machine Tests ────────────────────────────────────────────────────────

class TestStateMachine:

    def test_initial_state(self):
        state = WorkflowState(event_id="1")
        assert state.current_stage == Stage.VALIDATE

    def test_valid_transition(self):
        state = WorkflowState(event_id="1")
        ok = state.transition(Stage.CREATE_EVENT)
        assert ok
        assert state.current_stage == Stage.CREATE_EVENT

    def test_invalid_transition_rejected(self):
        state = WorkflowState(event_id="1")
        ok = state.transition(Stage.POST_EVENT)   # Can't jump from VALIDATE
        assert not ok
        assert state.current_stage == Stage.VALIDATE

    def test_completed_stages_tracked(self):
        state = WorkflowState(event_id="1")
        state.transition(Stage.CREATE_EVENT)
        assert Stage.VALIDATE.value in state.completed_stages

    def test_halted_state(self):
        state = WorkflowState(event_id="1")
        state.transition(Stage.HALTED)
        assert state.can_resume()
        assert not state.is_terminal()

    def test_failed_is_terminal(self):
        state = WorkflowState(event_id="1")
        state.transition(Stage.FAILED)
        assert state.is_terminal()

    def test_completed_is_terminal(self):
        state = WorkflowState(event_id="1")
        # Fast-forward to completed
        state.current_stage = Stage.ANALYTICS
        state.transition(Stage.COMPLETED)
        assert state.is_terminal()


# ── Orchestrator Tests ─────────────────────────────────────────────────────────

class TestOrchestrator:

    def test_dry_run_init(self):
        orch = Orchestrator(dry_run=True)
        assert orch.dry_run is True

    @patch("wimlds.core.orchestrator.sheets_client")
    def test_validate_fails_with_missing_fields(self, mock_sheets):
        mock_sheets.get_event.return_value = {
            "event_title": "",  # Missing
            "event_status": "Upcoming",
        }
        orch = Orchestrator(dry_run=True)
        result = orch._stage_validate({"event_title": ""}, row_num=1)
        assert not result.success

    @patch("wimlds.core.orchestrator.sheets_client")
    def test_validate_passes_with_all_fields(self, mock_sheets):
        from wimlds.tests.fixtures.sample_event import SAMPLE_EVENT
        orch = Orchestrator(dry_run=True)
        result = orch._stage_validate(SAMPLE_EVENT, row_num=1)
        assert result.success

    def test_run_agent_unknown_raises(self):
        orch = Orchestrator(dry_run=True)
        with patch("wimlds.core.orchestrator.sheets_client") as mock:
            mock.get_event.return_value = {}
            result = orch.run_agent("1", agent_name="nonexistent_agent_xyz")
        assert not result.success

    @patch("wimlds.core.orchestrator.sheets_client")
    @patch("wimlds.agents.qr_agent.QRAgent.generate_qr")
    def test_qr_stage_writes_back(self, mock_qr, mock_sheets):
        mock_qr.return_value = AgentResult(
            success=True, data={"qr_drive_url": "https://drive.google.com/qr_test"}
        )
        mock_sheets.write_field.return_value = True
        orch = Orchestrator(dry_run=True)
        result = orch._stage_generate_qr({"meetup_event_url": "https://meetup.com/test"}, 1)
        assert result.success


# ── Validator Tests ────────────────────────────────────────────────────────────

class TestValidator:
    def test_missing_required_fields(self):
        from wimlds.core.validator import validate_event
        result = validate_event({})
        assert not result.valid
        assert len(result.missing_fields) > 0

    def test_all_required_fields_present(self):
        from wimlds.core.validator import validate_event
        from wimlds.tests.fixtures.sample_event import SAMPLE_EVENT
        result = validate_event(SAMPLE_EVENT)
        assert result.valid, f"Unexpected missing: {result.missing_fields}"





