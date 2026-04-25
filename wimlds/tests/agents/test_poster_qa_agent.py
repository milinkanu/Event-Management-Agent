"""Unit tests for poster_qa_agent data models: QAIssue and QAResult."""
import pytest

from wimlds.agents.publishing.poster_qa_agent import (
    QAIssue,
    QAResult,
    ValidationError,
)


# ---------------------------------------------------------------------------
# QAIssue
# ---------------------------------------------------------------------------

class TestQAIssue:
    def _make(self, type="text_readability", description="Font too small", severity="high"):
        return QAIssue(type=type, description=description, severity=severity)

    def test_to_dict_returns_exactly_three_keys(self):
        issue = self._make()
        result = issue.to_dict()
        assert set(result.keys()) == {"type", "description", "severity"}

    def test_to_dict_values_round_trip(self):
        issue = self._make(type="alignment", description="Off-center logo", severity="low")
        result = issue.to_dict()
        assert result["type"] == "alignment"
        assert result["description"] == "Off-center logo"
        assert result["severity"] == "low"

    def test_to_dict_all_valid_types(self):
        for t in ("text_readability", "alignment", "color_contrast", "missing_information", "unclear_information"):
            issue = QAIssue(type=t, description="desc", severity="low")
            assert issue.to_dict()["type"] == t

    def test_to_dict_all_valid_severities(self):
        for s in ("low", "medium", "high"):
            issue = QAIssue(type="alignment", description="desc", severity=s)
            assert issue.to_dict()["severity"] == s


# ---------------------------------------------------------------------------
# QAResult
# ---------------------------------------------------------------------------

class TestQAResult:
    def test_to_dict_returns_exactly_two_keys(self):
        result = QAResult()
        d = result.to_dict()
        assert set(d.keys()) == {"issues", "verdict"}

    def test_default_empty_issues_and_pass_verdict(self):
        result = QAResult()
        d = result.to_dict()
        assert d["issues"] == []
        assert d["verdict"] == "pass"

    def test_to_dict_with_issues(self):
        issue = QAIssue(type="color_contrast", description="Low contrast", severity="medium")
        result = QAResult(issues=[issue], verdict="fail")
        d = result.to_dict()
        assert d["verdict"] == "fail"
        assert len(d["issues"]) == 1
        assert d["issues"][0] == {"type": "color_contrast", "description": "Low contrast", "severity": "medium"}

    def test_to_dict_issues_are_dicts_with_correct_keys(self):
        issues = [
            QAIssue(type="alignment", description="Misaligned", severity="low"),
            QAIssue(type="missing_information", description="No date", severity="high"),
        ]
        result = QAResult(issues=issues, verdict="fail")
        d = result.to_dict()
        for item in d["issues"]:
            assert set(item.keys()) == {"type", "description", "severity"}

    def test_to_dict_field_values_round_trip(self):
        issue = QAIssue(type="unclear_information", description="Blurry text", severity="medium")
        result = QAResult(issues=[issue], verdict="fail")
        d = result.to_dict()
        assert d["issues"][0]["type"] == "unclear_information"
        assert d["issues"][0]["description"] == "Blurry text"
        assert d["issues"][0]["severity"] == "medium"
        assert d["verdict"] == "fail"

    def test_to_dict_empty_issues_list(self):
        result = QAResult(issues=[], verdict="pass")
        d = result.to_dict()
        assert d == {"issues": [], "verdict": "pass"}

    def test_to_dict_multiple_issues(self):
        issues = [QAIssue(type="alignment", description=f"Issue {i}", severity="low") for i in range(3)]
        result = QAResult(issues=issues, verdict="pass")
        d = result.to_dict()
        assert len(d["issues"]) == 3


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------

