# Requirements Document

## Introduction

The Brand Intelligence Agent is a new publishing pipeline component that analyses unstructured text
(social media posts, website copy, marketing content) and extracts structured brand identity signals:
dominant colors, communication tone, and visual style hints. The agent follows the same
`InputNormalizer → PromptBuilder → LLMClient → OutputValidator → AgentResult` architecture used by
`ContentExtractionAgent` and `PosterDesignDecisionAgent`. Its output is a strict JSON envelope that
downstream agents (e.g. `PosterDesignDecisionAgent`) can consume directly as `brand_colors` and
tone context.

---

## Glossary

- **Brand_Intelligence_Agent**: The top-level orchestrator class that coordinates the full extraction pipeline and exposes `analyse(raw_input) -> AgentResult` and `run(state: dict) -> dict`.
- **Input_Normalizer**: The component responsible for accepting and normalising raw text or dict input into a plain string before prompt construction.
- **Prompt_Builder**: The component that constructs LLM prompts embedding the normalised input, output schema, tone vocabulary, and anti-hallucination rules.
- **Output_Validator**: The component that validates the raw LLM dict against the required JSON schema and returns a `BrandProfile` dataclass on success.
- **BrandProfile**: The structured result dataclass with fields `brand_colors: list[str]`, `tone: str`, and `style_notes: list[str]`.
- **LLM_Client**: The existing `wimlds.integrations.llm.llm_client.LLMClient` used for all LLM calls.
- **AgentResult**: The existing `wimlds.core.result.AgentResult` envelope (`success`, `data`, `error`).
- **Tone**: One of the four allowed tone labels: `luxury`, `fun`, `minimal`, `corporate`.
- **Hex_Color**: A CSS hex color string matching the pattern `#[0-9A-Fa-f]{3,6}`.
- **ValidationError**: An internal exception raised by `Output_Validator` when the LLM output violates the schema.

---

## Requirements

### Requirement 1: Input Acceptance and Normalisation

**User Story:** As a developer integrating the Brand Intelligence Agent, I want the agent to accept
both plain text and dict inputs, so that I can pass social media posts, website content, or
pre-structured data without pre-processing.

#### Acceptance Criteria

1. WHEN a non-empty string is provided, THE Input_Normalizer SHALL strip leading and trailing whitespace and return the result unchanged.
2. WHEN a non-empty dict is provided, THE Input_Normalizer SHALL serialise it to a JSON string and return that string.
3. IF the input is `None`, THEN THE Input_Normalizer SHALL raise a `ValueError` with a descriptive message.
4. IF the input is an empty string, THEN THE Input_Normalizer SHALL raise a `ValueError` with a descriptive message.
5. IF the input is an empty dict, THEN THE Input_Normalizer SHALL raise a `ValueError` with a descriptive message.
6. THE Input_Normalizer SHALL NOT mutate the original input value.

---

### Requirement 2: Prompt Construction

**User Story:** As a developer, I want the LLM prompt to embed all schema constraints and
anti-hallucination rules, so that the model returns valid, grounded output on the first attempt.

#### Acceptance Criteria

1. THE Prompt_Builder SHALL embed the normalised input text in every prompt it produces.
2. THE Prompt_Builder SHALL include the exact output JSON schema with fields `brand_colors`, `tone`, and `style_notes` in every prompt.
3. THE Prompt_Builder SHALL list all four valid tone values (`luxury`, `fun`, `minimal`, `corporate`) in every prompt.
4. THE Prompt_Builder SHALL instruct the model to return an empty list for `brand_colors` when no colors can be confidently identified.
5. THE Prompt_Builder SHALL instruct the model to return an empty string for `tone` when the tone cannot be confidently determined.
6. THE Prompt_Builder SHALL instruct the model to return an empty list for `style_notes` when no style hints can be confidently identified.
7. THE Prompt_Builder SHALL instruct the model to return pure JSON with no markdown fences, no preamble, and no explanation.
8. WHEN a correction is requested, THE Prompt_Builder SHALL append the previous error message to the base prompt as a correction hint.

---

### Requirement 3: LLM Output Validation

**User Story:** As a developer, I want the agent to validate every LLM response against the schema
before accepting it, so that downstream agents always receive well-formed data.

#### Acceptance Criteria

1. WHEN the LLM returns a valid dict, THE Output_Validator SHALL return a populated `BrandProfile` dataclass.
2. IF the LLM output is not a dict, THEN THE Output_Validator SHALL raise a `ValidationError`.
3. IF any of the required keys (`brand_colors`, `tone`, `style_notes`) is absent, THEN THE Output_Validator SHALL raise a `ValidationError` identifying the missing key.
4. IF `brand_colors` is not a list, THEN THE Output_Validator SHALL raise a `ValidationError`.
5. IF any element of `brand_colors` is not a string matching `#[0-9A-Fa-f]{3,6}`, THEN THE Output_Validator SHALL raise a `ValidationError` identifying the invalid value.
6. IF `tone` is a non-empty string that is not one of `luxury`, `fun`, `minimal`, `corporate`, THEN THE Output_Validator SHALL raise a `ValidationError`.
7. IF `style_notes` is not a list of strings, THEN THE Output_Validator SHALL raise a `ValidationError`.
8. THE Output_Validator SHALL accept an empty list for `brand_colors`.
9. THE Output_Validator SHALL accept an empty string for `tone`.
10. THE Output_Validator SHALL accept an empty list for `style_notes`.
11. THE Output_Validator SHALL normalise `tone` to lowercase before validation.
12. THE Output_Validator SHALL NOT mutate the input dict.

