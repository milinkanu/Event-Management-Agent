"""Unit tests for poster_design_improvement_agent component classes."""
import copy
import json
import pytest
from unittest.mock import MagicMock, patch

from wimlds.agents.publishing.poster_design_improvement_agent import (
    ImprovementInputValidator,
    PosterDesignImprovementAgent,
)
from wimlds.agents.publishing.poster_design_decision_agent import ValidationError

VALID_DESIGN = {
    "layout": "minimal",
    "colors": ["#4C1D95", "#EC4899", "#7C3AED"],
    "font_style": "sans-serif",
    "hierarchy": {
        "primary": "Event Title",
        "secondary": "Speaker Name",
        "tertiary": "Date and Venue",
    },
}

VALID_QA = {
    "issues": [
        {"type": "color_contrast", "description": "Low contrast on title", "severity": "high"}
    ],
    "verdict": "fail",
}


# ---------------------------------------------------------------------------
# ImprovementInputValidator
# ---------------------------------------------------------------------------

class TestImprovementInputValidator:
    def setup_method(self):
        self.val = ImprovementInputValidator()

    # --- design_decision validation ---

    def test_none_design_decision_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate(None, VALID_QA)

    def test_empty_dict_design_decision_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate({}, VALID_QA)

    def test_design_decision_missing_layout_raises_value_error(self):
        d = copy.deepcopy(VALID_DESIGN)
        del d["layout"]
        with pytest.raises(ValueError, match="layout"):
            self.val.validate(d, VALID_QA)

    def test_design_decision_missing_colors_raises_value_error(self):
        d = copy.deepcopy(VALID_DESIGN)
        del d["colors"]
        with pytest.raises(ValueError, match="colors"):
            self.val.validate(d, VALID_QA)

    def test_design_decision_missing_font_style_raises_value_error(self):
        d = copy.deepcopy(VALID_DESIGN)
        del d["font_style"]
        with pytest.raises(ValueError, match="font_style"):
            self.val.validate(d, VALID_QA)

    def test_design_decision_missing_hierarchy_raises_value_error(self):
        d = copy.deepcopy(VALID_DESIGN)
        del d["hierarchy"]
        with pytest.raises(ValueError, match="hierarchy"):
            self.val.validate(d, VALID_QA)

    # --- qa_result validation ---

    def test_none_qa_result_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate(VALID_DESIGN, None)

    def test_empty_dict_qa_result_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate(VALID_DESIGN, {})

    def test_qa_result_missing_issues_key_raises_value_error(self):
        with pytest.raises(ValueError, match="issues"):
            self.val.validate(VALID_DESIGN, {"verdict": "fail"})

    def test_qa_result_empty_issues_list_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate(VALID_DESIGN, {"issues": [], "verdict": "fail"})

    # --- valid inputs ---

    def test_valid_inputs_are_accepted(self):
        result = self.val.validate(VALID_DESIGN, VALID_QA)
        assert result == (VALID_DESIGN, VALID_QA)

    def test_valid_inputs_returned_unchanged(self):
        design = copy.deepcopy(VALID_DESIGN)
        qa = copy.deepcopy(VALID_QA)
        returned_design, returned_qa = self.val.validate(design, qa)
        assert returned_design == VALID_DESIGN
        assert returned_qa == VALID_QA

    # --- no mutation ---

    def test_inputs_not_mutated(self):
        design = copy.deepcopy(VALID_DESIGN)
        qa = copy.deepcopy(VALID_QA)
        original_design = copy.deepcopy(design)
        original_qa = copy.deepcopy(qa)
        self.val.validate(design, qa)
        assert design == original_design
        assert qa == original_qa


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_LLM_RESPONSE = {
    "layout": "minimal",
    "colors": ["#111111", "#222222", "#333333"],
    "font_style": "sans-serif",
    "hierarchy": {
        "primary": "Event Title",
        "secondary": "Speaker Name",
        "tertiary": "Date and Venue",
    },
}

VALID_QA_FAIL = {
    "issues": [
        {"type": "color_contrast", "description": "Low contrast on title", "severity": "high"}
    ],
    "verdict": "fail",
}

VALID_QA_PASS = {
    "issues": [],
    "verdict": "pass",
}


# ---------------------------------------------------------------------------
# PosterDesignImprovementAgent
# ---------------------------------------------------------------------------

