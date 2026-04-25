"""Unit tests for content_extraction_agent components."""
import json
import pytest

from wimlds.agents.publishing.content_extraction_agent import (
    ExtractedEvent,
    InputNormalizer,
    OutputValidator,
    PromptBuilder,
    ValidationError,
)

VALID_VIBES = {"formal", "corporate", "fun", "party", "tech", "minimal", "luxury"}

VALID_DICT = {
    "event_name": "WiMLDS Meetup",
    "date_time": "15 Nov 2025",
    "venue": "Pune Tech Park",
    "organizer": "WiMLDS Pune",
    "audience": "ML practitioners",
    "vibe": "tech",
    "key_highlights": ["RAG", "LLMs"],
}


# ---------------------------------------------------------------------------
# InputNormalizer
# ---------------------------------------------------------------------------

class TestInputNormalizer:
    def setup_method(self):
        self.norm = InputNormalizer()

    def test_str_input_is_stripped(self):
        assert self.norm.normalize("  hello world  ") == "hello world"

    def test_str_input_no_whitespace_unchanged(self):
        assert self.norm.normalize("hello") == "hello"

    def test_dict_input_returns_valid_json(self):
        d = {"key": "value", "num": 42}
        result = self.norm.normalize(d)
        assert json.loads(result) == d

    def test_other_type_returns_str_repr(self):
        assert self.norm.normalize(123) == "123"
        assert self.norm.normalize(3.14) == "3.14"
        assert self.norm.normalize(["a", "b"]) == str(["a", "b"])

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            self.norm.normalize(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            self.norm.normalize("")

    def test_whitespace_only_string_raises_value_error(self):
        with pytest.raises(ValueError):
            self.norm.normalize("   ")

    def test_empty_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            self.norm.normalize({})


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

FIELD_NAMES = [
    "event_name", "date_time", "venue", "organizer",
    "audience", "vibe", "key_highlights",
]

class TestPromptBuilder:
    def setup_method(self):
        self.pb = PromptBuilder()

    def test_build_contains_event_text(self):
        prompt = self.pb.build("My special event")
        assert "My special event" in prompt

    def test_build_contains_all_field_names(self):
        prompt = self.pb.build("some event text")
        for field in FIELD_NAMES:
            assert field in prompt, f"Field '{field}' missing from prompt"

    def test_build_contains_all_vibe_values(self):
        prompt = self.pb.build("some event text")
        for vibe in VALID_VIBES:
            assert vibe in prompt, f"Vibe '{vibe}' missing from prompt"

    def test_build_contains_pure_json_instruction(self):
        prompt = self.pb.build("some event text")
        assert "pure JSON" in prompt

    def test_build_is_deterministic(self):
        text = "WiMLDS Annual Gala 2025"
        assert self.pb.build(text) == self.pb.build(text)

    def test_build_with_correction_contains_event_text(self):
        prompt = self.pb.build_with_correction("My event", "missing key: vibe")
        assert "My event" in prompt

    def test_build_with_correction_contains_error_message(self):
        error = "missing key: vibe"
        prompt = self.pb.build_with_correction("My event", error)
        assert error in prompt


# ---------------------------------------------------------------------------
# OutputValidator
# ---------------------------------------------------------------------------

class TestOutputValidator:
    def setup_method(self):
        self.val = OutputValidator()

    def _valid(self, **overrides):
        d = dict(VALID_DICT)
        d.update(overrides)
        return d

    def test_valid_dict_returns_extracted_event(self):
        result = self.val.validate(self._valid())
        assert isinstance(result, ExtractedEvent)

    def test_non_dict_raises_validation_error(self):
        for bad in ["string", 42, None, ["list"], 3.14]:
            with pytest.raises(ValidationError):
                self.val.validate(bad)

    def test_missing_required_key_raises_validation_error(self):
        for key in FIELD_NAMES:
            d = self._valid()
            del d[key]
            with pytest.raises(ValidationError):
                self.val.validate(d)

    def test_invalid_vibe_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(vibe="casual"))

    def test_non_list_key_highlights_coerced_to_single_element_list(self):
        result = self.val.validate(self._valid(key_highlights="single highlight"))
        assert isinstance(result.key_highlights, list)
        assert len(result.key_highlights) == 1
        assert result.key_highlights[0] == "single highlight"

    def test_string_fields_are_stripped(self):
        result = self.val.validate(self._valid(
            event_name="  WiMLDS  ",
            venue="  Pune  ",
            vibe="  tech  ",
        ))
        assert result.event_name == "WiMLDS"
        assert result.venue == "Pune"
        assert result.vibe == "tech"

    def test_input_dict_not_mutated(self):
        d = self._valid(event_name="  WiMLDS  ", vibe="  tech  ")
        original = dict(d)
        self.val.validate(d)
        assert d == original

    def test_all_valid_vibes_accepted(self):
        for vibe in VALID_VIBES:
            result = self.val.validate(self._valid(vibe=vibe))
            assert result.vibe == vibe


# ---------------------------------------------------------------------------
# ExtractedEvent
# ---------------------------------------------------------------------------

