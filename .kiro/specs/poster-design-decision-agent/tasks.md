# Implementation Plan: Poster Design Decision Agent

## Overview

Implement `PosterDesignDecisionAgent` at `wimlds/agents/publishing/poster_design_decision_agent.py`, mirroring the architecture of `ContentExtractionAgent`. The pipeline is: `DesignInputValidator` → `DesignPromptBuilder` → `LLMClient.generate_json()` → `DesignOutputValidator` → `AgentResult`. Tests live at `wimlds/tests/agents/test_poster_design_decision_agent.py`.

## Tasks

- [x] 1. Define `ValidationError` and `DesignDecision` data model
  - Create `wimlds/agents/publishing/poster_design_decision_agent.py`
  - Define `ValidationError(Exception)` with docstring
  - Define `DesignDecision` dataclass with fields: `layout: str`, `colors: list[str]`, `font_style: str`, `hierarchy: dict[str, str]`
  - Implement `DesignDecision.to_dict()` returning a plain dict with exactly the four field names
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 1.1 Write unit tests for `DesignDecision`
    - Test `to_dict()` returns exactly the keys `{"layout", "colors", "font_style", "hierarchy"}`
    - Test field values round-trip correctly through `to_dict()`
    - _Requirements: 9.2, 9.3_

- [x] 2. Implement `DesignInputValidator`
  - Add `DesignInputValidator` class with `validate(content_json, brand_colors) -> tuple[dict, list[str] | None]`
  - Raise `ValueError` when `content_json` is `None` or empty dict
  - Accept any non-empty dict as valid `content_json`
  - Treat `None` or `[]` `brand_colors` as absent (return `None`)
  - Validate each element of `brand_colors` against `#[0-9A-Fa-f]{3,6}`; raise `ValueError` identifying the invalid value
  - Never mutate the inputs
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.1 Write property test for `DesignInputValidator` — non-empty dict always accepted (Property 1)
    - **Property 1: Non-empty dict inputs are always accepted by DesignInputValidator**
    - **Validates: Requirements 1.1**

  - [ ]* 2.2 Write property test for `DesignInputValidator` — invalid hex always raises (Property 2)
    - **Property 2: Invalid hex color strings always raise ValueError**
    - **Validates: Requirements 1.5**

  - [ ]* 2.3 Write property test for `DesignInputValidator` — no mutation (Property 3)
    - **Property 3: DesignInputValidator does not mutate its inputs**
    - **Validates: Requirements 1.6, 7.4**

  - [ ]* 2.4 Write unit tests for `DesignInputValidator`
    - Test `None` content_json raises `ValueError`
    - Test empty dict raises `ValueError`
    - Test valid non-empty dict is accepted
    - Test `None` brand_colors returns `None`
    - Test empty list brand_colors returns `None`
    - Test valid hex list is accepted
    - Test invalid hex element raises `ValueError` with the bad value in the message
    - Test inputs are not mutated
    - _Requirements: 1.1–1.6_

- [x] 3. Implement `DesignPromptBuilder`
  - Add `DesignPromptBuilder` class with `SYSTEM_PROMPT` class constant
  - Implement `build(content_json, brand_colors=None) -> str`
    - Embed serialized `content_json` in every prompt
    - Include the complete output JSON schema (`layout`, `colors`, `font_style`, `hierarchy`)
    - List all valid `layout` values (`minimal`, `bold`, `grid`, `modern`)
    - List all valid `font_style` values (`sans-serif`, `serif`, `display`)
    - Instruct the model to return pure JSON with no markdown fences or explanation
    - Require exactly three hex color codes in `colors`
    - Embed brand colors and palette-anchoring instruction when provided
    - Instruct vibe-derived color selection when brand colors are absent
    - Embed vibe-to-design mapping rules (tech/minimal → minimal/modern + sans-serif; fun/party → bold + display; formal/corporate → grid/modern + serif/sans-serif; luxury → modern + serif)
  - Implement `build_with_correction(content_json, brand_colors, error_message) -> str`
    - Append a correction hint containing `error_message` to the base prompt
  - _Requirements: 2.1–2.9, 11.1–11.5_

  - [ ]* 3.1 Write property test for `DesignPromptBuilder` — all required structural elements present (Property 4)
    - **Property 4: Every prompt contains all required structural elements**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.8**

  - [ ]* 3.2 Write property test for `DesignPromptBuilder` — brand colors embedded when provided (Property 5)
    - **Property 5: Brand colors are embedded in the prompt when provided**
    - **Validates: Requirements 2.6, 11.5**

  - [ ]* 3.3 Write property test for `DesignPromptBuilder` — correction prompt contains error hint (Property 6)
    - **Property 6: Correction prompt always contains the error hint**
    - **Validates: Requirements 2.9**

  - [ ]* 3.4 Write property test for `DesignPromptBuilder` — vibe-to-design mapping rules embedded (Property 20)
    - **Property 20: Vibe-to-design mapping rules are embedded in every prompt**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4**

  - [ ]* 3.5 Write unit tests for `DesignPromptBuilder`
    - Test all four output field names appear in prompt
    - Test all layout values listed
    - Test all font_style values listed
    - Test brand colors embedded when provided
    - Test vibe rules embedded
    - Test correction hint appended by `build_with_correction()`
    - _Requirements: 2.1–2.9_

