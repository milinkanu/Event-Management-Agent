"""Content Extraction Agent — extracts structured event fields from unstructured input."""
import json
from dataclasses import dataclass, field


class ValidationError(Exception):
    """Raised when LLM output does not satisfy the required schema constraints."""


@dataclass
class ExtractedEvent:
    event_name: str
    date_time: str
    venue: str
    organizer: str
    audience: str
    vibe: str  # one of VALID_VIBES
    key_highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event_name": self.event_name,
            "date_time": self.date_time,
            "venue": self.venue,
            "organizer": self.organizer,
            "audience": self.audience,
            "vibe": self.vibe,
            "key_highlights": self.key_highlights,
        }


class InputNormalizer:
    def normalize(self, raw_input: str | dict) -> str:
        """
        - dict  → JSON-serialized string
        - str   → stripped as-is
        - other → str(raw_input)
        Returns a non-empty string or raises ValueError.
        """
        if raw_input is None:
            raise ValueError("Input must not be None")
        if isinstance(raw_input, str):
            result = raw_input.strip()
            if not result:
                raise ValueError("Input string must not be empty")
            return result
        if isinstance(raw_input, dict):
            if not raw_input:
                raise ValueError("Input dict must not be empty")
            return json.dumps(raw_input)
        return str(raw_input)


class PromptBuilder:
    SYSTEM_PROMPT: str = (
        "You are a structured data extraction assistant. "
        "Your sole task is to extract event information from the provided text and return it as a JSON object. "
        "Return pure JSON only — no markdown fences, no explanation, no prose. "
        "Output nothing except the JSON object."
    )

    _PROMPT_TEMPLATE = """\
Extract the event details from the text below and return a JSON object with exactly these fields:

{{
  "event_name":     "string — full event title",
  "date_time":      "string — ISO-like or natural language date/time",
  "venue":          "string — location name and/or address",
  "organizer":      "string — person or organization running the event",
  "audience":       "string — target audience description",
  "vibe":           "formal | corporate | fun | party | tech | minimal | luxury",
  "key_highlights": ["string", "..."]
}}

Rules:
- "vibe" must be exactly one of: formal, corporate, fun, party, tech, minimal, luxury
- "key_highlights" must be a JSON array of strings (may be empty)
- Return pure JSON only — no markdown fences, no explanation, no extra text

Event text:
{event_text}"""

    def build(self, event_text: str) -> str:
        """
        Returns the full user prompt string.
        Embeds event_text into the template.
        """
        return self._PROMPT_TEMPLATE.format(event_text=event_text)

    def build_with_correction(self, event_text: str, error_message: str) -> str:
        """
        Returns the full user prompt with a correction hint appended.
        """
        base = self.build(event_text)
        return (
            f"{base}\n\n"
            f"Correction hint: Your previous response was invalid. "
            f"Error: {error_message}. "
            f"Please fix the issue and return valid JSON only."
        )


class OutputValidator:
    REQUIRED_KEYS: frozenset[str] = frozenset(
        {"event_name", "date_time", "venue", "organizer", "audience", "vibe", "key_highlights"}
    )
    VALID_VIBES: frozenset[str] = frozenset(
        {"formal", "corporate", "fun", "party", "tech", "minimal", "luxury"}
    )

    def validate(self, raw: dict) -> "ExtractedEvent":
        """
        Raises ValidationError if:
        - input is not a dict
        - any required key is missing
        - vibe is not in VALID_VIBES
        Returns a validated ExtractedEvent dataclass.
        Does not mutate the input dict.
        """
        if not isinstance(raw, dict):
            raise ValidationError("LLM returned non-dict output")

        for key in self.REQUIRED_KEYS:
            if key not in raw:
                raise ValidationError(f"Missing required key: {key}")

        vibe = raw["vibe"].strip().lower()
        if vibe not in self.VALID_VIBES:
            raise ValidationError(
                f"Invalid vibe: {vibe}. Must be one of: {self.VALID_VIBES}"
            )

        highlights = raw["key_highlights"]
        if not isinstance(highlights, list):
            highlights = [str(highlights)]

        return ExtractedEvent(
            event_name=raw["event_name"].strip(),
            date_time=raw["date_time"].strip(),
            venue=raw["venue"].strip(),
            organizer=raw["organizer"].strip(),
            audience=raw["audience"].strip(),
            vibe=vibe,
            key_highlights=[str(h).strip() for h in highlights],
        )


class ContentExtractionAgent:
    """
    Orchestrates the full extraction pipeline:
    InputNormalizer → PromptBuilder → LLMClient → OutputValidator

    Returns AgentResult — never raises to the caller.
    """

    def __init__(self, dry_run: bool = False, max_retries: int = 2) -> None:
        from wimlds.integrations.llm.llm_client import LLMClient

        self.dry_run = dry_run
        self.max_retries = max_retries
        self._normalizer = InputNormalizer()
        self._prompt_builder = PromptBuilder()
        self._llm = LLMClient(dry_run=dry_run)
        self._validator = OutputValidator()

    def extract(self, raw_input) -> "AgentResult":
        """
        Extract event fields from raw_input.

        Returns AgentResult with data={"extracted_event": dict} on success,
        or AgentResult(success=False, error=...) on any failure.
        Never raises.
        """
        from wimlds.core.result import AgentResult

        try:
            # Step 1: Normalize — raises ValueError on empty/None input
            try:
                event_text = self._normalizer.normalize(raw_input)
            except ValueError as exc:
                return AgentResult(success=False, error=str(exc))

            # Step 2: Build initial prompt
            prompt = self._prompt_builder.build(event_text)

            # Step 3: Retry loop
            attempt = 0
            while attempt < self.max_retries:
                try:
                    raw_dict = self._llm.generate_json(
                        prompt,
                        max_tokens=512,
                        system=PromptBuilder.SYSTEM_PROMPT,
                    )
                    extracted = self._validator.validate(raw_dict)
                    return AgentResult(
                        success=True,
                        data={"extracted_event": extracted.to_dict()},
                    )
                except ValidationError as exc:
                    attempt += 1
                    if attempt < self.max_retries:
                        prompt = self._prompt_builder.build_with_correction(
                            event_text, str(exc)
                        )
                except json.JSONDecodeError:
                    attempt += 1

            return AgentResult(
                success=False,
                error=f"Extraction failed after {self.max_retries} attempts",
            )

        except Exception as exc:
            # API-level or any unexpected error — no retry
            from wimlds.core.result import AgentResult
            return AgentResult(success=False, error=str(exc))

    def run(self, state: dict) -> dict:
        """
        LangGraph node interface.
        Reads state["raw_event_input"], writes state["extracted_event"] on success.
        """
        raw_input = state.get("raw_event_input")
        result = self.extract(raw_input)
        updated = dict(state)
        if result.success:
            updated["extracted_event"] = result.data["extracted_event"]
        return updated
