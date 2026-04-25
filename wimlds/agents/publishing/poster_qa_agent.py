"""Poster QA Agent — performs automated visual quality assurance on generated event poster images."""
from dataclasses import dataclass, field


class ValidationError(Exception):
    """Raised by QAOutputValidator when LLM output violates schema constraints."""


@dataclass
class QAIssue:
    type: str
    description: str
    severity: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class QAResult:
    issues: list[QAIssue] = field(default_factory=list)
    verdict: str = "pass"

    def to_dict(self) -> dict:
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "verdict": self.verdict,
        }


import os


class ImageInputValidator:
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg"})

    def validate(self, poster_image: "str | bytes | None") -> bytes:
        """
        Returns image bytes if valid.
        Raises ValueError with a descriptive message on any violation.
        Does not mutate the poster_image argument.
        """
        if poster_image is None:
            raise ValueError("poster_image must not be None")

        if isinstance(poster_image, bytes):
            if len(poster_image) == 0:
                raise ValueError("poster_image bytes must not be empty")
            return poster_image

        if isinstance(poster_image, str):
            if poster_image == "":
                raise ValueError("poster_image must not be an empty string")
            _, ext = os.path.splitext(poster_image)
            if ext.lower() not in self.ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"Unsupported file extension '{ext}'. "
                    f"Allowed extensions: {sorted(self.ALLOWED_EXTENSIONS)}"
                )
            if not os.path.exists(poster_image):
                raise ValueError(f"File not found: {poster_image}")
            with open(poster_image, "rb") as f:
                return f.read()

        raise ValueError(
            f"poster_image must be a str path or bytes, got {type(poster_image).__name__}"
        )


import base64


class QAPromptBuilder:
    SYSTEM_PROMPT: str = (
        "You are a visual quality assurance expert for event posters. "
        "Evaluate the provided poster image and return a strict JSON object with your findings. "
        "Be critical and only flag real, observable issues — do not invent problems that are not visible."
    )

    def build(self, image_bytes: bytes) -> str:
        """
        Returns the full prompt string with the image embedded as base64.
        Includes schema, enum lists, evaluation criteria, and verdict rules.
        """
        encoded = base64.b64encode(image_bytes).decode("utf-8")

        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            "## Poster Image (base64-encoded)\n"
            f"{encoded}\n\n"
            "## Evaluation Criteria\n"
            "Evaluate the poster across all four quality dimensions:\n"
            "1. **Text Readability**: Check font size, contrast, and legibility of all text elements.\n"
            "2. **Element Alignment**: Check visual balance and grid consistency of all design elements.\n"
            "3. **Color Contrast**: Check WCAG-style foreground/background contrast for all text and key elements.\n"
            "4. **Information Completeness**: Verify the presence of event name, date, venue, and speaker.\n\n"
            "## Output JSON Schema\n"
            "Return a JSON object with exactly these two top-level keys:\n"
            "- `issues`: a list of issue objects (may be empty)\n"
            "- `verdict`: overall result — one of: `pass`, `fail`\n\n"
            "Each issue object must have exactly these keys:\n"
            "- `type`: one of `text_readability`, `alignment`, `color_contrast`, `missing_information`, `unclear_information`\n"
            "- `description`: a human-readable description of the issue\n"
            "- `severity`: one of `low`, `medium`, `high`\n\n"
            "## Verdict Determination Rules\n"
            "- Set verdict to `fail` if any issue has severity `high` or `medium`.\n"
            "- Set verdict to `pass` only if all issues are `low` severity or the issues list is empty.\n\n"
            "## Instructions\n"
            "- Be critical and only flag real, observable issues visible in the poster.\n"
            "- Return pure JSON with no markdown fences, no explanation, and no additional text.\n"
            "- The response must be valid JSON that can be parsed directly.\n"
        )

    def build_with_correction(self, image_bytes: bytes, error_message: str) -> str:
        """
        Returns the full prompt with a correction hint appended.
        """
        base = self.build(image_bytes)
        return (
            base
            + "\n## Correction Required\n"
            + f"Your previous response was invalid. Error: {error_message}\n"
            + "Please fix the issue and return a valid JSON response matching the schema above.\n"
        )


