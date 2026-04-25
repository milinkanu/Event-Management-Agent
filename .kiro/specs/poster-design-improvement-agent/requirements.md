# Requirements Document

## Introduction

The Poster Design Improvement Agent is a LangGraph-compatible Python agent that accepts a previous `DesignDecision` JSON and a `QAResult` (list of issues with type, description, and severity) produced by the `PosterQAAgent`, then uses an LLM to make targeted, minimal corrections to the design — adjusting layout, colors, or text hierarchy — without redesigning from scratch. It outputs an updated `DesignDecision` JSON that resolves the reported issues while preserving all unaffected design choices. The agent integrates with the existing `LLMClient` (Anthropic Claude / OpenAI fallback), follows the `AgentResult` pattern used throughout the WiMLDS pipeline, and is designed to slot between `PosterQAAgent` and a second `PosterAgent` render pass in the LangGraph orchestrator.

## Glossary

- **PosterDesignImprovementAgent**: The top-level orchestrator class that coordinates the full improvement pipeline and exposes the public API.
- **ImprovementInputValidator**: The component responsible for validating the incoming `design_decision` dict and `qa_result` dict before they are passed to the prompt builder.
- **ImprovementPromptBuilder**: The component that constructs the full LLM prompt embedding the previous design decision, the QA issues, the output schema, and the minimal-change constraint rules.
- **ImprovementOutputValidator**: The component that validates the LLM's raw dict output against the `DesignDecision` schema and enum constraints.
- **DesignDecision**: The validated dataclass (shared with `PosterDesignDecisionAgent`) representing a complete set of design decisions with fields `layout`, `colors`, `font_style`, and `hierarchy`.
- **QAResult**: The output of `PosterQAAgent` — a dict containing an `issues` list (each with `type`, `description`, `severity`) and a `verdict` string.
- **QAIssue**: A single flagged issue from the QA agent with `type` ∈ `{text_readability, alignment, color_contrast, missing_information, unclear_information}`, a `description` string, and `severity` ∈ `{low, medium, high}`.
- **LLMClient**: The existing shared client that wraps Anthropic Claude (with OpenAI fallback) and exposes a `generate_json()` method.
- **AgentResult**: The standard result envelope used throughout the WiMLDS pipeline, containing `success`, `data`, and `error` fields.
- **ValidationError**: An exception raised by `ImprovementOutputValidator` when the LLM output does not satisfy the `DesignDecision` schema constraints.
- **MAX_RETRIES**: The configurable maximum number of LLM call attempts before the agent returns a failure result.
- **LangGraph_Node**: The `run()` method interface that reads from and writes to a LangGraph state dict.

---

## Requirements

### Requirement 1: Input Acceptance and Validation

**User Story:** As a downstream pipeline node, I want to provide the previous design decision and QA issues as dicts, so that the improvement agent can make targeted fixes without requiring me to pre-process or reformat the inputs.

#### Acceptance Criteria

1. WHEN a non-empty `dict` is provided as `design_decision` containing all four required keys (`layout`, `colors`, `font_style`, `hierarchy`), THE `ImprovementInputValidator` SHALL accept it as valid input.
2. WHEN a non-empty `dict` is provided as `qa_result` containing an `issues` list and a `verdict` string, THE `ImprovementInputValidator` SHALL accept it as valid input.
3. IF `design_decision` is `None` or an empty dict, THEN THE `ImprovementInputValidator` SHALL raise a `ValueError` with a descriptive message.
4. IF `qa_result` is `None` or an empty dict, THEN THE `ImprovementInputValidator` SHALL raise a `ValueError` with a descriptive message.
5. IF `design_decision` is missing any of the required keys (`layout`, `colors`, `font_style`, `hierarchy`), THEN THE `ImprovementInputValidator` SHALL raise a `ValueError` identifying the missing key.
6. IF `qa_result` does not contain an `issues` key, THEN THE `ImprovementInputValidator` SHALL raise a `ValueError` with a descriptive message.
7. IF `qa_result["issues"]` is an empty list, THEN THE `ImprovementInputValidator` SHALL raise a `ValueError` indicating there are no issues to fix.
8. THE `ImprovementInputValidator` SHALL NOT mutate the `design_decision` or `qa_result` arguments passed to it.

---

### Requirement 2: Prompt Construction

**User Story:** As the LLM, I want to receive a well-structured prompt that includes the previous design decision, the QA issues to fix, the output schema, and an explicit minimal-change constraint, so that I can produce a targeted correction rather than a full redesign.

#### Acceptance Criteria

