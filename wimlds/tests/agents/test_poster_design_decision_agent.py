"""Unit tests for poster_design_decision_agent component classes."""
import copy
import pytest

from wimlds.agents.publishing.poster_design_decision_agent import (
    DesignDecision,
    DesignInputValidator,
    DesignOutputValidator,
    DesignPromptBuilder,
    ValidationError,
)

VALID_RAW = {
    "layout": "minimal",
    "colors": ["#4C1D95", "#EC4899", "#7C3AED"],
    "font_style": "sans-serif",
    "hierarchy": {
        "primary": "Event Title",
        "secondary": "Speaker Name",
        "tertiary": "Date and Venue",
    },
}


# ---------------------------------------------------------------------------
# DesignDecision
# ---------------------------------------------------------------------------

class TestDesignDecision:
    def _make(self):
        return DesignDecision(
            layout="minimal",
            colors=["#4C1D95", "#EC4899", "#7C3AED"],
            font_style="sans-serif",
            hierarchy={
                "primary": "Event Title",
                "secondary": "Speaker Name",
                "tertiary": "Date and Venue",
            },
        )

    def test_to_dict_returns_exactly_four_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {"layout", "colors", "font_style", "hierarchy"}

    def test_to_dict_values_match_fields(self):
        decision = self._make()
        d = decision.to_dict()
        assert d["layout"] == decision.layout
        assert d["colors"] == decision.colors
        assert d["font_style"] == decision.font_style
        assert d["hierarchy"] == decision.hierarchy


# ---------------------------------------------------------------------------
# DesignInputValidator
# ---------------------------------------------------------------------------

class TestDesignInputValidator:
    def setup_method(self):
        self.val = DesignInputValidator()

    def test_none_content_json_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate(None, None)

    def test_empty_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            self.val.validate({}, None)

    def test_valid_non_empty_dict_accepted(self):
        content, colors = self.val.validate({"key": "value"}, None)
        assert content == {"key": "value"}

    def test_none_brand_colors_returns_none(self):
        _, colors = self.val.validate({"key": "value"}, None)
        assert colors is None

    def test_empty_list_brand_colors_returns_none(self):
        _, colors = self.val.validate({"key": "value"}, [])
        assert colors is None

    def test_valid_hex_list_accepted(self):
        hex_colors = ["#4C1D95", "#EC4899", "#7C3AED"]
        _, colors = self.val.validate({"key": "value"}, hex_colors)
        assert colors == hex_colors

    def test_invalid_hex_raises_value_error_with_bad_value(self):
        with pytest.raises(ValueError, match="not-a-color"):
            self.val.validate({"key": "value"}, ["#4C1D95", "not-a-color"])

    def test_inputs_not_mutated(self):
        content = {"key": "value"}
        colors = ["#4C1D95", "#EC4899"]
        original_content = dict(content)
        original_colors = list(colors)
        self.val.validate(content, colors)
        assert content == original_content
        assert colors == original_colors


# ---------------------------------------------------------------------------
# DesignPromptBuilder
# ---------------------------------------------------------------------------

class TestDesignPromptBuilder:
    def setup_method(self):
        self.pb = DesignPromptBuilder()
        self.content = {
            "event_name": "WiMLDS Meetup",
            "vibe": "tech",
        }

    def test_build_contains_serialized_content(self):
        prompt = self.pb.build(self.content)
        assert "WiMLDS Meetup" in prompt

    def test_build_contains_all_four_field_names(self):
        prompt = self.pb.build(self.content)
        for field in ("layout", "colors", "font_style", "hierarchy"):
            assert field in prompt, f"Field '{field}' missing from prompt"

    def test_build_contains_all_layout_values(self):
        prompt = self.pb.build(self.content)
        for value in ("minimal", "bold", "grid", "modern"):
            assert value in prompt, f"Layout value '{value}' missing from prompt"

    def test_build_contains_all_font_style_values(self):
        prompt = self.pb.build(self.content)
        for value in ("sans-serif", "serif", "display"):
            assert value in prompt, f"Font style '{value}' missing from prompt"

    def test_build_contains_pure_json_instruction(self):
        prompt = self.pb.build(self.content)
        assert "pure JSON" in prompt

    def test_build_embeds_brand_colors_when_provided(self):
        colors = ["#4C1D95", "#EC4899", "#7C3AED"]
        prompt = self.pb.build(self.content, brand_colors=colors)
        assert "#4C1D95" in prompt

    def test_build_with_correction_contains_error_hint(self):
        error = "missing key: font_style"
        prompt = self.pb.build_with_correction(self.content, None, error)
        assert error in prompt


# ---------------------------------------------------------------------------
# DesignOutputValidator
# ---------------------------------------------------------------------------

class TestDesignOutputValidator:
    def setup_method(self):
        self.val = DesignOutputValidator()

    def _valid(self, **overrides):
        d = copy.deepcopy(VALID_RAW)
        d.update(overrides)
        return d

    def test_valid_dict_returns_design_decision(self):
        result = self.val.validate(self._valid())
        assert isinstance(result, DesignDecision)

    def test_non_dict_raises_validation_error(self):
        for bad in ("string", 42, ["list"], None):
            with pytest.raises(ValidationError):
                self.val.validate(bad)

    def test_missing_required_key_raises_validation_error(self):
        for key in ("layout", "colors", "font_style", "hierarchy"):
            d = self._valid()
            del d[key]
            with pytest.raises(ValidationError):
                self.val.validate(d)

    def test_invalid_layout_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(layout="fancy"))

    def test_invalid_font_style_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(font_style="comic-sans"))

    def test_wrong_colors_count_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(colors=["#4C1D95", "#EC4899"]))

    def test_invalid_hex_in_colors_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(colors=["#4C1D95", "red", "#7C3AED"]))

    def test_malformed_hierarchy_raises_validation_error(self):
        with pytest.raises(ValidationError):
            self.val.validate(self._valid(hierarchy={"primary": "Title"}))

    def test_mixed_case_layout_accepted(self):
        result = self.val.validate(self._valid(layout="MINIMAL"))
        assert result.layout == "minimal"

    def test_mixed_case_font_style_accepted(self):
        result = self.val.validate(self._valid(font_style="Sans-Serif"))
        assert result.font_style == "sans-serif"

    def test_input_dict_not_mutated(self):
        d = self._valid(layout="MINIMAL", font_style="Sans-Serif")
        original = copy.deepcopy(d)
        self.val.validate(d)
        assert d == original

    def test_all_valid_layouts_accepted(self):
        for layout in ("minimal", "bold", "grid", "modern"):
            result = self.val.validate(self._valid(layout=layout))
            assert result.layout == layout

    def test_all_valid_font_styles_accepted(self):
        for font_style in ("sans-serif", "serif", "display"):
            result = self.val.validate(self._valid(font_style=font_style))
            assert result.font_style == font_style
