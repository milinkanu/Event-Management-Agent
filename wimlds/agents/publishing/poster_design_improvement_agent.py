"""Poster Design Improvement Agent — refines existing poster design decisions using LLM feedback."""
import json
import re

from wimlds.agents.publishing.poster_design_decision_agent import DesignDecision, ValidationError
from wimlds.core.result import AgentResult
from wimlds.integrations.llm.llm_client import LLMClient


class ImprovementInputValidator:
    """Validates inputs for PosterDesignImprovementAgent."""

    REQUIRED_DESIGN_KEYS: frozenset[str] = frozenset({"layout", "colors", "font_style", "hierarchy"})

    def validate(
        self,
        design_decision: dict | None,
        qa_result: dict | None,
    ) -> tuple[dict, dict]:
        """Validate inputs and return (design_decision, qa_result) unchanged.

        Raises:
            ValueError: if design_decision is None or empty, missing required keys,
                        or if qa_result is None, empty, missing 'issues', or has empty issues.
        """
        if not design_decision:
            raise ValueError(
                "design_decision must be a non-empty dict, got: "
                f"{design_decision!r}"
            )

        missing = self.REQUIRED_DESIGN_KEYS - design_decision.keys()
        if missing:
            raise ValueError(
                f"design_decision is missing required key(s): {sorted(missing)}."
            )

        if not qa_result:
            raise ValueError(
                "qa_result must be a non-empty dict, got: "
                f"{qa_result!r}"
            )

        if "issues" not in qa_result:
            raise ValueError(
                "qa_result must contain an 'issues' key."
            )

        if not qa_result["issues"]:
            raise ValueError(
                "qa_result['issues'] must not be empty — there are no issues to fix."
            )

        return (design_decision, qa_result)


class ImprovementPromptBuilder:
    """Constructs LLM prompts for targeted poster design improvements."""

    SYSTEM_PROMPT = (
        "You are a professional graphic design assistant specialised in event poster design. "
        "Your role is to make minimal, targeted corrections to an existing design decision "
        "based on QA feedback — fixing only the reported issues while preserving all other "
        "design choices. You always respond with pure JSON and nothing else."
    )

    # Maps issue types to the fields they affect
    _ISSUE_TO_FIELDS: dict[str, frozenset[str]] = {
        "color_contrast": frozenset({"colors"}),
        "alignment": frozenset({"layout"}),
        "text_readability": frozenset({"hierarchy", "font_style"}),
        "unclear_information": frozenset({"hierarchy", "font_style"}),
        "missing_information": frozenset({"hierarchy"}),
    }

    _ALL_FIELDS: frozenset[str] = frozenset({"layout", "colors", "font_style", "hierarchy"})

    def _derive_unchanged_fields(self, issues: list[dict]) -> frozenset[str]:
        """Return the set of fields that should remain unchanged given the issue types."""
        affected: set[str] = set()
        for issue in issues:
            issue_type = issue.get("type", "")
            affected |= self._ISSUE_TO_FIELDS.get(issue_type, set())
        return self._ALL_FIELDS - affected

    def build(self, design_decision: dict, qa_result: dict) -> str:
        """Build the user prompt embedding design_decision, QA issues, schema, and constraints."""
        serialized_design = json.dumps(design_decision, ensure_ascii=False, indent=2)
        issues = qa_result.get("issues", [])
        serialized_issues = json.dumps(issues, ensure_ascii=False, indent=2)
        unchanged_fields = sorted(self._derive_unchanged_fields(issues))

        unchanged_note = (
            f"Fields that MUST remain unchanged: {unchanged_fields}."
            if unchanged_fields
            else "All fields may be adjusted to address the reported issues."
        )

        prompt = f"""You are given the following existing poster design decision JSON:

{serialized_design}

The QA agent has reported the following issues that must be fixed:

{serialized_issues}

Your task is to produce a minimally-corrected design decision that resolves the reported issues.

Issue-to-field mapping guidance:
- color_contrast issues → adjust "colors"
- text_readability or unclear_information issues → adjust "hierarchy" or "font_style"
- alignment issues → adjust "layout"
- missing_information issues → adjust "hierarchy"

Minimal-change constraint:
- Modify ONLY the fields necessary to address the reported issues.
- Preserve all other fields exactly as they appear in the original design decision.
- {unchanged_note}

Return a JSON object with exactly these fields:

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
- "hierarchy" must contain exactly the keys "primary", "secondary", "tertiary" with non-empty string values

Return ONLY the JSON object described above. Do not include markdown fences, explanations, or any text outside the JSON."""

        return prompt

    def build_with_correction(
        self,
        design_decision: dict,
        qa_result: dict,
        error_message: str,
    ) -> str:
        """Build a prompt with a correction hint appended for retry attempts."""
        base_prompt = self.build(design_decision, qa_result)
        correction = (
            f"\n\nYour previous response was invalid. Error: {error_message}\n"
            "Please correct the issues described above and return a valid JSON object."
        )
        return base_prompt + correction


