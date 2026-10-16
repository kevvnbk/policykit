# Quick Start Guide

Complete guide for running pk-sandbox locally and deploying to Google Cloud.

## Table of Contents
1. [Local Development](#1-local-development)
2. [Deploy to Google Cloud](#2-deploy-to-google-cloud)
3. [Test Deployed APIs](#3-test-deployed-apis)

---

## 1. Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- AWS credentials configured (for testing LLM generation)

### Step 1: Install Dependencies

```bash
cd pk-sandbox

# Install sandbox package
cd sandbox
pip install -e .

# Install agent dependencies
cd ../agent
pip install -r requirements.txt

# Install frontend dependencies
cd ../sandbox/frontend
npm install
```

### Step 2: Start All Services

Open **3 terminal windows**:

#### Terminal 1: Sandbox Server (Port 8001)
```bash
cd pk-sandbox/sandbox/sandboxengine
python main.py
```

**Expected output:**
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8001
```

#### Terminal 2: Agent Server (Port 8002)
```bash
cd pk-sandbox/agent
python main.py
```

**Expected output:**
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8002
```

#### Terminal 3: Frontend (Port 5173)
```bash
cd pk-sandbox/sandbox/frontend
npm run dev
```

**Expected output:**
```
  ➜  Local:   http://localhost:5173/
```

### Step 3: Test the Pipeline

1. Open browser to **http://localhost:5173**
2. You should see the sandbox frontend
3. Paste a policy (e.g., "Delete messages containing spam")
4. Click "Run Pipeline"
5. The frontend will:
   - Fetch AWS credentials from your local environment (via sandbox `/credentials/aws`)
   - Send policy + credentials to agent (`POST /pipeline/start`)
   - Agent generates code and sends to sandbox for execution
   - Results are displayed in the UI

### Troubleshooting Local Setup

**"Module 'policyengine' not found"**
```bash
cd pk-sandbox/sandbox
pip install -e .
```

**"Connection refused to port 8001"**
- Make sure sandbox server is running
- Check: `curl http://localhost:8001/health`

**"Connection refused to port 8002"**
- Make sure agent server is running
- Check: `curl http://localhost:8002/health`

**"AWS credentials not found"**
- Configure AWS CLI: `aws configure`
- OR set environment variables:
  ```bash
  export AWS_ACCESS_KEY_ID=your-key
  export AWS_SECRET_ACCESS_KEY=your-secret
  export AWS_REGION=us-east-1
  ```

---

## 2. Deploy to Google Cloud

You have **two deployment options**:

### Option A: Deploy Sandbox Only (Recommended for Testing)
Agent runs locally, sandbox runs on Cloud Run. Good for development.

### Option B: Deploy Both Services (Production)
Both agent and sandbox run on Cloud Run. Better for sharing with others.

---

### Option A: Deploy Sandbox Only

#### Step 1: Setup Google Cloud

```bash
# Install gcloud CLI if needed
# https://cloud.google.com/sdk/docs/install

# Login
gcloud auth login

# Create project (or use existing)
gcloud projects create pk-sandbox-YOUR-ID --name="PK Sandbox"

# Set as default
gcloud config set project pk-sandbox-YOUR-ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
```

#### Step 2: Deploy Sandbox

```bash
cd pk-sandbox/sandbox

# Deploy (takes 2-3 minutes)
gcloud run deploy sandbox-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900 \
  --max-instances 10 \
  --min-instances 0 \
  --port 8001 \
  --set-env-vars="ENVIRONMENT=production"

# Get URL
gcloud run services describe sandbox-api \
  --region us-central1 \
  --format 'value(status.url)'
```

**Save the URL** - you'll need it for testing!

#### Step 3: Update Agent to Use Deployed Sandbox

Edit `pk-sandbox/agent/sandbox_client.py`:
```python
# Change this line:
SANDBOX_URL = "http://localhost:8001"

# To your deployed URL:
SANDBOX_URL = "https://sandbox-api-xxx-uc.a.run.app"
```

Now run agent locally, it will call the deployed sandbox.

---

### Option B: Deploy Both Services

#### Step 1: Deploy Sandbox (same as Option A)

Follow Option A steps 1-2 above.

#### Step 2: Create Agent Dockerfile

Create `pk-sandbox/agent/Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY . .

# Note: Agent imports from sandbox package, but doesn't need it at runtime
# (only uses it for type hints)

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
```

#### Step 3: Deploy Agent

```bash
cd pk-sandbox/agent

# Deploy
gcloud run deploy agent-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 900 \
  --max-instances 5 \
  --min-instances 0 \
  --port 8002 \
  --set-env-vars="ENVIRONMENT=production,SANDBOX_URL=https://YOUR-SANDBOX-URL"

# Get URL
gcloud run services describe agent-api \
  --region us-central1 \
  --format 'value(status.url)'
```

**Important:** Replace `YOUR-SANDBOX-URL` with your actual sandbox URL from step 1.

#### Step 4: Update Frontend

Edit `pk-sandbox/sandbox/frontend/src/App.jsx`:
```javascript
// Change agent URL:
const AGENT_URL = 'http://localhost:8002'; // OLD

// To:
const AGENT_URL = 'https://agent-api-xxx-uc.a.run.app'; // NEW
```

#### Step 5: Deploy Frontend (Optional)

**Deploy to Vercel (Free):**
```bash
cd pk-sandbox/sandbox/frontend

# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Follow prompts, it will give you a URL
```

**Or deploy to Netlify/other host**

---

## 3. Test Deployed APIs

### Test Sandbox API

#### Health Check
```bash
curl https://YOUR-SANDBOX-URL/health
```

**Expected:**
```json
{"status":"ok"}
```

#### Execute Script
```bash
curl -X POST https://YOUR-SANDBOX-URL/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{
    "script": "def setup(ctx): pass",
    "scenarios": [...]
  }'
```

#### Get API Reference
```bash
curl https://YOUR-SANDBOX-URL/sandbox/api-reference
```

### Test Agent API (if deployed)

#### Health Check
```bash
curl https://YOUR-AGENT-URL/health
```

#### Start Pipeline
```bash
curl -X POST https://YOUR-AGENT-URL/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "policy_text": "Delete messages containing spam",
    "credentials": {
      "aws_access_key_id": "YOUR-KEY",
      "aws_secret_access_key": "YOUR-SECRET",
      "aws_region": "us-east-1"
    }
  }'
```

**Expected:**
```json
{
  "run_id": "abc12345",
  "status": "running"
}
```

#### Poll Status
```bash
curl https://YOUR-AGENT-URL/pipeline/abc12345/status
```

### Test Frontend → Agent → Sandbox Flow

1. **Open frontend** (http://localhost:5173 or your deployed URL)
2. **Paste a policy:**
   ```
   When someone posts a message containing "spam", delete it immediately.
   ```
3. **Click "Run Pipeline"**
4. **Watch the stages progress:**
   - Headers → Script → Tests → Execute → Report
5. **Check results:**
   - Green = All tests passed
   - Red = Tests failed (check error details)

### Monitor Deployed Services

**View Logs:**
```bash
# Sandbox logs
gcloud run services logs tail sandbox-api --region us-central1

# Agent logs (if deployed)
gcloud run services logs tail agent-api --region us-central1
```

**View Metrics:**
1. Go to https://console.cloud.google.com/run
2. Click on service name
3. Click "METRICS" tab
4. See: requests/sec, latency, CPU, memory

**View in Browser:**
```bash
# Open sandbox in browser
gcloud run services describe sandbox-api \
  --region us-central1 \
  --format 'value(status.url)' | xargs open

# Or just visit the URL and add /health
```

---

## Cost Estimation

**Google Cloud Run Free Tier (per month):**
- 2M requests
- 360,000 GB-seconds
- 180,000 vCPU-seconds

**Typical Research Usage:**
- 100-500 pipeline runs/month
- **Cost: $0** (stays in free tier)

**AWS Bedrock (User pays):**
- ~$0.10-0.20 per pipeline run
- Users provide their own credentials

---

## Updating Deployments

### Update Sandbox Code
```bash
cd pk-sandbox/sandbox
git pull  # or make your changes
gcloud run deploy sandbox-api --source . --region us-central1
```

### Update Agent Code
```bash
cd pk-sandbox/agent
git pull  # or make your changes
gcloud run deploy agent-api --source . --region us-central1
```

### Update Environment Variables
```bash
# Update sandbox
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://your-frontend.vercel.app"

# Update agent
gcloud run services update agent-api \
  --region us-central1 \
  --set-env-vars="SANDBOX_URL=https://new-sandbox-url"
```

---

## Troubleshooting Deployments

### "Permission denied"
```bash
gcloud auth login
gcloud config set project YOUR-PROJECT-ID
```

### "API not enabled"
```bash
gcloud services enable cloudbuild.googleapis.com run.googleapis.com
```

### "CORS error" in frontend
Update ALLOWED_ORIGINS:
```bash
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://your-frontend-url.com,http://localhost:5173"
```

### Deployment times out
```bash
# Check build logs
gcloud builds list --limit 1

# View specific build
gcloud builds log BUILD-ID
```

### Service not responding
```bash
# Check if service is running
gcloud run services describe sandbox-api --region us-central1

# View recent logs
gcloud run services logs read sandbox-api --region us-central1 --limit 50
```

---

## Architecture Summary

```
┌─────────────┐
│  Frontend   │ (Port 5173 / Vercel)
│  React App  │
└──────┬──────┘
       │
       │ 1. Fetch AWS credentials
       ├────────────────────────────┐
       │                            │
       ▼                            ▼
┌─────────────┐            ┌─────────────┐
│   Sandbox   │            │    Agent    │
│  Port 8001  │◄───────────│  Port 8002  │
│             │  2. Execute│             │
│ - Validate  │    script  │ - Generate  │
│ - Execute   │            │   code (LLM)│
│ - Return    │            │ - Orchestrate│
│   results   │            │   pipeline  │
└─────────────┘            └─────────────┘
```

**Data Flow:**
1. Frontend fetches AWS creds from sandbox `/credentials/aws`
2. Frontend sends policy + creds to agent `/pipeline/start`
3. Agent generates code using AWS Bedrock
4. Agent sends script to sandbox `/sandbox/execute`
5. Sandbox runs script and returns results
6. Agent aggregates results and sends to frontend

---

## Next Steps

1. ✅ Run locally to verify everything works
2. ✅ Deploy sandbox to Cloud Run
3. ✅ Test with deployed sandbox URL
4. ✅ (Optional) Deploy agent + frontend
5. ✅ Share URLs with collaborators

---

## Support Resources

- **Sandbox README:** [sandbox/README.md](sandbox/README.md)
- **Agent README:** [agent/README.md](agent/README.md)
- **Deployment Guide:** [sandbox/DEPLOYMENT.md](sandbox/DEPLOYMENT.md)
- **Google Cloud Console:** https://console.cloud.google.com/run

---

**Total Setup Time:** 15-20 minutes  
**Cost:** $0 (free tier)  
**Maintenance:** Minimal (auto-scales, deploy updates in ~2 minutes)
