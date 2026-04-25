# Requirements Document

## Introduction

The Poster Design Decision Agent is a LangGraph-compatible Python agent that accepts structured event content (as a JSON dict) and optional brand colors, then uses an LLM to make intelligent design decisions for poster generation. It outputs a strict JSON object specifying layout type, color palette, font style, and text hierarchy. The agent integrates with the existing `LLMClient` (Anthropic Claude / OpenAI fallback), follows the `AgentResult` pattern used throughout the WiMLDS pipeline, and is designed to be called by `PosterAgent` before composing the final poster image.

## Glossary

- **PosterDesignDecisionAgent**: The top-level orchestrator class that coordinates the full design decision pipeline and exposes the public API.
- **DesignInputValidator**: The component responsible for validating and normalizing the incoming content JSON and optional brand colors before they are passed to the prompt builder.
- **DesignPromptBuilder**: The component that constructs the full LLM prompt by embedding the event content, brand colors, output schema, and design rules.
- **DesignOutputValidator**: The component that validates the LLM's raw dict output against the required schema and enum constraints.
- **DesignDecision**: The validated dataclass representing a complete set of design decisions with all required fields.
- **LLMClient**: The existing shared client that wraps Anthropic Claude (with OpenAI fallback) and exposes a `generate_json()` method.
- **AgentResult**: The standard result envelope used throughout the WiMLDS pipeline, containing `success`, `data`, and `error` fields.
- **ContentJSON**: A dict containing structured event data (e.g., event name, speaker, vibe, highlights) as produced by `ContentExtractionAgent`.
- **BrandColors**: An optional list of hex color strings (e.g., `["#4C1D95", "#EC4899"]`) provided by the caller to anchor the palette.
- **LayoutType**: A categorical label for the poster layout; must be one of: `minimal`, `bold`, `grid`, `modern`.
- **FontStyle**: A categorical label for the dominant font style; must be one of: `sans-serif`, `serif`, `display`.
- **Hierarchy**: A dict with exactly three keys — `primary`, `secondary`, `tertiary` — each containing a non-empty string describing the content element at that level.
- **ValidationError**: An exception raised by `DesignOutputValidator` when the LLM output does not satisfy the schema constraints.
- **MAX_RETRIES**: The configurable maximum number of LLM call attempts before the agent returns a failure result.
- **LangGraph_Node**: The `run()` method interface that reads from and writes to a LangGraph state dict.

---

## Requirements

### Requirement 1: Input Acceptance and Validation

**User Story:** As a downstream pipeline node, I want to provide event content as a JSON dict and optionally supply brand colors, so that the agent can make design decisions without requiring me to pre-process or format the input.

#### Acceptance Criteria

1. WHEN a non-empty `dict` is provided as `content_json`, THE `DesignInputValidator` SHALL accept it as valid input.
2. WHEN `brand_colors` is provided as a non-empty list of strings, THE `DesignInputValidator` SHALL accept it and pass it to the prompt builder.
3. WHEN `brand_colors` is `None` or an empty list, THE `DesignInputValidator` SHALL treat it as absent and allow the agent to derive colors from the content vibe.
4. IF `content_json` is `None` or an empty dict, THEN THE `DesignInputValidator` SHALL raise a `ValueError` with a descriptive message.
5. IF any element in `brand_colors` is not a string matching the pattern `#[0-9A-Fa-f]{3,6}`, THEN THE `DesignInputValidator` SHALL raise a `ValueError` identifying the invalid color value.
6. THE `DesignInputValidator` SHALL NOT mutate the `content_json` or `brand_colors` arguments passed to it.

---

### Requirement 2: Prompt Construction

**User Story:** As the LLM, I want to receive a well-structured prompt that includes the event content, optional brand colors, output schema, layout rules, and vibe-matching guidance, so that I can produce a consistent, schema-compliant design decision.

#### Acceptance Criteria

1. WHEN `DesignPromptBuilder.build()` is called with a non-empty content dict, THE `DesignPromptBuilder` SHALL return a prompt string that embeds the serialized content JSON.
2. THE `DesignPromptBuilder` SHALL include the complete output JSON schema in every prompt it produces, matching the required output contract exactly.
3. THE `DesignPromptBuilder` SHALL include the full list of valid `layout` values (`minimal`, `bold`, `grid`, `modern`) in every prompt it produces.
4. THE `DesignPromptBuilder` SHALL include the full list of valid `font_style` values (`sans-serif`, `serif`, `display`) in every prompt it produces.
5. THE `DesignPromptBuilder` SHALL include an explicit instruction in every prompt directing the LLM to return pure JSON with no explanation and no markdown fences.
6. WHEN `brand_colors` is provided, THE `DesignPromptBuilder` SHALL embed the brand colors in the prompt and instruct the LLM to anchor the palette to those colors.
7. WHEN `brand_colors` is absent, THE `DesignPromptBuilder` SHALL instruct the LLM to derive the color palette from the event vibe and content.
8. THE `DesignPromptBuilder` SHALL include a rule instructing the LLM to produce exactly three hex color codes in the `colors` array.
9. WHEN `DesignPromptBuilder.build_with_correction()` is called, THE `DesignPromptBuilder` SHALL append a correction hint describing the previous validation failure to the prompt.

