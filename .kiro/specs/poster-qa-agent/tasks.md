# Implementation Plan: Poster QA Agent

## Overview

Implement `PosterQAAgent` at `wimlds/agents/publishing/poster_qa_agent.py`, mirroring the architecture of `ContentExtractionAgent` and `PosterDesignDecisionAgent`. The pipeline is: `ImageInputValidator` → `QAPromptBuilder` → `LLMClient.generate_json()` → `QAOutputValidator` → `AgentResult`. Tests live at `wimlds/tests/agents/test_poster_qa_agent.py`.

## Tasks

- [x] 1. Define `ValidationError`, `QAIssue`, and `QAResult` data models
  - Create `wimlds/agents/publishing/poster_qa_agent.py`
  - Define `ValidationError(Exception)` with docstring
  - Define `QAIssue` dataclass with fields: `type: str`, `description: str`, `severity: str`
  - Implement `QAIssue.to_dict()` returning a plain dict with exactly the three field names
  - Define `QAResult` dataclass with fields: `issues: list[QAIssue]` (default empty list) and `verdict: str` (default `"pass"`)
  - Implement `QAResult.to_dict()` returning a dict with `issues` (list of dicts) and `verdict`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 1.1 Write unit tests for `QAIssue` and `QAResult`
    - Test `QAIssue.to_dict()` returns exactly the keys `{"type", "description", "severity"}`
    - Test `QAResult.to_dict()` returns exactly the keys `{"issues", "verdict"}`
    - Test `QAResult.to_dict()` with empty issues list returns `{"issues": [], "verdict": "pass"}`
    - Test field values round-trip correctly through `to_dict()`
    - _Requirements: 9.2, 9.3, 9.4_

- [x] 2. Implement `ImageInputValidator`
  - Add `ImageInputValidator` class with `ALLOWED_EXTENSIONS: frozenset[str]` class constant (`{".png", ".jpg", ".jpeg"}`)
  - Implement `validate(poster_image: str | bytes | None) -> bytes`
    - Raise `ValueError` when `poster_image` is `None` or empty string or empty bytes
    - For string inputs: check file exists (raise `ValueError` if not), check extension is in `ALLOWED_EXTENSIONS` case-insensitively (raise `ValueError` if not), read and return file bytes
    - For bytes inputs: accept any non-empty bytes as-is and return them
    - Never mutate the `poster_image` argument
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.1 Write property test for `ImageInputValidator` — Property 1: Invalid file path inputs always raise ValueError
    - **Property 1: Invalid file path inputs always raise ValueError**
    - **Validates: Requirements 1.4, 1.5**

  - [ ]* 2.2 Write property test for `ImageInputValidator` — Property 2: ImageInputValidator does not mutate its input
    - **Property 2: ImageInputValidator does not mutate its input**
    - **Validates: Requirements 1.6**

  - [ ]* 2.3 Write unit tests for `ImageInputValidator`
    - Test `None` raises `ValueError`
    - Test empty string raises `ValueError`
    - Test empty bytes raises `ValueError`
    - Test valid bytes input returns the same bytes
    - Test non-existent file path raises `ValueError` identifying the path
    - Test unsupported extension (e.g. `.gif`, `.bmp`) raises `ValueError`
    - Test `.png`, `.jpg`, `.jpeg` extensions accepted (case-insensitive: `.PNG`, `.JPG`, `.JPEG`)
    - Test valid file path returns file bytes
    - Test input is not mutated
    - _Requirements: 1.1–1.6_

- [x] 3. Implement `QAPromptBuilder`
  - Add `QAPromptBuilder` class with `SYSTEM_PROMPT` class-level constant
  - Implement `build(image_bytes: bytes) -> str`
    - Encode `image_bytes` as base64 and embed in the prompt for vision analysis
    - Include the complete output JSON schema (`issues`, `verdict`) in every prompt
    - List all five valid `type` values: `text_readability`, `alignment`, `color_contrast`, `missing_information`, `unclear_information`
    - List all three valid `severity` values: `low`, `medium`, `high`
    - List both valid `verdict` values: `pass`, `fail`
    - Include explicit verdict determination rules: `fail` if any `high` or `medium` severity issue; `pass` only if all issues are `low` or list is empty
    - Include evaluation criteria covering all four quality dimensions: text readability (font size, contrast, legibility), element alignment (visual balance, grid consistency), color contrast (WCAG-style foreground/background contrast), information completeness (event name, date, venue, speaker)
    - Include instruction to be critical and only flag real, observable issues
    - Include instruction to return pure JSON with no markdown fences or explanation
  - Implement `build_with_correction(image_bytes: bytes, error_message: str) -> str`
    - Append a correction hint containing `error_message` to the base prompt
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 11.4_

  - [ ]* 3.1 Write property test for `QAPromptBuilder` — Property 3: Every prompt contains all required structural elements
    - **Property 3: Every prompt contains all required structural elements**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 11.4**

  - [ ]* 3.2 Write property test for `QAPromptBuilder` — Property 4: Correction prompt always contains the error hint
    - **Property 4: Correction prompt always contains the error hint**
    - **Validates: Requirements 2.9**

  - [ ]* 3.3 Write unit tests for `QAPromptBuilder`
    - Test all five issue type values appear in prompt
    - Test all three severity values appear in prompt
    - Test both verdict values appear in prompt
    - Test verdict determination rules appear in prompt (`high`, `medium` → `fail`)
    - Test all four evaluation criteria dimensions appear in prompt
    - Test pure JSON instruction appears in prompt
    - Test base64-encoded image content is embedded in prompt
    - Test `build_with_correction()` appends the error hint
    - _Requirements: 2.1–2.9, 11.4_