1. WHEN `ImprovementPromptBuilder.build()` is called with a valid `design_decision` and `qa_result`, THE `ImprovementPromptBuilder` SHALL return a prompt string that embeds the serialized `design_decision` JSON.
2. THE `ImprovementPromptBuilder` SHALL embed the full `qa_result["issues"]` list in every prompt it produces, including each issue's `type`, `description`, and `severity`.
3. THE `ImprovementPromptBuilder` SHALL include the complete output JSON schema in every prompt it produces, matching the `DesignDecision` output contract exactly.
4. THE `ImprovementPromptBuilder` SHALL include the full list of valid `layout` values (`minimal`, `bold`, `grid`, `modern`) in every prompt it produces.
5. THE `ImprovementPromptBuilder` SHALL include the full list of valid `font_style` values (`sans-serif`, `serif`, `display`) in every prompt it produces.
6. THE `ImprovementPromptBuilder` SHALL include an explicit instruction in every prompt directing the LLM to return pure JSON with no explanation and no markdown fences.
7. THE `ImprovementPromptBuilder` SHALL include an explicit minimal-change constraint in every prompt instructing the LLM to modify ONLY the fields necessary to address the reported issues and preserve all other fields unchanged.
8. THE `ImprovementPromptBuilder` SHALL include issue-to-field mapping guidance in every prompt: `color_contrast` issues → adjust `colors`; `text_readability` or `unclear_information` issues → adjust `hierarchy` or `font_style`; `alignment` issues → adjust `layout`; `missing_information` issues → adjust `hierarchy`.
9. WHEN `ImprovementPromptBuilder.build_with_correction()` is called, THE `ImprovementPromptBuilder` SHALL append a correction hint describing the previous validation failure to the prompt.

---

### Requirement 3: LLM-Based Targeted Design Improvement

**User Story:** As a caller, I want the agent to use an LLM to produce a minimally-modified design decision that resolves the QA issues, so that I receive an updated design without losing the original design intent.

#### Acceptance Criteria

1. WHEN `PosterDesignImprovementAgent.improve()` is called with valid inputs, THE `PosterDesignImprovementAgent` SHALL invoke `LLMClient.generate_json()` with the constructed prompt.
2. WHEN the LLM returns a valid, schema-compliant dict, THE `PosterDesignImprovementAgent` SHALL return an `AgentResult` with `success=True` and `data["improved_design"]` containing all four `DesignDecision` fields.
3. THE `PosterDesignImprovementAgent` SHALL use the existing `LLMClient` (Anthropic Claude with OpenAI fallback) for all LLM calls.
4. THE `PosterDesignImprovementAgent` SHALL pass both the `design_decision` and the `qa_result["issues"]` to the prompt builder on every call.
5. WHEN `qa_result["verdict"]` is `"pass"`, THE `PosterDesignImprovementAgent` SHALL return an `AgentResult` with `success=True` and `data["improved_design"]` equal to the original `design_decision` without calling the LLM.

---

### Requirement 4: Output Validation

**User Story:** As a downstream consumer, I want the improved design decision to be validated against the same strict schema as the original design decision, so that `PosterAgent` can consume it without additional checks.

#### Acceptance Criteria

1. WHEN `ImprovementOutputValidator.validate()` is called with a dict containing all four required keys and valid enum values, THE `ImprovementOutputValidator` SHALL return a populated `DesignDecision` dataclass.
2. IF the LLM output is not a dict, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` with a descriptive message.
3. IF any of the required keys (`layout`, `colors`, `font_style`, `hierarchy`) are absent from the LLM output, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` identifying the missing key.
4. IF the `layout` field is not one of `minimal`, `bold`, `grid`, `modern`, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` identifying the invalid layout value.
5. IF the `font_style` field is not one of `sans-serif`, `serif`, `display`, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` identifying the invalid font style value.
6. IF the `colors` field is not a list of exactly three strings each matching `#[0-9A-Fa-f]{3,6}`, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` describing the violation.
7. IF the `hierarchy` field is not a dict containing exactly the keys `primary`, `secondary`, and `tertiary` with non-empty string values, THEN THE `ImprovementOutputValidator` SHALL raise a `ValidationError` describing the violation.
8. THE `ImprovementOutputValidator` SHALL normalize `layout` and `font_style` values to lowercase before validation.
9. THE `ImprovementOutputValidator` SHALL NOT mutate the original `raw` dict passed to it.

---

### Requirement 5: Minimal-Change Constraint

**User Story:** As a poster designer, I want the agent to fix only the reported problems and leave everything else intact, so that the overall design intent is preserved and the improvement is surgical rather than a full redesign.

#### Acceptance Criteria

1. WHEN the `qa_result["issues"]` list contains only `color_contrast` issues, THE `PosterDesignImprovementAgent` SHALL instruct the LLM to modify only the `colors` field and preserve `layout`, `font_style`, and `hierarchy` unchanged.
2. WHEN the `qa_result["issues"]` list contains only `alignment` issues, THE `PosterDesignImprovementAgent` SHALL instruct the LLM to modify only the `layout` field and preserve `colors`, `font_style`, and `hierarchy` unchanged.
3. WHEN the `qa_result["issues"]` list contains only `text_readability` or `unclear_information` issues, THE `PosterDesignImprovementAgent` SHALL instruct the LLM to modify only `hierarchy` or `font_style` and preserve `colors` and `layout` unchanged.
4. WHEN the `qa_result["issues"]` list contains only `missing_information` issues, THE `PosterDesignImprovementAgent` SHALL instruct the LLM to modify only the `hierarchy` field and preserve `colors`, `layout`, and `font_style` unchanged.
5. THE `ImprovementPromptBuilder` SHALL explicitly list which fields are expected to remain unchanged based on the issue types present in the `qa_result["issues"]` list.

---

### Requirement 6: Retry Mechanism

**User Story:** As a caller, I want the agent to automatically retry failed LLM calls with corrective hints, so that transient or schema-related failures are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN `ImprovementOutputValidator.validate()` raises a `ValidationError`, THE `PosterDesignImprovementAgent` SHALL retry the LLM call with a correction hint appended to the prompt.
2. WHEN a `json.JSONDecodeError` is raised by the LLM call, THE `PosterDesignImprovementAgent` SHALL retry the LLM call up to `MAX_RETRIES` times.
3. THE `PosterDesignImprovementAgent` SHALL attempt at most `MAX_RETRIES` total LLM calls before returning a failure result.
4. WHEN all retry attempts are exhausted without a valid result, THE `PosterDesignImprovementAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
5. THE `PosterDesignImprovementAgent` SHALL accept `max_retries` as a constructor parameter with a default value of `2`.

