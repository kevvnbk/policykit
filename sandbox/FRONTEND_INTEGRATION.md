# PolicyKit Sandbox - Frontend Integration Guide

Complete guide for integrating the PolicyKit script generation pipeline into your frontend application.

---

## Quick Start

**Agent API URL:**  
```
https://agent-api-695390404745.us-central1.run.app
```

**Single workflow:**
1. POST to `/pipeline/start` with policy text + AWS credentials
2. Poll `/pipeline/{run_id}/status` every 1-2 seconds
3. Pipeline completes in 30-90 seconds
4. Get generated script from final response

---

## Architecture Overview

The system consists of two services:

```
Your Frontend
    ↓
Agent API (port 8002)
    ↓ generates code using AWS Bedrock
    ↓
Sandbox API (port 8001)
    ↓ executes & validates scripts
    ↓
Results back to Agent → Frontend
```

**You only need to call the Agent API.** It handles all communication with the sandbox.

---

## API Reference

### 1. Start Pipeline

**Endpoint:** `POST /pipeline/start`

**Request:**
```typescript
interface StartPipelineRequest {
  policy_text: string;              // Natural language policy description (10-10000 chars)
  document_schemas?: object;        // Optional: external document schemas
  
  // AWS Bedrock credentials (required - provided at root level)
  // The user must provide their own AWS credentials
  aws_access_key_id: string;        // AWS access key
  aws_secret_access_key: string;    // AWS secret key
  aws_session_token?: string;       // Optional: for temporary credentials
  aws_region?: string;              // Optional: defaults to "us-east-1"
}
```

**Response:**
```typescript
interface StartPipelineResponse {
  run_id: string;                   // Unique ID for this pipeline run
  status: "running";                // Initial status
}
```

**Example:**
```javascript
const response = await fetch('https://agent-api-695390404745.us-central1.run.app/pipeline/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    policy_text: "Delete any message that contains the word 'spam'",
    aws_access_key_id: "AKIA...",
    aws_secret_access_key: "...",
    aws_region: "us-east-1"
  })
});

const { run_id } = await response.json();
// run_id: "abc12345"
```

---

### 2. Poll Pipeline Status

**Endpoint:** `GET /pipeline/{run_id}/status`

**Response:**
```typescript
interface PipelineStatus {
  run_id: string;
  status: "running" | "completed" | "failed";
  policy_text: string;
  created_at: number;
  revision_count: number;
  
  stages: {
    headers: StageResult;
    script: StageResult;
    tests: StageResult;
    execute: StageResult;
    revise: StageResult;
    report: StageResult;
  };
}

interface StageResult {
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  output: any;                      // Stage-specific output
  error: string | null;             // Error message if failed
}
```

**Example:**
```javascript
// Poll every 1 second
const pollInterval = setInterval(async () => {
  const response = await fetch(
    `https://agent-api-695390404745.us-central1.run.app/pipeline/${run_id}/status`
  );
  const status = await response.json();
  
  console.log(`Status: ${status.status}`);
  
  if (status.status === 'completed' || status.status === 'failed') {
    clearInterval(pollInterval);
    handleResults(status);
  }
}, 1000);
```

---

### 3. WebSocket (Optional)

For real-time updates without polling:

**Endpoint:** `WS /pipeline/{run_id}/ws`

**Example:**
```javascript
const ws = new WebSocket(
  `wss://agent-api-695390404745.us-central1.run.app/pipeline/${run_id}/ws`
);

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(`Stage ${update.current_stage}: ${update.stages[update.current_stage]?.status}`);
  
  if (update.status === 'completed' || update.status === 'failed') {
    ws.close();
    handleResults(update);
  }
};
```

---

## Pipeline Stages

The pipeline progresses through 6 stages:

| Stage | Description | Output |
|-------|-------------|--------|
| **headers** | Generate function signatures | Python function stubs |
| **script** | Implement functions | Complete Python script |
| **tests** | Generate test scenarios | JSON test scenarios |
| **execute** | Run tests against script | Pass/fail results |
| **revise** | Fix failing scripts (if needed) | Revised script |
| **report** | Final summary | Pass/fail counts |

---

## Complete Example: React Component

```tsx
import { useState, useEffect } from 'react';