- [x] 4. Implement `QAOutputValidator`
  - Add `QAOutputValidator` class with class-level constants: `VALID_ISSUE_TYPES`, `VALID_SEVERITIES`, `VALID_VERDICTS`, `REQUIRED_ISSUE_KEYS`
  - Implement `validate(raw) -> QAResult`
    - Raise `ValidationError` for non-dict input
    - Raise `ValidationError` for any missing required top-level key (`issues`, `verdict`)
    - Normalize `verdict`, issue `type`, and issue `severity` to lowercase before validation
    - Raise `ValidationError` for invalid `verdict` value
    - Raise `ValidationError` if `issues` is not a list
    - Raise `ValidationError` if any issue element is not a dict with `type`, `description`, `severity` keys
    - Raise `ValidationError` for invalid issue `type` value
    - Raise `ValidationError` for invalid issue `severity` value
    - Never mutate the input dict
    - Return a populated `QAResult` on success
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [ ]* 4.1 Write property test for `QAOutputValidator` — Property 6: Valid dicts always pass output validation
    - **Property 6: Valid dicts always pass output validation**
    - **Validates: Requirements 4.1**

  - [ ]* 4.2 Write property test for `QAOutputValidator` — Property 7: Non-dict inputs always fail output validation
    - **Property 7: Non-dict inputs always fail output validation**
    - **Validates: Requirements 4.2**

  - [ ]* 4.3 Write property test for `QAOutputValidator` — Property 8: Schema violations always fail output validation
    - **Property 8: Schema violations always fail output validation**
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.7, 4.8**

  - [ ]* 4.4 Write property test for `QAOutputValidator` — Property 9: Enum values are normalized to lowercase before validation
    - **Property 9: Enum values are normalized to lowercase before validation**
    - **Validates: Requirements 4.9**

  - [ ]* 4.5 Write property test for `QAOutputValidator` — Property 10: QAOutputValidator does not mutate its input
    - **Property 10: QAOutputValidator does not mutate its input**
    - **Validates: Requirements 4.10**

  - [ ]* 4.6 Write unit tests for `QAOutputValidator`
    - Test valid dict with empty issues list and `"pass"` verdict returns `QAResult`
    - Test valid dict with one issue of each type and severity accepted
    - Test non-dict inputs raise `ValidationError`
    - Test missing `issues` key raises `ValidationError`
    - Test missing `verdict` key raises `ValidationError`
    - Test invalid verdict value raises `ValidationError`
    - Test non-list `issues` raises `ValidationError`
    - Test issue missing `type` key raises `ValidationError`
    - Test issue missing `description` key raises `ValidationError`
    - Test issue missing `severity` key raises `ValidationError`
    - Test invalid issue type raises `ValidationError`
    - Test invalid issue severity raises `ValidationError`
    - Test mixed-case `verdict`, `type`, `severity` are normalized and accepted
    - Test input dict not mutated
    - _Requirements: 4.1–4.10_