---

### Requirement 7: Error Handling

**User Story:** As a caller, I want the agent to return a structured failure result for all error conditions rather than raising exceptions, so that I can handle failures uniformly without wrapping calls in try/except.

#### Acceptance Criteria

1. IF `design_decision` or `qa_result` passed to `PosterDesignImprovementAgent.improve()` is empty or `None`, THEN THE `PosterDesignImprovementAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
2. IF the LLM API raises a network, rate-limit, or authentication error, THEN THE `PosterDesignImprovementAgent` SHALL return an `AgentResult` with `success=False` and `error` set to the exception message.
3. THE `PosterDesignImprovementAgent.improve()` SHALL never raise an exception to the caller under any input condition.
4. WHEN `AgentResult.success` is `False`, THE `PosterDesignImprovementAgent` SHALL ensure `AgentResult.error` is a non-empty, human-readable string describing the failure.
5. THE `PosterDesignImprovementAgent` SHALL NOT retry LLM API-level errors (network failures, rate limits, authentication errors).

---

### Requirement 8: AgentResult Contract

**User Story:** As a WiMLDS pipeline node, I want the agent to return results using the standard `AgentResult` envelope, so that it integrates consistently with the rest of the pipeline.

#### Acceptance Criteria

1. THE `PosterDesignImprovementAgent` SHALL always return an `AgentResult` from `improve()`, regardless of success or failure.
2. WHEN the improvement succeeds, THE `PosterDesignImprovementAgent` SHALL set `AgentResult.success = True` and populate `AgentResult.data["improved_design"]` with a dict containing all four `DesignDecision` fields.
3. WHEN the improvement fails, THE `PosterDesignImprovementAgent` SHALL set `AgentResult.success = False` and populate `AgentResult.error` with a descriptive string.
4. THE `PosterDesignImprovementAgent` SHALL NOT mutate the `design_decision` or `qa_result` arguments passed to `improve()`.

---

### Requirement 9: LangGraph Node Interface

**User Story:** As a LangGraph workflow author, I want to use the agent as a drop-in graph node, so that I can integrate design improvement into any LangGraph pipeline without custom wiring.

#### Acceptance Criteria

1. THE `PosterDesignImprovementAgent` SHALL expose a `run(state: dict) -> dict` method compatible with the LangGraph node interface.
2. WHEN `run()` is called, THE `PosterDesignImprovementAgent` SHALL read `design_decision` from `state["design_decision"]` and `qa_result` from `state["qa_result"]`.
3. WHEN the improvement succeeds in `run()`, THE `PosterDesignImprovementAgent` SHALL write the improved design dict to `state["design_decision"]` and return the updated state.
4. THE `PosterDesignImprovementAgent` SHALL accept a `dry_run` boolean constructor parameter that controls whether real LLM calls are made.
5. WHEN `dry_run=True`, THE `PosterDesignImprovementAgent` SHALL return a deterministic stub `AgentResult` with `data["improved_design"]` equal to the original `design_decision` without calling the LLM.

---

### Requirement 10: Serialization Round-Trip

**User Story:** As a developer, I want the improved `DesignDecision` serialization to be lossless, so that data is not corrupted when converting between the dataclass and dict representations.

#### Acceptance Criteria

1. WHEN a valid `DesignDecision` produced by `ImprovementOutputValidator.validate()` is serialized via `to_dict()` and the resulting dict is passed back to `ImprovementOutputValidator.validate()`, THE `ImprovementOutputValidator` SHALL return an equivalent `DesignDecision`.
2. THE `DesignDecision.to_dict()` SHALL produce a dict that satisfies all constraints enforced by `ImprovementOutputValidator.validate()`.
