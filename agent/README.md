# Agent - LLM Governance Script Generator

The agent is responsible for generating, testing, and refining governance scripts using LLMs.

## Architecture

```
Agent (Port 8002)
├── LLM Client → AWS Bedrock (Claude)
└── Sandbox Client → Sandbox API (Port 8001)
```

The agent is **separate** from the sandbox:
- **Agent**: Generates code via LLM, orchestrates workflow
- **Sandbox**: Executes code, validates structure, provides API reference

## Running the Agent

### Prerequisites

1. **Sandbox must be running** on port 8001:
   ```bash
   cd ../sandbox/sandboxengine
   python main.py
   ```

2. **AWS credentials** configured:
   - IAM credentials (access key + secret)
   - OR AWS SSO session
   - OR bearer token

### Start Agent Server

```bash
cd agent
pip install -r requirements.txt
uvicorn main:app --port 8002 --reload
```

Agent will be available at `http://localhost:8002`

## API Endpoints

### Start Pipeline

```bash
POST /pipeline/start
{
  "policy_text": "When a message contains spam...",
  "document_schemas": {},
  "aws_access_key_id": "...",
  "aws_secret_access_key": "...",
  "aws_region": "us-east-1"
}
→ {"run_id": "abc123", "status": "running"}
```

### Poll Status

```bash
GET /pipeline/{run_id}/status
→ {
  "run_id": "abc123",
  "status": "running",
  "current_stage": "script",
  "stages": {...}
}
```

### Get Stage Details

```bash
GET /pipeline/{run_id}/stages/script
→ {
  "stage": "script",
  "status": "completed",
  "output": {
    "script": "def setup(ctx): ...",
    "tokens_used": 4532,
    "latency_ms": 2341
  }
}
```

### WebSocket (Real-time updates)

```javascript
const ws = new WebSocket('ws://localhost:8002/pipeline/abc123/ws');
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(update.stages);
};
```

### Health Check

```bash
GET /health
→ {
  "status": "ok",
  "agent": "ok",
  "sandbox": "ok"
}
```

## Pipeline Stages

1. **Headers** - Generate function signatures from policy
2. **Script** - Implement functions with governance logic
3. **Tests** - Generate test scenarios (never sees script)
4. **Execute** - Run script against tests in sandbox
5. **Revise** - Fix failing scripts (up to 3 attempts)
6. **Suggestions** - Natural-language scenarios users can try in their real community to see the policy work (independent of the sandbox results: runs on the final script even if sandbox tests still failed after revisions; a failure here does not fail the run)
7. **Report** - Final pass/fail summary

### Scenario Suggestions

Generated automatically as the `suggestions` stage (`GET /pipeline/{run_id}/stages/suggestions`). The LLM first lists the parts of the policy worth seeing in practice (`focus_areas`), then designs as many scenarios as needed to cover them (`scenarios`, each with `covers`, `steps`, `expected_outcome`, etc.).

Can also be called without a pipeline run:

```bash
POST /scenarios/suggest
{"policy_text": "...", "aws_access_key_id": "...", "aws_secret_access_key": "..."}
# "script" is optional; include it to make scenarios specific to the implemented behaviour

POST /pipeline/{run_id}/suggestions     # regenerate for an existing run (credentials in body)
```

## Frontend Integration

The sandbox frontend calls the agent API:

```typescript
// Start pipeline
const response = await fetch('http://localhost:8002/pipeline/start', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    policy_text: policyText,
    document_schemas: documentSchemas,
    aws_access_key_id: '...',
    aws_secret_access_key: '...',
    aws_region: 'us-east-1'
  })
});

const { run_id } = await response.json();

// Poll or use WebSocket for updates
const pollStatus = setInterval(async () => {
  const status = await fetch(`http://localhost:8002/pipeline/${run_id}/status`);
  const data = await status.json();

  if (data.status === 'completed' || data.status === 'failed') {
    clearInterval(pollStatus);
    // Display results
  }
}, 1000);
```

## Configuration

Edit defaults in `llm_client.py`:

```python
DEFAULT_MODEL = "anthropic.claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 8000
```

Edit max revisions in `main.py`:

```python
orchestrator = PipelineOrchestrator(
    llm_client=llm_client,
    sandbox_client=sandbox_client,
    max_revisions=3  # Change this
)
```

## Development

### Add New LLM Prompt

1. Edit `llm_client.py`
2. Add new system/user prompt templates
3. Create generation function (e.g., `generate_foo()`)
4. Update orchestrator to call it

### Change Sandbox URL

```python
sandbox_client = SandboxClient(sandbox_url="http://remote-sandbox:8001")
```

### Debug Pipeline

Check agent logs for LLM calls:
```
2024-01-01 12:00:00 - agent.llm_client - INFO - [abc123] Headers generated (1234 tokens, 2341ms)
```

Check sandbox logs for execution:
```
2024-01-01 12:00:05 - sandboxengine - INFO - Executed 3 scenarios. Passed: 2/3
```

## Troubleshooting

**"Sandbox is not reachable"**
- Ensure sandbox is running on port 8001
- Check `http://localhost:8001/sandbox/health`

**"AWS credentials invalid"**
- Verify IAM credentials are correct
- Check AWS region matches your Bedrock access
- Try `aws bedrock list-foundation-models` in terminal

**"Pipeline stuck in running"**
- Check agent logs for exceptions
- Check LLM token limits (may hit max_tokens)
- Try shorter policy text

**"Tests always fail"**
- Check sandbox validation: `POST /sandbox/validate`
- Review generated script in `GET /pipeline/{run_id}/stages/script`
- Check error summary in revision stage

## Next Steps

See [REFACTORING_PLAN.md](../REFACTORING_PLAN.md) for full architecture details.
