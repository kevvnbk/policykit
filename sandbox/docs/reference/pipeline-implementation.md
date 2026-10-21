# Pipeline Implementation Guide

This document describes the full LLM-powered pipeline implementation, including
the workflow, prompts used, design choices, and integration points.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       Frontend (React)                      │
│  Port 5174 — Vite dev server with proxy to backend          │
│  Three-panel layout: Policy Input | Pipeline | Inspector    |
│  Polls /sandbox/run/{id}/status every 1s while running      │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTP (proxied)
┌─────────────────────────────▼───────────────────────────────┐
│                     Backend (FastAPI)                       │
│  Port 8001 — sandboxengine/main.py                          │
│                                                             │
│  POST /sandbox/run → creates run, launches background thread│
│  GET  /sandbox/run/{id}/status → returns current stage state│
│  GET  /sandbox/history → list all runs                      │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│               PipelineOrchestrator (tasks.py)               │
│                                                             │
│  Manages pipeline runs. Two modes:                          │
│  1. execute_full() — full LLM pipeline (background thread)  │
│  2. execute_with_script() — pre-written script (sync)       │
└─────────────────────────────┬───────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │  llm.py     │   │  engine.py  │   │  utils.py   │
    │  LLM calls  │   │  Execution  │   │  Error      │
    │  via Bedrock│   │  sandbox    │   │  handling   │
    └─────────────┘   └─────────────┘   └─────────────┘
```

---

## Pipeline Stages

### Stage 1: Generate Headers

**Purpose**: Translate NL policy into Python function signatures.

**Why this stage exists**: Separates intent (what functions are needed) from
implementation (how they work). The headers become a shared contract: the script
generator implements them, and the test generator tests against them — without
either seeing the other's work.

**LLM Call**:
- Model: Claude Sonnet 4.6 (via Bedrock)
- Temperature: 0.3 (low — we want deterministic, focused output)
- Max tokens: 2000

**Prompt strategy**: System prompt instructs the model to produce function stubs
with type hints and docstrings. User prompt provides the NL policy + full API
reference. The model returns Python code with `pass` bodies.

**Example output**:
```python
def setup(ctx):
    """Register spam detection handler."""
    pass

def handle_message(event, ctx):
    """Check if message contains spam keywords and delete if so."""
    pass
