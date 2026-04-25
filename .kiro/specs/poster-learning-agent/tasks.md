# Implementation Plan: Poster Learning Agent

## Overview

Implement the `PosterLearningAgent` in Python following the same
`InputNormalizer → PromptBuilder → LLMClient → OutputValidator → AgentResult`
architecture used by `BrandIntelligenceAgent`.
The agent lives at `wimlds/agents/publishing/poster_learning_agent.py` and is
a drop-in LangGraph node for the publishing pipeline.

## Tasks

- [x] 1. Create module skeleton, `ValidationError`, `FeedbackRecord`, and `DesignSnapshot`
  - Create `wimlds/agents/publishing/poster_learning_agent.py`
  - Define `ValidationError(Exception)` at module level
  - Define `FeedbackRecord` dataclass with fields `design_snapshot: dict`, `feedback: str`, `timestamp: str`
  - Implement `FeedbackRecord.to_dict() -> dict` returning exactly `design_snapshot`, `feedback`, `timestamp`
  - Implement `FeedbackRecord.from_dict(cls, d: dict) -> FeedbackRecord` classmethod
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 2. Implement `PatternStore`
  - [x] 2.1 Write `PatternStore` class in `poster_learning_agent.py`
    - `__init__(self, file_path: Optional[str] = None)`: initialise empty in-memory list; load from file if path given
    - `append(record: FeedbackRecord) -> None`: add to list; persist to file if path configured
    - `get_summary() -> dict`: return `{"total": int, "by_layout": {...}, "by_colors": {...}}` with approved/rejected counts
    - `__len__() -> int`: return number of stored records
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [ ]* 2.2 Write property test for `PatternStore` — Property 5: Records are never lost on append
    - **Property 5: PatternStore records are never lost on append**
    - **Validates: Requirements 2.7**

  - [ ]* 2.3 Write property test for `PatternStore` — Property 6: get_summary() counts correctly by layout and colors
    - **Property 6: get_summary() counts correctly by layout and colors**
    - **Validates: Requirements 2.5, 2.6**

  - [ ]* 2.4 Write property test for `PatternStore` — Property 7: File round-trip preserves all records
    - **Property 7: PatternStore file round-trip preserves all records**
    - **Validates: Requirements 2.8, 2.9**

  - [ ]* 2.5 Write property test for `FeedbackRecord` — Property 18: Serialization round-trip
    - **Property 18: FeedbackRecord serialization round-trip**
    - **Validates: Requirements 9.1, 9.3**

  - [ ]* 2.6 Write property test for `FeedbackRecord` — Property 19: to_dict() key set is exactly the output contract
    - **Property 19: FeedbackRecord.to_dict() key set is exactly the output contract**
    - **Validates: Requirements 9.2**

- [x] 3. Implement `InputNormalizer`
  - [x] 3.1 Write `InputNormalizer.normalize()` in `poster_learning_agent.py`
    - Accept `design_json: dict` and `feedback: str`
    - Raise `ValueError` if `design_json` is `None` or empty dict
    - Raise `ValueError` if `design_json` is missing `layout` or `colors` key (identify the missing key in the message)
    - Normalise `feedback` to lowercase; raise `ValueError` if not `"approved"` or `"rejected"`
    - Never mutate the inputs
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 3.2 Write property test for `InputNormalizer` — Property 1: Valid inputs are accepted without error
    - **Property 1: Valid inputs are accepted without error**
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 3.3 Write property test for `InputNormalizer` — Property 2: Invalid feedback strings are always rejected
    - **Property 2: Invalid feedback strings are always rejected**
    - **Validates: Requirements 1.6**

- [x] 4. Implement `InsightBuilder`
  - [x] 4.1 Write `InsightBuilder` class in `poster_learning_agent.py`
    - Define `SYSTEM_PROMPT` class-level constant
    - `build_prompt(summary: dict) -> str`: embed JSON-serialised summary; instruct LLM to return `{"insight": ..., "future_adjustment": ...}`; plain language, no ML jargon, pure JSON only
    - `build_with_correction(summary: dict, error_message: str) -> str`: base prompt + correction hint
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 Write property test for `InsightBuilder` — Property 8: Every prompt contains all required structural elements
    - **Property 8: Every InsightBuilder prompt contains all required structural elements**
    - **Validates: Requirements 3.2, 3.3, 3.5**

  - [ ]* 4.3 Write property test for `InsightBuilder` — Property 9: Correction prompt contains both summary and error hint
    - **Property 9: Correction prompt contains both summary and error hint**
    - **Validates: Requirements 5.1**

