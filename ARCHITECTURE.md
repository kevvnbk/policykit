# PolicyKit Architecture

## Overview

PolicyKit is organized as a **monorepo** containing three independently deployable services:

1. **PolicyKit** (Django) - Main governance platform
2. **Sandbox** (FastAPI) - Policy testing and simulation environment
3. **Agent** (FastAPI) - LLM-powered policy generation service

```
┌─────────────────────────────────────────────────────────────────┐
│                        PolicyKit Monorepo                        │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │   PolicyKit    │  │    Sandbox     │  │      Agent       │  │
│  │    (Django)    │  │   (FastAPI)    │  │    (FastAPI)     │  │
│  │                │  │                │  │                  │  │
│  │  Port 8000     │  │  Port 8001     │  │  Port 8002       │  │
│  │                │  │                │  │                  │  │
│  │ • Live         │  │ • Test         │  │ • Generate       │  │
│  │   governance   │  │   policies     │  │   policies       │  │
│  │ • Community    │  │ • Simulate     │  │   from NL        │  │
│  │   management   │  │   scenarios    │  │ • LLM            │  │
│  │ • PostgreSQL   │  │ • Stateless    │  │   orchestration  │  │
│  │ • Celery       │  │                │  │ • Calls sandbox  │  │
│  └────────────────┘  └────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Service Details

### 1. PolicyKit (Django)

**Purpose:** Production governance platform for online communities

**Technology:**
- Framework: Django 3.2
- Database: PostgreSQL
- Task Queue: Celery + RabbitMQ
- Frontend: Vite + React

**Key Features:**
- User authentication and authorization
- Integration with platforms (Slack, Discord, Reddit, etc.)
- Live policy execution on community events
- Constitutional governance framework
- Action logging and history

**Port:** 8000

**Deployment:**
- Docker Compose (local dev)
- Can be deployed to any Django-compatible host
- Requires: PostgreSQL, RabbitMQ, persistent storage

---

### 2. Sandbox (FastAPI)

**Purpose:** Testing and simulation environment for governance policies

**Technology:**
- Framework: FastAPI
- Runtime: Python 3.11+
- Dependencies: RestrictedPython, Pydantic

**Key Features:**
- Execute governance scripts in isolated environment
- Simulate community events and scenarios
- Validate policy syntax and structure
- Test policies without affecting live communities
- Mock integrations (Slack, Discord, etc.)

**API Endpoints:**
- `POST /sandbox/execute` - Execute script against scenarios
- `POST /sandbox/validate` - Validate script syntax
- `GET /sandbox/api-reference` - Get API documentation
- `GET /sandbox/health` - Health check

**Port:** 8001

**Deployment:**
- Stateless (scales to zero)
- Google Cloud Run (recommended)
- Docker container

---

### 3. Agent (FastAPI)

**Purpose:** LLM-powered governance policy generation from natural language

**Technology:**
- Framework: FastAPI
- LLM: AWS Bedrock (Claude)
- Dependencies: boto3, websockets

**Key Features:**
- Generate policy headers from natural language
- Generate implementation scripts
- Generate test scenarios (independently from script)
- Execute tests via Sandbox API
- Revise failing policies (up to 3 attempts)
- WebSocket support for real-time progress

**API Endpoints:**
- `POST /pipeline/start` - Start policy generation pipeline
- `GET /pipeline/{id}/status` - Poll pipeline status
- `GET /pipeline/{id}/stages/{stage}` - Get stage output
- `WS /pipeline/{id}/ws` - Real-time progress updates
- `GET /health` - Health check

**Port:** 8002

**Deployment:**
- Stateless (scales to zero)
- Google Cloud Run (recommended)
- Docker container
- Requires: Sandbox URL, user AWS credentials

---

## Service Communication

```
┌──────────┐
│ Frontend │
└─────┬────┘
      │
      ├──────────────┐
      │              │
      ▼              ▼