- [x] 4. Implement `DesignOutputValidator`
  - Add `DesignOutputValidator` class with class-level constants: `VALID_LAYOUTS`, `VALID_FONT_STYLES`, `REQUIRED_KEYS`
  - Implement `validate(raw) -> DesignDecision`
    - Raise `ValidationError` for non-dict input
    - Raise `ValidationError` for any missing required key
    - Normalize `layout` and `font_style` to lowercase before validation
    - Raise `ValidationError` for invalid `layout` value
    - Raise `ValidationError` for invalid `font_style` value
    - Raise `ValidationError` if `colors` is not a list of exactly three strings each matching `#[0-9A-Fa-f]{3,6}`
    - Raise `ValidationError` if `hierarchy` is not a dict with exactly `primary`, `secondary`, `tertiary` as non-empty string values
    - Never mutate the input dict
    - Return a populated `DesignDecision` on success
  - _Requirements: 4.1–4.9_

  - [ ]* 4.1 Write property test for `DesignOutputValidator` — valid dicts always pass (Property 8)
    - **Property 8: Valid dicts always pass output validation**
    - **Validates: Requirements 4.1**

  - [ ]* 4.2 Write property test for `DesignOutputValidator` — non-dict inputs always fail (Property 9)
    - **Property 9: Non-dict inputs always fail output validation**
    - **Validates: Requirements 4.2**

  - [ ]* 4.3 Write property test for `DesignOutputValidator` — missing required keys always fail (Property 10)
    - **Property 10: Missing required keys always fail output validation**
    - **Validates: Requirements 4.3**

  - [ ]* 4.4 Write property test for `DesignOutputValidator` — invalid field values always fail (Property 11)
    - **Property 11: Invalid field values always fail output validation**
    - **Validates: Requirements 4.4, 4.5, 4.6, 4.7**

  - [ ]* 4.5 Write property test for `DesignOutputValidator` — lowercase normalization (Property 12)
    - **Property 12: Layout and font_style are normalized to lowercase before validation**
    - **Validates: Requirements 4.8**

  - [ ]* 4.6 Write property test for `DesignOutputValidator` — no mutation (Property 13)
    - **Property 13: DesignOutputValidator does not mutate its input**
    - **Validates: Requirements 4.9**

  - [ ]* 4.7 Write unit tests for `DesignOutputValidator`
    - Test all valid layout/font_style values accepted (including mixed case)
    - Test missing keys raise `ValidationError`
    - Test invalid enum values raise `ValidationError`
    - Test wrong colors count/format raises `ValidationError`
    - Test malformed hierarchy raises `ValidationError`
    - Test input dict not mutated
    - _Requirements: 4.1–4.9_

