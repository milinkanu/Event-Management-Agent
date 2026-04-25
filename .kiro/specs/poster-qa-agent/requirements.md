# Requirements Document

## Introduction

The Poster QA Agent is a LangGraph-compatible Python agent that performs automated visual quality assurance on generated event poster images. It accepts a poster image (as a file path or binary data) and uses an LLM with vision capabilities to evaluate text readability, element alignment, color contrast, and information completeness. The agent outputs a strict JSON object containing a list of flagged issues (each with type, description, and severity) and a pass/fail verdict. It integrates with the existing WiMLDS publishing pipeline — specifically designed to run after `PosterAgent.create_poster()` and before the approval email is sent — following the `AgentResult` pattern used throughout the codebase.

## Glossary

- **PosterQAAgent**: The top-level orchestrator class that coordinates the full QA pipeline and exposes the public API.
- **ImageInputValidator**: The component responsible for validating the incoming poster image input (file path or bytes) before it is passed to the vision prompt builder.
- **QAPromptBuilder**: The component that constructs the LLM vision prompt embedding the poster image, evaluation criteria, output schema, and severity rules.
- **QAOutputValidator**: The component that validates the LLM's raw dict output against the required JSON schema before returning it to the caller.
- **QAResult**: The validated dataclass representing a complete QA evaluation with an `issues` list and a `verdict` field.
- **QAIssue**: A dataclass representing a single flagged issue with `type`, `description`, and `severity` fields.
- **LLMClient**: The existing shared client that wraps Anthropic Claude (with OpenAI fallback) and exposes a `generate_json()` method.
- **AgentResult**: The standard result envelope used throughout the WiMLDS pipeline, containing `success`, `data`, and `error` fields.
- **PosterImage**: The input poster image provided as a local file path string or raw bytes in PNG or JPEG format.
- **IssueType**: A categorical label for the type of QA issue; must be one of: `text_readability`, `alignment`, `color_contrast`, `missing_information`, `unclear_information`.
- **Severity**: A categorical label for the severity of a QA issue; must be one of: `low`, `medium`, `high`.
- **Verdict**: The overall QA outcome; must be one of: `pass`, `fail`.
- **ValidationError**: An exception raised by `QAOutputValidator` when the LLM output does not satisfy the schema constraints.
- **MAX_RETRIES**: The configurable maximum number of LLM call attempts before the agent returns a failure result.
- **LangGraph_Node**: The `run()` method interface that reads from and writes to a LangGraph state dict.

---

## Requirements

### Requirement 1: Image Input Acceptance and Validation

**User Story:** As a downstream pipeline node, I want to provide a poster image as a file path or bytes, so that the QA agent can evaluate it without requiring me to pre-process or encode the image.

#### Acceptance Criteria

1. WHEN a non-empty string is provided as `poster_image` and the file exists at that path, THE `ImageInputValidator` SHALL accept it as a valid file path input.
2. WHEN a non-empty `bytes` object is provided as `poster_image`, THE `ImageInputValidator` SHALL accept it as valid binary image input.
3. IF `poster_image` is `None` or an empty string, THEN THE `ImageInputValidator` SHALL raise a `ValueError` with a descriptive message.
4. IF `poster_image` is a string and the file does not exist at that path, THEN THE `ImageInputValidator` SHALL raise a `ValueError` identifying the missing file path.
5. IF `poster_image` is a string pointing to a file whose extension is not `.png` or `.jpg` or `.jpeg` (case-insensitive), THEN THE `ImageInputValidator` SHALL raise a `ValueError` identifying the unsupported format.
6. THE `ImageInputValidator` SHALL NOT mutate the `poster_image` argument passed to it.

---

### Requirement 2: Vision Prompt Construction

**User Story:** As the LLM, I want to receive a well-structured vision prompt that includes the poster image, evaluation criteria, output schema, and severity rules, so that I can produce a consistent, schema-compliant QA evaluation.

#### Acceptance Criteria

1. WHEN `QAPromptBuilder.build()` is called with a valid image, THE `QAPromptBuilder` SHALL return a prompt that embeds the image for vision analysis.
2. THE `QAPromptBuilder` SHALL include the complete output JSON schema in every prompt it produces, matching the required output contract exactly.
3. THE `QAPromptBuilder` SHALL include the full list of valid `type` values (`text_readability`, `alignment`, `color_contrast`, `missing_information`, `unclear_information`) in every prompt it produces.
4. THE `QAPromptBuilder` SHALL include the full list of valid `severity` values (`low`, `medium`, `high`) in every prompt it produces.
5. THE `QAPromptBuilder` SHALL include the full list of valid `verdict` values (`pass`, `fail`) in every prompt it produces.
6. THE `QAPromptBuilder` SHALL include an explicit instruction in every prompt directing the LLM to return pure JSON with no explanation and no markdown fences.
7. THE `QAPromptBuilder` SHALL include an instruction directing the LLM to be critical and only flag real, observable issues.
8. THE `QAPromptBuilder` SHALL include evaluation criteria covering: text readability (font size, contrast, legibility), element alignment (visual balance, grid consistency), color contrast (WCAG-style foreground/background contrast), and information completeness (presence of event name, date, venue, speaker).
9. WHEN `QAPromptBuilder.build_with_correction()` is called, THE `QAPromptBuilder` SHALL append a correction hint describing the previous validation failure to the prompt.

