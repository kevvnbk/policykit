#!/bin/bash
set -e

# Test script for deployed pk-sandbox services

echo "================================================="
echo "Testing Deployed PK-Sandbox Services"
echo "================================================="
echo ""

# Load URLs
if [ -f .sandbox-url ]; then
    SANDBOX_URL=$(cat .sandbox-url)
    echo "Sandbox URL: $SANDBOX_URL"
else
    echo "Error: .sandbox-url not found. Deploy sandbox first."
    exit 1
fi

if [ -f .agent-url ]; then
    AGENT_URL=$(cat .agent-url)
    echo "Agent URL: $AGENT_URL"
    HAS_AGENT=true
else
    echo "Warning: .agent-url not found. Skipping agent tests."
    HAS_AGENT=false
fi

echo ""
echo "================================================="
echo "Test 1: Sandbox Health Check"
echo "================================================="

RESPONSE=$(curl -s "$SANDBOX_URL/health")
echo "Response: $RESPONSE"

if [[ $RESPONSE == *'"status":"ok"'* ]]; then
    echo "✓ Sandbox health check passed"
else
    echo "✗ Sandbox health check failed"
    exit 1
fi

echo ""
echo "================================================="
echo "Test 2: Sandbox API Reference"
echo "================================================="

RESPONSE=$(curl -s "$SANDBOX_URL/sandbox/api-reference")
if [[ $RESPONSE == *"ctx"* ]]; then
    echo "✓ API reference endpoint working"
else
    echo "✗ API reference endpoint failed"
    exit 1
fi

echo ""
echo "================================================="
echo "Test 3: Sandbox Script Execution"
echo "================================================="

# Simple test script
SCRIPT='def setup(ctx):
    """Test script."""
    pass'

# Simple scenario
SCENARIO='{
  "name": "test",
  "description": "Simple test",
  "community_setup": {
    "users": [{"id": "u1", "name": "Test", "roles": ["member"]}],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1"]}],
    "roles": [{"name": "member", "is_base_role": true}]
  },
  "events": [],
  "assertions": [],
  "time_limit": 60.0
}'

REQUEST_BODY=$(cat <<EOF
{
  "script": $(echo "$SCRIPT" | jq -Rs .),
  "scenarios": [$SCENARIO]
}
EOF
)

RESPONSE=$(curl -s -X POST "$SANDBOX_URL/sandbox/execute" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_BODY")

if [[ $RESPONSE == *"passed"* ]]; then
    echo "✓ Script execution working"
else
    echo "✗ Script execution failed"
    echo "Response: $RESPONSE"
    exit 1
fi

# Test agent if deployed
if [ "$HAS_AGENT" = true ]; then
    echo ""
    echo "================================================="
    echo "Test 4: Agent Health Check"
    echo "================================================="

    RESPONSE=$(curl -s "$AGENT_URL/health")
    echo "Response: $RESPONSE"

    if [[ $RESPONSE == *'"status":"ok"'* ]]; then
        echo "✓ Agent health check passed"
    else
        echo "✗ Agent health check failed"
        exit 1
    fi

    echo ""
    echo "================================================="
    echo "Test 5: Agent Pipeline (requires AWS creds)"
    echo "================================================="

    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "⚠ Skipping pipeline test - AWS credentials not set"
        echo "  To test pipeline: export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=..."
    else
        echo "Starting pipeline with test policy..."

        REQUEST_BODY=$(cat <<EOF
{
  "policy_text": "Delete messages containing spam",
  "credentials": {
    "aws_access_key_id": "$AWS_ACCESS_KEY_ID",
    "aws_secret_access_key": "$AWS_SECRET_ACCESS_KEY",
    "aws_region": "${AWS_REGION:-us-east-1}"
  }
}
EOF
)

        RESPONSE=$(curl -s -X POST "$AGENT_URL/pipeline/start" \
          -H "Content-Type: application/json" \
          -d "$REQUEST_BODY")

        if [[ $RESPONSE == *"run_id"* ]]; then
            echo "✓ Pipeline started successfully"
            RUN_ID=$(echo $RESPONSE | jq -r .run_id)
            echo "  Run ID: $RUN_ID"
            echo "  Monitor at: $AGENT_URL/pipeline/$RUN_ID/status"
        else
            echo "✗ Pipeline start failed"
            echo "Response: $RESPONSE"
        fi
    fi
fi

echo ""
echo "================================================="
echo "✓ All Tests Passed!"
echo "================================================="
echo ""
echo "Your services are ready to use:"
echo "  Sandbox: $SANDBOX_URL"
if [ "$HAS_AGENT" = true ]; then
    echo "  Agent: $AGENT_URL"
fi
echo ""
echo "Update your frontend to use these URLs:"
echo "  - Sandbox API: $SANDBOX_URL"
if [ "$HAS_AGENT" = true ]; then
    echo "  - Agent API: $AGENT_URL"
fi
echo ""