```

---

### Stage 2: Generate Script

**Purpose**: Implement the functions defined in Stage 1.

**Key design choice**: The script generator receives both the headers AND the
original NL policy. It does NOT see the test scenarios. This prevents the
implementation from being shaped by test expectations rather than policy intent.

**LLM Call**:
- Temperature: 0.2 (very low — implementation should be precise)
- Max tokens: 4000

**Prompt strategy**: System prompt emphasizes using ctx.on()/ctx.emit_action()
and keeping code simple. User prompt provides headers, policy, and API reference.
The model returns a complete, self-contained script.

**Output constraints**:
- Must define setup(ctx) that registers handlers
- Import standard library modules (datetime, json, re, etc.) as needed at the top
- Must use ctx.store for state persistence
- Note: RestrictedPython sandboxing planned but not yet implemented

---

### Stage 3: Generate Tests

**Purpose**: Create scenario-based tests that verify the policy's behavior.

**Critical design principle**: Tests are generated from headers + NL policy,
NEVER from the implementation script. This prevents bias where tests are
written to match what the code does rather than what the policy requires.
This is the same separation used in the main project's PK-Slack workflow.

**LLM Call**:
- Temperature: 0.3 (slightly creative — diverse test scenarios)
- Max tokens: 6000

**Prompt strategy**: System prompt defines the scenario JSON schema and
available assertion types. User prompt provides NL policy, function headers
(NOT the script), and API reference. The model returns a JSON array.

**Output format**: JSON array of scenario objects, each with:
- `community_setup` — users, channels, roles
- `events` — timeline of community events
- `assertions` — expected outcomes to verify

**Target**: 3-8 scenarios per policy covering:
- Happy path (policy triggers correctly)
- Boundary conditions (thresholds, timing)
- Negative cases (policy should NOT trigger)
- Edge cases mentioned in the policy

---

### Stage 4: Execute

**Purpose**: Run the generated script against all test scenarios.

**No LLM involved** — this is deterministic execution:
1. Build community from scenario's `community_setup`
2. Create PolicyContext + EventBus
3. Call script's `setup(ctx)` to register handlers
4. Replay events in timestamp order, firing registered handlers
5. Check assertions against final community/action state

**Engine details** (engine.py):
- `SandboxRunner.run(script, scenario)` → `ScenarioResult`
- Scripts execute via Python `exec()` (not RestrictedPython in MVP — see Future Work)
- Time simulation via EventBus: `advance_time()` fires scheduled tasks
- Actions recorded in `community.actions` list

---

### Stage 5: Revise (Retry Loop)

**Purpose**: If execution fails, fix the script and retry.

**When triggered**: Only if Stage 4 has failing scenarios.

**Loop**:
1. Build structured error summary (which scenarios failed, why, which assertions)
2. Call LLM with: original policy + current script + error summary + API reference
3. LLM returns fixed script
4. Re-execute all scenarios
5. If still failing and attempts < MAX_REVISION_ATTEMPTS (3), goto 1

**LLM Call**:
- Temperature: 0.2 (precise fixes)
- Max tokens: 4000

**Prompt strategy**: System prompt categorizes errors (SYNTAX, API_MISUSE,
BEHAVIORAL, TIMEOUT) and instructs focused fixes. The revision prompt shows
exactly which assertions failed and why, giving the model clear targets.

**Design choice**: We re-run ALL scenarios, not just failing ones. A fix for
one failure might break another scenario. This catches regressions.

---

### Stage 6: Report

**Purpose**: Summarize results for the UI.

**No LLM involved** — deterministic aggregation:
- Total scenarios, passed, failed
- Revision count
- Per-scenario action logs
- Pipeline timing

---

## Execution Model

### Why Background Threads?

The full pipeline takes 15-30 seconds (multiple LLM calls). A blocking request
would timeout or leave the user staring at a spinner with no progress indication.

Instead:
1. `POST /sandbox/run` returns immediately with run ID
2. Pipeline executes in a `threading.Thread(daemon=True)`
3. Frontend polls `GET /status` every 1 second
4. Each stage transitions: pending → running → completed/failed
5. UI updates in real-time as stages complete

### Thread Safety

Each run has its own thread and its own state (PipelineRun dataclass). The
orchestrator's `_runs` dict is the only shared state — Python's GIL makes
dict reads/writes atomic. No explicit locking needed for this use case.

---

## Prompt Design Principles

### 1. API Reference Injection

Every LLM call includes the full `docs/api_reference.md`. This ensures the model
knows exactly what's available (ctx.on, ctx.emit_action, ctx.store, etc.) and
doesn't hallucinate non-existent methods. The reference is ~4KB — well within
context limits.

### 2. Output Format Enforcement

Each prompt explicitly states the expected output format and ends with
"Return ONLY X — no markdown fences, no explanation." The extraction functions
(`_extract_python_code`, `_extract_json`) handle cases where the model adds
fences despite instructions.

### 3. Temperature Calibration

| Stage | Temperature | Rationale |
|-------|------------|-----------|
| Headers | 0.3 | Mostly deterministic (what functions are needed) |
| Script | 0.2 | Implementation should be precise and correct |
| Tests | 0.3 | Slightly creative to generate diverse scenarios |
| Revise | 0.2 | Bug fixes should be surgical, not creative |

### 4. Separation of Concerns

The key insight (borrowed from the main project's PK-Slack workflow): the test
generator NEVER sees the script implementation. It receives only function headers.
This prevents a class of bugs where tests are "too easy" because they test what
the code does rather than what the policy requires.

---

## Error Handling

### Error Categories (utils.py)

| Category | Examples | LLM Guidance |
|----------|----------|-------------|
| SYNTAX | IndentationError, SyntaxError | "Fix syntax at line N" |
| API_MISUSE | AttributeError on ctx, TypeError | "Check API reference for correct method" |
| BEHAVIORAL | Assertions fail (wrong actions taken) | "Logic doesn't match policy" |
| TIMEOUT | Infinite loop | "Reduce computation or add bounds" |

### Graceful Degradation

- If headers generation fails → pipeline stops, reports error
- If script generation fails → pipeline stops (can't test nothing)
- If test generation returns invalid JSON → pipeline stops
- If execution fails → enters revision loop
- If revision exhausts attempts → reports partial results (shows what passed)
- If LLM returns empty/garbage → caught at extraction, reported as stage error

---

## Frontend Architecture

### Three-Panel Layout

```
┌──────────┬───────────────────┬───────────────────┐
│          │                   │                   │
│  Policy  │    Pipeline       │    Inspector      │
│  Input   │    Stages         │    (detail view)  │
│          │                   │                   │
│  Examples│    ● Headers      │    Status: ...    │
│          │    ● Script       │    Output: ...    │
│  History │    ● Tests        │    Error: ...     │
│          │    ● Execute      │                   │
│          │    ● Revise       │                   │
│          │    ● Report       │                   │
│          │                   │                   │
│          │    Result: PASS   │                   │
└──────────┴───────────────────┴───────────────────┘
│             Action Log (collapsible)             │
└──────────────────────────────────────────────────┘
```

### Polling Mechanism

```javascript
// Start polling after run creation
pollRef.current = setInterval(async () => {
  const data = await fetch(`/sandbox/run/${runId}/status`)
  setCurrentRun(data)
  if (data.status !== 'running') {
    clearInterval(pollRef.current)
  }
}, 1000)
```

Cleanup on unmount prevents memory leaks. Selecting a different history item
stops any active poll.

---

## Integration with Main Project

### Shared Patterns

| Pattern | Main Project | Sandbox |
|---------|-------------|---------|
| LLM abstraction | `app/services/llm_service.py` | `policyengine/llm.py` |
| Bedrock client | `BedrockClient` class | `_call_bedrock()` function |
| Prompt loading | File-based with `_load_prompt()` | Inline constants (simpler) |
| Code extraction | `_extract_python_code()` | Same function, copied |
| Pipeline stages | PK-Slack 5-step workflow | 6-stage pipeline |
| Test separation | Headers-only for test gen | Same principle |
| Error handling | pytest output parsing | Scenario assertion checking |

### Key Differences

| Concern | Main Project | Sandbox |
|---------|-------------|---------|
| Policy model | PolicyKit class inheritance | Function registration |
| Test format | pytest scripts | Declarative JSON scenarios |
| Execution | subprocess + pytest | In-process SandboxRunner |
| State | Django ORM | In-memory per-scenario |
| Async model | FastAPI async endpoints | Background threads |

---

## Future Work

- **RestrictedPython execution**: Currently scripts run via bare `exec()`.
  Wire up the borrowed `safe_exec_code.py` for actual sandboxing.
- **Prompt versioning**: Save/load prompt versions like the main project's
  prompt management system.
- **Model selection**: Allow frontend to choose between Sonnet/Opus/Haiku.
- **Streaming**: Use Bedrock streaming for real-time token output in the inspector.
- **Revision diffs**: Show what changed between revision attempts.
- **Parallel test/script generation**: Stages 2 and 3 can run concurrently
  since they only depend on Stage 1 (headers).
