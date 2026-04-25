"""Poster Learning Agent — observes poster design outcomes and builds a simple pattern memory."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from wimlds.core.result import AgentResult  # noqa: F401  (used by later components)


class ValidationError(Exception):
    """Raised by InsightOutputValidator when the LLM output violates the required schema."""


@dataclass
class FeedbackRecord:
    """A single observation stored in pattern memory."""

    design_snapshot: dict  # {"layout": str, "colors": any}
    feedback: str          # "approved" or "rejected"
    timestamp: str         # ISO-8601 string

    def to_dict(self) -> dict:
        return {
            "design_snapshot": self.design_snapshot,
            "feedback":        self.feedback,
            "timestamp":       self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeedbackRecord":
        return cls(
            design_snapshot=d["design_snapshot"],
            feedback=d["feedback"],
            timestamp=d["timestamp"],
        )


class PatternStore:
    """Persists FeedbackRecord entries in memory (and optionally to a JSON file)."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file_path = file_path
        self._records: list[FeedbackRecord] = []
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                self._records = [FeedbackRecord.from_dict(d) for d in json.loads(content)]

    def append(self, record: FeedbackRecord) -> None:
        """Append a record to the in-memory store and persist if file_path is set."""
        self._records.append(record)
        if self._file_path:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._records], f, indent=2)

    def get_summary(self) -> dict:
        """Return a PatternSummary dict with counts grouped by layout and colors."""
        by_layout: dict[str, dict[str, int]] = {}
        by_colors: dict[str, dict[str, int]] = {}

        for record in self._records:
            layout = record.design_snapshot.get("layout", "")
            colors = record.design_snapshot.get("colors")
            colors_key = json.dumps(colors, sort_keys=True) if not isinstance(colors, str) else colors
            fb = record.feedback  # "approved" or "rejected"

            if layout not in by_layout:
                by_layout[layout] = {"approved": 0, "rejected": 0}
            by_layout[layout][fb] = by_layout[layout].get(fb, 0) + 1

            if colors_key not in by_colors:
                by_colors[colors_key] = {"approved": 0, "rejected": 0}
            by_colors[colors_key][fb] = by_colors[colors_key].get(fb, 0) + 1

        return {
            "total": len(self._records),
            "by_layout": by_layout,
            "by_colors": by_colors,
        }

    def __len__(self) -> int:
        """Return the number of stored records."""
        return len(self._records)


class InputNormalizer:
    def normalize(self, design_json: dict, feedback: str) -> tuple[dict, str]:
        """
        Validates design_json (non-None, non-empty, has 'layout' and 'colors').
        Normalises feedback to lowercase and validates it is 'approved' or 'rejected'.
        Returns (design_json, normalised_feedback).
        Raises ValueError with a descriptive message on any violation.
        Does not mutate the inputs.
        """
        if design_json is None or design_json == {}:
            raise ValueError("design_json must be a non-empty dict")
        if "layout" not in design_json:
            raise ValueError("design_json is missing required key: layout")
        if "colors" not in design_json:
            raise ValueError("design_json is missing required key: colors")
        norm_feedback = feedback.strip().lower()
        if norm_feedback not in {"approved", "rejected"}:
            raise ValueError(
                f"feedback must be 'approved' or 'rejected', got: {feedback}"
            )
        return design_json, norm_feedback


class InsightBuilder:
    """Constructs the LLM prompt from a PatternSummary and provides a correction variant."""

    SYSTEM_PROMPT: str = (
        "You are a poster design advisor. "
        "Analyse the provided design feedback data and respond with a JSON object only. "
        "Do not include markdown fences, code blocks, or any explanation outside the JSON. "
        "Use plain, everyday language — avoid technical or machine-learning terminology. "
        "Your response must contain exactly two keys: "
        '"insight" (a concise observation about what has worked or not worked) and '
        '"future_adjustment" (a concrete recommendation for the next poster design).'
    )

    def build_prompt(self, summary: dict) -> str:
        """
        Embed the PatternSummary in a prompt asking for insight + future_adjustment.
        Instructs the LLM to use plain language, no ML jargon, pure JSON only.
        """
        summary_json = json.dumps(summary, indent=2)
        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            "Here is the poster design feedback data collected so far:\n\n"
            f"{summary_json}\n\n"
            "Based on this data, respond with a JSON object containing exactly these two keys:\n"
            '  "insight": a plain-language observation about which layouts or colour combinations '
            "tend to be approved or rejected,\n"
            '  "future_adjustment": a plain-language recommendation for the next poster design.\n\n'
            "Return pure JSON only — no markdown fences, no extra text."
        )

    def build_with_correction(self, summary: dict, error_message: str) -> str:
        """
        Returns the base prompt with the previous error appended as a correction hint.
        """
        base = self.build_prompt(summary)
        return (
            f"{base}\n\n"
            "Your previous response was invalid. Please correct the following error and try again:\n"
            f"{error_message}"
        )