class TestPosterDesignImprovementAgent:

    def _make_agent(self, max_retries=2):
        return PosterDesignImprovementAgent(dry_run=False, max_retries=max_retries)

    # --- success path ---

    def test_success_path_returns_agent_result_with_all_four_fields(self):
        agent = self._make_agent()
        with patch.object(agent._llm, "generate_json", return_value=VALID_LLM_RESPONSE):
            result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)
        assert result.success is True
        improved = result.data["improved_design"]
        assert set(improved.keys()) == {"layout", "colors", "font_style", "hierarchy"}

    # --- verdict == "pass" short-circuit ---

    def test_verdict_pass_returns_original_design_without_calling_llm(self):
        agent = self._make_agent()
        mock_generate = MagicMock()
        agent._llm.generate_json = mock_generate

        result = agent.improve(VALID_DESIGN, VALID_QA_PASS)

        mock_generate.assert_not_called()
        assert result.success is True
        assert result.data["improved_design"] == VALID_DESIGN

    # --- input validation failures ---

    def test_none_design_decision_returns_failure_agent_result(self):
        agent = self._make_agent()
        result = agent.improve(None, VALID_QA_FAIL)
        assert result.success is False
        assert result.error

    def test_empty_design_decision_returns_failure_agent_result(self):
        agent = self._make_agent()
        result = agent.improve({}, VALID_QA_FAIL)
        assert result.success is False
        assert result.error

    def test_none_qa_result_returns_failure_agent_result(self):
        agent = self._make_agent()
        result = agent.improve(VALID_DESIGN, None)
        assert result.success is False
        assert result.error

    def test_empty_qa_result_returns_failure_agent_result(self):
        agent = self._make_agent()
        result = agent.improve(VALID_DESIGN, {})
        assert result.success is False
        assert result.error

    # --- retry on ValidationError ---

    def test_validation_error_triggers_retry_with_correction_prompt(self):
        agent = self._make_agent(max_retries=2)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValidationError("bad layout")
            return VALID_LLM_RESPONSE

        with patch.object(agent._llm, "generate_json", side_effect=side_effect):
            result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)

        assert call_count == 2
        assert result.success is True

    # --- retry on JSONDecodeError ---

    def test_json_decode_error_triggers_retry(self):
        agent = self._make_agent(max_retries=2)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise json.JSONDecodeError("Expecting value", "", 0)
            return VALID_LLM_RESPONSE

        with patch.object(agent._llm, "generate_json", side_effect=side_effect):
            result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)

        assert call_count == 2
        assert result.success is True

    # --- exhausted retries ---

    def test_exhausted_retries_returns_failure_agent_result(self):
        agent = self._make_agent(max_retries=2)

        with patch.object(
            agent._llm, "generate_json",
            side_effect=ValidationError("always bad"),
        ):
            result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)

        assert result.success is False
        assert result.error

    # --- API-level error: no retry ---

    def test_api_level_error_returns_failure_without_retry(self):
        agent = self._make_agent(max_retries=3)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("network error")

        with patch.object(agent._llm, "generate_json", side_effect=side_effect):
            result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)

        assert call_count == 1  # no retry
        assert result.success is False
        assert result.error

    # --- improve() never raises ---

    def test_improve_never_raises(self):
        agent = self._make_agent()
        with patch.object(agent._llm, "generate_json", side_effect=Exception("boom")):
            try:
                result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)
            except Exception:
                pytest.fail("improve() raised an exception")
        assert result.success is False

    # --- no mutation ---

    def test_design_decision_not_mutated(self):
        agent = self._make_agent()
        original = copy.deepcopy(VALID_DESIGN)
        with patch.object(agent._llm, "generate_json", return_value=VALID_LLM_RESPONSE):
            agent.improve(VALID_DESIGN, VALID_QA_FAIL)
        assert VALID_DESIGN == original

    def test_qa_result_not_mutated(self):
        agent = self._make_agent()
        qa = copy.deepcopy(VALID_QA_FAIL)
        original_qa = copy.deepcopy(qa)
        with patch.object(agent._llm, "generate_json", return_value=VALID_LLM_RESPONSE):
            agent.improve(VALID_DESIGN, qa)
        assert qa == original_qa

    # --- dry_run ---

    def test_dry_run_returns_stub_without_calling_llm(self):
        agent = PosterDesignImprovementAgent(dry_run=True)
        mock_generate = MagicMock()
        agent._llm.generate_json = mock_generate

        result = agent.improve(VALID_DESIGN, VALID_QA_FAIL)

        mock_generate.assert_not_called()
        assert result.success is True
        assert result.data["improved_design"] == VALID_DESIGN

    # --- run() interface ---

    def test_run_reads_from_state_keys(self):
        agent = self._make_agent()
        state = {
            "design_decision": VALID_DESIGN,
            "qa_result": VALID_QA_FAIL,
        }
        with patch.object(agent._llm, "generate_json", return_value=VALID_LLM_RESPONSE):
            agent.run(state)
        # If we got here without KeyError, the correct keys were read

    def test_run_writes_design_decision_on_success(self):
        agent = self._make_agent()
        state = {
            "design_decision": VALID_DESIGN,
            "qa_result": VALID_QA_FAIL,
        }
        with patch.object(agent._llm, "generate_json", return_value=VALID_LLM_RESPONSE):
            updated = agent.run(state)
        assert updated["design_decision"] == VALID_LLM_RESPONSE

    def test_run_does_not_overwrite_design_decision_on_failure(self):
        agent = self._make_agent(max_retries=1)
        original_design = copy.deepcopy(VALID_DESIGN)
        state = {
            "design_decision": copy.deepcopy(VALID_DESIGN),
            "qa_result": VALID_QA_FAIL,
        }
        with patch.object(
            agent._llm, "generate_json",
            side_effect=ValidationError("always bad"),
        ):
            updated = agent.run(state)
        assert updated["design_decision"] == original_design


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    """Validates: Requirements 10.1, 10.2"""

    def test_design_decision_round_trip_via_improvement_output_validator(self):
        """DesignDecision → to_dict() → ImprovementOutputValidator.validate() returns equal DesignDecision."""
        from wimlds.agents.publishing.poster_design_decision_agent import DesignDecision
        from wimlds.agents.publishing.poster_design_improvement_agent import ImprovementOutputValidator

        original = DesignDecision(
            layout="modern",
            colors=["#1A2B3C", "#FFFFFF", "#EC4899"],
            font_style="serif",
            hierarchy={
                "primary": "WiMLDS Workshop",
                "secondary": "Dr. Jane Smith",
                "tertiary": "15 June 2025, Cape Town",
            },
        )

        raw = original.to_dict()
        validator = ImprovementOutputValidator()
        restored = validator.validate(raw)

        assert restored == original