class QAOutputValidator:
    VALID_ISSUE_TYPES: frozenset = frozenset({
        "text_readability",
        "alignment",
        "color_contrast",
        "missing_information",
        "unclear_information",
    })
    VALID_SEVERITIES: frozenset = frozenset({"low", "medium", "high"})
    VALID_VERDICTS: frozenset = frozenset({"pass", "fail"})
    REQUIRED_ISSUE_KEYS: frozenset = frozenset({"type", "description", "severity"})

    def validate(self, raw) -> QAResult:
        """
        Validates the LLM's raw dict output against the required schema and enum constraints.
        Raises ValidationError if any constraint is violated.
        Returns a populated QAResult dataclass.
        Does not mutate the input dict.
        """
        if not isinstance(raw, dict):
            raise ValidationError(
                f"Expected a dict, got {type(raw).__name__}"
            )

        for key in ("issues", "verdict"):
            if key not in raw:
                raise ValidationError(f"Missing required key: {key}")

        verdict = str(raw["verdict"]).strip().lower()
        if verdict not in self.VALID_VERDICTS:
            raise ValidationError(
                f"Invalid verdict: '{verdict}'. Must be one of {sorted(self.VALID_VERDICTS)}."
            )

        issues_raw = raw["issues"]
        if not isinstance(issues_raw, list):
            raise ValidationError(
                f"'issues' must be a list, got {type(issues_raw).__name__}"
            )

        issues = []
        for item in issues_raw:
            if not isinstance(item, dict):
                raise ValidationError(
                    f"Each issue must be a dict, got {type(item).__name__}"
                )
            for key in self.REQUIRED_ISSUE_KEYS:
                if key not in item:
                    raise ValidationError(f"Issue missing required key: '{key}'")

            issue_type = str(item["type"]).strip().lower()
            if issue_type not in self.VALID_ISSUE_TYPES:
                raise ValidationError(
                    f"Invalid issue type: '{issue_type}'. Must be one of {sorted(self.VALID_ISSUE_TYPES)}."
                )

            severity = str(item["severity"]).strip().lower()
            if severity not in self.VALID_SEVERITIES:
                raise ValidationError(
                    f"Invalid severity: '{severity}'. Must be one of {sorted(self.VALID_SEVERITIES)}."
                )

            issues.append(QAIssue(
                type=issue_type,
                description=str(item["description"]).strip(),
                severity=severity,
            ))

        return QAResult(issues=issues, verdict=verdict)


import json


class PosterQAAgent:
    """
    Orchestrates the full QA pipeline:
    ImageInputValidator → QAPromptBuilder → LLMClient → QAOutputValidator

    Returns AgentResult — never raises to the caller.
    """

    def __init__(self, dry_run: bool = False, max_retries: int = 2) -> None:
        from wimlds.integrations.llm.llm_client import LLMClient

        self.dry_run = dry_run
        self.max_retries = max_retries
        self._input_validator = ImageInputValidator()
        self._prompt_builder = QAPromptBuilder()
        self._output_validator = QAOutputValidator()
        self._llm = LLMClient(dry_run=dry_run)

    def evaluate(self, poster_image: "str | bytes") -> "AgentResult":
        """
        Evaluate a poster image for visual quality issues.
        Returns AgentResult with data={"qa_result": {"issues": [...], "verdict": "pass"|"fail"}}.
        Never raises.
        """
        from wimlds.core.result import AgentResult

        # Dry-run: return stub without calling LLM
        if self.dry_run:
            return AgentResult(
                success=True,
                data={"qa_result": {"issues": [], "verdict": "pass"}},
            )

        try:
            # Step 1: Validate input
            try:
                image_bytes = self._input_validator.validate(poster_image)
            except ValueError as exc:
                return AgentResult(success=False, error=str(exc))

            # Step 2: Build initial prompt
            prompt = self._prompt_builder.build(image_bytes)

            # Step 3: Retry loop
            attempt = 0
            last_error = ""
            while attempt < self.max_retries:
                try:
                    raw_dict = self._llm.generate_json(
                        prompt,
                        max_tokens=1024,
                        system=QAPromptBuilder.SYSTEM_PROMPT,
                    )
                    qa_result = self._output_validator.validate(raw_dict)
                    return AgentResult(
                        success=True,
                        data={"qa_result": qa_result.to_dict()},
                    )
                except ValidationError as exc:
                    last_error = str(exc)
                    attempt += 1
                    if attempt < self.max_retries:
                        prompt = self._prompt_builder.build_with_correction(
                            image_bytes, last_error
                        )
                except json.JSONDecodeError as exc:
                    last_error = str(exc)
                    attempt += 1
                except Exception as exc:
                    # API-level or unexpected error — no retry
                    return AgentResult(success=False, error=str(exc))

            return AgentResult(
                success=False,
                error=f"QA evaluation failed after {self.max_retries} attempts: {last_error}",
            )

        except Exception as exc:
            return AgentResult(success=False, error=str(exc))

    def run(self, state: dict) -> dict:
        """
        LangGraph node interface.
        Reads state["_poster_local_path"], writes state["qa_result"] on success.
        """
        poster_image = state.get("_poster_local_path")
        result = self.evaluate(poster_image)
        updated = dict(state)
        if result.success:
            updated["qa_result"] = result.data["qa_result"]
        return updated