class InsightOutputValidator:
    """Validates the LLM's raw dict against {"insight": str, "future_adjustment": str}."""

    REQUIRED_KEYS: frozenset = frozenset({"insight", "future_adjustment"})

    def validate(self, raw: dict) -> dict:
        """
        Raises ValidationError if any schema constraint is violated.
        Returns the validated dict unchanged on success.
        Does not mutate the input dict.
        """
        if not isinstance(raw, dict):
            raise ValidationError(
                f"Expected a dict, got {type(raw).__name__}"
            )
        for key in self.REQUIRED_KEYS:
            if key not in raw:
                raise ValidationError(f"Missing required key: {key}")
            if raw[key] == "":
                raise ValidationError(f"Value for '{key}' must be non-empty")
        return raw


class PosterLearningAgent:
    """Orchestrates the full learning pipeline; public API for callers and LangGraph nodes."""

    def __init__(
        self,
        dry_run: bool = False,
        max_retries: int = 2,
        store_path: Optional[str] = None,
    ) -> None:
        from datetime import datetime as _datetime  # noqa: F401 — ensure stdlib available
        self._dry_run = dry_run
        self._max_retries = max_retries
        self._normalizer = InputNormalizer()
        self._store = PatternStore(file_path=store_path)
        self._insight_builder = InsightBuilder()
        self._validator = InsightOutputValidator()
        from wimlds.integrations.llm.llm_client import LLMClient
        self._llm = LLMClient(dry_run=dry_run)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def learn(self, design_json: dict, feedback: str) -> "AgentResult":
        """
        Record the design outcome and produce an insight.
        Returns AgentResult with data={"insight": str, "future_adjustment": str} on success.
        Never raises.
        """
        import json as _json
        from datetime import datetime

        try:
            # Step 1: Validate and normalise inputs
            try:
                snapshot, norm_feedback = self._normalizer.normalize(design_json, feedback)
            except ValueError as e:
                return AgentResult(success=False, error=str(e))

            # Step 2: Store the record
            record = FeedbackRecord(
                design_snapshot={"layout": snapshot["layout"], "colors": snapshot["colors"]},
                feedback=norm_feedback,
                timestamp=datetime.utcnow().isoformat(),
            )
            self._store.append(record)

            # Step 3: Dry-run early exit (after storing)
            if self._dry_run:
                return AgentResult(
                    success=True,
                    data={"insight": "dry-run", "future_adjustment": "dry-run"},
                )

            # Step 4: Early-exit if not enough data
            if len(self._store) < 2:
                return AgentResult(
                    success=True,
                    data={
                        "insight": "Not enough data yet — keep submitting feedback.",
                        "future_adjustment": "",
                    },
                )

            # Step 5: Build prompt from pattern summary
            summary = self._store.get_summary()
            prompt = self._insight_builder.build_prompt(summary)

            # Step 6: Retry loop
            attempt = 0
            while attempt < self._max_retries:
                try:
                    raw_dict = self._llm.generate_json(prompt)
                    validated = self._validator.validate(raw_dict)
                    return AgentResult(success=True, data=validated)
                except ValidationError as e:
                    attempt += 1
                    if attempt < self._max_retries:
                        prompt = self._insight_builder.build_with_correction(summary, str(e))
                except _json.JSONDecodeError:
                    attempt += 1
                except Exception as e:
                    return AgentResult(success=False, error=str(e))

            return AgentResult(
                success=False,
                error=f"Insight generation failed after {self._max_retries} attempts",
            )

        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def run(self, state: dict) -> dict:
        """
        LangGraph node interface.
        Reads state["design_json"] and state["feedback"].
        Writes state["learning_insight"] on success.
        Returns updated state dict in all cases.
        Never raises.
        """
        try:
            design_json = state.get("design_json")
            feedback = state.get("feedback")
            result = self.learn(design_json, feedback)
            if result.success:
                state = dict(state)
                state["learning_insight"] = result.data
        except Exception:
            pass
        return state
