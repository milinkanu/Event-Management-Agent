"""Brand Intelligence Agent — extracts brand colors, tone, and style hints from unstructured text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from wimlds.integrations.llm.llm_client import LLMClient
from wimlds.core.result import AgentResult


class ValidationError(Exception):
    """Raised by OutputValidator when the LLM output violates the required schema."""


@dataclass
class BrandProfile:
    """Structured brand identity extracted from unstructured text."""

    brand_colors: list[str]  # zero or more hex color strings
    tone: str                 # one of VALID_TONES or empty string
    style_notes: list[str]   # zero or more style hint strings

    def to_dict(self) -> dict:
        return {
            "brand_colors": self.brand_colors,
            "tone": self.tone,
            "style_notes": self.style_notes,
        }


class InputNormalizer:
    """Converts any input shape into a clean prompt-ready string."""

    def normalize(self, raw_input: str | dict) -> str:
        """
        - str  → strip() and return
        - dict → json.dumps() and return
        - None → raise ValueError
        - ""   → raise ValueError
        - {}   → raise ValueError
        Does not mutate the original input.
        """
        if raw_input is None:
            raise ValueError("Input must not be None; provide a non-empty string or dict.")

        if isinstance(raw_input, str):
            stripped = raw_input.strip()
            if not stripped:
                raise ValueError("Input string must not be empty or whitespace-only.")
            return stripped

        if isinstance(raw_input, dict):
            if not raw_input:
                raise ValueError("Input dict must not be empty.")
            return json.dumps(raw_input)

        raise ValueError(
            f"Unsupported input type '{type(raw_input).__name__}'; expected str or dict."
        )


class PromptBuilder:
    """Constructs LLM prompts with output schema, tone vocabulary, and anti-hallucination rules."""

    SYSTEM_PROMPT: str = (
        "You are a brand identity analyst. "
        "Your task is to extract structured brand signals from unstructured text. "
        "You must return ONLY a valid JSON object — no markdown fences, no preamble, no explanation. "
        "Do not fabricate or infer information that is not explicitly present in the input text."
    )

    def build(self, text: str) -> str:
        """
        Returns the full user prompt embedding text, output schema,
        valid tone values, and anti-hallucination instructions.
        """
        return (
            f"Analyse the following text and extract brand identity signals.\n\n"
            f"TEXT:\n{text}\n\n"
            "Return a JSON object with exactly these fields:\n"
            "{\n"
            '  "brand_colors": ["#hex1", "#hex2"],\n'
            '  "tone": "luxury | fun | minimal | corporate | \\"\\"",\n'
            '  "style_notes": ["string", "..."]\n'
            "}\n\n"
            "Rules:\n"
            "- brand_colors: list of hex color strings (e.g. #1A2B4C). "
            "Return an empty list [] if no colors can be confidently identified from the text. "
            "Do NOT fabricate or infer colors that are not explicitly present in the input text.\n"
            "- tone: must be exactly one of: luxury, fun, minimal, corporate. "
            "Return an empty string \"\" if the tone cannot be confidently determined.\n"
            "- style_notes: list of style hint strings. "
            "Return an empty list [] if no style hints can be confidently identified.\n"
            "- Return pure JSON only — no markdown fences, no preamble, no explanation.\n"
            "- When confidence is low, return empty values rather than guessing."
        )

    def build_with_correction(self, text: str, error_message: str) -> str:
        """
        Returns the base prompt with the previous error appended as a correction hint.
        """
        base = self.build(text)
        return (
            f"{base}\n\n"
            f"CORRECTION REQUIRED: Your previous response contained an error. "
            f"Please fix the following issue and return valid JSON:\n{error_message}"
        )


class OutputValidator:
    """Validates the LLM's raw dict against the required schema and returns a BrandProfile."""

    VALID_TONES: frozenset[str] = frozenset({"luxury", "fun", "minimal", "corporate"})
    REQUIRED_KEYS: frozenset[str] = frozenset({"brand_colors", "tone", "style_notes"})
    HEX_PATTERN: re.Pattern = re.compile(r"#[0-9A-Fa-f]{3,6}")

    def validate(self, raw: dict) -> BrandProfile:
        """
        Raises ValidationError if any schema constraint is violated.
        Returns a populated BrandProfile on success.
        Does not mutate the input dict.
        """
        if not isinstance(raw, dict):
            raise ValidationError("Expected dict, got " + type(raw).__name__)

        for key in self.REQUIRED_KEYS:
            if key not in raw:
                raise ValidationError("Missing required key: " + key)

        if not isinstance(raw["brand_colors"], list):
            raise ValidationError("brand_colors must be a list")

        for color in raw["brand_colors"]:
            if not re.fullmatch(r"#[0-9A-Fa-f]{3,6}", color):
                raise ValidationError("Invalid hex color: " + color)

        if not isinstance(raw["tone"], str):
            raise ValidationError("tone must be a string")
        tone = raw["tone"].lower()

        if tone != "" and tone not in self.VALID_TONES:
            raise ValidationError("Invalid tone: " + tone)

        if not isinstance(raw["style_notes"], list):
            raise ValidationError("style_notes must be a list")

        for note in raw["style_notes"]:
            if not isinstance(note, str):
                raise ValidationError("style_notes must be a list of strings")

        return BrandProfile(
            brand_colors=list(raw["brand_colors"]),
            tone=tone,
            style_notes=list(raw["style_notes"]),
        )


