# Implementation Plan: Brand Intelligence Agent

## Overview

Implement the `BrandIntelligenceAgent` in Python following the same
`InputNormalizer → PromptBuilder → LLMClient → OutputValidator → AgentResult`
architecture used by `ContentExtractionAgent` and `PosterDesignDecisionAgent`.
The agent lives at `wimlds/agents/publishing/brand_intelligence_agent.py` and is
a drop-in LangGraph node for the publishing pipeline.

## Tasks

- [x] 1. Create the `BrandProfile` dataclass and `ValidationError`
  - Create `wimlds/agents/publishing/brand_intelligence_agent.py`
  - Define `ValidationError(Exception)` at module level
  - Define `BrandProfile` dataclass with fields `brand_colors: list[str]`, `tone: str`, `style_notes: list[str]`
  - Implement `BrandProfile.to_dict() -> dict` returning exactly the three keys
  - _Requirements: 8.1, 8.2_

- [x] 2. Implement `InputNormalizer`
  - [x] 2.1 Write `InputNormalizer.normalize()` in `brand_intelligence_agent.py`
    - Handle `str` → `strip()` and return; raise `ValueError` on empty/whitespace-only
    - Handle `dict` → `json.dumps()` and return; raise `ValueError` on empty dict
    - Raise `ValueError` with descriptive message for `None`
    - Never mutate the original input
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 Write property test for `InputNormalizer` — Property 1: String normalization strips whitespace without interior mutation
    - **Property 1: String normalization strips whitespace without interior mutation**
    - **Validates: Requirements 1.1**

  - [ ]* 2.3 Write property test for `InputNormalizer` — Property 2: Dict normalization produces round-trippable JSON
    - **Property 2: Dict normalization produces round-trippable JSON**
    - **Validates: Requirements 1.2**

  - [ ]* 2.4 Write property test for `InputNormalizer` — Property 3: Whitespace-only strings are rejected
    - **Property 3: Whitespace-only strings are rejected**
    - **Validates: Requirements 1.4**

  - [ ]* 2.5 Write property test for `InputNormalizer` — Property 4: normalize() never mutates its input
    - **Property 4: normalize() never mutates its input**
    - **Validates: Requirements 1.6**

- [x] 3. Implement `PromptBuilder`
  - [x] 3.1 Write `PromptBuilder` class with `SYSTEM_PROMPT`, `build()`, and `build_with_correction()` in `brand_intelligence_agent.py`
    - `build(text)` must embed the input text, the full output schema (`brand_colors`, `tone`, `style_notes`), all four valid tone values, anti-hallucination instructions (no fabricated colors, return empty values when confidence is low), and a pure-JSON-only instruction
    - `build_with_correction(text, error_message)` must return the base prompt with the error message appended as a correction hint
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 9.1, 9.2_

  - [ ]* 3.2 Write property test for `PromptBuilder` — Property 5: Every prompt contains all required structural elements
    - **Property 5: Every prompt contains all required structural elements**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.7**

  - [ ]* 3.3 Write property test for `PromptBuilder` — Property 6: Correction prompt contains both input text and error hint
    - **Property 6: Correction prompt contains both input text and error hint**
    - **Validates: Requirements 2.8**

