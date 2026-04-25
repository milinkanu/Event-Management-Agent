# Requirements Document

## Introduction

The Poster Learning Agent is a LangGraph-compatible Python agent that observes poster design outcomes over time and builds a simple pattern memory. It accepts a poster design JSON and a user feedback signal (Approved or Rejected), stores what worked and what did not, and produces a plain-language insight plus a future adjustment recommendation. The agent requires no machine learning — it uses rule-based pattern counting and an LLM to summarise findings in human-readable language. It integrates with the existing `LLMClient`, follows the `AgentResult` pattern used throughout the WiMLDS pipeline, and is designed to slot into the LangGraph orchestrator after the user feedback step.

## Glossary

- **PosterLearningAgent**: The top-level orchestrator class that coordinates the full learning pipeline and exposes the public API.
- **FeedbackRecord**: A single observation stored in pattern memory, containing a `design_snapshot` (subset of the poster design JSON), a `feedback` value (`approved` or `rejected`), and a `timestamp`.
- **PatternStore**: The in-memory (and optionally file-backed) component that persists `FeedbackRecord` entries and exposes query methods for layout and color pattern counts.
- **InsightBuilder**: The component that queries `PatternStore` for pattern counts and constructs the LLM prompt asking for a plain-language insight and future adjustment.
- **InsightOutputValidator**: The component that validates the LLM's raw dict output against the required `{"insight": str, "future_adjustment": str}` schema.
- **DesignSnapshot**: The subset of the poster design JSON captured per feedback record — specifically `layout` and `colors` (the two fields most relevant to learning).
- **Feedback**: A string value that is exactly `"approved"` or `"rejected"` (case-insensitive on input, normalised to lowercase on storage).
- **PatternSummary**: A dict produced by `PatternStore` summarising counts of approved/rejected layouts and color combinations, used as input to `InsightBuilder`.
- **LLMClient**: The existing shared client that wraps Anthropic Claude (with OpenAI fallback) and exposes a `generate_json()` method.
- **AgentResult**: The standard result envelope used throughout the WiMLDS pipeline, containing `success`, `data`, and `error` fields.
- **ValidationError**: An exception raised by `InsightOutputValidator` when the LLM output does not satisfy the required schema.
- **MAX_RETRIES**: The configurable maximum number of LLM call attempts before the agent returns a failure result.

---

## Requirements

### Requirement 1: Input Acceptance and Validation

**User Story:** As a pipeline node, I want to submit a poster design JSON and a feedback signal so that the agent can record the outcome and learn from it.

#### Acceptance Criteria

1. WHEN a non-empty `dict` is provided as `design_json` containing at least the keys `layout` and `colors`, THE `PosterLearningAgent` SHALL accept it as valid input.
2. WHEN `feedback` is provided as the string `"approved"` or `"rejected"` (case-insensitive), THE `PosterLearningAgent` SHALL accept it as valid input.
3. IF `design_json` is `None` or an empty dict, THEN THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` and a descriptive error string.
4. IF `design_json` is missing the `layout` key, THEN THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` identifying the missing key.
5. IF `design_json` is missing the `colors` key, THEN THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` identifying the missing key.
6. IF `feedback` is not `"approved"` or `"rejected"` (after case normalisation), THEN THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` and a descriptive error string.
7. THE `PosterLearningAgent` SHALL NOT mutate the `design_json` or `feedback` arguments passed to it.

---

### Requirement 2: Pattern Storage

**User Story:** As the agent, I want to store each design outcome so that I can accumulate enough observations to identify which layouts succeed and which color combinations fail.

#### Acceptance Criteria