class TestValidationError:
    def test_is_exception_subclass(self):
        assert issubclass(ValidationError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(ValidationError):
            raise ValidationError("schema violation")

    def test_has_docstring(self):
        assert ValidationError.__doc__ is not None
        assert len(ValidationError.__doc__.strip()) > 0


from wimlds.agents.publishing.poster_qa_agent import ImageInputValidator


# ---------------------------------------------------------------------------
# ImageInputValidator
# ---------------------------------------------------------------------------

class TestImageInputValidator:
    def _validator(self):
        return ImageInputValidator()

    # --- None / empty inputs ---

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            self._validator().validate(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            self._validator().validate("")

    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            self._validator().validate(b"")

    # --- Valid bytes ---

    def test_valid_bytes_returns_same_bytes(self):
        data = b"\x89PNG\r\n\x1a\n"
        result = self._validator().validate(data)
        assert result == data

    # --- Non-existent file path ---

    def test_nonexistent_path_raises_value_error_with_path(self):
        path = "/nonexistent/path/poster.png"
        with pytest.raises(ValueError, match="poster.png"):
            self._validator().validate(path)

    # --- Unsupported extensions ---

    def test_gif_extension_raises_value_error(self):
        with pytest.raises(ValueError):
            self._validator().validate("/some/file.gif")

    def test_bmp_extension_raises_value_error(self):
        with pytest.raises(ValueError):
            self._validator().validate("/some/file.bmp")

    # --- Supported extensions (case-insensitive) ---

    def test_png_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.png"
        f.write_bytes(b"fake png data")
        result = self._validator().validate(str(f))
        assert result == b"fake png data"

    def test_jpg_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.jpg"
        f.write_bytes(b"fake jpg data")
        result = self._validator().validate(str(f))
        assert result == b"fake jpg data"

    def test_jpeg_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.jpeg"
        f.write_bytes(b"fake jpeg data")
        result = self._validator().validate(str(f))
        assert result == b"fake jpeg data"

    def test_uppercase_PNG_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.PNG"
        f.write_bytes(b"fake PNG data")
        result = self._validator().validate(str(f))
        assert result == b"fake PNG data"

    def test_uppercase_JPG_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.JPG"
        f.write_bytes(b"fake JPG data")
        result = self._validator().validate(str(f))
        assert result == b"fake JPG data"

    def test_uppercase_JPEG_extension_accepted(self, tmp_path):
        f = tmp_path / "poster.JPEG"
        f.write_bytes(b"fake JPEG data")
        result = self._validator().validate(str(f))
        assert result == b"fake JPEG data"

    # --- Valid file path returns file bytes ---

    def test_valid_file_path_returns_file_bytes(self, tmp_path):
        content = b"\x00\x01\x02\x03"
        f = tmp_path / "image.png"
        f.write_bytes(content)
        result = self._validator().validate(str(f))
        assert result == content

    # --- Input not mutated ---

    def test_bytes_input_not_mutated(self):
        original = bytearray(b"some image bytes")
        snapshot = bytes(original)
        # Pass as bytes (immutable), just confirm the value is unchanged
        data = bytes(original)
        self._validator().validate(data)
        assert data == snapshot

    def test_string_input_not_mutated(self, tmp_path):
        f = tmp_path / "poster.png"
        f.write_bytes(b"data")
        path = str(f)
        original_path = path
        self._validator().validate(path)
        assert path == original_path


from wimlds.agents.publishing.poster_qa_agent import QAPromptBuilder
import base64


# ---------------------------------------------------------------------------
# QAPromptBuilder
# ---------------------------------------------------------------------------

class TestQAPromptBuilder:
    def _builder(self):
        return QAPromptBuilder()

    def _sample_bytes(self):
        return b"\x89PNG\r\n\x1a\nfake image data"

    def _prompt(self):
        return self._builder().build(self._sample_bytes())

    def test_all_five_issue_types_in_prompt(self):
        prompt = self._prompt()
        for t in ("text_readability", "alignment", "color_contrast", "missing_information", "unclear_information"):
            assert t in prompt, f"Expected issue type '{t}' in prompt"

    def test_all_three_severity_values_in_prompt(self):
        prompt = self._prompt()
        for s in ("low", "medium", "high"):
            assert s in prompt, f"Expected severity '{s}' in prompt"

    def test_both_verdict_values_in_prompt(self):
        prompt = self._prompt()
        assert "pass" in prompt
        assert "fail" in prompt

    def test_verdict_determination_rules_in_prompt(self):
        prompt = self._prompt()
        # Rules: fail if high or medium; pass if all low or empty
        assert "high" in prompt
        assert "medium" in prompt
        assert "fail" in prompt
        # Explicit rule language
        assert "fail" in prompt.lower()
        assert "medium" in prompt.lower()

    def test_evaluation_criteria_text_readability_in_prompt(self):
        prompt = self._prompt()
        assert "text readability" in prompt.lower() or "text_readability" in prompt.lower()
        assert "font size" in prompt.lower() or "legibility" in prompt.lower()

    def test_evaluation_criteria_alignment_in_prompt(self):
        prompt = self._prompt()
        assert "alignment" in prompt.lower()
        assert "visual balance" in prompt.lower() or "grid" in prompt.lower()

    def test_evaluation_criteria_color_contrast_in_prompt(self):
        prompt = self._prompt()
        assert "color contrast" in prompt.lower() or "color_contrast" in prompt.lower()
        assert "wcag" in prompt.lower() or "foreground" in prompt.lower()

    def test_evaluation_criteria_information_completeness_in_prompt(self):
        prompt = self._prompt()
        assert "event name" in prompt.lower() or "information completeness" in prompt.lower()
        assert "date" in prompt.lower()
        assert "venue" in prompt.lower()
        assert "speaker" in prompt.lower()

    def test_pure_json_instruction_in_prompt(self):
        prompt = self._prompt()
        assert "pure json" in prompt.lower() or "no markdown" in prompt.lower()
        assert "no explanation" in prompt.lower() or "no additional text" in prompt.lower()

    def test_base64_encoded_image_embedded_in_prompt(self):
        image_bytes = self._sample_bytes()
        prompt = self._builder().build(image_bytes)
        expected_b64 = base64.b64encode(image_bytes).decode("utf-8")
        assert expected_b64 in prompt

    def test_build_with_correction_appends_error_hint(self):
        image_bytes = self._sample_bytes()
        error_msg = "Missing required key: verdict"
        prompt = self._builder().build_with_correction(image_bytes, error_msg)
        assert error_msg in prompt

    def test_build_with_correction_contains_base_prompt_content(self):
        image_bytes = self._sample_bytes()
        base_prompt = self._builder().build(image_bytes)
        correction_prompt = self._builder().build_with_correction(image_bytes, "some error")
        # The correction prompt should contain all the base content
        assert base64.b64encode(image_bytes).decode("utf-8") in correction_prompt
        assert "text_readability" in correction_prompt

    def test_build_with_correction_longer_than_base(self):
        image_bytes = self._sample_bytes()
        base_prompt = self._builder().build(image_bytes)
        correction_prompt = self._builder().build_with_correction(image_bytes, "some error")
        assert len(correction_prompt) > len(base_prompt)


from wimlds.agents.publishing.poster_qa_agent import QAOutputValidator


# ---------------------------------------------------------------------------
# QAOutputValidator
# ---------------------------------------------------------------------------

class TestQAOutputValidator:
    def _validator(self):
        return QAOutputValidator()

    def _valid_raw(self, issues=None, verdict="pass"):
        return {
            "issues": issues if issues is not None else [],
            "verdict": verdict,
        }

    def _valid_issue(self, type="text_readability", description="Font too small", severity="high"):
        return {"type": type, "description": description, "severity": severity}

    # --- Valid inputs ---

    def test_valid_empty_issues_pass_verdict_returns_qa_result(self):
        raw = self._valid_raw(issues=[], verdict="pass")
        result = self._validator().validate(raw)
        assert isinstance(result, QAResult)
        assert result.verdict == "pass"
        assert result.issues == []

    def test_valid_one_issue_each_type_and_severity_accepted(self):
        types = ["text_readability", "alignment", "color_contrast", "missing_information", "unclear_information"]
        severities = ["low", "medium", "high"]
        for t in types:
            for s in severities:
                raw = self._valid_raw(
                    issues=[self._valid_issue(type=t, severity=s)],
                    verdict="fail",
                )
                result = self._validator().validate(raw)
                assert isinstance(result, QAResult)
                assert result.issues[0].type == t
                assert result.issues[0].severity == s

    # --- Non-dict inputs ---

    def test_none_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate(None)

    def test_string_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate("not a dict")

    def test_list_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate([{"issues": [], "verdict": "pass"}])

    def test_int_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate(42)

    # --- Missing required keys ---

    def test_missing_issues_key_raises_validation_error(self):
        with pytest.raises(ValidationError, match="issues"):
            self._validator().validate({"verdict": "pass"})

    def test_missing_verdict_key_raises_validation_error(self):
        with pytest.raises(ValidationError, match="verdict"):
            self._validator().validate({"issues": []})

    # --- Invalid verdict ---

    def test_invalid_verdict_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate(self._valid_raw(verdict="maybe"))

    def test_empty_verdict_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate(self._valid_raw(verdict=""))

    # --- Non-list issues ---

    def test_issues_as_string_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate({"issues": "not a list", "verdict": "pass"})

    def test_issues_as_dict_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self._validator().validate({"issues": {}, "verdict": "pass"})

    # --- Issue missing required keys ---

    def test_issue_missing_type_raises_validation_error(self):
        issue = {"description": "desc", "severity": "low"}
        with pytest.raises(ValidationError, match="type"):
            self._validator().validate(self._valid_raw(issues=[issue]))

    def test_issue_missing_description_raises_validation_error(self):
        issue = {"type": "alignment", "severity": "low"}
        with pytest.raises(ValidationError, match="description"):
            self._validator().validate(self._valid_raw(issues=[issue]))

    def test_issue_missing_severity_raises_validation_error(self):
        issue = {"type": "alignment", "description": "desc"}
        with pytest.raises(ValidationError, match="severity"):
            self._validator().validate(self._valid_raw(issues=[issue]))

    # --- Invalid enum values ---

    def test_invalid_issue_type_raises_validation_error(self):
        issue = self._valid_issue(type="unknown_type")
        with pytest.raises(ValidationError):
            self._validator().validate(self._valid_raw(issues=[issue]))

    def test_invalid_issue_severity_raises_validation_error(self):
        issue = self._valid_issue(severity="critical")
        with pytest.raises(ValidationError):
            self._validator().validate(self._valid_raw(issues=[issue]))

    # --- Normalization ---

    def test_uppercase_verdict_normalized_and_accepted(self):
        raw = self._valid_raw(verdict="PASS")
        result = self._validator().validate(raw)
        assert result.verdict == "pass"

    def test_mixed_case_verdict_normalized_and_accepted(self):
        raw = self._valid_raw(verdict="Fail")
        result = self._validator().validate(raw)
        assert result.verdict == "fail"

    def test_uppercase_issue_type_normalized_and_accepted(self):
        issue = self._valid_issue(type="ALIGNMENT", severity="low")
        raw = self._valid_raw(issues=[issue], verdict="pass")
        result = self._validator().validate(raw)
        assert result.issues[0].type == "alignment"

    def test_uppercase_issue_severity_normalized_and_accepted(self):
        issue = self._valid_issue(type="alignment", severity="HIGH")
        raw = self._valid_raw(issues=[issue], verdict="fail")
        result = self._validator().validate(raw)
        assert result.issues[0].severity == "high"

    def test_mixed_case_all_enum_fields_normalized_and_accepted(self):
        issue = {"type": "Color_Contrast", "description": "Low contrast", "severity": "Medium"}
        raw = {"issues": [issue], "verdict": "FAIL"}
        result = self._validator().validate(raw)
        assert result.verdict == "fail"
        assert result.issues[0].type == "color_contrast"
        assert result.issues[0].severity == "medium"

    # --- Input not mutated ---

    def test_input_dict_not_mutated_on_success(self):
        issue = {"type": "ALIGNMENT", "description": "Off-center", "severity": "LOW"}
        raw = {"issues": [issue], "verdict": "PASS"}
        import copy
        original = copy.deepcopy(raw)
        self._validator().validate(raw)
        assert raw == original

    def test_input_dict_not_mutated_on_failure(self):
        raw = {"issues": "not a list", "verdict": "pass"}
        import copy
        original = copy.deepcopy(raw)
        with pytest.raises(ValidationError):
            self._validator().validate(raw)
        assert raw == original


from unittest.mock import MagicMock, patch
import json as _json

from wimlds.agents.publishing.poster_qa_agent import PosterQAAgent
from wimlds.core.result import AgentResult


# ---------------------------------------------------------------------------
# PosterQAAgent.evaluate()
# ---------------------------------------------------------------------------

class TestPosterQAAgentEvaluate:
    """Unit tests for PosterQAAgent.evaluate()."""

    _VALID_LLM_RESPONSE = {
        "issues": [
            {"type": "alignment", "description": "Logo is off-center", "severity": "low"}
        ],
        "verdict": "pass",
    }

    def _make_agent(self, dry_run=False, max_retries=2):
        agent = PosterQAAgent.__new__(PosterQAAgent)
        agent.dry_run = dry_run
        agent.max_retries = max_retries
        agent._input_validator = MagicMock()
        agent._prompt_builder = MagicMock()
        agent._output_validator = MagicMock()
        agent._llm = MagicMock()
        return agent

    # --- Success path ---

    def test_success_path_returns_agent_result_with_issues_and_verdict(self, tmp_path):
        f = tmp_path / "poster.png"
        f.write_bytes(b"fake png")
        agent = self._make_agent()
        agent._input_validator.validate.return_value = b"fake png"
        agent._prompt_builder.build.return_value = "prompt"
        agent._llm.generate_json.return_value = self._VALID_LLM_RESPONSE
        agent._output_validator.validate.return_value = QAResult(
            issues=[QAIssue(type="alignment", description="Off-center", severity="low")],
            verdict="pass",
        )

        result = agent.evaluate(str(f))

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "qa_result" in result.data
        assert "issues" in result.data["qa_result"]
        assert "verdict" in result.data["qa_result"]

    # --- Invalid inputs ---

    def test_none_input_returns_failure_agent_result(self):
        agent = self._make_agent()
        agent._input_validator.validate.side_effect = ValueError("poster_image must not be None")

        result = agent.evaluate(None)

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.error

    def test_empty_string_input_returns_failure_agent_result(self):
        agent = self._make_agent()
        agent._input_validator.validate.side_effect = ValueError("poster_image must not be an empty string")

        result = agent.evaluate("")

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.error

    def test_nonexistent_file_path_returns_failure_agent_result(self):
        agent = self._make_agent()
        agent._input_validator.validate.side_effect = ValueError("File not found: /no/such/file.png")

        result = agent.evaluate("/no/such/file.png")

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.error

    # --- Retry on ValidationError ---

    def test_validation_error_triggers_retry_with_correction_prompt(self):
        agent = self._make_agent(max_retries=2)
        agent._input_validator.validate.return_value = b"img"
        agent._prompt_builder.build.return_value = "base_prompt"
        agent._prompt_builder.build_with_correction.return_value = "correction_prompt"

        # First call raises ValidationError, second succeeds
        agent._llm.generate_json.side_effect = [
            {"issues": [], "verdict": "pass"},  # raw dict returned both times
            {"issues": [], "verdict": "pass"},
        ]
        agent._output_validator.validate.side_effect = [
            ValidationError("missing key"),
            QAResult(issues=[], verdict="pass"),
        ]

        result = agent.evaluate(b"img")

        assert result.success is True
        agent._prompt_builder.build_with_correction.assert_called_once()

    # --- Retry on JSONDecodeError ---

    def test_json_decode_error_triggers_retry(self):
        agent = self._make_agent(max_retries=2)
        agent._input_validator.validate.return_value = b"img"
        agent._prompt_builder.build.return_value = "prompt"
        agent._prompt_builder.build_with_correction.return_value = "correction_prompt"

        # First call raises JSONDecodeError, second succeeds
        agent._llm.generate_json.side_effect = [
            _json.JSONDecodeError("Expecting value", "", 0),
            {"issues": [], "verdict": "pass"},
        ]
        agent._output_validator.validate.return_value = QAResult(issues=[], verdict="pass")

        result = agent.evaluate(b"img")

        assert result.success is True
        assert agent._llm.generate_json.call_count == 2

    # --- Exhausted retries ---

    def test_exhausted_retries_returns_failure_with_non_empty_error(self):
        agent = self._make_agent(max_retries=2)
        agent._input_validator.validate.return_value = b"img"
        agent._prompt_builder.build.return_value = "prompt"
        agent._prompt_builder.build_with_correction.return_value = "correction_prompt"
        agent._llm.generate_json.return_value = {"issues": [], "verdict": "pass"}
        agent._output_validator.validate.side_effect = ValidationError("bad schema")

        result = agent.evaluate(b"img")

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.error  # non-empty

    # --- API-level exception ---

    def test_api_level_exception_returns_failure_without_retry(self):
        agent = self._make_agent(max_retries=3)
        agent._input_validator.validate.return_value = b"img"
        agent._prompt_builder.build.return_value = "prompt"
        agent._llm.generate_json.side_effect = RuntimeError("API rate limit exceeded")

        result = agent.evaluate(b"img")

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert "rate limit" in result.error.lower() or result.error
        # Should not retry — only one call made
        assert agent._llm.generate_json.call_count == 1

    # --- Never raises ---

    def test_evaluate_never_raises_on_none(self):
        agent = self._make_agent()
        agent._input_validator.validate.side_effect = ValueError("none input")
        # Should not raise
        result = agent.evaluate(None)
        assert isinstance(result, AgentResult)

    def test_evaluate_never_raises_on_unexpected_exception(self):
        agent = self._make_agent()
        agent._input_validator.validate.side_effect = Exception("totally unexpected")
        result = agent.evaluate(b"img")
        assert isinstance(result, AgentResult)
        assert result.success is False

    # --- poster_image not mutated ---

    def test_poster_image_bytes_not_mutated(self):
        agent = self._make_agent()
        original = b"some image bytes"
        snapshot = bytes(original)
        agent._input_validator.validate.side_effect = ValueError("fail")
        agent.evaluate(original)
        assert original == snapshot

    def test_poster_image_string_not_mutated(self):
        agent = self._make_agent()
        path = "/some/path/poster.png"
        snapshot = str(path)
        agent._input_validator.validate.side_effect = ValueError("fail")
        agent.evaluate(path)
        assert path == snapshot

    # --- dry_run mode ---

    def test_dry_run_returns_stub_result_without_calling_llm(self):
        agent = self._make_agent(dry_run=True)

        result = agent.evaluate(b"any image bytes")

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.data["qa_result"] == {"issues": [], "verdict": "pass"}
        agent._llm.generate_json.assert_not_called()

    def test_dry_run_with_invalid_input_still_returns_stub(self):
        """dry_run bypasses input validation entirely."""
        agent = self._make_agent(dry_run=True)

        result = agent.evaluate(None)

        assert result.success is True
        assert result.data["qa_result"]["verdict"] == "pass"
        agent._llm.generate_json.assert_not_called()


# ---------------------------------------------------------------------------
# PosterQAAgent.run()
# ---------------------------------------------------------------------------

class TestPosterQAAgentRun:
    """Unit tests for PosterQAAgent.run() LangGraph node interface."""

    def _make_agent(self):
        agent = PosterQAAgent.__new__(PosterQAAgent)
        agent.dry_run = False
        agent.max_retries = 2
        agent._input_validator = MagicMock()
        agent._prompt_builder = MagicMock()
        agent._output_validator = MagicMock()
        agent._llm = MagicMock()
        return agent

    def test_run_reads_from_poster_local_path(self):
        """run() passes state["_poster_local_path"] to evaluate()."""
        agent = self._make_agent()
        agent.evaluate = MagicMock(return_value=AgentResult(
            success=True,
            data={"qa_result": {"issues": [], "verdict": "pass"}},
        ))
        state = {"_poster_local_path": "/tmp/poster.png"}
        agent.run(state)
        agent.evaluate.assert_called_once_with("/tmp/poster.png")

    def test_run_writes_qa_result_on_success(self):
        """run() writes state["qa_result"] when evaluate() succeeds."""
        agent = self._make_agent()
        qa_result = {"issues": [], "verdict": "pass"}
        agent.evaluate = MagicMock(return_value=AgentResult(
            success=True,
            data={"qa_result": qa_result},
        ))
        state = {"_poster_local_path": "/tmp/poster.png"}
        updated = agent.run(state)
        assert "qa_result" in updated
        assert updated["qa_result"] == qa_result

    def test_run_does_not_write_qa_result_on_failure(self):
        """run() does not write state["qa_result"] when evaluate() fails."""
        agent = self._make_agent()
        agent.evaluate = MagicMock(return_value=AgentResult(
            success=False,
            error="LLM error",
        ))
        state = {"_poster_local_path": "/tmp/poster.png"}
        updated = agent.run(state)
        assert "qa_result" not in updated

    def test_run_returns_updated_state_dict(self):
        """run() returns a dict that includes all original state keys plus qa_result."""
        agent = self._make_agent()
        qa_result = {"issues": [{"type": "alignment", "description": "Off-center", "severity": "low"}], "verdict": "pass"}
        agent.evaluate = MagicMock(return_value=AgentResult(
            success=True,
            data={"qa_result": qa_result},
        ))
        state = {"_poster_local_path": "/tmp/poster.png", "event_name": "WiMLDS Meetup"}
        updated = agent.run(state)
        assert isinstance(updated, dict)
        assert updated["event_name"] == "WiMLDS Meetup"
        assert updated["_poster_local_path"] == "/tmp/poster.png"
        assert updated["qa_result"] == qa_result


# ---------------------------------------------------------------------------
# QAResult Serialization Round-Trip (Task 8.1)
# ---------------------------------------------------------------------------

class TestQAResultSerializationRoundTrip:
    """
    Unit tests for QAResult.to_dict() covering all field names, empty issues,
    and multi-issue lists, plus serialization round-trip via QAOutputValidator.
    """

    # --- Requirement 9.3: to_dict() returns exactly {"issues", "verdict"} ---

    def test_to_dict_returns_exactly_issues_and_verdict_keys(self):
        """to_dict() top-level keys are exactly {"issues", "verdict"} (Req 9.3)."""
        result = QAResult()
        d = result.to_dict()
        assert set(d.keys()) == {"issues", "verdict"}

    def test_to_dict_no_extra_keys_with_issues(self):
        """to_dict() has no extra top-level keys even when issues are present (Req 9.3)."""
        issue = QAIssue(type="alignment", description="Off-center", severity="low")
        result = QAResult(issues=[issue], verdict="fail")
        d = result.to_dict()
        assert set(d.keys()) == {"issues", "verdict"}

    # --- Requirement 9.4: each issue dict has exactly {"type", "description", "severity"} ---

    def test_each_issue_dict_has_exactly_three_keys(self):
        """Each issue in to_dict()["issues"] has exactly {"type", "description", "severity"} (Req 9.4)."""
        issues = [
            QAIssue(type="text_readability", description="Font too small", severity="high"),
            QAIssue(type="color_contrast", description="Low contrast", severity="medium"),
        ]
        result = QAResult(issues=issues, verdict="fail")
        d = result.to_dict()
        for item in d["issues"]:
            assert set(item.keys()) == {"type", "description", "severity"}

    def test_issue_dict_keys_all_five_types(self):
        """Issue dicts have correct keys for all five valid issue types (Req 9.4)."""
        types = [
            "text_readability", "alignment", "color_contrast",
            "missing_information", "unclear_information",
        ]
        for t in types:
            issue = QAIssue(type=t, description="desc", severity="low")
            result = QAResult(issues=[issue], verdict="pass")
            d = result.to_dict()
            assert set(d["issues"][0].keys()) == {"type", "description", "severity"}

    # --- Requirement 9.1: empty issues list returns {"issues": [], "verdict": "pass"} ---

    def test_empty_issues_returns_correct_dict(self):
        """to_dict() with empty issues returns {"issues": [], "verdict": "pass"} (Req 9.1)."""
        result = QAResult(issues=[], verdict="pass")
        d = result.to_dict()
        assert d == {"issues": [], "verdict": "pass"}

    def test_empty_issues_issues_key_is_empty_list(self):
        """to_dict()["issues"] is an empty list when no issues (Req 9.1)."""
        result = QAResult()
        d = result.to_dict()
        assert d["issues"] == []
        assert isinstance(d["issues"], list)

    # --- Requirement 9.2: multi-issue list serializes all issues correctly ---

    def test_multi_issue_list_all_issues_serialized(self):
        """to_dict() with multiple issues serializes all of them (Req 9.2)."""
        issues = [
            QAIssue(type="alignment", description=f"Issue {i}", severity="low")
            for i in range(5)
        ]
        result = QAResult(issues=issues, verdict="pass")
        d = result.to_dict()
        assert len(d["issues"]) == 5
        for i, item in enumerate(d["issues"]):
            assert item["description"] == f"Issue {i}"
            assert item["type"] == "alignment"
            assert item["severity"] == "low"

    def test_multi_issue_list_preserves_order(self):
        """to_dict() preserves issue order in the serialized list (Req 9.2)."""
        types = ["text_readability", "alignment", "color_contrast"]
        issues = [QAIssue(type=t, description="d", severity="low") for t in types]
        result = QAResult(issues=issues, verdict="pass")
        d = result.to_dict()
        for i, t in enumerate(types):
            assert d["issues"][i]["type"] == t

    def test_multi_issue_mixed_severities_serialized(self):
        """to_dict() correctly serializes issues with mixed severities (Req 9.2)."""
        issues = [
            QAIssue(type="alignment", description="low issue", severity="low"),
            QAIssue(type="color_contrast", description="medium issue", severity="medium"),
            QAIssue(type="text_readability", description="high issue", severity="high"),
        ]
        result = QAResult(issues=issues, verdict="fail")
        d = result.to_dict()
        assert d["issues"][0]["severity"] == "low"
        assert d["issues"][1]["severity"] == "medium"
        assert d["issues"][2]["severity"] == "high"

    # --- Requirements 10.1, 10.2: serialization round-trip via QAOutputValidator ---

    def test_round_trip_empty_issues(self):
        """Round-trip: QAResult → to_dict() → QAOutputValidator.validate() returns equivalent QAResult (Req 10.1, 10.2)."""
        from wimlds.agents.publishing.poster_qa_agent import QAOutputValidator
        original = QAResult(issues=[], verdict="pass")
        d = original.to_dict()
        validator = QAOutputValidator()
        restored = validator.validate(d)
        assert restored.verdict == original.verdict
        assert restored.issues == original.issues

    def test_round_trip_single_issue(self):
        """Round-trip with one issue returns equivalent QAResult (Req 10.1, 10.2)."""
        from wimlds.agents.publishing.poster_qa_agent import QAOutputValidator
        issue = QAIssue(type="color_contrast", description="Low contrast text", severity="high")
        original = QAResult(issues=[issue], verdict="fail")
        d = original.to_dict()
        validator = QAOutputValidator()
        restored = validator.validate(d)
        assert restored.verdict == original.verdict
        assert len(restored.issues) == 1
        assert restored.issues[0].type == issue.type
        assert restored.issues[0].description == issue.description
        assert restored.issues[0].severity == issue.severity

    def test_round_trip_multi_issue(self):
        """Round-trip with multiple issues returns equivalent QAResult (Req 10.1, 10.2)."""
        from wimlds.agents.publishing.poster_qa_agent import QAOutputValidator
        issues = [
            QAIssue(type="alignment", description="Off-center logo", severity="low"),
            QAIssue(type="missing_information", description="No date shown", severity="high"),
            QAIssue(type="unclear_information", description="Blurry venue text", severity="medium"),
        ]
        original = QAResult(issues=issues, verdict="fail")
        d = original.to_dict()
        validator = QAOutputValidator()
        restored = validator.validate(d)
        assert restored.verdict == original.verdict
        assert len(restored.issues) == len(original.issues)
        for orig_issue, rest_issue in zip(original.issues, restored.issues):
            assert rest_issue.type == orig_issue.type
            assert rest_issue.description == orig_issue.description
            assert rest_issue.severity == orig_issue.severity

    def test_round_trip_to_dict_satisfies_validator_constraints(self):
        """to_dict() output satisfies all QAOutputValidator constraints (Req 10.2)."""
        from wimlds.agents.publishing.poster_qa_agent import QAOutputValidator
        issues = [
            QAIssue(type="text_readability", description="Font too small", severity="medium"),
        ]
        result = QAResult(issues=issues, verdict="fail")
        d = result.to_dict()
        validator = QAOutputValidator()
        # Should not raise
        restored = validator.validate(d)
        assert isinstance(restored, QAResult)


# ---------------------------------------------------------------------------
# Verdict Determination Rules (Task 9.2)
# ---------------------------------------------------------------------------

class TestVerdictDetermination:
    """
    Unit tests for verdict determination rules (Requirements 11.1, 11.2, 11.3).

    The verdict is determined by the LLM based on prompt instructions.
    QAOutputValidator validates the verdict but trusts the LLM to follow the rules.
    These tests verify that QAResult instances with the correct verdict for their
    issue severities pass validation successfully.
    """

    def _validator(self):
        return QAOutputValidator()

    def test_high_severity_issue_with_fail_verdict_passes_validation(self):
        """A QAResult with one high severity issue and verdict='fail' passes validation (Req 11.1)."""
        raw = {
            "issues": [
                {"type": "text_readability", "description": "Font too small", "severity": "high"}
            ],
            "verdict": "fail",
        }
        result = self._validator().validate(raw)
        assert isinstance(result, QAResult)
        assert result.verdict == "fail"
        assert len(result.issues) == 1
        assert result.issues[0].severity == "high"

    def test_medium_severity_issue_with_fail_verdict_passes_validation(self):
        """A QAResult with one medium severity issue and verdict='fail' passes validation (Req 11.2)."""
        raw = {
            "issues": [
                {"type": "color_contrast", "description": "Low contrast", "severity": "medium"}
            ],
            "verdict": "fail",
        }
        result = self._validator().validate(raw)
        assert isinstance(result, QAResult)
        assert result.verdict == "fail"
        assert len(result.issues) == 1
        assert result.issues[0].severity == "medium"

    def test_only_low_severity_issues_with_pass_verdict_passes_validation(self):
        """A QAResult with only low severity issues and verdict='pass' passes validation (Req 11.3)."""
        raw = {
            "issues": [
                {"type": "alignment", "description": "Slightly off-center", "severity": "low"}
            ],
            "verdict": "pass",
        }
        result = self._validator().validate(raw)
        assert isinstance(result, QAResult)
        assert result.verdict == "pass"
        assert all(issue.severity == "low" for issue in result.issues)

    def test_empty_issues_with_pass_verdict_passes_validation(self):
        """A QAResult with an empty issues list and verdict='pass' passes validation (Req 11.3)."""
        raw = {
            "issues": [],
            "verdict": "pass",
        }
        result = self._validator().validate(raw)
        assert isinstance(result, QAResult)
        assert result.verdict == "pass"
        assert result.issues == []
