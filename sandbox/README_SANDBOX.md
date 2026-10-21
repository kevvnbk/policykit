# PolicyKit Sandbox

A development sandbox for PolicyKit governance automation, featuring an LLM-powered agent that generates governance scripts from natural language policies.

## Repository Structure

```
pk-sandbox/
├── agent/           # LLM agent service (code generation, orchestration)
│   ├── prompts/     # Organized prompt templates for each generation stage
│   ├── llm_client.py
│   ├── orchestrator.py
│   ├── sandbox_client.py
│   └── main.py      # FastAPI server on port 8002
│
└── sandbox/         # Execution sandbox (policy engine, frontend)
    ├── sandboxengine/     # Core sandbox engine
    │   ├── policyengine/  # Policy execution runtime
    │   └── sandboxengine/ # API endpoints
    ├── frontend/          # React development UI
    ├── docs/             # Documentation
    └── examples/         # Example policies and scripts
```

## Architecture

The system is split into two independent services:

### Agent Service (Port 8002)
- Generates governance scripts from natural language policies using AWS Bedrock (Claude)
- Orchestrates the full pipeline: headers → script → tests → execution → revision
- Maintains organized prompt templates in `agent/prompts/`
- Communicates with sandbox via HTTP API

### Sandbox Service (Port 8001)
- Executes governance scripts in an isolated environment
- Provides policy engine APIs for script execution and validation
- Serves development frontend for testing policies
- Returns scenario results and action logs

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- AWS credentials configured (for LLM agent)

### Installation

1. **Install sandbox package:**
   ```bash
   cd sandbox
   pip install -e .
   ```

2. **Install agent dependencies:**
   ```bash
   cd ../agent
   pip install -r requirements.txt
   ```

3. **Install frontend dependencies:**
   ```bash
   cd ../sandbox/frontend
   npm install
   ```

### Running the Services

1. **Start sandbox server:**
   ```bash
   cd sandbox/sandboxengine
   python main.py
   # Runs on http://localhost:8001
   ```

2. **Start agent server:**
   ```bash
   cd agent
   python main.py
   # Runs on http://localhost:8002
   ```

3. **Start frontend (optional):**
   ```bash
   cd sandbox/frontend
   npm run dev
   # Runs on http://localhost:5173
   ```

## API Flow

1. **Frontend** fetches AWS credentials from `/credentials/aws` (sandbox)
2. **Frontend** sends policy + credentials to `/pipeline/start` (agent)
3. **Agent** generates code via LLM and sends scripts to sandbox endpoints
4. **Sandbox** executes scripts and returns results
5. **Frontend** polls `/pipeline/{id}/status` for progress

## Development

### Agent Development
- Prompts are organized in `agent/prompts/` by stage (headers, script, tests, revise)
- Each module has a `format_prompt()` function returning (system_prompt, user_prompt)
- Add new generation stages by creating a new prompt module

### Sandbox Development
- Core engine is in `sandbox/sandboxengine/policyengine/`
- Script execution happens in `engine.py`
- Add new API endpoints in `sandboxengine/sandbox_api.py`

## Testing

```bash
# Test sandbox execution
cd sandbox
pytest tests/

# Test agent orchestration
cd agent
pytest tests/

# Manual integration test via frontend
# 1. Start both services
# 2. Open http://localhost:5173
# 3. Paste a policy and click "Run Pipeline"
```

## Documentation

- [Sandbox Documentation](sandbox/README.md)
- [Agent Architecture](agent/README.md) *(if exists)*
- [Policy Authoring Guide](sandbox/docs/guides/policy-authoring-guide.md)
- [API Reference](sandbox/docs/guides/api_reference.md)

## Architecture Decision: Agent/Sandbox Split

The agent and sandbox were intentionally separated to:
- **Isolate concerns**: LLM generation logic stays out of execution environment
- **Enable reuse**: Sandbox can execute pre-written scripts without LLM
- **Simplify deployment**: Each service can scale independently
- **Clear boundaries**: Agent handles "how to generate", sandbox handles "how to run"

## Contributing

See individual service READMEs for contribution guidelines:
- [Agent Contributions](agent/README.md)
- [Sandbox Contributions](sandbox/README.md)

## License

[Your License Here]