┌──────────┐   ┌──────────┐
│PolicyKit │   │  Agent   │
│   API    │   │   API    │
└──────────┘   └────┬─────┘
                    │
                    ▼
              ┌──────────┐
              │ Sandbox  │
              │   API    │
              └──────────┘
```

**Communication Pattern:**
- Frontend → PolicyKit: Live governance operations
- Frontend → Agent: Generate new policies
- Frontend → Sandbox: Test policies directly
- Agent → Sandbox: Execute generated policies (HTTP)

**No database sharing** - each service is independent

---

## Deployment Options

### Option 1: Google Cloud Run (Recommended)

Deploy all 3 services independently:

```bash
# Deploy all services
GCP_PROJECT_ID=your-project ./deploy-all.sh all

# Or deploy individually
GCP_PROJECT_ID=your-project ./deploy-all.sh policykit
GCP_PROJECT_ID=your-project ./deploy-all.sh sandbox
GCP_PROJECT_ID=your-project ./deploy-all.sh agent
```

**Result:**
- `https://policykit-api-xxx.run.app` - Django
- `https://sandbox-api-xxx.run.app` - Sandbox
- `https://agent-api-xxx.run.app` - Agent

**Scaling:**
- PolicyKit: min=1, max=10 (always running)
- Sandbox: min=0, max=10 (scales to zero)
- Agent: min=0, max=5 (scales to zero)

**Cost:**
- PolicyKit: ~$10-30/month
- Sandbox: $0 when idle, ~$0.01/request
- Agent: $0 when idle, LLM costs paid by user

---

### Option 2: Docker Compose (Local Development)

```bash
# Use the full compose file
docker-compose -f docker-compose-full.yml up

# Or use profiles for specific services
docker-compose up web frontend postgres rabbit  # PolicyKit only
docker-compose up sandbox                        # Add sandbox
docker-compose up agent                          # Add agent
```

**Access:**
- PolicyKit: http://localhost:8000
- Sandbox: http://localhost:8001
- Agent: http://localhost:8002
- RabbitMQ UI: http://localhost:15672

---

### Option 3: Kubernetes

Create separate deployments:

```yaml
# k8s/policykit-deployment.yaml
# k8s/sandbox-deployment.yaml
# k8s/agent-deployment.yaml
```

Use services for inter-service communication.

---

## Frontend Integration

### Calling PolicyKit

```javascript
// Existing PolicyKit API calls
const response = await fetch('http://localhost:8000/api/communities', {
  method: 'GET',
  headers: { 'Authorization': 'Bearer ' + token }
});
```

### Calling Sandbox

```javascript
// Test a policy
const response = await fetch('http://localhost:8001/sandbox/execute', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    script: policyScript,
    scenarios: testScenarios
  })
});

const { results } = await response.json();
```

### Calling Agent

```javascript
// Generate a policy from natural language
const response = await fetch('http://localhost:8002/pipeline/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    policy_text: "Delete messages containing spam",
    document_schemas: {},
    aws_access_key_id: userAwsKey,
    aws_secret_access_key: userAwsSecret,
    aws_region: "us-east-1"
  })
});

const { run_id } = await response.json();

// Poll for results
const statusResponse = await fetch(`http://localhost:8002/pipeline/${run_id}/status`);
const status = await statusResponse.json();
```

---

## Shared Code

The monorepo enables code sharing without tight coupling:

```python
# Agent can import sandbox types
from sandbox.sandboxengine.policyengine.scenarios import Scenario, ScenarioResult

# Sandbox can import PolicyKit utilities
from policykit.policyengine.safe_exec_code import execute_user_code

