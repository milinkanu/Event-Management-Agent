# Implementation Plan: Content Extraction Agent

## Overview

Implement the `ContentExtractionAgent` as a LangGraph-compatible Python agent that extracts structured event fields from unstructured input using an LLM. The implementation follows the existing WiMLDS `AgentResult` pattern and integrates with the shared `LLMClient`.

## Tasks

- [x] 1. Define core data models and exceptions
  - Create `ExtractedEvent` dataclass with all seven fields (`event_name`, `date_time`, `venue`, `organizer`, `audience`, `vibe`, `key_highlights`)
  - Implement `to_dict()` method returning a plain dict with exactly the seven field names
  - Define `ValidationError` exception class
  - Place in `wimlds/agents/publishing/content_extraction_agent.py`
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 2. Implement `InputNormalizer`
  - [x] 2.1 Implement `InputNormalizer.normalize()` method
    - Handle `str` input: return stripped string
    - Handle `dict` input: return `json.dumps()` of the dict
    - Handle any other type: return `str(raw_input)`
    - Raise `ValueError` for `None`, empty string, or empty dict
    - Never truncate content
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write property test for `InputNormalizer` — Property 1: Input normalization preserves content without truncation
    - **Property 1: Input normalization preserves content without truncation**
    - **Validates: Requirements 1.1, 1.5**

  - [ ]* 2.3 Write property test for `InputNormalizer` — Property 2: Dict normalization produces valid round-trippable JSON
    - **Property 2: Dict normalization produces valid round-trippable JSON**
    - **Validates: Requirements 1.2**

  - [ ]* 2.4 Write property test for `InputNormalizer` — Property 3: Invalid inputs always raise ValueError
    - **Property 3: Invalid inputs always raise ValueError**
    - **Validates: Requirements 1.4**

- [x] 3. Implement `PromptBuilder`
  - [x] 3.1 Implement `PromptBuilder.build()` and `build_with_correction()` methods
    - Define `SYSTEM_PROMPT` as a class-level constant
    - Embed event text, full output JSON schema, all seven vibe values, and "pure JSON only" instruction in every prompt
    - `build_with_correction()` appends the validation error message as a correction hint
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 3.2 Write property test for `PromptBuilder` — Property 4: Every prompt contains all required structural elements
    - **Property 4: Every prompt contains all required structural elements**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [ ]* 3.3 Write property test for `PromptBuilder` — Property 5: Prompt construction is deterministic
    - **Property 5: Prompt construction is deterministic**
    - **Validates: Requirements 2.5**

  - [ ]* 3.4 Write property test for `PromptBuilder` — Property 6: Correction prompt contains the error hint
    - **Property 6: Correction prompt contains the error hint**
    - **Validates: Requirements 2.6**

- [x] 4. Implement `OutputValidator`
  - [x] 4.1 Implement `OutputValidator.validate()` method
    - Define `REQUIRED_KEYS` and `VALID_VIBES` as class-level frozensets
    - Raise `ValidationError` if input is not a dict
    - Raise `ValidationError` identifying any missing required key
    - Raise `ValidationError` for invalid `vibe` value
    - Coerce non-list `key_highlights` to a single-element list
    - Strip whitespace from all string fields
    - Do not mutate the input dict
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.2 Write property test for `OutputValidator` — Property 8: Valid dicts always pass validation
    - **Property 8: Valid dicts always pass validation**
    - **Validates: Requirements 4.1**

  - [ ]* 4.3 Write property test for `OutputValidator` — Property 9: Non-dict inputs always fail validation
    - **Property 9: Non-dict inputs always fail validation**
    - **Validates: Requirements 4.2**

  - [ ]* 4.4 Write property test for `OutputValidator` — Property 10: Missing required keys always fail validation
    - **Property 10: Missing required keys always fail validation**
    - **Validates: Requirements 4.3**

  - [ ]* 4.5 Write property test for `OutputValidator` — Property 11: Invalid vibe values always fail validation
    - **Property 11: Invalid vibe values always fail validation**
    - **Validates: Requirements 4.4**

  - [ ]* 4.6 Write property test for `OutputValidator` — Property 12: Non-list key_highlights is coerced to a single-element list
    - **Property 12: Non-list key_highlights is coerced to a single-element list**
    - **Validates: Requirements 4.5**

  - [ ]* 4.7 Write property test for `OutputValidator` — Property 13: String fields are always stripped in validated output
    - **Property 13: String fields are always stripped in validated output**
    - **Validates: Requirements 4.6**

  - [ ]* 4.8 Write property test for `OutputValidator` — Property 14: Validation does not mutate the input dict
    - **Property 14: Validation does not mutate the input dict**
    - **Validates: Requirements 4.7**

