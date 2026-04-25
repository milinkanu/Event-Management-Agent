# Requirements Document

## Introduction

The Content Extraction Agent is a LangGraph-compatible Python agent that accepts structured or unstructured event data (text, dict, or raw string) and uses an LLM to extract key event fields — name, date/time, venue, organizer, audience, vibe, and key highlights — returning a strict, validated JSON object. It integrates with the existing `LLMClient` (Anthropic Claude / OpenAI fallback) and follows the `AgentResult` pattern used throughout the WiMLDS pipeline, making it a drop-in node in any LangGraph workflow.

## Glossary

- **ContentExtractionAgent**: The top-level orchestrator class that coordinates the full extraction pipeline and exposes the public API.
- **InputNormalizer**: The component responsible for converting any input shape (str, dict, or other) into a clean, prompt-ready string.
- **PromptBuilder**: The component that constructs the full LLM prompt by embedding the event text, output schema, field rules, and vibe enum.
- **LLMClient**: The existing shared client that wraps Anthropic Claude (with OpenAI fallback) and exposes a `generate_json()` method.
- **OutputValidator**: The component that validates the LLM's raw dict output against the required schema and enum constraints.
- **ExtractedEvent**: The validated dataclass representing a successfully extracted event with all required fields.
- **AgentResult**: The standard result envelope used throughout the WiMLDS pipeline, containing `success`, `data`, and `error` fields.
- **ValidationError**: An exception raised by `OutputValidator` when the LLM output does not satisfy the schema constraints.
- **Vibe**: A categorical label describing the tone or atmosphere of an event; must be one of: `formal`, `corporate`, `fun`, `party`, `tech`, `minimal`, `luxury`.
- **MAX_RETRIES**: The configurable maximum number of LLM call attempts before the agent returns a failure result.
- **LangGraph_Node**: The `run()` method interface that reads from and writes to a LangGraph state dict.

---

## Requirements

### Requirement 1: Input Acceptance and Normalization

**User Story:** As a downstream pipeline node, I want to provide event data in any format (raw text, structured dict, or mixed), so that I do not need to pre-process input before calling the agent.

#### Acceptance Criteria

1. WHEN a non-empty `str` is provided as input, THE `InputNormalizer` SHALL return that string stripped of leading and trailing whitespace.
2. WHEN a non-empty `dict` is provided as input, THE `InputNormalizer` SHALL return a valid JSON-serialized string representation of that dict.
3. WHEN any other type is provided as input, THE `InputNormalizer` SHALL return the string representation of that value via `str()`.
4. IF the input is `None`, an empty string, or an empty dict, THEN THE `InputNormalizer` SHALL raise a `ValueError`.
5. THE `InputNormalizer` SHALL never truncate the input content before passing it to the prompt builder.

---

### Requirement 2: Prompt Construction

**User Story:** As the LLM, I want to receive a well-structured prompt that includes the output schema, field rules, and vibe enum, so that I can produce a consistent, schema-compliant JSON response.

#### Acceptance Criteria

1. WHEN `PromptBuilder.build()` is called with a non-empty event text, THE `PromptBuilder` SHALL return a prompt string that embeds the event text.
2. THE `PromptBuilder` SHALL include the complete output JSON schema definition in every prompt it produces.
3. THE `PromptBuilder` SHALL include the full list of valid vibe values (`formal`, `corporate`, `fun`, `party`, `tech`, `minimal`, `luxury`) in every prompt it produces.
4. THE `PromptBuilder` SHALL include an explicit instruction in every prompt directing the LLM to return pure JSON with no explanation and no markdown fences.
5. THE `PromptBuilder` SHALL maintain a stable, deterministic system prompt to encourage consistent LLM output.
6. WHEN `PromptBuilder.build_with_correction()` is called, THE `PromptBuilder` SHALL append a correction hint describing the previous validation failure to the prompt.

---

### Requirement 3: LLM-Based Event Field Extraction

**User Story:** As a caller, I want the agent to use an LLM to extract structured event fields from unstructured text, so that I receive a normalized event payload without writing custom parsing logic.

#### Acceptance Criteria

1. WHEN `ContentExtractionAgent.extract()` is called with valid input, THE `ContentExtractionAgent` SHALL invoke `LLMClient.generate_json()` with the constructed prompt.
2. THE `ContentExtractionAgent` SHALL extract all seven fields: `event_name`, `date_time`, `venue`, `organizer`, `audience`, `vibe`, and `key_highlights`.
3. WHEN the LLM returns a valid, schema-compliant dict, THE `ContentExtractionAgent` SHALL return an `AgentResult` with `success=True` and `data["extracted_event"]` containing all seven fields.
4. THE `ContentExtractionAgent` SHALL use the existing `LLMClient` (Anthropic Claude with OpenAI fallback) for all LLM calls.

---

### Requirement 4: Output Validation

**User Story:** As a downstream consumer, I want the extracted event data to be validated against a strict schema before it is returned, so that I can rely on the output structure without additional checks.

#### Acceptance Criteria