class BrandIntelligenceAgent:
    """
    Orchestrates the full brand extraction pipeline.
    Exposes analyse(raw_input) -> AgentResult and run(state) -> dict (LangGraph node).
    Never raises to the caller.
    """

    def __init__(self, dry_run: bool = False, max_retries: int = 2) -> None:
        self.dry_run = dry_run
        self.max_retries = max_retries
        self._normalizer = InputNormalizer()
        self._prompt_builder = PromptBuilder()
        self._llm = LLMClient(dry_run=dry_run)
        self._validator = OutputValidator()

    def analyse(self, raw_input: str | dict) -> AgentResult:
        """
        Extract brand signals from raw_input.
        Returns AgentResult with data={"brand_profile": dict} on success.
        Never raises.
        """
        # Dry-run: return deterministic stub without calling the LLM
        if self.dry_run:
            return AgentResult(
                success=True,
                data={"brand_profile": {"brand_colors": [], "tone": "", "style_notes": []}},
            )

        # Step 1: Normalize
        try:
            text = self._normalizer.normalize(raw_input)
        except ValueError as e:
            return AgentResult(success=False, error=str(e))

        # Step 2: Build initial prompt
        prompt = self._prompt_builder.build(text)

        # Step 3: Retry loop
        attempt = 0
        while attempt < self.max_retries:
            try:
                raw_dict = self._llm.generate_json(prompt, system=PromptBuilder.SYSTEM_PROMPT)
                profile = self._validator.validate(raw_dict)
                return AgentResult(success=True, data={"brand_profile": profile.to_dict()})
            except ValidationError as e:
                attempt += 1
                if attempt < self.max_retries:
                    prompt = self._prompt_builder.build_with_correction(text, str(e))
            except json.JSONDecodeError:
                attempt += 1
            except Exception as e:
                return AgentResult(success=False, error=str(e))

        return AgentResult(
            success=False,
            error=f"Extraction failed after {self.max_retries} attempts",
        )

    def run(self, state: dict) -> dict:
        """
        LangGraph node interface.
        Reads state["raw_brand_input"], writes state["brand_profile"] on success.
        Returns updated state dict in all cases.
        """
        raw_input = state.get("raw_brand_input")
        result = self.analyse(raw_input)
        if result.success:
            state["brand_profile"] = result.data["brand_profile"]
        return state
