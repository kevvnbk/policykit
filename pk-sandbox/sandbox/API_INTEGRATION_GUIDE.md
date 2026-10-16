# Sandbox Pipeline API - Frontend Integration Guide

Simple guide for integrating the PolicyKit script generation API into your frontend.

---

## API Endpoint

**Production URL:**
```
https://pk-sandbox-pipeline-695390404745.us-central1.run.app
```

**Single Endpoint:**
```
POST /execute
```

That's it. One endpoint does everything.

---

## How It Works

1. User provides their AWS Bedrock credentials + policy description
2. API generates a governance script
3. Returns the script (or error if failed)

**Pipeline takes ~30-60 seconds** to complete.

---

## Request Format

```typescript
interface ExecuteRequest {
  policy_text: string;              // Natural language policy description
  
  // AWS IAM credentials (required)
  aws_access_key_id: string;        // AWS access key (required)
  aws_secret_access_key: string;    // AWS secret key (required)
  aws_session_token?: string;       // Optional: for temporary credentials (AWS SSO, STS)
  
  aws_region?: string;              // Optional: defaults to "us-east-1"
}
```

**Example with permanent IAM credentials:**
```json
{
  "policy_text": "Delete any message that contains the word 'spam'",
  "aws_access_key_id": "AKIA...",
  "aws_secret_access_key": "...",
  "aws_region": "us-east-1"
}
```

**Example with temporary credentials (AWS SSO or STS):**
```json
{
  "policy_text": "Delete any message that contains the word 'spam'",
  "aws_access_key_id": "ASIA...",
  "aws_secret_access_key": "...",
  "aws_session_token": "IQoJb3JpZ2luX2...",
  "aws_region": "us-east-1"
}
```

---

## Response Format

```typescript
interface ExecuteResponse {
  success: boolean;       // true if pipeline succeeded
  script: string | null;  // Generated Python script (or latest version if failed)
  error: string | null;   // Error message if failed
}
```

**Success Response:**
```json
{
  "success": true,
  "script": "def setup(ctx):\n    ctx.on('message_posted', handle_message)\n\ndef handle_message(event, ctx):\n    ...",
  "error": null
}
```

**Failure Response:**
```json
{
  "success": false,
  "script": "def setup(ctx):\n    # Last attempted script before failure",
  "error": "Revise stage failed: Failed after 3 revision attempts"
}
```

**Note:** `script` is returned even on failure (contains the last generated version). Only `null` if generation completely failed.

---

## JavaScript/TypeScript Example

### Simple Fetch (IAM Credentials)

```typescript
async function generateScript(
  policyText: string,
  awsCredentials: {
    accessKeyId: string;
    secretAccessKey: string;
    sessionToken?: string;
    region?: string;
  }
): Promise<{ success: boolean; script: string | null; error: string | null }> {
  const response = await fetch(
    'https://pk-sandbox-pipeline-695390404745.us-central1.run.app/execute',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        policy_text: policyText,
        aws_access_key_id: awsCredentials.accessKeyId,
        aws_secret_access_key: awsCredentials.secretAccessKey,
        aws_session_token: awsCredentials.sessionToken,
        aws_region: awsCredentials.region || 'us-east-1',
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`API request failed: ${response.statusText}`);
  }

  return response.json();
}

// Usage
const result = await generateScript(
  'Delete messages containing spam',
  {
    accessKeyId: 'AKIA...',
    secretAccessKey: '...',
  }
);

if (result.success) {
  console.log('Generated script:', result.script);
} else {
  console.error('Generation failed:', result.error);
  console.log('Last attempted script:', result.script);
}
```

### Simple Fetch (Bearer Token)

```typescript
async function generateScriptWithBearer(
  policyText: string,
  bearerToken: string,
  region: string = 'us-east-1'
): Promise<{ success: boolean; script: string | null; error: string | null }> {
  const response = await fetch(
    'https://pk-sandbox-pipeline-695390404745.us-central1.run.app/execute',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        policy_text: policyText,
        aws_bearer_token: bearerToken,
        aws_region: region,
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`API request failed: ${response.statusText}`);
  }

  return response.json();
}

// Usage
const result = await generateScriptWithBearer(
  'Delete messages containing spam',
  'your-bearer-token-here',
  'us-east-2'
);

if (result.success) {
  console.log('Generated script:', result.script);
} else {
  console.error('Generation failed:', result.error);
}
```

---

## React Component Example