---

### Requirement 3: LLM-Based Visual QA Evaluation

**User Story:** As a caller, I want the agent to use an LLM with vision capabilities to evaluate the poster image, so that I receive actionable QA feedback without writing custom image analysis logic.

#### Acceptance Criteria

1. WHEN `PosterQAAgent.evaluate()` is called with a valid image input, THE `PosterQAAgent` SHALL invoke `LLMClient.generate_json()` with the constructed vision prompt.
2. THE `PosterQAAgent` SHALL evaluate all four quality dimensions: text readability, alignment, color contrast, and information completeness.
3. WHEN the LLM returns a valid, schema-compliant dict, THE `PosterQAAgent` SHALL return an `AgentResult` with `success=True` and `data["qa_result"]` containing `issues` and `verdict`.
4. THE `PosterQAAgent` SHALL use the existing `LLMClient` (Anthropic Claude with OpenAI fallback) for all LLM calls.
5. WHEN no issues are found, THE `PosterQAAgent` SHALL return an `AgentResult` with `data["qa_result"]["issues"]` as an empty list and `data["qa_result"]["verdict"]` as `"pass"`.

---

### Requirement 4: Output Validation

**User Story:** As a downstream consumer, I want the QA output to be validated against a strict schema before it is returned, so that the pipeline can consume it without additional checks.

#### Acceptance Criteria

1. WHEN `QAOutputValidator.validate()` is called with a dict containing all required keys and valid enum values, THE `QAOutputValidator` SHALL return a populated `QAResult` dataclass.
2. IF the LLM output is not a dict, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` with a descriptive message.
3. IF either of the required keys (`issues`, `verdict`) is absent from the LLM output, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` identifying the missing key.
4. IF the `verdict` field is not one of `pass`, `fail`, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` identifying the invalid verdict value.
5. IF the `issues` field is not a list, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` describing the violation.
6. IF any element in the `issues` list is not a dict containing `type`, `description`, and `severity` keys, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` identifying the malformed issue.
7. IF any issue's `type` field is not one of `text_readability`, `alignment`, `color_contrast`, `missing_information`, `unclear_information`, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` identifying the invalid type value.
8. IF any issue's `severity` field is not one of `low`, `medium`, `high`, THEN THE `QAOutputValidator` SHALL raise a `ValidationError` identifying the invalid severity value.
9. THE `QAOutputValidator` SHALL normalize `verdict`, `type`, and `severity` values to lowercase before validation.
10. THE `QAOutputValidator` SHALL NOT mutate the original `raw` dict passed to it.

---

### Requirement 5: Retry Mechanism

**User Story:** As a caller, I want the agent to automatically retry failed LLM calls with corrective hints, so that transient or schema-related failures are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN `QAOutputValidator.validate()` raises a `ValidationError`, THE `PosterQAAgent` SHALL retry the LLM call with a correction hint appended to the prompt.
2. WHEN a `json.JSONDecodeError` is raised by the LLM call, THE `PosterQAAgent` SHALL retry the LLM call up to `MAX_RETRIES` times.
3. THE `PosterQAAgent` SHALL attempt at most `MAX_RETRIES` total LLM calls before returning a failure result.
4. WHEN all retry attempts are exhausted without a valid result, THE `PosterQAAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
5. THE `PosterQAAgent` SHALL accept `max_retries` as a constructor parameter with a default value of `2`.

---

### Requirement 6: Error Handling

**User Story:** As a caller, I want the agent to return a structured failure result for all error conditions rather than raising exceptions, so that I can handle failures uniformly without wrapping calls in try/except.

#### Acceptance Criteria

1. IF `poster_image` passed to `PosterQAAgent.evaluate()` is `None` or empty, THEN THE `PosterQAAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
2. IF the LLM API raises a network, rate-limit, or authentication error, THEN THE `PosterQAAgent` SHALL return an `AgentResult` with `success=False` and `error` set to the exception message.
3. THE `PosterQAAgent.evaluate()` SHALL never raise an exception to the caller under any input condition.
4. WHEN `AgentResult.success` is `False`, THE `PosterQAAgent` SHALL ensure `AgentResult.error` is a non-empty, human-readable string describing the failure.
5. THE `PosterQAAgent` SHALL NOT retry LLM API-level errors (network failures, rate limits, authentication errors).

