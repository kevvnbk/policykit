## Sandbox PolicyEngine Module

This `policyengine` module contains **sandbox-specific** code that mirrors PolicyKit's structure but implements sandbox functionality (simulation, testing, etc.).

### Important: PolicyKit vs Sandbox policyengine

There are TWO separate `policyengine` modules:

1. **PolicyKit's policyengine** (`policykit/policyengine/`)
   - Contains the production PolicyKit code
   - Used for RestrictedPython execution, core models, etc.

2. **Sandbox's policyengine** (`sandbox/sandboxengine/policyengine/`)
   - Contains sandbox-specific testing and simulation code
   - Mirrors PolicyKit structure but implements different functionality

### Importing from PolicyKit

When sandbox code needs to use PolicyKit's functionality (e.g., `execute_user_code`, `policykit_builtins`), import directly from PolicyKit:

```python
# Import from PolicyKit's policyengine module
from policykit.policyengine.safe_exec_code import execute_user_code, policykit_builtins
from policykit.policyengine.engine import AttrDict, exec_code_block
```

Note: PolicyKit is now integrated into the same repository, so no sys.path manipulation is needed.

### Files in This Module

| File | Purpose |
|------|---------|
| `__init__.py` | Package marker (empty) |
| `engine.py` | Sandbox execution engine, PolicyContext, SandboxRunner |
| `handlers.py` | Event bus and event handling for simulation |
| `models.py` | Sandbox data models (Community, User, Channel, Message, etc.) |
| `utils.py` | Utility functions for error handling and API reference |
| `validation.py` | Script and test validation logic |
| `tasks.py` | Pipeline orchestration for LLM-driven code generation |
| `llm.py` | LLM integration for code generation and revision |
| `datasources.py` | External data source integration |
| `datasources_sandbox.py` | Sandbox implementations of data sources |

### Do NOT Create Re-exports

DO NOT create files like `safe_exec_code.py` in this directory that try to re-export from PolicyKit. This causes circular imports because both PolicyKit and the sandbox have a `policyengine` module.