```typescript
import { useState } from 'react';

interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
  region?: string;
}

export function PolicyGenerator() {
  const [policyText, setPolicyText] = useState('');
  const [credentials, setCredentials] = useState<AWSCredentials>({
    accessKeyId: '',
    secretAccessKey: '',
    region: 'us-east-1',
  });
  const [result, setResult] = useState<{
    success: boolean;
    script: string | null;
    error: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(
        'https://pk-sandbox-pipeline-695390404745.us-central1.run.app/execute',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            policy_text: policyText,
            aws_access_key_id: credentials.accessKeyId,
            aws_secret_access_key: credentials.secretAccessKey,
            aws_session_token: credentials.sessionToken,
            aws_region: credentials.region,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({
        success: false,
        script: null,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Policy Text Input */}
      <div>
        <label className="block text-sm font-medium mb-1">
          Policy Description
        </label>
        <textarea
          value={policyText}
          onChange={(e) => setPolicyText(e.target.value)}
          placeholder="Describe your governance policy in plain English..."
          className="w-full h-32 p-2 border rounded"
          disabled={loading}
        />
      </div>

      {/* AWS Credentials */}
      <div className="space-y-2">
        <h3 className="text-sm font-medium">AWS Credentials</h3>
        <input
          type="text"
          placeholder="AWS Access Key ID"
          value={credentials.accessKeyId}
          onChange={(e) =>
            setCredentials({ ...credentials, accessKeyId: e.target.value })
          }
          className="w-full p-2 border rounded"
          disabled={loading}
        />
        <input
          type="password"
          placeholder="AWS Secret Access Key"
          value={credentials.secretAccessKey}
          onChange={(e) =>
            setCredentials({ ...credentials, secretAccessKey: e.target.value })
          }
          className="w-full p-2 border rounded"
          disabled={loading}
        />
        <select
          value={credentials.region}
          onChange={(e) =>
            setCredentials({ ...credentials, region: e.target.value })
          }
          className="w-full p-2 border rounded"
          disabled={loading}
        >
          <option value="us-east-1">US East (N. Virginia)</option>
          <option value="us-west-2">US West (Oregon)</option>
          <option value="eu-west-1">Europe (Ireland)</option>
        </select>
      </div>

      {/* Generate Button */}
      <button
        onClick={handleGenerate}
        disabled={loading || !policyText || !credentials.accessKeyId}
        className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
      >
        {loading ? 'Generating... (30-60s)' : 'Generate Script'}
      </button>

      {/* Results */}
      {result && (
        <div className="mt-4">
          {result.success ? (
            <div className="border border-green-500 rounded p-4">
              <h3 className="font-bold text-green-600 mb-2">
                ✓ Script Generated Successfully
              </h3>
              <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-sm">
                <code>{result.script}</code>
              </pre>
            </div>
          ) : (
            <div className="border border-red-500 rounded p-4">
              <h3 className="font-bold text-red-600 mb-2">
                ✗ Generation Failed
              </h3>
              <p className="text-red-500 mb-2">{result.error}</p>
              {result.script && (
                <div>
                  <p className="text-sm text-gray-600 mb-1">
                    Last attempted script:
                  </p>
                  <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-sm">
                    <code>{result.script}</code>
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `"Invalid AWS credentials"` | Credentials don't work | User needs to check their AWS keys |
| `"Pipeline execution timed out"` | Pipeline took >10 minutes | Policy too complex, try simplifying |
| `"Script stage failed"` | LLM couldn't generate valid script | Policy ambiguous, ask user to clarify |
| HTTP 503 | Service starting up (cold start) | Retry after 30 seconds |
| HTTP 429 | Rate limit exceeded | Wait 1 minute, then retry |

### Retry Logic

```typescript
async function generateWithRetry(
  policyText: string,
  credentials: AWSCredentials,
  maxRetries = 3
): Promise<ExecuteResponse> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(API_URL + '/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          policy_text: policyText,
          aws_access_key_id: credentials.accessKeyId,
          aws_secret_access_key: credentials.secretAccessKey,
          aws_region: credentials.region,
        }),
      });

      // Retry on 503 (service starting up)
      if (response.status === 503 && i < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, 30000)); // Wait 30s
        continue;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response.json();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await new Promise((resolve) => setTimeout(resolve, 5000)); // Wait 5s
    }
  }
  throw new Error('Max retries exceeded');
}
```

---

## AWS Credentials - User Instructions

Users need AWS Bedrock access. Here's what to tell them:

### How to Get AWS Credentials

**Option 1: Create IAM User (Permanent Credentials)**

1. Go to AWS Console → IAM → Users
2. Create new user: `bedrock-user`
3. Attach policy: `AmazonBedrockFullAccess`
4. Create access key → Copy Access Key ID and Secret Access Key
5. Paste into your app

**Option 2: Use AWS SSO (Temporary Credentials)**

1. Run: `aws sso login --profile bedrock`
2. Get credentials from: `~/.aws/credentials` under `[bedrock]`
3. Includes: access key, secret key, and session token
4. Valid for 1-12 hours (depending on config)

**Note:** If using temporary credentials, include `aws_session_token` in the request.

---

## Cost Information (for Users)

**Backend (Your Cost):** $0/month (stays within Google Cloud free tier)

**User's AWS Cost:**
- ~$0.10-0.20 per script generation (Bedrock Claude API usage)
- Claude Sonnet 4.5: $3 per 1M input tokens, $15 per 1M output tokens
- Typical policy uses ~5,000 tokens = $0.10-0.15

---

## Testing the API

**Health Check:**
```bash
curl https://pk-sandbox-pipeline-695390404745.us-central1.run.app/health
```

**Expected:** `{"status":"ok"}`

**Test Script Generation:**
```bash
curl -X POST https://pk-sandbox-pipeline-695390404745.us-central1.run.app/execute \
  -H "Content-Type: application/json" \
  -d '{
    "policy_text": "Delete messages containing spam",
    "aws_access_key_id": "YOUR_KEY",
    "aws_secret_access_key": "YOUR_SECRET",
    "aws_region": "us-east-1"
  }'