---

### Requirement 3: LLM-Based Design Decision

**User Story:** As a caller, I want the agent to use an LLM to decide layout, colors, font style, and text hierarchy from event content, so that I receive actionable design parameters without writing custom decision logic.

#### Acceptance Criteria

1. WHEN `PosterDesignDecisionAgent.decide()` is called with valid input, THE `PosterDesignDecisionAgent` SHALL invoke `LLMClient.generate_json()` with the constructed prompt.
2. THE `PosterDesignDecisionAgent` SHALL produce all four design decision fields: `layout`, `colors`, `font_style`, and `hierarchy`.
3. WHEN the LLM returns a valid, schema-compliant dict, THE `PosterDesignDecisionAgent` SHALL return an `AgentResult` with `success=True` and `data["design_decision"]` containing all four fields.
4. THE `PosterDesignDecisionAgent` SHALL use the existing `LLMClient` (Anthropic Claude with OpenAI fallback) for all LLM calls.
5. THE `PosterDesignDecisionAgent` SHALL pass the event `vibe` field from `content_json` (when present) to the prompt to guide layout and color matching.

---

### Requirement 4: Output Validation

**User Story:** As a downstream consumer, I want the design decision output to be validated against a strict schema before it is returned, so that `PosterAgent` can consume it without additional checks.

#### Acceptance Criteria

1. WHEN `DesignOutputValidator.validate()` is called with a dict containing all required keys and valid enum values, THE `DesignOutputValidator` SHALL return a populated `DesignDecision` dataclass.
2. IF the LLM output is not a dict, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` with a descriptive message.
3. IF any of the required keys (`layout`, `colors`, `font_style`, `hierarchy`) are absent from the LLM output, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` identifying the missing key.
4. IF the `layout` field is not one of `minimal`, `bold`, `grid`, `modern`, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` identifying the invalid layout value.
5. IF the `font_style` field is not one of `sans-serif`, `serif`, `display`, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` identifying the invalid font style value.
6. IF the `colors` field is not a list of exactly three strings each matching `#[0-9A-Fa-f]{3,6}`, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` describing the violation.
7. IF the `hierarchy` field is not a dict containing exactly the keys `primary`, `secondary`, and `tertiary` with non-empty string values, THEN THE `DesignOutputValidator` SHALL raise a `ValidationError` describing the violation.
8. THE `DesignOutputValidator` SHALL normalize `layout` and `font_style` values to lowercase before validation.
9. THE `DesignOutputValidator` SHALL NOT mutate the original `raw` dict passed to it.

---

### Requirement 5: Retry Mechanism

**User Story:** As a caller, I want the agent to automatically retry failed LLM calls with corrective hints, so that transient or schema-related failures are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN `DesignOutputValidator.validate()` raises a `ValidationError`, THE `PosterDesignDecisionAgent` SHALL retry the LLM call with a correction hint appended to the prompt.
2. WHEN a `json.JSONDecodeError` is raised by the LLM call, THE `PosterDesignDecisionAgent` SHALL retry the LLM call up to `MAX_RETRIES` times.
3. THE `PosterDesignDecisionAgent` SHALL attempt at most `MAX_RETRIES` total LLM calls before returning a failure result.
4. WHEN all retry attempts are exhausted without a valid result, THE `PosterDesignDecisionAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
5. THE `PosterDesignDecisionAgent` SHALL accept `max_retries` as a constructor parameter with a default value of `2`.

---

### Requirement 6: Error Handling

**User Story:** As a caller, I want the agent to return a structured failure result for all error conditions rather than raising exceptions, so that I can handle failures uniformly without wrapping calls in try/except.

#### Acceptance Criteria