- [x] 5. Implement `InsightOutputValidator`
  - [x] 5.1 Write `InsightOutputValidator` class in `poster_learning_agent.py`
    - Define `REQUIRED_KEYS: frozenset = frozenset({"insight", "future_adjustment"})`
    - `validate(raw: dict) -> dict`: raise `ValidationError` for non-dict, missing keys, or empty string values; return dict unchanged on success; never mutate input
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 5.2 Write property test for `InsightOutputValidator` — Property 10: Valid dicts are returned unchanged
    - **Property 10: Valid dicts are returned unchanged by InsightOutputValidator**
    - **Validates: Requirements 4.1**

  - [ ]* 5.3 Write property test for `InsightOutputValidator` — Property 11: Non-dict inputs always fail validation
    - **Property 11: Non-dict inputs always fail InsightOutputValidator**
    - **Validates: Requirements 4.2**

  - [ ]* 5.4 Write property test for `InsightOutputValidator` — Property 12: validate() never mutates its input dict
    - **Property 12: validate() never mutates its input dict**
    - **Validates: Requirements 4.7**

- [x] 6. Checkpoint — Ensure all component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement `PosterLearningAgent` orchestrator
  - [x] 7.1 Write `PosterLearningAgent` class in `poster_learning_agent.py`
    - `__init__(self, dry_run: bool = False, max_retries: int = 2, store_path: Optional[str] = None)`: instantiate `InputNormalizer`, `PatternStore`, `InsightBuilder`, `LLMClient`, `InsightOutputValidator`
    - `learn(design_json: dict, feedback: str) -> AgentResult`: implement the main learning algorithm (normalize → store → early-exit if < 2 records → build prompt → retry loop)
    - In dry-run mode: store the record but return `AgentResult(success=True, data={"insight": "dry-run", "future_adjustment": "dry-run"})` without calling the LLM
    - `run(state: dict) -> dict`: read `state["design_json"]` and `state["feedback"]`; call `learn()`; write `state["learning_insight"]` only on success; return updated state in all cases
    - Never raise to the caller
    - _Requirements: 1.7, 3.1, 3.6, 3.7, 4.1–4.7, 5.1–5.5, 6.1–6.4, 7.1–7.4, 8.1–8.6_

  - [ ]* 7.2 Write property test for `PosterLearningAgent` — Property 3: learn() never mutates its inputs
    - **Property 3: learn() never mutates its inputs**
    - **Validates: Requirements 1.7, 7.4**

  - [ ]* 7.3 Write property test for `PosterLearningAgent` — Property 4: Each valid learn() call grows the store by exactly one record with correct fields
    - **Property 4: Each valid learn() call grows the store by exactly one record with correct fields**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [ ]* 7.4 Write property test for `PosterLearningAgent` — Property 13: Retry count never exceeds max_retries
    - **Property 13: Retry count never exceeds max_retries**
    - **Validates: Requirements 5.2, 5.3, 5.4**

  - [ ]* 7.5 Write property test for `PosterLearningAgent` — Property 14: learn() never raises under any input
    - **Property 14: learn() never raises under any input**
    - **Validates: Requirements 6.1, 7.1**

  - [ ]* 7.6 Write property test for `PosterLearningAgent` — Property 15: Failure results always carry a non-empty error string
    - **Property 15: Failure results always carry a non-empty error string**
    - **Validates: Requirements 6.4, 7.3**

  - [ ]* 7.7 Write property test for `PosterLearningAgent.run()` — Property 16: run() writes learning_insight to state on success
    - **Property 16: run() writes learning_insight to state on success**
    - **Validates: Requirements 8.3**

  - [ ]* 7.8 Write property test for `PosterLearningAgent.run()` — Property 17: run() does not write learning_insight to state on failure
    - **Property 17: run() does not write learning_insight to state on failure**
    - **Validates: Requirements 8.4**

- [x] 8. Wire agent into the publishing package
  - Add `PosterLearningAgent` to `wimlds/agents/publishing/__init__.py` exports
  - _Requirements: 8.1_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All property tests use `hypothesis` — add it to `wimlds/requirements.txt` if not already present
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