- [x] 4. Implement `OutputValidator`
  - [x] 4.1 Write `OutputValidator` class in `brand_intelligence_agent.py`
    - Define `VALID_TONES`, `REQUIRED_KEYS`, and `HEX_PATTERN` as class-level constants
    - Implement `validate(raw) -> BrandProfile` following the validation algorithm in the design
    - Reject non-dict inputs, missing keys, invalid hex colors, invalid tone values, non-list `style_notes`
    - Normalise `tone` to lowercase before validation
    - Accept empty list for `brand_colors`, empty string for `tone`, empty list for `style_notes`
    - Never mutate the input dict
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 9.3_

  - [ ]* 4.2 Write property test for `OutputValidator` — Property 7: Valid dicts always produce a BrandProfile
    - **Property 7: Valid dicts always produce a BrandProfile**
    - **Validates: Requirements 3.1, 3.8, 3.9, 3.10**

  - [ ]* 4.3 Write property test for `OutputValidator` — Property 8: Non-dict inputs always fail validation
    - **Property 8: Non-dict inputs always fail validation**
    - **Validates: Requirements 3.2**

  - [ ]* 4.4 Write property test for `OutputValidator` — Property 9: Dicts with missing required keys always fail validation
    - **Property 9: Dicts with missing required keys always fail validation**
    - **Validates: Requirements 3.3**

  - [ ]* 4.5 Write property test for `OutputValidator` — Property 10: Invalid hex colors always fail validation
    - **Property 10: Invalid hex colors always fail validation**
    - **Validates: Requirements 3.5**

  - [ ]* 4.6 Write property test for `OutputValidator` — Property 11: Invalid tone values always fail validation
    - **Property 11: Invalid tone values always fail validation**
    - **Validates: Requirements 3.6**

  - [ ]* 4.7 Write property test for `OutputValidator` — Property 12: Tone case normalisation preserves valid tones
    - **Property 12: Tone case normalisation preserves valid tones**
    - **Validates: Requirements 3.11**

  - [ ]* 4.8 Write property test for `OutputValidator` — Property 13: validate() never mutates its input dict
    - **Property 13: validate() never mutates its input dict**
    - **Validates: Requirements 3.12**

- [x] 5. Checkpoint — Ensure all component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `BrandIntelligenceAgent` orchestrator
  - [x] 6.1 Write `BrandIntelligenceAgent` class in `brand_intelligence_agent.py`
    - Implement `__init__(self, dry_run: bool = False, max_retries: int = 2)`; instantiate `InputNormalizer`, `PromptBuilder`, `LLMClient`, `OutputValidator`
    - Implement `analyse(raw_input) -> AgentResult` following the main extraction algorithm in the design: normalize → build prompt → retry loop (ValidationError and JSONDecodeError increment counter; other exceptions return immediately)
    - In dry-run mode, return `AgentResult(success=True, data={"brand_profile": {"brand_colors": [], "tone": "", "style_notes": []}})` without calling the LLM
    - Implement `run(state: dict) -> dict`: read `state["raw_brand_input"]`, call `analyse()`, write `state["brand_profile"]` only on success, return updated state in all cases
    - Never raise to the caller
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3_

  - [ ]* 6.2 Write property test for `BrandIntelligenceAgent` — Property 14: Retry count never exceeds max_retries
    - **Property 14: Retry count never exceeds max_retries**
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 6.3 Write property test for `BrandIntelligenceAgent` — Property 15: analyse() never raises under any input
    - **Property 15: analyse() never raises under any input**
    - **Validates: Requirements 4.6**

  - [ ]* 6.4 Write property test for `BrandProfile` — Property 16: BrandProfile to_dict() key set is exactly the output contract
    - **Property 16: BrandProfile to_dict() key set is exactly the output contract**
    - **Validates: Requirements 5.2, 8.2**

  - [ ]* 6.5 Write property test for `BrandProfile` — Property 17: BrandProfile serialization round-trip
    - **Property 17: BrandProfile serialization round-trip**
    - **Validates: Requirements 8.3**

  - [ ]* 6.6 Write property test for `BrandIntelligenceAgent.run()` — Property 18: run() writes brand_profile to state on success
    - **Property 18: run() writes brand_profile to state on success**
    - **Validates: Requirements 6.3**

  - [ ]* 6.7 Write property test for `BrandIntelligenceAgent.run()` — Property 19: run() does not write brand_profile to state on failure
    - **Property 19: run() does not write brand_profile to state on failure**
    - **Validates: Requirements 6.4**

- [x] 7. Wire agent into the publishing package
  - Add `BrandIntelligenceAgent` to `wimlds/agents/publishing/__init__.py` exports
  - _Requirements: 6.1_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All property tests use `hypothesis` — add it to `wimlds/requirements.txt` if not already present
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