- [x] 5. Checkpoint — Ensure all component-level tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `ContentExtractionAgent.extract()` with retry loop
  - [x] 6.1 Implement `ContentExtractionAgent.__init__()` and `extract()` method
    - Accept `dry_run: bool = False` and `max_retries: int = 2` constructor parameters
    - Coordinate `InputNormalizer → PromptBuilder → LLMClient → OutputValidator` pipeline
    - Retry on `ValidationError` with correction hint; retry on `json.JSONDecodeError`
    - Do not retry on LLM API-level errors (network, rate-limit, auth)
    - Return `AgentResult(success=False, ...)` on all failure paths; never raise to caller
    - Do not mutate `raw_input`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 6.2 Write property test for `ContentExtractionAgent` — Property 7: Successful extraction always yields all seven fields
    - **Property 7: Successful extraction always yields all seven fields**
    - **Validates: Requirements 3.2, 3.3, 7.2**

  - [ ]* 6.3 Write property test for `ContentExtractionAgent` — Property 15: Retry count never exceeds MAX_RETRIES
    - **Property 15: Retry count never exceeds MAX_RETRIES**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 6.4 Write property test for `ContentExtractionAgent` — Property 16: API-level errors produce failure results without retry
    - **Property 16: API-level errors produce failure results without retry**
    - **Validates: Requirements 6.2, 6.5**

  - [ ]* 6.5 Write property test for `ContentExtractionAgent` — Property 17: extract() never raises under any input
    - **Property 17: extract() never raises under any input**
    - **Validates: Requirements 6.3, 7.1**

  - [ ]* 6.6 Write property test for `ContentExtractionAgent` — Property 18: Failure results always carry a non-empty error string
    - **Property 18: Failure results always carry a non-empty error string**
    - **Validates: Requirements 6.4, 7.3**

  - [ ]* 6.7 Write property test for `ContentExtractionAgent` — Property 19: extract() does not mutate dict inputs
    - **Property 19: extract() does not mutate dict inputs**
    - **Validates: Requirements 7.4**

- [x] 7. Implement `ContentExtractionAgent.run()` LangGraph node interface
  - [x] 7.1 Implement `run(state: dict) -> dict` method
    - Read raw event input from `state["raw_event_input"]`
    - Call `self.extract()` and write result to `state["extracted_event"]` on success
    - Return the updated state dict
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 7.2 Write property test for `run()` — Property 20: run() writes extracted event to state on success
    - **Property 20: run() writes extracted event to state on success**
    - **Validates: Requirements 8.3**

- [x] 8. Validate `ExtractedEvent` serialization round-trip
  - [x] 8.1 Write unit tests for `ExtractedEvent.to_dict()` covering all field names and default `key_highlights`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 8.2 Write property test for `ExtractedEvent` — Property 21: to_dict() keys exactly match the output JSON contract
    - **Property 21: to_dict() keys exactly match the output JSON contract**
    - **Validates: Requirements 9.2, 9.4**

  - [ ]* 8.3 Write property test for `ExtractedEvent` — Property 22: ExtractedEvent serialization round-trip
    - **Property 22: ExtractedEvent serialization round-trip**
    - **Validates: Requirements 10.1, 10.2**

- [x] 9. Wire agent into the existing publishing agents package
  - Export `ContentExtractionAgent` from `wimlds/agents/publishing/__init__.py`
  - Add `hypothesis` to dev dependencies in `wimlds/requirements.txt` or `pyproject.toml`
  - _Requirements: 3.4, 8.1_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use the `hypothesis` library — add it to dev dependencies before running
- All components live in a single file: `wimlds/agents/publishing/content_extraction_agent.py`
- Tests go in `wimlds/tests/agents/test_content_extraction_agent.py`
- The `dry_run` flag on `ContentExtractionAgent` controls whether real LLM calls are made, enabling integration tests without API credentials