# But at runtime, they communicate via HTTP APIs
```

---

## Why Not a Monolith?

### ❌ Why NOT integrate into one Django app:

1. **Different scaling needs**
   - PolicyKit needs to be always-on
   - Sandbox/Agent should scale to zero when idle

2. **Different tech stacks**
   - FastAPI is better for stateless APIs
   - Django is better for full web apps with auth/DB

3. **Optional components**
   - A PolicyKit installation doesn't need sandbox/agent
   - Research users might only want sandbox

4. **Independent development**
   - Teams can work on each service independently
   - Deploy services independently

5. **Cost efficiency**
   - Don't pay for LLM generation infrastructure 24/7
   - Sandbox scales down when not testing

---

## When to Use Each Service

| Task | Service | Why |
|------|---------|-----|
| Manage live community | PolicyKit | Full governance platform |
| Test a policy before deploying | Sandbox | Isolated testing environment |
| Generate policy from NL | Agent | LLM-powered generation |
| Write policy manually | Sandbox | Use API reference, test locally |
| Review policy effectiveness | PolicyKit | Real action logs and analytics |

---

## Configuration

### Environment Variables

**PolicyKit:**
- `DATABASE_URL` - PostgreSQL connection
- `CELERY_BROKER_URL` - RabbitMQ connection
- `ALLOWED_HOSTS` - Allowed domains
- `DJANGO_SECRET_KEY` - Django secret

**Sandbox:**
- `ENVIRONMENT` - production|development
- `ALLOWED_ORIGINS` - CORS allowed origins
- `RATE_LIMIT` - Rate limit (e.g., 10/minute)

**Agent:**
- `SANDBOX_URL` - URL of sandbox service
- `ENVIRONMENT` - production|development

---

## Development Workflow

1. **Start all services:**
   ```bash
   docker-compose -f docker-compose-full.yml up
   ```

2. **Access services:**
   - PolicyKit: http://localhost:8000
   - Sandbox: http://localhost:8001
   - Agent: http://localhost:8002

3. **Make changes:**
   - Edit files in `policykit/`, `sandbox/`, or `agent/`
   - Hot reload enabled in development

4. **Test integration:**
   ```bash
   # Test sandbox imports
   python -c "from sandbox.sandboxengine.policyengine.scenarios import Scenario"
   
   # Test agent → sandbox
   python -c "from agent.sandbox_client import SandboxClient"
   
   # Test sandbox → policykit
   python -c "from policykit.policyengine.safe_exec_code import execute_user_code"
   ```

5. **Deploy:**
   ```bash
   GCP_PROJECT_ID=your-project ./deploy-all.sh all
   ```

---

## Benefits of This Architecture

✅ **Monorepo Benefits:**
- Shared code via imports
- Single repository to manage
- Atomic cross-service changes
- Shared CI/CD pipeline

✅ **Independent Services Benefits:**
- Scale independently
- Deploy independently
- Optional components
- Technology flexibility

✅ **Best of Both Worlds:**
- Code sharing without tight coupling
- Independent scaling and deployment
- Clear service boundaries
- Pay only for what you use

---

## Migration from Previous Setup

**Before:** Separate `pk-sandbox` repository with agent + sandbox

**After:** Monorepo with 3 services (policykit + agent + sandbox)

**What Changed:**
- ✅ Imports: `from policyengine.*` → `from sandbox.sandboxengine.policyengine.*`
- ✅ No more `policykit_path.py` sys.path manipulation
- ✅ All code in one repository
- ❌ Architecture: **No change** - still 3 separate services
- ❌ APIs: **No change** - same endpoints
- ❌ Deployment: **No change** - still independently deployed

**Result:** Better code organization, same runtime architecture.

---

## Next Steps

1. **Local Development:**
   ```bash
   docker-compose -f docker-compose-full.yml up
   ```

2. **Deploy to Cloud:**
   ```bash
   chmod +x deploy-all.sh
   GCP_PROJECT_ID=your-project ./deploy-all.sh all
   ```

3. **Update Frontend:**
   - Configure API URLs for all 3 services
   - Test integration with each service

4. **Monitor:**
   - Google Cloud Console for metrics
   - Service logs via `gcloud run services logs tail`