1. IF `content_json` passed to `PosterDesignDecisionAgent.decide()` is empty or `None`, THEN THE `PosterDesignDecisionAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
2. IF the LLM API raises a network, rate-limit, or authentication error, THEN THE `PosterDesignDecisionAgent` SHALL return an `AgentResult` with `success=False` and `error` set to the exception message.
3. THE `PosterDesignDecisionAgent.decide()` SHALL never raise an exception to the caller under any input condition.
4. WHEN `AgentResult.success` is `False`, THE `PosterDesignDecisionAgent` SHALL ensure `AgentResult.error` is a non-empty, human-readable string describing the failure.
5. THE `PosterDesignDecisionAgent` SHALL NOT retry LLM API-level errors (network failures, rate limits, authentication errors).

---

### Requirement 7: AgentResult Contract

**User Story:** As a WiMLDS pipeline node, I want the agent to return results using the standard `AgentResult` envelope, so that it integrates consistently with the rest of the pipeline.

#### Acceptance Criteria

1. THE `PosterDesignDecisionAgent` SHALL always return an `AgentResult` from `decide()`, regardless of success or failure.
2. WHEN the decision succeeds, THE `PosterDesignDecisionAgent` SHALL set `AgentResult.success = True` and populate `AgentResult.data["design_decision"]` with a dict containing all four fields.
3. WHEN the decision fails, THE `PosterDesignDecisionAgent` SHALL set `AgentResult.success = False` and populate `AgentResult.error` with a descriptive string.
4. THE `PosterDesignDecisionAgent` SHALL NOT mutate the `content_json` or `brand_colors` arguments passed to `decide()`.

---

### Requirement 8: LangGraph Node Interface

**User Story:** As a LangGraph workflow author, I want to use the agent as a drop-in graph node, so that I can integrate design decisions into any LangGraph pipeline without custom wiring.

#### Acceptance Criteria

1. THE `PosterDesignDecisionAgent` SHALL expose a `run(state: dict) -> dict` method compatible with the LangGraph node interface.
2. WHEN `run()` is called, THE `PosterDesignDecisionAgent` SHALL read `content_json` from `state["extracted_event"]` and `brand_colors` from `state.get("brand_colors")`.
3. WHEN the decision succeeds in `run()`, THE `PosterDesignDecisionAgent` SHALL write the design decision dict to `state["design_decision"]` and return the updated state.
4. THE `PosterDesignDecisionAgent` SHALL accept a `dry_run` boolean constructor parameter that controls whether real LLM calls are made.
5. WHEN `dry_run=True`, THE `PosterDesignDecisionAgent` SHALL return a deterministic stub `AgentResult` without calling the LLM.

---

### Requirement 9: DesignDecision Data Model

**User Story:** As a downstream consumer, I want the design decision to be represented as a well-defined data model with a serialization method, so that I can reliably access fields and convert to dict for `PosterAgent` consumption.

#### Acceptance Criteria

1. THE `DesignDecision` dataclass SHALL contain the fields: `layout`, `colors`, `font_style`, and `hierarchy`.
2. THE `DesignDecision` SHALL expose a `to_dict()` method that returns a plain dict containing all four fields.
3. WHEN `DesignDecision.to_dict()` is called, THE `DesignDecision` SHALL return a dict whose keys exactly match the four field names defined in the output JSON contract.
4. THE `DesignDecision.colors` field SHALL be typed as a list of exactly three hex color strings.
5. THE `DesignDecision.hierarchy` field SHALL be typed as a dict with exactly the keys `primary`, `secondary`, and `tertiary`.

---

### Requirement 10: Serialization Round-Trip

**User Story:** As a developer, I want the `DesignDecision` serialization to be lossless, so that data is not corrupted when converting between the dataclass and dict representations.

#### Acceptance Criteria

1. WHEN a valid `DesignDecision` is serialized via `to_dict()` and the resulting dict is passed to `DesignOutputValidator.validate()`, THE `DesignOutputValidator` SHALL return an equivalent `DesignDecision`.
2. THE `DesignDecision.to_dict()` SHALL produce a dict that satisfies all constraints enforced by `DesignOutputValidator.validate()`.

---

### Requirement 11: Vibe-to-Design Mapping

**User Story:** As a poster designer, I want the agent to match design decisions to the event vibe, so that the generated poster visually reflects the tone of the event.

#### Acceptance Criteria

1. WHEN the `content_json` contains a `vibe` field with value `tech` or `minimal`, THE `PosterDesignDecisionAgent` SHALL instruct the LLM to prefer `minimal` or `modern` layout and `sans-serif` font style.
2. WHEN the `content_json` contains a `vibe` field with value `fun` or `party`, THE `PosterDesignDecisionAgent` SHALL instruct the LLM to prefer `bold` layout and `display` font style.
3. WHEN the `content_json` contains a `vibe` field with value `formal` or `corporate`, THE `PosterDesignDecisionAgent` SHALL instruct the LLM to prefer `grid` or `modern` layout and `serif` or `sans-serif` font style.
4. WHEN the `content_json` contains a `vibe` field with value `luxury`, THE `PosterDesignDecisionAgent` SHALL instruct the LLM to prefer `modern` layout and `serif` font style.
5. WHEN `brand_colors` are provided, THE `PosterDesignDecisionAgent` SHALL instruct the LLM to incorporate those colors as the dominant palette regardless of vibe.