---

### Requirement 4: Retry and Error Handling

**User Story:** As a developer, I want the agent to retry with a correction prompt on validation
failures, so that transient LLM formatting errors are recovered automatically.

#### Acceptance Criteria

1. WHEN a `ValidationError` is raised, THE Brand_Intelligence_Agent SHALL rebuild the prompt with a correction hint and retry the LLM call.
2. THE Brand_Intelligence_Agent SHALL retry at most `max_retries` times (default: 2).
3. WHEN `max_retries` attempts are exhausted without a valid response, THE Brand_Intelligence_Agent SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
4. WHEN a `json.JSONDecodeError` is raised, THE Brand_Intelligence_Agent SHALL increment the retry counter and attempt again.
5. WHEN any other exception is raised during an LLM call, THE Brand_Intelligence_Agent SHALL return an `AgentResult` with `success=False` immediately without further retries.
6. THE Brand_Intelligence_Agent SHALL never raise an exception to the caller; all errors SHALL be returned as `AgentResult(success=False, error=...)`.

---

### Requirement 5: Successful Extraction Output

**User Story:** As a developer, I want a successful extraction to return a structured `AgentResult`
with the brand profile data, so that downstream agents can consume it without additional parsing.

#### Acceptance Criteria

1. WHEN extraction succeeds, THE Brand_Intelligence_Agent SHALL return `AgentResult(success=True, data={"brand_profile": <dict>})`.
2. THE `brand_profile` dict SHALL contain exactly the keys `brand_colors`, `tone`, and `style_notes`.
3. THE `brand_colors` value SHALL be a list of zero or more Hex_Color strings.
4. THE `tone` value SHALL be one of `luxury`, `fun`, `minimal`, `corporate`, or an empty string.
5. THE `style_notes` value SHALL be a list of zero or more strings.

---

### Requirement 6: LangGraph Node Interface

**User Story:** As a pipeline engineer, I want the agent to expose a `run(state)` method compatible
with the LangGraph node interface, so that it can be wired into the existing publishing graph.

#### Acceptance Criteria

1. THE Brand_Intelligence_Agent SHALL implement `run(state: dict) -> dict`.
2. WHEN `run` is called, THE Brand_Intelligence_Agent SHALL read the raw input from `state["raw_brand_input"]`.
3. WHEN extraction succeeds, THE Brand_Intelligence_Agent SHALL write the brand profile dict to `state["brand_profile"]`.
4. WHEN extraction fails, THE Brand_Intelligence_Agent SHALL NOT write `state["brand_profile"]`.
5. THE Brand_Intelligence_Agent SHALL return the updated state dict in all cases.

---

### Requirement 7: Dry-Run Mode

**User Story:** As a developer writing tests, I want a `dry_run` mode that bypasses the LLM, so
that I can test the pipeline wiring without incurring API costs.

#### Acceptance Criteria

1. WHEN `dry_run=True` is passed to the constructor, THE Brand_Intelligence_Agent SHALL return a deterministic stub `AgentResult` without calling the LLM.
2. THE stub result SHALL have `success=True` and a `brand_profile` dict with the correct keys.
3. THE Brand_Intelligence_Agent SHALL NOT mutate the input or state dict in dry-run mode.

---

### Requirement 8: BrandProfile Data Model

**User Story:** As a developer, I want a typed `BrandProfile` dataclass that mirrors the output
JSON contract, so that I can work with brand data in a type-safe way.

#### Acceptance Criteria

1. THE BrandProfile SHALL be a dataclass with fields: `brand_colors: list[str]`, `tone: str`, `style_notes: list[str]`.
2. THE BrandProfile SHALL implement `to_dict() -> dict` returning exactly the keys `brand_colors`, `tone`, `style_notes`.
3. FOR ALL valid `BrandProfile` instances, constructing a `BrandProfile` from `to_dict()` output SHALL produce an equivalent object (round-trip property).

---

### Requirement 9: No Hallucination Contract

**User Story:** As a downstream consumer, I want the agent to return empty values rather than
fabricated data when the input does not contain sufficient brand signals, so that I can trust the
output is grounded in the provided text.

#### Acceptance Criteria

1. THE Prompt_Builder SHALL include an explicit instruction that the model must not infer or fabricate brand colors not present in the input text.
2. THE Prompt_Builder SHALL include an explicit instruction that the model must return empty values when confidence is low.
3. THE Output_Validator SHALL accept empty `brand_colors`, empty `tone`, and empty `style_notes` as valid outputs.
