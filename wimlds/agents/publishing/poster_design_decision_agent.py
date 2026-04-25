"""Poster Design Decision Agent — makes LLM-driven design decisions for poster generation."""
import json
import re
from dataclasses import dataclass
from typing import Optional


class ValidationError(Exception):
    """Raised by DesignOutputValidator when LLM output violates schema constraints."""


@dataclass
class DesignDecision:
    layout: str
    colors: list[str]
    font_style: str
    hierarchy: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "layout": self.layout,
            "colors": self.colors,
            "font_style": self.font_style,
            "hierarchy": self.hierarchy,
        }


class DesignInputValidator:
    """Validates and normalises inputs for PosterDesignDecisionAgent."""

    def validate(
        self,
        content_json: dict | None,
        brand_colors: list[str] | None,
    ) -> tuple[dict, list[str] | None]:
        """Validate inputs and return a normalised (content_json, brand_colors) tuple.

        Raises:
            ValueError: if content_json is None or empty, or if any brand color is invalid.
        """
        if not content_json:
            raise ValueError(
                "content_json must be a non-empty dict, got: "
                f"{content_json!r}"
            )

        normalised_colors: list[str] | None = None
        if brand_colors:
            for color in brand_colors:
                if not re.fullmatch(r"#[0-9A-Fa-f]{3,6}", color):
                    raise ValueError(
                        f"Invalid brand color: {color!r}. "
                        "Expected a hex color matching #[0-9A-Fa-f]{3,6}."
                    )
            normalised_colors = brand_colors

        return (content_json, normalised_colors)


class DesignPromptBuilder:
    """Constructs LLM prompts for poster design decisions."""

    SYSTEM_PROMPT = (
        "You are a professional graphic design assistant specialised in event poster design. "
        "Your role is to analyse event content and produce structured design decisions "
        "(layout, color palette, font style, and visual hierarchy) that best match the event's "
        "vibe and brand identity. You always respond with pure JSON and nothing else."
    )

    def build(self, content_json: dict, brand_colors: list[str] | None = None) -> str:
        """Build the user prompt embedding content_json, schema, enum constraints, and vibe rules."""
        serialized = json.dumps(content_json, ensure_ascii=False, indent=2)

        color_instruction = (
            f"Use the following brand colors as anchors for the palette: {brand_colors}. "
            "Derive the remaining colors to complement them while staying on-brand."
            if brand_colors
            else "Derive the color palette from the event vibe described in the content."
        )

        prompt = f"""You are given the following event content JSON:

{serialized}

Based on this content, produce a design decision as a JSON object with exactly these fields:

{{
  "layout": "<one of: minimal | bold | grid | modern>",
  "colors": ["<hex1>", "<hex2>", "<hex3>"],
  "font_style": "<one of: sans-serif | serif | display>",
  "hierarchy": {{
    "primary": "<most prominent text element>",
    "secondary": "<second most prominent text element>",
    "tertiary": "<third most prominent text element>"
  }}
}}

Constraints:
- "layout" must be exactly one of: minimal, bold, grid, modern
- "font_style" must be exactly one of: sans-serif, serif, display
- "colors" must contain exactly three valid hex color codes (e.g. "#FF5733")

Color instructions:
{color_instruction}

Vibe-to-design mapping rules (apply the best match):
- tech / minimal vibe  → layout: minimal or modern  |  font_style: sans-serif
- fun / party vibe     → layout: bold               |  font_style: display
- formal / corporate   → layout: grid or modern     |  font_style: serif or sans-serif
- luxury vibe          → layout: modern             |  font_style: serif

Return ONLY the JSON object described above. Do not include markdown fences, explanations, or any text outside the JSON."""

        return prompt

    def build_with_correction(
        self,
        content_json: dict,
        brand_colors: list[str] | None,
        error_message: str,
    ) -> str:
        """Build a prompt with a correction hint appended for retry attempts."""
        base_prompt = self.build(content_json, brand_colors)
        correction = (
            f"\n\nYour previous response was invalid. Error: {error_message}\n"
            "Please correct the issues described above and return a valid JSON object."
        )
        return base_prompt + correction


class DesignOutputValidator:
    """Validates LLM raw dict output against schema constraints, returning a DesignDecision."""

    VALID_LAYOUTS: frozenset[str] = frozenset({"minimal", "bold", "grid", "modern"})
    VALID_FONT_STYLES: frozenset[str] = frozenset({"sans-serif", "serif", "display"})
    REQUIRED_KEYS: frozenset[str] = frozenset({"layout", "colors", "font_style", "hierarchy"})

    def validate(self, raw) -> DesignDecision:
        """Validate raw LLM output and return a populated DesignDecision.

        Raises:
            ValidationError: if any schema constraint is violated.
        """
        if not isinstance(raw, dict):
            raise ValidationError(
                f"Expected a dict, got {type(raw).__name__!r}."
            )

        missing = self.REQUIRED_KEYS - raw.keys()
        if missing:
            raise ValidationError(
                f"Missing required keys: {sorted(missing)}."
            )

        layout = raw["layout"].strip().lower()
        font_style = raw["font_style"].strip().lower()

        if layout not in self.VALID_LAYOUTS:
            raise ValidationError(
                f"Invalid layout {layout!r}. Must be one of {sorted(self.VALID_LAYOUTS)}."
            )

        if font_style not in self.VALID_FONT_STYLES:
            raise ValidationError(
                f"Invalid font_style {font_style!r}. Must be one of {sorted(self.VALID_FONT_STYLES)}."
            )

        colors = raw["colors"]
        if (
            not isinstance(colors, list)
            or len(colors) != 3
            or not all(isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{3,6}", c) for c in colors)
        ):
            raise ValidationError(
                "colors must be a list of exactly three strings each matching #[0-9A-Fa-f]{3,6}."
            )

        hierarchy = raw["hierarchy"]
        expected_keys = {"primary", "secondary", "tertiary"}
        if (
            not isinstance(hierarchy, dict)
            or set(hierarchy.keys()) != expected_keys
            or not all(isinstance(v, str) and v for v in hierarchy.values())
        ):
            raise ValidationError(
                "hierarchy must be a dict with exactly 'primary', 'secondary', 'tertiary' "
                "keys, each a non-empty string."
            )

        return DesignDecision(
            layout=layout,
            colors=list(colors),
            font_style=font_style,
            hierarchy=dict(hierarchy),
        )