1. WHEN `OutputValidator.validate()` is called with a dict containing all required keys and a valid vibe, THE `OutputValidator` SHALL return a populated `ExtractedEvent` dataclass.
2. IF the LLM output is not a dict, THEN THE `OutputValidator` SHALL raise a `ValidationError` with a descriptive message.
3. IF any of the required keys (`event_name`, `date_time`, `venue`, `organizer`, `audience`, `vibe`, `key_highlights`) are absent from the LLM output, THEN THE `OutputValidator` SHALL raise a `ValidationError` identifying the missing key.
4. IF the `vibe` field is not one of `formal`, `corporate`, `fun`, `party`, `tech`, `minimal`, `luxury`, THEN THE `OutputValidator` SHALL raise a `ValidationError` identifying the invalid vibe value.
5. IF the `key_highlights` field is not a list, THEN THE `OutputValidator` SHALL coerce it to a single-element list containing the string representation of the value.
6. THE `OutputValidator` SHALL strip leading and trailing whitespace from all string field values before returning the `ExtractedEvent`.
7. THE `OutputValidator` SHALL NOT mutate the original `raw` dict passed to it.

---

### Requirement 5: Retry Mechanism

**User Story:** As a caller, I want the agent to automatically retry failed LLM calls with corrective hints, so that transient or schema-related failures are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN `OutputValidator.validate()` raises a `ValidationError`, THE `ContentExtractionAgent` SHALL retry the LLM call with a correction hint appended to the prompt.
2. WHEN a `json.JSONDecodeError` is raised by the LLM call, THE `ContentExtractionAgent` SHALL retry the LLM call up to `MAX_RETRIES` times.
3. THE `ContentExtractionAgent` SHALL attempt at most `MAX_RETRIES` total LLM calls before returning a failure result.
4. WHEN all retry attempts are exhausted without a valid result, THE `ContentExtractionAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
5. THE `ContentExtractionAgent` SHALL accept `max_retries` as a constructor parameter with a default value of `2`.

---

### Requirement 6: Error Handling

**User Story:** As a caller, I want the agent to return a structured failure result for all error conditions rather than raising exceptions, so that I can handle failures uniformly without wrapping calls in try/except.

#### Acceptance Criteria

1. IF the input to `ContentExtractionAgent.extract()` is empty or `None`, THEN THE `ContentExtractionAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
2. IF the LLM API raises a network, rate-limit, or authentication error, THEN THE `ContentExtractionAgent` SHALL return an `AgentResult` with `success=False` and `error` set to the exception message.
3. THE `ContentExtractionAgent.extract()` SHALL never raise an exception to the caller under any input condition.
4. WHEN `AgentResult.success` is `False`, THE `ContentExtractionAgent` SHALL ensure `AgentResult.error` is a non-empty, human-readable string describing the failure.
5. THE `ContentExtractionAgent` SHALL NOT retry LLM API-level errors (network failures, rate limits, authentication errors).

---

### Requirement 7: AgentResult Contract

**User Story:** As a WiMLDS pipeline node, I want the agent to return results using the standard `AgentResult` envelope, so that it integrates consistently with the rest of the pipeline.

#### Acceptance Criteria

1. THE `ContentExtractionAgent` SHALL always return an `AgentResult` from `extract()`, regardless of success or failure.
2. WHEN extraction succeeds, THE `ContentExtractionAgent` SHALL set `AgentResult.success = True` and populate `AgentResult.data["extracted_event"]` with a dict containing all seven fields.
3. WHEN extraction fails, THE `ContentExtractionAgent` SHALL set `AgentResult.success = False` and populate `AgentResult.error` with a descriptive string.
4. THE `ContentExtractionAgent` SHALL NOT mutate the `raw_input` argument passed to `extract()`.

---

### Requirement 8: LangGraph Node Interface

**User Story:** As a LangGraph workflow author, I want to use the agent as a drop-in graph node, so that I can integrate event extraction into any LangGraph pipeline without custom wiring.

#### Acceptance Criteria

1. THE `ContentExtractionAgent` SHALL expose a `run(state: dict) -> dict` method compatible with the LangGraph node interface.
2. WHEN `run()` is called, THE `ContentExtractionAgent` SHALL read the raw event input from `state["raw_event_input"]`.
3. WHEN extraction succeeds in `run()`, THE `ContentExtractionAgent` SHALL write the extracted event dict to `state["extracted_event"]` and return the updated state.
4. THE `ContentExtractionAgent` SHALL accept a `dry_run` boolean constructor parameter that controls whether real LLM calls are made.

---

### Requirement 9: ExtractedEvent Data Model

**User Story:** As a downstream consumer, I want the extracted event to be represented as a well-defined data model with a serialization method, so that I can reliably access fields and convert to dict for downstream use.

#### Acceptance Criteria

1. THE `ExtractedEvent` dataclass SHALL contain the fields: `event_name`, `date_time`, `venue`, `organizer`, `audience`, `vibe`, and `key_highlights`.
2. THE `ExtractedEvent` SHALL expose a `to_dict()` method that returns a plain dict containing all seven fields.
3. THE `ExtractedEvent.key_highlights` field SHALL default to an empty list when not provided.
4. WHEN `ExtractedEvent.to_dict()` is called, THE `ExtractedEvent` SHALL return a dict whose keys exactly match the seven field names defined in the output JSON contract.

---

### Requirement 10: Serialization Round-Trip

**User Story:** As a developer, I want the `ExtractedEvent` serialization to be lossless, so that data is not corrupted when converting between the dataclass and dict representations.

#### Acceptance Criteria

1. WHEN a valid `ExtractedEvent` is serialized via `to_dict()` and the resulting dict is passed to `OutputValidator.validate()`, THE `OutputValidator` SHALL return an equivalent `ExtractedEvent`.
2. THE `ExtractedEvent.to_dict()` SHALL produce a dict that satisfies all constraints enforced by `OutputValidator.validate()`.