class TestExtractedEvent:
    def test_to_dict_returns_all_seven_keys(self):
        event = ExtractedEvent(
            event_name="Test",
            date_time="2025-01-01",
            venue="Venue",
            organizer="Org",
            audience="All",
            vibe="tech",
            key_highlights=["a", "b"],
        )
        d = event.to_dict()
        assert set(d.keys()) == {
            "event_name", "date_time", "venue", "organizer",
            "audience", "vibe", "key_highlights",
        }

    def test_default_key_highlights_is_empty_list(self):
        event = ExtractedEvent(
            event_name="Test",
            date_time="2025-01-01",
            venue="Venue",
            organizer="Org",
            audience="All",
            vibe="fun",
        )
        assert event.key_highlights == []
        assert event.to_dict()["key_highlights"] == []

    def test_to_dict_values_match_dataclass_fields(self):
        event = ExtractedEvent(
            event_name="WiMLDS Meetup",
            date_time="15 Nov 2025",
            venue="Pune Tech Park",
            organizer="WiMLDS Pune",
            audience="ML practitioners",
            vibe="tech",
            key_highlights=["RAG", "LLMs"],
        )
        d = event.to_dict()
        assert d["event_name"] == event.event_name
        assert d["date_time"] == event.date_time
        assert d["venue"] == event.venue
        assert d["organizer"] == event.organizer
        assert d["audience"] == event.audience
        assert d["vibe"] == event.vibe
        assert d["key_highlights"] == event.key_highlights


# ---------------------------------------------------------------------------
# ContentExtractionAgent
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch
from wimlds.agents.publishing.content_extraction_agent import ContentExtractionAgent
from wimlds.core.result import AgentResult


VALID_LLM_RESPONSE = {
    "event_name": "WiMLDS Meetup",
    "date_time": "15 Nov 2025",
    "venue": "Pune Tech Park",
    "organizer": "WiMLDS Pune",
    "audience": "ML practitioners",
    "vibe": "tech",
    "key_highlights": ["RAG", "LLMs"],
}


class TestContentExtractionAgent:
    def _make_agent(self, dry_run=False, max_retries=2):
        agent = ContentExtractionAgent.__new__(ContentExtractionAgent)
        agent.dry_run = dry_run
        agent.max_retries = max_retries
        agent._normalizer = InputNormalizer()
        agent._prompt_builder = PromptBuilder()
        agent._validator = OutputValidator()
        agent._llm = MagicMock()
        return agent

    def test_success_path_returns_agent_result_with_all_fields(self):
        agent = self._make_agent()
        agent._llm.generate_json.return_value = dict(VALID_LLM_RESPONSE)
        result = agent.extract("WiMLDS event text")
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert set(result.data["extracted_event"].keys()) == {
            "event_name", "date_time", "venue", "organizer",
            "audience", "vibe", "key_highlights",
        }

    def test_empty_input_returns_failure(self):
        agent = self._make_agent()
        result = agent.extract("")
        assert result.success is False
        assert result.error

    def test_none_input_returns_failure(self):
        agent = self._make_agent()
        result = agent.extract(None)
        assert result.success is False
        assert result.error

    def test_validation_error_triggers_retry_with_correction(self):
        agent = self._make_agent(max_retries=2)
        # First call returns invalid dict (missing key), second returns valid
        agent._llm.generate_json.side_effect = [
            {"event_name": "X"},  # will fail validation
            dict(VALID_LLM_RESPONSE),
        ]
        result = agent.extract("some event")
        assert result.success is True
        assert agent._llm.generate_json.call_count == 2

    def test_exhausted_retries_returns_failure(self):
        agent = self._make_agent(max_retries=2)
        agent._llm.generate_json.return_value = {"event_name": "X"}  # always invalid
        result = agent.extract("some event")
        assert result.success is False
        assert result.error
        assert agent._llm.generate_json.call_count == 2

    def test_json_decode_error_triggers_retry(self):
        agent = self._make_agent(max_retries=2)
        agent._llm.generate_json.side_effect = [
            json.JSONDecodeError("bad json", "", 0),
            dict(VALID_LLM_RESPONSE),
        ]
        result = agent.extract("some event")
        assert result.success is True
        assert agent._llm.generate_json.call_count == 2

    def test_api_level_error_returns_failure_without_retry(self):
        agent = self._make_agent(max_retries=2)
        agent._llm.generate_json.side_effect = ConnectionError("network failure")
        result = agent.extract("some event")
        assert result.success is False
        assert "network failure" in result.error
        assert agent._llm.generate_json.call_count == 1

    def test_extract_never_raises(self):
        agent = self._make_agent()
        agent._llm.generate_json.side_effect = RuntimeError("unexpected crash")
        result = agent.extract("some event")
        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_dict_input_not_mutated(self):
        agent = self._make_agent()
        agent._llm.generate_json.return_value = dict(VALID_LLM_RESPONSE)
        original = {"title": "My Event", "date": "2025-01-01"}
        copy = dict(original)
        agent.extract(original)
        assert original == copy

    def test_run_writes_extracted_event_to_state(self):
        agent = self._make_agent()
        agent._llm.generate_json.return_value = dict(VALID_LLM_RESPONSE)
        state = {"raw_event_input": "WiMLDS event text", "other_key": "preserved"}
        result_state = agent.run(state)
        assert "extracted_event" in result_state
        assert result_state["other_key"] == "preserved"

    def test_run_does_not_write_extracted_event_on_failure(self):
        agent = self._make_agent()
        agent._llm.generate_json.return_value = {}  # always invalid
        state = {"raw_event_input": "some event"}
        result_state = agent.run(state)
        assert "extracted_event" not in result_state