- [-] 5. Checkpoint — Ensure all component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [~] 6. Implement `PosterDesignDecisionAgent`
  - Add `PosterDesignDecisionAgent` class with `__init__(self, dry_run=False, max_retries=2)`
    - Instantiate `DesignInputValidator`, `DesignPromptBuilder`, `DesignOutputValidator`, and `LLMClient`
  - Implement `decide(content_json, brand_colors=None) -> AgentResult`
    - Validate inputs via `DesignInputValidator`; return failure `AgentResult` on `ValueError`
    - Build initial prompt via `DesignPromptBuilder.build()`
    - Retry loop (up to `max_retries`): call `LLMClient.generate_json()`, validate via `DesignOutputValidator`
    - On `ValidationError`: increment attempt, rebuild prompt with `build_with_correction()` if retries remain
    - On `json.JSONDecodeError`: increment attempt
    - On any other exception (API-level): return failure `AgentResult` immediately, no retry
    - On exhaustion: return failure `AgentResult` with non-empty error string
    - On success: return `AgentResult(success=True, data={"design_decision": decision.to_dict()})`
    - Never raise to the caller; never mutate `content_json` or `brand_colors`
  - Implement `run(state: dict) -> dict`
    - Read `content_json` from `state["extracted_event"]` and `brand_colors` from `state.get("brand_colors")`
    - Call `decide()` and write `state["design_decision"]` on success
    - Return updated state dict
  - When `dry_run=True`, return a deterministic stub `AgentResult` without calling the LLM
  - _Requirements: 3.1–3.5, 5.1–5.5, 6.1–6.5, 7.1–7.4, 8.1–8.5_

  - [ ]* 6.1 Write property test for `PosterDesignDecisionAgent` — successful decide() yields all four fields (Property 7)
    - **Property 7: Successful decide() always yields all four design fields**
    - **Validates: Requirements 3.2, 3.3, 7.2**

  - [ ]* 6.2 Write property test for `PosterDesignDecisionAgent` — retry count never exceeds MAX_RETRIES (Property 14)
    - **Property 14: Retry count never exceeds MAX_RETRIES**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 6.3 Write property test for `PosterDesignDecisionAgent` — decide() never raises under any input (Property 15)
    - **Property 15: decide() never raises under any input**
    - **Validates: Requirements 6.1, 6.3, 7.1**

  - [ ]* 6.4 Write property test for `PosterDesignDecisionAgent` — API-level errors produce failure without retry (Property 16)
    - **Property 16: API-level errors produce failure results without retry**
    - **Validates: Requirements 6.2, 6.5**

  - [ ]* 6.5 Write property test for `PosterDesignDecisionAgent` — failure results always carry non-empty error string (Property 17)
    - **Property 17: Failure results always carry a non-empty error string**
    - **Validates: Requirements 6.4, 7.3**

  - [ ]* 6.6 Write property test for `PosterDesignDecisionAgent` — run() writes design_decision on success (Property 21)
    - **Property 21: run() writes design_decision to state on success**
    - **Validates: Requirements 8.2, 8.3**

  - [ ]* 6.7 Write unit tests for `PosterDesignDecisionAgent`
    - Test success path returns `AgentResult` with all four fields in `data["design_decision"]`
    - Test empty/None `content_json` returns failure
    - Test `ValidationError` triggers retry with correction prompt
    - Test `JSONDecodeError` triggers retry
    - Test exhausted retries returns failure
    - Test API-level error returns failure without retry
    - Test `decide()` never raises
    - Test `content_json` and `brand_colors` not mutated
    - Test `dry_run=True` returns stub result without calling LLM
    - Test `run()` reads from `state["extracted_event"]` and writes `state["design_decision"]`
    - Test `run()` does not write `design_decision` on failure
    - _Requirements: 3.1–3.5, 5.1–5.5, 6.1–6.5, 7.1–7.4, 8.1–8.5_

- [~] 7. Implement serialization round-trip property test (Property 18 & 19)
  - [ ]* 7.1 Write property test for `DesignDecision.to_dict()` key set (Property 18)
    - **Property 18: to_dict() keys exactly match the output JSON contract**
    - **Validates: Requirements 9.2, 9.3**

  - [ ]* 7.2 Write property test for `DesignDecision` serialization round-trip (Property 19)
    - **Property 19: DesignDecision serialization round-trip**
    - Construct a valid `DesignDecision`, call `to_dict()`, pass result to `DesignOutputValidator.validate()`, assert returned `DesignDecision` equals the original
    - **Validates: Requirements 10.1, 10.2**

- [~] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property-based tests use `hypothesis`; each property should run a minimum of 100 examples
- All components mirror the `ContentExtractionAgent` pattern — same file structure, same `AgentResult` envelope
- The agent file lives at `wimlds/agents/publishing/poster_design_decision_agent.py`
- Tests live at `wimlds/tests/agents/test_poster_design_decision_agent.py`
- Run tests with: `pytest wimlds/tests/agents/test_poster_design_decision_agent.py --tb=short`
