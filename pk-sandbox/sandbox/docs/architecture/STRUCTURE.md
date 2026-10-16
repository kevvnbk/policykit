# Sandbox Directory Structure

This document maps the sandbox's directory structure to PolicyKit's, explaining what each file is responsible for and how it relates to its PolicyKit counterpart.

## High-Level Comparison

```
PolicyKit                          Sandbox
─────────────────────────         ─────────────────────────
policykit/                         sandbox/
├── docs/                          ├── docs/
├── frontend/                      ├── frontend/
└── policykit/      (django root)  └── sandboxengine/    (app root)
    ├── manage.py                      ├── main.py
    ├── requirements.txt               ├── requirements.txt
    ├── policykit/  (settings)         ├── sandboxengine/  (settings)
    │   ├── settings.py                │   ├── settings.py
    │   ├── urls.py                    │   ├── urls.py
    │   └── celery.py                  │   └── api_views.py
    ├── policyengine/                  ├── policyengine/
    │   ├── models.py                  │   ├── models.py
    │   ├── engine.py                  │   ├── engine.py
    │   ├── safe_exec_code.py          │   ├── safe_exec_code.py (re-export)
    │   ├── handlers.py                │   ├── handlers.py
    │   ├── tasks.py                   │   ├── tasks.py
    │   └── utils.py                   │   └── utils.py
    ├── integrations/                  ├── integrations/
    │   ├── slack/                     │   ├── slack/
    │   │   ├── models.py              │   │   ├── models.py
    │   │   ├── handlers.py            │   │   ├── handlers.py
    │   │   ├── utils.py               │   │   ├── utils.py
    │   │   └── tests.py               │   │   └── tests.py
    │   └── ...                        │   └── ...
    ├── tests/                         ├── tests/
    │   ├── utils.py                   │   ├── utils.py
    │   ├── test_engine.py             │   ├── test_engine.py
    │   └── test_exec_code.py          │   └── test_exec_code.py
    N/A                                └── policykit_borrowed/
                                           ├── safe_exec_code.py (verbatim)
                                           └── exec_utils.py     (verbatim)
```

## File-by-File Mapping

### Project Root (`sandboxengine/`)

| File | PK Equivalent | Purpose |
|------|--------------|---------|
| `main.py` | `manage.py` | Application entry point. Starts uvicorn/FastAPI. |
| `requirements.txt` | `requirements.txt` | Python dependencies |

### Settings Package (`sandboxengine/sandboxengine/`)

| File | PK Equivalent | Purpose |
|------|--------------|---------|
| `settings.py` | `policykit/settings.py` | Configuration constants (ports, model, limits) |
| `urls.py` | `policykit/urls.py` | FastAPI app creation + router mounting |
| `api_views.py` | `policyengine/api_views.py` | REST API endpoint definitions |

### Core Engine (`sandboxengine/policyengine/`)

| File | PK Equivalent | Purpose |
|------|--------------|---------|
| `models.py` | `policyengine/models.py` | Community, User, Role, Action, Proposal, DataStore, Vote models |
| `engine.py` | `policyengine/engine.py` | PolicyContext, script execution, SandboxRunner |
| `safe_exec_code.py` | `policyengine/safe_exec_code.py` | Re-exports from `policykit_borrowed/` |
| `handlers.py` | `policyengine/handlers.py` | EventBus, EventLog, event dispatch |
| `tasks.py` | `policyengine/tasks.py` | Pipeline orchestration (replaces Celery tasks) |
| `utils.py` | `policyengine/utils.py` | Error classification, API reference loading |

### Integrations (`sandboxengine/integrations/`)

Each integration follows PolicyKit's file pattern:

| File | Purpose |
|------|---------|
| `__init__.py` | Package marker |
| `models.py` | Platform-specific community + action models |
| `handlers.py` | Event type mapping and dispatch |
| `utils.py` | Helpers for event construction and fixtures |
| `tests.py` | Platform-specific test scenarios |

**Slack** (`integrations/slack/`) is the primary focus. All other integrations are stubs.

### Tests (`sandboxengine/tests/`)

| File | PK Equivalent | Purpose |
|------|--------------|---------|
| `utils.py` | `tests/utils.py` | Community fixtures, predefined policy scripts |
| `test_engine.py` | `tests/test_engine.py` | Core execution, event dispatch, assertions |
| `test_exec_code.py` | `tests/test_exec_code.py` | RestrictedPython sandbox verification |

### Borrowed Code (`sandboxengine/policykit_borrowed/`)

**NO PolicyKit equivalent** — this directory is unique to the sandbox.

Contains verbatim copies of PolicyKit code that has zero Django dependencies. These files are NOT modified and will be deleted when PolicyKit is integrated directly.

| File | PK Source | Contains |
|------|-----------|----------|
| `safe_exec_code.py` | `policyengine/safe_exec_code.py` | `execute_user_code()`, builtins, guards |
| `exec_utils.py` | `policyengine/engine.py:30-405` | `AttrDict`, `exec_code_block()`, `PolicyCodeError` |

## Key Architectural Differences

| Concern | PolicyKit | Sandbox |
|---------|-----------|---------|
| Framework | Django + DRF | FastAPI + Pydantic |
| Persistence | PostgreSQL via Django ORM | In-memory (per scenario) |
| Async tasks | Celery + Redis | Synchronous pipeline |
| Event dispatch | Django Signals + Metagov | EventBus (in-memory pub/sub) |
| Time | Real wall-clock (`datetime.now`) | Simulated (virtual clock) |
| External APIs | Live Slack/Discord/etc. | Simulated (actions recorded, not executed) |
| Code execution | RestrictedPython | RestrictedPython (same) |
| Policy model | 5-stage class (filter/init/check/notify/pass/fail) | Event-handler registration (setup + on/schedule) |

## What Goes Where (When Implementing)

- **New community model?** → `policyengine/models.py`
- **New event type?** → `policyengine/handlers.py` (EventBus) + relevant integration's `handlers.py`
- **New Slack action?** → `integrations/slack/models.py`
- **Execution logic?** → `policyengine/engine.py`
- **Pipeline/orchestration?** → `policyengine/tasks.py`
- **Test fixtures?** → `tests/utils.py`
- **API endpoint?** → `sandboxengine/api_views.py`
- **Configuration?** → `sandboxengine/settings.py`
