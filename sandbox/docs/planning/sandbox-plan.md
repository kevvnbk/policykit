# Sandbox Implementation Plan

## Overview

The sandbox simulates an online community where LLM-generated governance code can be tested against realistic scenarios. It validates both syntactic correctness (does it parse?) and behavioural correctness (does it produce the right outcomes given community interactions?).

The sandbox is a **standalone Python runtime** — no Django, no Celery. Generated scripts import sandbox infrastructure classes and execute directly against generated test scenarios. The directory structure mirrors PolicyKit to ease future integration.

---

## Pipeline

```
NL Policy (Slack-adapted)
  │
  ├─ [1] Generate Function Headers + API docs
  │       ↓
  ├─ [2] Generate Script (from headers + sandbox API)
  │       ↓
  ├─ [3] Generate Test Suite (from headers + sandbox API, NOT from script)
  │       ↓
  ├─ [4] Execute in Sandbox (script against tests)
  │       ↓
  ├─ [5] Revise on Error (structured error summaries → LLM → retry)
  │       ↓
  └─ [6] Report (pass/fail, action logs, flagged ambiguities)
```

Key design principle: Steps 2 and 3 both receive the headers from Step 1 but **never see each other's output**. This prevents bias where tests are written to match the implementation rather than the spec.

---

## Code Provenance Tracking

### Direct PolicyKit Imports (✅ Migration Complete)

The sandbox now imports directly from the PolicyKit repository instead of copying code.

| Module | PolicyKit Source | Import Pattern |
|--------|------------------|----------------|
| `safe_exec_code` | `policykit/policyengine/safe_exec_code.py` | `from policykit.policyengine.safe_exec_code import execute_user_code, policykit_builtins, STATIC_GLOBAL_VARIABLES, OwnRestrictingNodeTransformer` |
| `engine` (if needed) | `policykit/policyengine/engine.py` | `from policykit.policyengine.engine import AttrDict, exec_code_block, PolicyCodeError` |

**Note**: The sandbox is now integrated into the main PolicyKit repository, so no path setup is needed.

### Adapted from PolicyKit (logic preserved, Django stripped)

| Component | PolicyKit Source | Adaptation | Integration Path |
|-----------|-----------------|------------|------------------|
| `DataStore` | `policyengine/models.py:407-464` | Replace `models.Model` with plain dict. Same `get/set/remove` interface. | Replace with PolicyKit DataStore import |
| Vote tallying | `Proposal.get_yes_votes()` etc. + BooleanVote/ChoiceVote/SelectVote/NumberVote | Replace ORM queries with list comprehensions. Unified into `VoteTracker`. | Replace with Proposal vote interface |
| Community model (User) | `CommunityUser` (line 291): readable_name, get_roles(), has_role() | Stripped to dataclass. Same field names. | Replace with CommunityUser queries |
| Community model (roles) | `CommunityRole` (line 248): role_name, is_base_role, user_set | Simplified to `dict[str, list[str]]`. | Replace with CommunityRole queries |
| Action recording | `LogAPICall` + `actstream` + persisted GovernableAction | Consolidated into single `ActionLog` class | Replace with actstream + GovernableAction |
| PolicyContext | `EvaluationContext` (engine.py:30-108) | Same "context object IS API surface" pattern. Event-handler model. | Adapt to wrap EvaluationContext |

### New (sandbox-specific, no PolicyKit equivalent)

| Component | File Location | Purpose | Why No PK Equivalent |
|-----------|--------------|---------|---------------------|
| EventBus | `policyengine/handlers.py` | In-memory pub/sub dispatch | PK uses Django Signals + Metagov |
| EventLog | `policyengine/handlers.py` | Queryable event history | PK actstream tracks lifecycle, not raw events |
| Time simulation | `policyengine/handlers.py` | Virtual clock via event timestamps | PK uses real `datetime.now()` + Celery beat |
| Channel model | `policyengine/models.py` | Simulated chat channel | PK has no channel model (calls live Slack API) |
| Message model | `policyengine/models.py` | Simulated chat message | PK uses SlackPostMessage (a GovernableAction) |
| Scenario schema | `policyengine/engine.py` | Declarative test format | PK uses imperative Django TestCases |
| SandboxRunner | `policyengine/engine.py` | Executes scripts against scenarios | PK needs Django test runner + DB + mocking |
| Error classification | `policyengine/utils.py` | Categorizes failures for revision | PK raises generic PolicyCodeError |
| Pipeline orchestrator | `policyengine/tasks.py` | Manages generation pipeline | No LLM integration in PK |
| API reference doc | `docs/` | Structured doc for LLM prompt injection | N/A |

---

## Implementation Order

| Step | File(s) | What To Build |
|------|---------|---------------|
| 1 | `policyengine/models.py` | Community, User, Channel, Message, DataStore, VoteTracker |
| 2 | `policyengine/handlers.py` | Event, EventLog, EventBus (with time simulation) |
| 3 | `policyengine/engine.py` | PolicyContext, SandboxRunner, Scenario, assertions |
| 4 | `integrations/slack/models.py` | SlackCommunity (simulated), Slack event types |
| 5 | `integrations/slack/handlers.py` | Slack event → sandbox event mapping |
| 6 | `tests/utils.py` + `tests/test_engine.py` | Fixtures + engine tests |
| 7 | `policyengine/tasks.py` | PipelineOrchestrator |
| 8 | `sandboxengine/api_views.py` | REST endpoints |
| 9 | `policyengine/utils.py` | Error classification, API ref loading, LLM integration |
| 10 | `frontend/` | React UI |

---

## Generated Script Interface

Scripts use **function registration** (not PolicyKit's 5-stage class inheritance):

```python
def setup(ctx):
    ctx.on("message_posted", handle_message)
    ctx.schedule(3600, check_quiet_channels)

def handle_message(event, ctx):
    if "spam" in event.data.get("text", "").lower():
        ctx.emit_action("delete_message", message_id=event.data["message_id"])
```

**Why function registration?** Advisor preference: sandbox should define its own optimal abstraction. Class inheritance constrains LLM output format and mirrors PolicyKit internals unnecessarily.

---

## UI Plan

Three-panel layout:
- **Left**: NL policy input + run history
- **Center**: Pipeline stages with progress (clickable)
- **Right**: Context-sensitive inspector (code, tests, traces, diffs)
- **Footer**: Collapsible action log (transparency trace)

Technology: React + Vite on port 5174, proxying to FastAPI on port 8001.

---

## Policy Authoring Guide

See [policy-authoring-guide.md](./policy-authoring-guide.md) for comprehensive guidance on writing natural language policies. Key topics:

- What makes a good policy (triggers, conditions, actions, edge cases, timing)
- Slack platform capabilities and limitations
- Common pitfalls (vague conditions, unsupported events, missing state tracking)
- Examples of good vs. bad policies
- Quality checklist for policy authors and LLM generators

---

## What We're NOT Doing (Yet)

| Deferred | Reason |
|----------|--------|
| Personas / persona-driven test generation | Focus on prescribed edge cases first |
| External data adapters | DataStore covers basic state needs |
| PolicyKit integration / translation | Sandbox designs own abstraction first |
| Platform-specific API simulation | Actions are abstract, not Slack-specific |
| Multi-policy interaction | v1 tests one policy at a time |
| Non-Slack integrations | Slack first; others are stubs |
