#!/bin/bash
# Test script for deployed pipeline API

set -e

echo "================================================="
echo "Testing PolicyKit Pipeline API"
echo "================================================="
echo ""

# Check for AWS credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "❌ Error: AWS credentials not set"
    echo ""
    echo "Please set your AWS credentials:"
    echo "  export AWS_ACCESS_KEY_ID=your-key"
    echo "  export AWS_SECRET_ACCESS_KEY=your-secret"
    echo "  export AWS_SESSION_TOKEN=your-token  # optional, required for SSO"
    echo "  export AWS_REGION=us-east-2  # optional"
    echo ""
    exit 1
fi

API_URL="https://agent-api-695390404745.us-central1.run.app"
POLICY_TEXT="Delete any message that contains the word 'spam'"
REGION=${AWS_REGION:-us-east-2}

echo "📋 Policy: $POLICY_TEXT"
echo "🌍 Region: $REGION"
echo ""

# Build request body
REQUEST_BODY="{
  \"policy_text\": \"$POLICY_TEXT\",
  \"aws_access_key_id\": \"$AWS_ACCESS_KEY_ID\",
  \"aws_secret_access_key\": \"$AWS_SECRET_ACCESS_KEY\",
  \"aws_region\": \"$REGION\""

# Add session token if present (required for SSO/temporary credentials)
if [ -n "$AWS_SESSION_TOKEN" ]; then
    REQUEST_BODY="$REQUEST_BODY,
  \"aws_session_token\": \"$AWS_SESSION_TOKEN\""
fi

REQUEST_BODY="$REQUEST_BODY
}"

# Start pipeline
echo "🚀 Starting pipeline..."
START_RESPONSE=$(curl -s -X POST "$API_URL/pipeline/start" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_BODY")

RUN_ID=$(echo $START_RESPONSE | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$RUN_ID" ]; then
    echo "❌ Failed to start pipeline"
    echo "Response: $START_RESPONSE"
    exit 1
fi

echo "✅ Pipeline started: $RUN_ID"
echo ""
echo "⏳ Waiting for completion (this takes 30-90 seconds)..."
echo ""

# Poll status
DOTS=0
while true; do
    sleep 2

    STATUS_RESPONSE=$(curl -s "$API_URL/pipeline/$RUN_ID/status")
    STATUS=$(echo $STATUS_RESPONSE | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

    # Show progress dots
    printf "."
    DOTS=$((DOTS + 1))
    if [ $DOTS -ge 30 ]; then
        echo ""
        DOTS=0
    fi

    # Check if done
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        echo ""
        echo ""

        if [ "$STATUS" = "completed" ]; then
            echo "================================================="
            echo "✅ Pipeline Completed Successfully!"
            echo "================================================="
            echo ""

            # Extract script (basic JSON parsing)
            SCRIPT=$(echo $STATUS_RESPONSE | sed 's/.*"script":"\([^"]*\)".*/\1/' | sed 's/\\n/\n/g' | sed 's/\\"/"/g')

            echo "Generated Script:"
            echo "----------------"
            echo "$SCRIPT" | head -50
            echo ""

            # Check if truncated
            LINES=$(echo "$SCRIPT" | wc -l)
            if [ $LINES -gt 50 ]; then
                echo "... (truncated, showing first 50 lines)"
            fi

        else
            echo "================================================="
            echo "❌ Pipeline Failed"
            echo "================================================="
            echo ""
            echo "Full Response:"
            echo "$STATUS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATUS_RESPONSE"
        fi

        break
    fi
done

echo ""
echo "View full status at:"
echo "$API_URL/pipeline/$RUN_ID/status"