- [x] 5. Checkpoint — Ensure all component-level tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `PosterQAAgent.evaluate()` with retry loop
  - Add `PosterQAAgent` class with `__init__(self, dry_run: bool = False, max_retries: int = 2)`
    - Instantiate `ImageInputValidator`, `QAPromptBuilder`, `QAOutputValidator`, and `LLMClient`
  - Implement `evaluate(poster_image: str | bytes) -> AgentResult`
    - Validate input via `ImageInputValidator`; return failure `AgentResult` on `ValueError`
    - Build initial prompt via `QAPromptBuilder.build()`
    - Retry loop (up to `max_retries`): call `LLMClient.generate_json()`, validate via `QAOutputValidator`
    - On `ValidationError`: increment attempt, rebuild prompt with `build_with_correction()` if retries remain
    - On `json.JSONDecodeError`: increment attempt
    - On any other exception (API-level): return failure `AgentResult` immediately, no retry
    - On exhaustion: return failure `AgentResult` with non-empty error string
    - On success: return `AgentResult(success=True, data={"qa_result": qa_result.to_dict()})`
    - Never raise to the caller; never mutate `poster_image`
    - When `dry_run=True`: return `AgentResult(success=True, data={"qa_result": {"issues": [], "verdict": "pass"}})` without calling the LLM
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 8.4, 8.5_

  - [ ]* 6.1 Write property test for `PosterQAAgent` — Property 5: Successful evaluate() always yields issues list and verdict
    - **Property 5: Successful evaluate() always yields issues list and verdict**
    - **Validates: Requirements 3.3, 7.2**

  - [ ]* 6.2 Write property test for `PosterQAAgent` — Property 11: Retry count never exceeds MAX_RETRIES
    - **Property 11: Retry count never exceeds MAX_RETRIES**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 6.3 Write property test for `PosterQAAgent` — Property 12: evaluate() never raises under any input
    - **Property 12: evaluate() never raises under any input**
    - **Validates: Requirements 6.3, 7.1**

  - [ ]* 6.4 Write property test for `PosterQAAgent` — Property 13: Failure results always carry a non-empty error string
    - **Property 13: Failure results always carry a non-empty error string**
    - **Validates: Requirements 6.4, 7.3**

  - [ ]* 6.5 Write property test for `PosterQAAgent` — Property 14: evaluate() does not mutate its input
    - **Property 14: evaluate() does not mutate its input**
    - **Validates: Requirements 7.4**

  - [ ]* 6.6 Write unit tests for `PosterQAAgent.evaluate()`
    - Test success path returns `AgentResult` with `issues` and `verdict` in `data["qa_result"]`
    - Test `None` input returns failure `AgentResult`
    - Test empty string input returns failure `AgentResult`
    - Test non-existent file path returns failure `AgentResult`
    - Test `ValidationError` from validator triggers retry with correction prompt
    - Test `JSONDecodeError` triggers retry
    - Test exhausted retries returns failure with non-empty error string
    - Test API-level exception returns failure without retry
    - Test `evaluate()` never raises
    - Test `poster_image` not mutated
    - Test `dry_run=True` returns stub result without calling LLM
    - _Requirements: 3.1–3.5, 5.1–5.5, 6.1–6.5, 7.1–7.4, 8.4, 8.5_

- [x] 7. Implement `PosterQAAgent.run()` LangGraph node interface
  - Implement `run(state: dict) -> dict` method
    - Read poster image from `state["_poster_local_path"]`
    - Call `self.evaluate()` and write result to `state["qa_result"]` on success
    - Return the updated state dict
  - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 7.1 Write property test for `PosterQAAgent` — Property 18: run() writes qa_result to state on success
    - **Property 18: run() writes qa_result to state on success**
    - **Validates: Requirements 8.3**

  - [ ]* 7.2 Write unit tests for `PosterQAAgent.run()`
    - Test `run()` reads from `state["_poster_local_path"]`
    - Test `run()` writes `state["qa_result"]` on success
    - Test `run()` does not write `qa_result` on failure
    - Test `run()` returns the updated state dict
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. Validate `QAResult` serialization round-trip
  - [x] 8.1 Write unit tests for `QAResult.to_dict()` covering all field names, empty issues, and multi-issue lists
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 8.2 Write property test for `QAResult` — Property 16: to_dict() produces the correct key structure
    - **Property 16: to_dict() produces the correct key structure**
    - **Validates: Requirements 9.3, 9.4**

  - [ ]* 8.3 Write property test for `QAResult` — Property 15: QAResult serialization round-trip
    - **Property 15: QAResult serialization round-trip**
    - Construct a valid `QAResult`, call `to_dict()`, pass result to `QAOutputValidator.validate()`, assert returned `QAResult` equals the original
    - **Validates: Requirements 10.1, 10.2**

- [x] 9. Validate verdict determination rules
  - [ ]* 9.1 Write property test for `PosterQAAgent` — Property 17: High or medium severity issues always produce a fail verdict
    - **Property 17: High or medium severity issues always produce a fail verdict**
    - Use hypothesis to generate issues lists containing at least one `high` or `medium` severity issue, mock the LLM to return them, and assert the verdict in `data["qa_result"]` is `"fail"`
    - **Validates: Requirements 11.1, 11.2**

  - [ ]* 9.2 Write unit tests for verdict determination
    - Test that a QA result with one `high` severity issue has verdict `"fail"`
    - Test that a QA result with one `medium` severity issue has verdict `"fail"`
    - Test that a QA result with only `low` severity issues has verdict `"pass"`
    - Test that a QA result with an empty issues list has verdict `"pass"`
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 10. Wire agent into the existing publishing agents package
  - Export `PosterQAAgent` from `wimlds/agents/publishing/__init__.py`
  - Ensure `hypothesis` is present in `wimlds/requirements.txt` or `pyproject.toml` (already added for prior agents)
  - _Requirements: 3.4, 8.1_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property-based tests use `hypothesis`; each property should run a minimum of 100 examples
- All components mirror the `ContentExtractionAgent` and `PosterDesignDecisionAgent` pattern — same file structure, same `AgentResult` envelope
- The agent file lives at `wimlds/agents/publishing/poster_qa_agent.py`
- Tests live at `wimlds/tests/agents/test_poster_qa_agent.py`
- The `dry_run` flag controls whether real LLM calls are made, enabling tests without API credentials
- Vision prompts embed the image as base64; the `LLMClient` must be called with a model that supports vision (Claude claude-haiku-4-5-20251001 or better)
- Run tests with: `pytest wimlds/tests/agents/test_poster_qa_agent.py --tb=short`