1. WHEN `PosterLearningAgent.learn()` is called with valid inputs, THE `PatternStore` SHALL append a new `FeedbackRecord` containing the `DesignSnapshot` (layout and colors) and the normalised feedback value.
2. THE `PatternStore` SHALL record the `layout` value from `design_json` in every `FeedbackRecord` it stores.
3. THE `PatternStore` SHALL record the `colors` value from `design_json` in every `FeedbackRecord` it stores.
4. THE `PatternStore` SHALL normalise the `feedback` value to lowercase before storing it.
5. WHEN `PatternStore.get_summary()` is called, THE `PatternStore` SHALL return a `PatternSummary` dict containing counts of approved and rejected occurrences grouped by `layout`.
6. WHEN `PatternStore.get_summary()` is called, THE `PatternStore` SHALL return a `PatternSummary` dict containing counts of approved and rejected occurrences grouped by `colors` combination.
7. THE `PatternStore` SHALL NOT lose previously stored records when a new record is appended.
8. WHEN `PatternStore` is initialised with a file path, THE `PatternStore` SHALL load existing records from that file on startup.
9. WHEN a new record is appended and a file path is configured, THE `PatternStore` SHALL persist the updated records to that file.

---

### Requirement 3: Insight Generation

**User Story:** As a user, I want the agent to produce a plain-language insight and a future adjustment recommendation so that I can understand what the agent has learned without needing to read raw data.

#### Acceptance Criteria

1. WHEN `PosterLearningAgent.learn()` is called with valid inputs, THE `PosterLearningAgent` SHALL invoke `InsightBuilder` to produce an insight after storing the record.
2. WHEN `InsightBuilder.build_prompt()` is called, THE `InsightBuilder` SHALL embed the full `PatternSummary` in the prompt.
3. THE `InsightBuilder` SHALL instruct the LLM to return a JSON object with exactly two keys: `insight` and `future_adjustment`.
4. THE `InsightBuilder` SHALL instruct the LLM to use plain language with no ML jargon.
5. THE `InsightBuilder` SHALL instruct the LLM to return pure JSON with no markdown fences and no explanation.
6. WHEN the LLM returns a valid response, THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=True` and `data` containing `insight` and `future_adjustment` as non-empty strings.
7. WHEN `PatternStore` contains fewer than 2 records, THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=True` and `data["insight"]` indicating that not enough data has been collected yet.

---

### Requirement 4: Output Validation

**User Story:** As a caller, I want the agent output to always conform to the `{"insight": "", "future_adjustment": ""}` schema so that I can consume it without additional checks.

#### Acceptance Criteria

1. WHEN `InsightOutputValidator.validate()` is called with a dict containing both `insight` and `future_adjustment` as non-empty strings, THE `InsightOutputValidator` SHALL return the validated dict unchanged.
2. IF the LLM output is not a dict, THEN THE `InsightOutputValidator` SHALL raise a `ValidationError` with a descriptive message.
3. IF `insight` is absent from the LLM output, THEN THE `InsightOutputValidator` SHALL raise a `ValidationError` identifying the missing key.
4. IF `future_adjustment` is absent from the LLM output, THEN THE `InsightOutputValidator` SHALL raise a `ValidationError` identifying the missing key.
5. IF `insight` is an empty string, THEN THE `InsightOutputValidator` SHALL raise a `ValidationError` indicating the value must be non-empty.
6. IF `future_adjustment` is an empty string, THEN THE `InsightOutputValidator` SHALL raise a `ValidationError` indicating the value must be non-empty.
7. THE `InsightOutputValidator` SHALL NOT mutate the dict passed to it.

---

### Requirement 5: Retry Mechanism