---

### Requirement 7: AgentResult Contract

**User Story:** As a WiMLDS pipeline node, I want the agent to return results using the standard `AgentResult` envelope, so that it integrates consistently with the rest of the pipeline.

#### Acceptance Criteria

1. THE `PosterQAAgent` SHALL always return an `AgentResult` from `evaluate()`, regardless of success or failure.
2. WHEN the evaluation succeeds, THE `PosterQAAgent` SHALL set `AgentResult.success = True` and populate `AgentResult.data["qa_result"]` with a dict containing `issues` and `verdict`.
3. WHEN the evaluation fails, THE `PosterQAAgent` SHALL set `AgentResult.success = False` and populate `AgentResult.error` with a descriptive string.
4. THE `PosterQAAgent` SHALL NOT mutate the `poster_image` argument passed to `evaluate()`.

---

### Requirement 8: LangGraph Node Interface

**User Story:** As a LangGraph workflow author, I want to use the agent as a drop-in graph node, so that I can integrate poster QA into any LangGraph pipeline without custom wiring.

#### Acceptance Criteria

1. THE `PosterQAAgent` SHALL expose a `run(state: dict) -> dict` method compatible with the LangGraph node interface.
2. WHEN `run()` is called, THE `PosterQAAgent` SHALL read the poster image from `state["_poster_local_path"]`.
3. WHEN the evaluation succeeds in `run()`, THE `PosterQAAgent` SHALL write the QA result dict to `state["qa_result"]` and return the updated state.
4. THE `PosterQAAgent` SHALL accept a `dry_run` boolean constructor parameter that controls whether real LLM calls are made.
5. WHEN `dry_run=True`, THE `PosterQAAgent` SHALL return a deterministic stub `AgentResult` with an empty `issues` list and `verdict` of `"pass"` without calling the LLM.

---

### Requirement 9: QAResult and QAIssue Data Models

**User Story:** As a downstream consumer, I want the QA result to be represented as a well-defined data model with a serialization method, so that I can reliably access fields and convert to dict for pipeline consumption.

#### Acceptance Criteria

1. THE `QAIssue` dataclass SHALL contain the fields: `type`, `description`, and `severity`.
2. THE `QAResult` dataclass SHALL contain the fields: `issues` (a list of `QAIssue`) and `verdict`.
3. THE `QAResult` SHALL expose a `to_dict()` method that returns a plain dict containing `issues` (as a list of dicts) and `verdict`.
4. WHEN `QAResult.to_dict()` is called, THE `QAResult` SHALL return a dict whose `issues` key maps to a list where each element is a dict with exactly the keys `type`, `description`, and `severity`.
5. THE `QAResult.verdict` field SHALL be typed as a string constrained to `"pass"` or `"fail"`.

---

### Requirement 10: Serialization Round-Trip

**User Story:** As a developer, I want the `QAResult` serialization to be lossless, so that data is not corrupted when converting between the dataclass and dict representations.

#### Acceptance Criteria

1. WHEN a valid `QAResult` is serialized via `to_dict()` and the resulting dict is passed to `QAOutputValidator.validate()`, THE `QAOutputValidator` SHALL return an equivalent `QAResult`.
2. THE `QAResult.to_dict()` SHALL produce a dict that satisfies all constraints enforced by `QAOutputValidator.validate()`.

---

### Requirement 11: Verdict Determination

**User Story:** As a pipeline orchestrator, I want the verdict to reflect the severity of issues found, so that I can route the poster to rework or approval based on the QA outcome.

#### Acceptance Criteria

1. WHEN the LLM returns an `issues` list containing at least one issue with `severity` of `high`, THE `PosterQAAgent` SHALL ensure the `verdict` is `"fail"`.
2. WHEN the LLM returns an `issues` list containing at least one issue with `severity` of `medium` and no `high` severity issues, THE `PosterQAAgent` SHALL instruct the LLM to set the `verdict` to `"fail"`.
3. WHEN the LLM returns an `issues` list containing only `low` severity issues or an empty list, THE `PosterQAAgent` SHALL instruct the LLM that the `verdict` may be `"pass"`.
4. THE `QAPromptBuilder` SHALL include explicit verdict determination rules in every prompt: `fail` if any `high` or `medium` severity issue exists; `pass` only if all issues are `low` or the list is empty.
