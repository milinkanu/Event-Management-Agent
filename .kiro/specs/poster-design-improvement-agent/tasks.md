# Implementation Plan: Poster Design Improvement Agent

## Overview

Implement `PosterDesignImprovementAgent` at `wimlds/agents/publishing/poster_design_improvement_agent.py`, mirroring the architecture of `PosterDesignDecisionAgent`. The pipeline is: `ImprovementInputValidator` → `ImprovementPromptBuilder` → `LLMClient.generate_json()` → `ImprovementOutputValidator` → `AgentResult`. The agent reuses the `DesignDecision` dataclass and `ValidationError` from `poster_design_decision_agent.py`. Tests live at `wimlds/tests/agents/test_poster_design_improvement_agent.py`.

## Tasks

- [x] 1. Create agent file and import shared types
  - Create `wimlds/agents/publishing/poster_design_improvement_agent.py`
  - Import `DesignDecision`, `ValidationError` from `poster_design_decision_agent`
  - Import `AgentResult` from `wimlds.core.result`
  - Import `LLMClient` from `wimlds.integrations.llm.llm_client`
  - _Requirements: 8.1, 9.1_

- [x] 2. Implement `ImprovementInputValidator`
  - Add `ImprovementInputValidator` class with `validate(design_decision, qa_result) -> tuple[dict, dict]`
  - Raise `ValueError` when `design_decision` is `None` or empty dict
  - Raise `ValueError` when `qa_result` is `None` or empty dict
  - Raise `ValueError` identifying any missing key from `{layout, colors, font_style, hierarchy}` in `design_decision`
  - Raise `ValueError` when `qa_result` does not contain an `issues` key
  - Raise `ValueError` when `qa_result["issues"]` is an empty list
  - Never mutate the input arguments
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ]* 2.1 Write unit tests for `ImprovementInputValidator`
    - Test `None` design_decision raises `ValueError`
    - Test empty dict design_decision raises `ValueError`
    - Test design_decision missing each required key raises `ValueError` with key name in message
    - Test `None` qa_result raises `ValueError`
    - Test empty dict qa_result raises `ValueError`
    - Test qa_result missing `issues` key raises `ValueError`
    - Test qa_result with empty issues list raises `ValueError`
    - Test valid inputs are accepted and returned unchanged
    - Test inputs are not mutated
    - _Requirements: 1.1–1.8_

- [x] 3. Implement `ImprovementPromptBuilder`
  - Add `ImprovementPromptBuilder` class with `SYSTEM_PROMPT` class constant
  - Implement `build(design_decision, qa_result) -> str`
    - Embed serialized `design_decision` JSON in every prompt
    - Embed the full `qa_result["issues"]` list (type, description, severity per issue)
    - Include the complete output JSON schema matching `DesignDecision` contract
    - List all valid `layout` values (`minimal`, `bold`, `grid`, `modern`)
    - List all valid `font_style` values (`sans-serif`, `serif`, `display`)
    - Include explicit instruction to return pure JSON with no markdown fences or explanation
    - Include explicit minimal-change constraint: modify ONLY fields needed to address reported issues
    - Include issue-to-field mapping guidance: `color_contrast` → `colors`; `text_readability`/`unclear_information` → `hierarchy` or `font_style`; `alignment` → `layout`; `missing_information` → `hierarchy`
    - Derive and explicitly list which fields should remain unchanged based on issue types present
  - Implement `build_with_correction(design_decision, qa_result, error_message) -> str`
    - Append a correction hint containing `error_message` to the base prompt
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 5.5_

  - [ ]* 3.1 Write unit tests for `ImprovementPromptBuilder`
    - Test serialized design_decision JSON appears in prompt
    - Test all issue fields (type, description, severity) appear in prompt
    - Test all four output field names appear in prompt
    - Test all layout values listed
    - Test all font_style values listed
    - Test minimal-change constraint instruction present
    - Test issue-to-field mapping guidance present
    - Test correction hint appended by `build_with_correction()`
    - _Requirements: 2.1–2.9_