**User Story:** As a caller, I want the agent to automatically retry failed LLM calls with corrective hints so that transient or schema-related failures are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN `InsightOutputValidator.validate()` raises a `ValidationError`, THE `PosterLearningAgent` SHALL retry the LLM call with a correction hint appended to the prompt.
2. WHEN a `json.JSONDecodeError` is raised during the LLM call, THE `PosterLearningAgent` SHALL retry the LLM call up to `MAX_RETRIES` times.
3. THE `PosterLearningAgent` SHALL attempt at most `MAX_RETRIES` total LLM calls before returning a failure result.
4. WHEN all retry attempts are exhausted without a valid result, THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` and a non-empty `error` string.
5. THE `PosterLearningAgent` SHALL accept `max_retries` as a constructor parameter with a default value of `2`.

---

### Requirement 6: Error Handling

**User Story:** As a caller, I want the agent to return a structured failure result for all error conditions rather than raising exceptions so that I can handle failures uniformly.

#### Acceptance Criteria

1. THE `PosterLearningAgent.learn()` SHALL never raise an exception to the caller under any input condition.
2. IF the LLM API raises a network, rate-limit, or authentication error, THEN THE `PosterLearningAgent` SHALL return an `AgentResult` with `success=False` and `error` set to the exception message.
3. THE `PosterLearningAgent` SHALL NOT retry LLM API-level errors (network failures, rate limits, authentication errors).
4. WHEN `AgentResult.success` is `False`, THE `PosterLearningAgent` SHALL ensure `AgentResult.error` is a non-empty, human-readable string describing the failure.

---

### Requirement 7: AgentResult Contract

**User Story:** As a WiMLDS pipeline node, I want the agent to return results using the standard `AgentResult` envelope so that it integrates consistently with the rest of the pipeline.

#### Acceptance Criteria

1. THE `PosterLearningAgent` SHALL always return an `AgentResult` from `learn()`, regardless of success or failure.
2. WHEN the learning succeeds, THE `PosterLearningAgent` SHALL set `AgentResult.success = True` and populate `AgentResult.data` with `{"insight": str, "future_adjustment": str}`.
3. WHEN the learning fails, THE `PosterLearningAgent` SHALL set `AgentResult.success = False` and populate `AgentResult.error` with a descriptive string.
4. THE `PosterLearningAgent` SHALL NOT mutate the `design_json` or `feedback` arguments passed to `learn()`.

---

### Requirement 8: LangGraph Node Interface

**User Story:** As a LangGraph workflow author, I want to use the agent as a drop-in graph node so that I can integrate poster learning into any LangGraph pipeline without custom wiring.

#### Acceptance Criteria

1. THE `PosterLearningAgent` SHALL expose a `run(state: dict) -> dict` method compatible with the LangGraph node interface.
2. WHEN `run()` is called, THE `PosterLearningAgent` SHALL read `design_json` from `state["design_json"]` and `feedback` from `state["feedback"]`.
3. WHEN `learn()` succeeds in `run()`, THE `PosterLearningAgent` SHALL write `state["learning_insight"]` with the `AgentResult.data` dict and return the updated state.
4. WHEN `learn()` fails in `run()`, THE `PosterLearningAgent` SHALL return the state dict unchanged (without writing `learning_insight`).
5. THE `PosterLearningAgent` SHALL accept a `dry_run` boolean constructor parameter that controls whether real LLM calls are made.
6. WHEN `dry_run=True`, THE `PosterLearningAgent` SHALL store the record in `PatternStore` but return a deterministic stub `AgentResult` with `data={"insight": "dry-run", "future_adjustment": "dry-run"}` without calling the LLM.

---

### Requirement 9: Serialization Round-Trip

**User Story:** As a developer, I want `FeedbackRecord` serialization to be lossless so that records are not corrupted when saving to and loading from a file.

#### Acceptance Criteria

1. WHEN a `FeedbackRecord` is serialised to a dict via `to_dict()` and the resulting dict is passed to `FeedbackRecord.from_dict()`, THE `PatternStore` SHALL reconstruct an equivalent `FeedbackRecord`.
2. THE `FeedbackRecord.to_dict()` SHALL produce a dict containing exactly the keys `design_snapshot`, `feedback`, and `timestamp`.
3. FOR ALL valid `FeedbackRecord` objects, serialising then deserialising SHALL produce an equivalent record (round-trip property).
