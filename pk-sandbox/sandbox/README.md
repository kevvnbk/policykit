# Policy Sandbox

A standalone sandbox environment for generating, testing, and validating governance policy scripts against simulated community scenarios.

## Architecture

This repository mirrors PolicyKit's directory structure to ease future integration. The sandbox replaces Django/Celery/Metagov with lightweight standalone equivalents while keeping naming conventions, file organization, and integration patterns identical.

```
sandbox/
├── README.md
├── docs/                        # Documentation (organized by type)
│   ├── README.md                # Documentation index
│   ├── architecture/            # System design and structure
│   ├── guides/                  # Step-by-step tutorials
│   ├── planning/                # Design documents
│   └── reference/               # Quick references
├── examples/                    # Example policies and runners
├── scripts/                     # Utility scripts (Google Sheets, etc.)
├── tests/                       # Test suite
│   ├── integration/             # Integration tests
│   └── test_*.py                # Unit tests
├── frontend/                    # React/Vite UI (mirrors PolicyKit frontend/)
└── sandboxengine/               # Core engine (mirrors PolicyKit policykit/)
    ├── main.py                  # Entry point (replaces manage.py)
    ├── requirements.txt
    ├── sandboxengine/           # Project config (mirrors policykit/policykit/)
    │   ├── settings.py          # Configuration
    │   ├── urls.py              # FastAPI route registration
    │   └── api_views.py         # API endpoints
    ├── policyengine/            # Core engine (mirrors policykit/policyengine/)
    │   ├── models.py            # Community, User, Role, Action, Proposal
    │   ├── engine.py            # Policy evaluation logic
    │   ├── handlers.py          # Event dispatch
    │   ├── tasks.py             # Pipeline orchestration
    │   ├── utils.py             # Utilities
    │   ├── validation.py        # Validation pipeline
    │   └── datasources/         # Data source module
    │       ├── base.py          # Abstract interfaces
    │       ├── mock.py          # In-memory testing implementation
    │       └── __init__.py      # Module exports
    ├── integrations/            # Platform integrations (mirrors policykit/integrations/)
    │   ├── slack/               # Slack (primary focus)
    │   ├── discord/             # Stub
    │   ├── discourse/           # Stub
    │   ├── github/              # Stub
    │   ├── reddit/              # Stub
    │   ├── opencollective/      # Stub
    │   ├── loomio/              # Stub
    │   └── sourcecred/          # Stub
    ├── tests/                   # Sandboxengine unit tests
    └── policykit_path.py        # PolicyKit import path setup
```

## Relationship to PolicyKit

| PolicyKit | Sandbox Equivalent | Notes |
|-----------|-------------------|-------|
| Django ORM models | Pydantic/dataclass models | Same field names and method signatures |
| Django Signals + Metagov | EventBus (in-memory pub/sub) | Same event types |
| Celery beat tasks | Simulated time + scheduled handlers | Same periodic re-evaluation pattern |
| `manage.py` | `main.py` (uvicorn + FastAPI) | Same entry point role |
| `policykit/settings.py` | `sandboxengine/settings.py` | Configuration |
| `policyengine/` | `policyengine/` | Core models, engine, execution |
| `integrations/slack/` | `integrations/slack/` | Slack-specific models and handlers |
| `tests/` | `tests/` | Centralized test suite |
| `safe_exec_code.py` | Direct import from PolicyKit's `policyengine/safe_exec_code.py` | See POLICYKIT_INTEGRATION.md |

## Running

```bash
# Backend (port 8001)
cd sandboxengine
pip install -r requirements.txt
python main.py

# Frontend (port 5174)
cd frontend
npm install
npm run dev
```

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

- **[Policy Authoring Guide](docs/guides/policy-authoring-guide.md)** - Write governance policies
- **[Test Scenario Guide](docs/test-scenario-guide.md)** - Write test scenarios for the sandbox
- **[Test Scenario Quick Reference](docs/test-scenario-quick-reference.md)** - Cheat sheet for scenarios
- **[API Reference](docs/guides/api_reference.md)** - Sandbox API (ctx.*, events, assertions)
- **[External Documents Guide](docs/guides/external-documents-guide.md)** - Google Sheets integration
- **[Documentation Index](docs/README.md)** - Full documentation catalog

## API Authentication

The sandbox pipeline API supports two authentication methods for AWS Bedrock:

1. **IAM Credentials** (access key + secret key)
   - Standard AWS IAM authentication
   - Supports temporary credentials via session tokens (AWS SSO)

2. **Bearer Token** (alternative auth)
   - Direct bearer token authentication
   - Useful for proxy/gateway services

See [API_INTEGRATION_GUIDE.md](API_INTEGRATION_GUIDE.md) for integration details.

## Design Principles

1. **Mirror PolicyKit naming**: File names, class names, method signatures match PolicyKit wherever the concept exists.
2. **Slack first**: The Slack integration is the primary focus. Other integrations are stubs.
3. **Direct PolicyKit imports**: The sandbox now imports directly from PolicyKit (see [POLICYKIT_INTEGRATION.md](POLICYKIT_INTEGRATION.md)).
4. **Integration path is clear**: Each sandbox component documents which PolicyKit class/module it replaces, so integration is a find-and-replace of imports.