interface AWSCredentials {
  aws_access_key_id: string;
  aws_secret_access_key: string;
  aws_session_token?: string;
  aws_region?: string;
}

export function PolicyGenerator() {
  const [policyText, setPolicyText] = useState('');
  const [credentials, setCredentials] = useState<AWSCredentials>({
    aws_access_key_id: '',
    aws_secret_access_key: '',
    aws_region: 'us-east-1',
  });
  
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Start pipeline
  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setStatus(null);

    try {
      const response = await fetch(
        'https://agent-api-695390404745.us-central1.run.app/pipeline/start',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            policy_text: policyText,
            ...credentials, // Spread credentials at root level
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start pipeline');
      }

      const data = await response.json();
      setRunId(data.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setLoading(false);
    }
  };

  // Poll status when runId changes
  useEffect(() => {
    if (!runId) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(
          `https://agent-api-695390404745.us-central1.run.app/pipeline/${runId}/status`
        );
        const data = await response.json();
        setStatus(data);

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollInterval);
          setLoading(false);
        }
      } catch (err) {
        console.error('Poll error:', err);
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [runId]);

  // Extract generated script
  const generatedScript = status?.stages?.script?.output?.script || null;
  const finalStatus = status?.status;

  return (
    <div>
      <h2>Policy Generator</h2>
      
      {/* Policy Input */}
      <textarea
        value={policyText}
        onChange={(e) => setPolicyText(e.target.value)}
        placeholder="Enter your policy (e.g., Delete messages containing spam)"
        rows={4}
        cols={50}
      />

      {/* AWS Credentials */}
      <div>
        <input
          type="text"
          placeholder="AWS Access Key ID"
          value={credentials.aws_access_key_id}
          onChange={(e) => setCredentials({ ...credentials, aws_access_key_id: e.target.value })}
        />
        <input
          type="password"
          placeholder="AWS Secret Access Key"
          value={credentials.aws_secret_access_key}
          onChange={(e) => setCredentials({ ...credentials, aws_secret_access_key: e.target.value })}
        />
        <input
          type="text"
          placeholder="Region (default: us-east-1)"
          value={credentials.aws_region}
          onChange={(e) => setCredentials({ ...credentials, aws_region: e.target.value })}
        />
      </div>

      {/* Generate Button */}
      <button onClick={handleGenerate} disabled={loading}>
        {loading ? 'Generating...' : 'Generate Script'}
      </button>

      {/* Error Display */}
      {error && <div style={{ color: 'red' }}>Error: {error}</div>}

      {/* Progress Display */}
      {status && (
        <div>
          <h3>Status: {status.status}</h3>
          <ul>
            {Object.entries(status.stages).map(([stage, data]: [string, any]) => (
              <li key={stage}>
                {stage}: {data.status}
                {data.error && ` - ${data.error}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Result Display */}
      {finalStatus === 'completed' && generatedScript && (
        <div>
          <h3>✅ Generated Script</h3>
          <pre>{generatedScript}</pre>
        </div>
      )}

      {finalStatus === 'failed' && (
        <div style={{ color: 'red' }}>
          <h3>❌ Generation Failed</h3>
          <p>{status.stages?.execute?.error || status.stages?.revise?.error || 'Unknown error'}</p>
          {generatedScript && (
            <div>
              <h4>Last Attempted Script:</h4>
              <pre>{generatedScript}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## TypeScript Helper Function

```typescript
interface PipelineResult {
  success: boolean;
  script: string | null;
  error: string | null;
  fullStatus: any;
}

async function generatePolicyScript(
  policyText: string,
  credentials: AWSCredentials,
  onProgress?: (stage: string, status: string) => void
): Promise<PipelineResult> {
  // Start pipeline
  const startResponse = await fetch(
    'https://agent-api-695390404745.us-central1.run.app/pipeline/start',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        policy_text: policyText,
        ...credentials, // Spread credentials at root level
      }),
    }
  );

  if (!startResponse.ok) {
    const error = await startResponse.json();
    return {
      success: false,
      script: null,
      error: error.detail || 'Failed to start pipeline',
      fullStatus: null,
    };
  }

  const { run_id } = await startResponse.json();

  // Poll for completion
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const statusResponse = await fetch(
      `https://agent-api-695390404745.us-central1.run.app/pipeline/${run_id}/status`
    );
    const status = await statusResponse.json();

    // Report progress
    if (onProgress) {
      const currentStage = Object.entries(status.stages).find(
        ([_, stage]: [string, any]) => stage.status === 'running'
      );
      if (currentStage) {
        onProgress(currentStage[0], 'running');
      }
    }

    // Check if done
    if (status.status === 'completed') {
      return {
        success: true,
        script: status.stages.script.output.script,
        error: null,
        fullStatus: status,
      };
    }

    if (status.status === 'failed') {
      const failedStage = Object.entries(status.stages).find(
        ([_, stage]: [string, any]) => stage.status === 'failed'
      );
      
      return {
        success: false,
        script: status.stages.script?.output?.script || null,
        error: failedStage ? failedStage[1].error : 'Pipeline failed',
        fullStatus: status,
      };
    }
  }
}

// Usage
const result = await generatePolicyScript(
  'Delete messages containing spam',
  {
    aws_access_key_id: 'AKIA...',
    aws_secret_access_key: '...',
    aws_region: 'us-east-1',
  },
  (stage, status) => {
    console.log(`${stage}: ${status}`);
  }
);

if (result.success) {
  console.log('Generated script:', result.script);
} else {
  console.error('Error:', result.error);
  console.log('Last attempted script:', result.script);
}
```

---

## AWS Credentials - User Instructions

**Your users need AWS Bedrock access.** Here's what to tell them:

### Option 1: IAM User (Permanent Credentials)

1. Go to **AWS Console → IAM → Users**
2. Click **Create user** → Name it `bedrock-user`
3. Click **Attach policies directly** → Search for `AmazonBedrockFullAccess`
4. Create the user
5. Click on the user → **Security credentials** → **Create access key**
6. Choose **"Third-party service"** → Create
7. **Copy the Access Key ID and Secret Access Key**
8. Paste into your application

**Region:** Make sure you're using a region where Claude models are available (e.g., `us-east-1`, `us-west-2`)

### Option 2: Temporary Credentials (AWS SSO)

1. Run: `aws sso login --profile bedrock`
2. Get credentials from: `~/.aws/credentials` under `[bedrock]`
3. Copy: `aws_access_key_id`, `aws_secret_access_key`, and `aws_session_token`
4. Include all three in your request

**Note:** Temporary credentials expire after a few hours.

### Required AWS Bedrock Models

Users need access to Claude models in AWS Bedrock. The API currently uses:
- **Claude Sonnet 4.6** (`anthropic.claude-sonnet-4-6`)

To enable:
1. Go to **AWS Console → Bedrock → Model access**
2. Click **Modify model access**
3. Enable **Anthropic Claude models**
4. Submit request (usually instant approval)

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Continue |
| 400 | Bad request | Check request format |
| 401 | Invalid AWS credentials | User needs to update credentials |
| 429 | Rate limit exceeded | Wait 1 minute, retry |
| 500 | Internal server error | Retry after 30 seconds |
| 503 | Service starting (cold start) | Retry after 30 seconds |

### Common Errors

**Error:** `"Failed to start pipeline: ValidationException: The provided model identifier is invalid"`  
**Cause:** AWS region doesn't support the model  
**Solution:** Try `us-east-1` or `us-west-2`

**Error:** `"Failed to start pipeline: AccessDeniedException"`  
**Cause:** User doesn't have Bedrock access  
**Solution:** User needs to enable model access in AWS Bedrock console

**Error:** `"Script stage failed: Validation failed after 2 attempts"`  
**Cause:** LLM couldn't generate valid script  
**Solution:** Policy is too complex or ambiguous - ask user to simplify

**Error:** `"Pipeline execution timed out"`  
**Cause:** Pipeline took >15 minutes  
**Solution:** Policy is too complex - split into simpler policies

### Retry Logic

```typescript
async function generateWithRetry(
  policyText: string,
  credentials: AWSCredentials,
  maxRetries = 3
): Promise<PipelineResult> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await generatePolicyScript(policyText, credentials);
    } catch (error) {
      if (attempt === maxRetries) throw error;
      
      // Exponential backoff
      const delay = Math.pow(2, attempt) * 1000;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  throw new Error('Max retries exceeded');
}
```

---

## Response Times

| Operation | Typical Time |
|-----------|--------------|
| Cold start (first request) | ~30 seconds |
| Pipeline (simple policy) | 30-60 seconds |
| Pipeline (complex policy) | 60-120 seconds |
| Pipeline (with revisions) | 90-180 seconds |

**Timeout:** Set request timeout to at least 10 minutes (600 seconds)

```javascript
// Example with timeout
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 minutes

try {
  const response = await fetch(url, {
    signal: controller.signal,
    // ... other options
  });
} finally {
  clearTimeout(timeoutId);
}
```

---

## Testing the API

### Health Check

```bash
curl https://agent-api-695390404745.us-central1.run.app/health
```

**Expected:**
```json
{
  "status": "ok",
  "agent": "ok",
  "sandbox": "ok"
}
```

### Test Pipeline

```bash
curl -X POST https://agent-api-695390404745.us-central1.run.app/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "policy_text": "Delete messages containing spam",
    "credentials": {
      "aws_access_key_id": "YOUR_KEY",
      "aws_secret_access_key": "YOUR_SECRET",
      "aws_region": "us-east-1"
    }
  }'
```

---

## Security Notes

1. **Never store AWS credentials in your frontend code or version control**
2. **Users provide their own credentials** - your app just passes them through
3. **Credentials are sent over HTTPS** to the agent API
4. **Credentials are NOT logged or stored** by the API
5. **Users are billed on their own AWS account** (~$0.10-0.20 per pipeline run)

---

## Rate Limits

- **Default:** 10 requests per minute per IP
- **Burst:** Up to 20 requests in a short burst
- **Exceeded:** Returns HTTP 429, wait 1 minute before retrying

---

## Support & Troubleshooting

### Getting Help

1. Check the [QUICKSTART.md](QUICKSTART.md) for deployment details
2. View logs: `gcloud run services logs tail agent-api --region us-central1`
3. Check service status: https://console.cloud.google.com/run

### Debug Tips

**Pipeline stuck in "running":**
- Check user's AWS credentials are valid
- Verify user has Bedrock access enabled
- Check AWS region supports Claude models

**Scripts failing tests:**
- Policy is ambiguous - ask user to be more specific
- Policy requests unsupported features - clarify limitations

**Service unreachable:**
- Check health endpoint first
- Could be cold start (~30 sec wait)
- Check your network/firewall settings

---

## Migration from Old API

If you're migrating from the old `/execute` endpoint:

### Before (Old API)
```javascript
const response = await fetch('https://pk-sandbox-pipeline.../execute', {
  method: 'POST',
  body: JSON.stringify({
    policy_text: "...",
    aws_access_key_id: "...",
    aws_secret_access_key: "...",
  })
});
const { success, script, error } = await response.json();
```

### After (New API)
```javascript
// 1. Start pipeline
const startResponse = await fetch('.../pipeline/start', {
  method: 'POST',
  body: JSON.stringify({
    policy_text: "...",
    aws_access_key_id: "...",
    aws_secret_access_key: "...",
  })
});
const { run_id } = await startResponse.json();

// 2. Poll status
const pollInterval = setInterval(async () => {
  const statusResponse = await fetch(`.../pipeline/${run_id}/status`);
  const status = await statusResponse.json();
  
  if (status.status === 'completed') {
    clearInterval(pollInterval);
    const script = status.stages.script.output.script;
    const success = true;
    // Use script...
  }
}, 1000);
```

**Key differences:**
- Credentials now wrapped in `credentials` object
- Two-step process: start → poll
- More detailed progress information
- Real-time stage updates

---

## API Changelog

### v2.0 (2026-10-07)
- Split into Agent + Sandbox architecture
- New `/pipeline/start` and `/pipeline/{id}/status` endpoints
- Added WebSocket support for real-time updates
- Credentials moved to nested `credentials` object
- Deprecated old `/execute` endpoint

---

**Questions?** Check [DEPLOYED_URLS.md](DEPLOYED_URLS.md) for full API details and deployment information.