class ImprovementOutputValidator:
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


class PosterDesignImprovementAgent:
    """Orchestrates LLM-driven targeted improvements to poster design decisions.

    Reads a previous DesignDecision and QA issues, calls the LLM to produce a
    minimally-corrected design, and returns an AgentResult. Compatible with the
    LangGraph node interface via the run() method.
    """

    def __init__(self, dry_run: bool = False, max_retries: int = 2) -> None:
        self.dry_run = dry_run
        self.max_retries = max_retries
        self._input_validator = ImprovementInputValidator()
        self._prompt_builder = ImprovementPromptBuilder()
        self._output_validator = ImprovementOutputValidator()
        self._llm = LLMClient(dry_run=dry_run)

    def improve(self, design_decision: dict | None, qa_result: dict | None) -> AgentResult:
        """Produce a minimally-corrected design decision that resolves QA issues.

        Args:
            design_decision: The existing design decision dict (layout, colors, font_style, hierarchy).
            qa_result: The QA agent output dict containing 'issues' and 'verdict'.

        Returns:
            AgentResult with success=True and data["improved_design"] on success,
            or success=False and a non-empty error string on failure.
            Never raises.
        """
        # Short-circuit: if QA passed, return original design unchanged
        if isinstance(qa_result, dict) and qa_result.get("verdict") == "pass":
            return AgentResult(success=True, data={"improved_design": design_decision})

        # dry_run: return stub without calling LLM
        if self.dry_run:
            return AgentResult(success=True, data={"improved_design": design_decision})

        # Validate inputs
        try:
            self._input_validator.validate(design_decision, qa_result)
        except ValueError as exc:
            return AgentResult(success=False, error=str(exc))

        # Retry loop
        last_error: str = ""
        prompt = self._prompt_builder.build(design_decision, qa_result)

        for attempt in range(self.max_retries):
            try:
                raw = self._llm.generate_json(
                    prompt,
                    system=ImprovementPromptBuilder.SYSTEM_PROMPT,
                )
                decision = self._output_validator.validate(raw)
                return AgentResult(success=True, data={"improved_design": decision.to_dict()})

            except ValidationError as exc:
                last_error = str(exc)
                if attempt + 1 < self.max_retries:
                    prompt = self._prompt_builder.build_with_correction(
                        design_decision, qa_result, last_error
                    )

            except json.JSONDecodeError as exc:
                last_error = str(exc)
                # rebuild base prompt for next attempt (no correction hint for JSON errors)
                prompt = self._prompt_builder.build(design_decision, qa_result)

            except Exception as exc:
                # API-level error — do not retry
                return AgentResult(success=False, error=str(exc))

        return AgentResult(
            success=False,
            error=f"Exhausted {self.max_retries} retries. Last error: {last_error}",
        )

    def run(self, state: dict) -> dict:
        """LangGraph-compatible node interface.

        Reads design_decision and qa_result from state, calls improve(), and
        writes the improved design back to state on success.

        Args:
            state: LangGraph state dict with 'design_decision' and 'qa_result' keys.

        Returns:
            Updated state dict (design_decision overwritten only on success).
        """
        design_decision = state.get("design_decision")
        qa_result = state.get("qa_result")

        result = self.improve(design_decision, qa_result)

        if result.success:
            state["design_decision"] = result.data["improved_design"]

        return state