```

---

## CORS Configuration

The API allows requests from:
- `http://localhost:3000`
- `http://localhost:5173`
- `http://localhost:5174`

**If your frontend is on a different domain**, let me know and I'll add it to the allowed origins.

---

## Rate Limits

- **5 requests per minute** per IP address
- Exceeding this returns HTTP 429
- Sufficient for user testing, adjust if needed

---

## Timeouts

- **Request timeout:** 10 minutes (600 seconds)
- **Cold start:** ~30 seconds (first request after idle)
- **Typical generation time:** 30-60 seconds

Set your frontend timeout to at least 10 minutes:
```typescript
fetch(url, { 
  timeout: 600000 // 10 minutes
})
```

---

## Support & Questions

**API Issues:**
- Check health endpoint: `/health`
- View logs: `gcloud run services logs read pk-sandbox-pipeline --region us-central1`

**Common Questions:**

**Q: Why does the first request take 30+ seconds?**
A: Cold start - the service scales to zero when idle. After the first request, subsequent requests are fast.

**Q: Can I increase the timeout?**
A: Yes, but 10 minutes should be enough. Complex policies may need simplification.

**Q: How do I update CORS origins?**
A: Send me the domain, I'll add it to the allowed list.

**Q: Can users provide just AWS profile name instead of credentials?**
A: No - credentials must be explicit in the request for security. Users should never send their profile/config files.

---

## Complete Example: Full Integration

```typescript
// api/sandbox.ts
const API_BASE = 'https://pk-sandbox-pipeline-695390404745.us-central1.run.app';

export interface GenerateScriptRequest {
  policyText: string;
  awsCredentials: {
    accessKeyId: string;
    secretAccessKey: string;
    sessionToken?: string;
    region?: string;
  };
}

export interface GenerateScriptResponse {
  success: boolean;
  script: string | null;
  error: string | null;
}

export async function generateScript(
  request: GenerateScriptRequest
): Promise<GenerateScriptResponse> {
  const response = await fetch(`${API_BASE}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      policy_text: request.policyText,
      aws_access_key_id: request.awsCredentials.accessKeyId,
      aws_secret_access_key: request.awsCredentials.secretAccessKey,
      aws_session_token: request.awsCredentials.sessionToken,
      aws_region: request.awsCredentials.region || 'us-east-1',
    }),
  });

  if (!response.ok) {
    if (response.status === 503) {
      throw new Error('Service is starting up. Please try again in 30 seconds.');
    }
    if (response.status === 429) {
      throw new Error('Rate limit exceeded. Please wait 1 minute.');
    }
    throw new Error(`Request failed: ${response.statusText}`);
  }

  return response.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
```

---

That's everything you need! The API is simple:
1. User enters policy + AWS credentials
2. POST to `/execute`
3. Get script back (or error)

Questions? Let me know!