- [x] 4. Implement `ImprovementOutputValidator`
  - Add `ImprovementOutputValidator` class with class-level constants: `VALID_LAYOUTS`, `VALID_FONT_STYLES`, `REQUIRED_KEYS`
  - Implement `validate(raw) -> DesignDecision` — reuse the same logic as `DesignOutputValidator` in `poster_design_decision_agent.py`
    - Raise `ValidationError` for non-dict input
    - Raise `ValidationError` for any missing required key
    - Normalize `layout` and `font_style` to lowercase before validation
    - Raise `ValidationError` for invalid `layout` value
    - Raise `ValidationError` for invalid `font_style` value
    - Raise `ValidationError` if `colors` is not a list of exactly three strings each matching `#[0-9A-Fa-f]{3,6}`
    - Raise `ValidationError` if `hierarchy` is not a dict with exactly `primary`, `secondary`, `tertiary` as non-empty string values
    - Never mutate the input dict
    - Return a populated `DesignDecision` on success
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [ ]* 4.1 Write unit tests for `ImprovementOutputValidator`
    - Test all valid layout/font_style values accepted (including mixed case)
    - Test non-dict input raises `ValidationError`
    - Test missing keys raise `ValidationError`
    - Test invalid enum values raise `ValidationError`
    - Test wrong colors count/format raises `ValidationError`
    - Test malformed hierarchy raises `ValidationError`
    - Test input dict not mutated
    - Test successful validation returns correct `DesignDecision`
    - _Requirements: 4.1–4.9_

- [x] 5. Checkpoint — Ensure all component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `PosterDesignImprovementAgent`
  - Add `PosterDesignImprovementAgent` class with `__init__(self, dry_run=False, max_retries=2)`
    - Instantiate `ImprovementInputValidator`, `ImprovementPromptBuilder`, `ImprovementOutputValidator`, and `LLMClient`
  - Implement `improve(design_decision, qa_result) -> AgentResult`
    - When `qa_result["verdict"]` is `"pass"`, return `AgentResult(success=True, data={"improved_design": design_decision})` without calling the LLM
    - Validate inputs via `ImprovementInputValidator`; return failure `AgentResult` on `ValueError`
    - Build initial prompt via `ImprovementPromptBuilder.build()`
    - Retry loop (up to `max_retries`): call `LLMClient.generate_json()`, validate via `ImprovementOutputValidator`
    - On `ValidationError`: increment attempt, rebuild prompt with `build_with_correction()` if retries remain
    - On `json.JSONDecodeError`: increment attempt
    - On any other exception (API-level): return failure `AgentResult` immediately, no retry
    - On exhaustion: return failure `AgentResult` with non-empty error string
    - On success: return `AgentResult(success=True, data={"improved_design": decision.to_dict()})`
    - Never raise to the caller; never mutate `design_decision` or `qa_result`
  - Implement `run(state: dict) -> dict`
    - Read `design_decision` from `state["design_decision"]` and `qa_result` from `state["qa_result"]`
    - Call `improve()` and write `state["design_decision"]` on success
    - Return updated state dict
  - When `dry_run=True`, return a deterministic stub `AgentResult` with `data["improved_design"]` equal to the original `design_decision` without calling the LLM
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 6.1 Write unit tests for `PosterDesignImprovementAgent`
    - Test success path returns `AgentResult` with all four fields in `data["improved_design"]`
    - Test `qa_result["verdict"] == "pass"` returns original design without calling LLM
    - Test empty/None `design_decision` returns failure `AgentResult`
    - Test empty/None `qa_result` returns failure `AgentResult`
    - Test `ValidationError` triggers retry with correction prompt
    - Test `JSONDecodeError` triggers retry
    - Test exhausted retries returns failure `AgentResult`
    - Test API-level error returns failure without retry
    - Test `improve()` never raises
    - Test `design_decision` and `qa_result` not mutated
    - Test `dry_run=True` returns stub result without calling LLM
    - Test `run()` reads from `state["design_decision"]` and `state["qa_result"]`
    - Test `run()` writes `state["design_decision"]` on success
    - Test `run()` does not overwrite `state["design_decision"]` on failure
    - _Requirements: 3.1–3.5, 6.1–6.5, 7.1–7.5, 8.1–8.4, 9.1–9.5_

- [x] 7. Write serialization round-trip test
  - [ ]* 7.1 Write unit test for `DesignDecision` serialization round-trip via `ImprovementOutputValidator`
    - Construct a valid `DesignDecision`, call `to_dict()`, pass result to `ImprovementOutputValidator.validate()`, assert returned `DesignDecision` equals the original
    - _Requirements: 10.1, 10.2_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- `DesignDecision` and `ValidationError` are imported from `poster_design_decision_agent.py` — do not redefine them
- `ImprovementOutputValidator` logic mirrors `DesignOutputValidator` exactly — same schema, same enum constraints
- The agent file lives at `wimlds/agents/publishing/poster_design_improvement_agent.py`
- Tests live at `wimlds/tests/agents/test_poster_design_improvement_agent.py`
- Run tests with: `pytest wimlds/tests/agents/test_poster_design_improvement_agent.py --tb=short`
