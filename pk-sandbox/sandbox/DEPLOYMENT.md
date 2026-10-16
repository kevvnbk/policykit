# Sandbox Pipeline API - Deployment Guide

Complete guide for deploying the Sandbox Pipeline API to Google Cloud Run (free tier).

## Prerequisites

Before you begin, you need:

1. **Google Cloud Account** (free tier available)
   - Go to https://cloud.google.com/
   - Sign up (requires credit card for verification, but won't charge for free tier usage)

2. **Google Cloud CLI** installed
   - Download: https://cloud.google.com/sdk/docs/install
   - Verify installation: `gcloud --version`

3. **AWS Bedrock Access** (for users, not for deployment)
   - Users will provide their own AWS credentials
   - Server doesn't need AWS credentials

---

## Quick Start (5 minutes)

### Step 1: Install Google Cloud CLI

**Windows:**
```bash
# Download installer from:
https://cloud.google.com/sdk/docs/install#windows

# Or use PowerShell:
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe
```

**Mac:**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

**Linux:**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### Step 2: Authenticate and Setup

```bash
# 1. Login to Google Cloud
gcloud auth login

# 2. Create a new project (or use existing)
gcloud projects create sandbox-pipeline-PROJECT_ID --name="Sandbox Pipeline"

# 3. Set the project as default
gcloud config set project sandbox-pipeline-PROJECT_ID

# 4. Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

**Note:** Replace `PROJECT_ID` with a unique identifier (e.g., your name + random number).

### Step 3: Deploy

```bash
# Navigate to sandbox directory
cd sandbox

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

# Get your API URL
gcloud run services describe sandbox-api \
  --region us-central1 \
  --format 'value(status.url)'
```

**Output will be something like:**
```
https://sandbox-api-HASH-uc.a.run.app
```

### Step 4: Test the Deployment

```bash
# Test health endpoint
curl https://YOUR_URL/health

# Run test client
cd client
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
python test_client.py --url https://YOUR_URL --test basic
```

---

## Using the Deployment Script (Alternative)

We provide a deployment script that automates the process:

```bash
# Set your project ID
export GCP_PROJECT_ID="your-project-id"

# Make script executable (Mac/Linux)
chmod +x deploy/deploy.sh

# Run deployment
cd sandbox
./deploy/deploy.sh
```

**On Windows:**
```bash
# Use Git Bash or WSL
bash deploy/deploy.sh
```

---

## Configuration Options

### Environment Variables

Set environment variables during deployment:

```bash
gcloud run deploy sandbox-api \
  --source . \
  --region us-central1 \
  --set-env-vars="ENVIRONMENT=production,ALLOWED_ORIGINS=https://yourfrontend.com,RATE_LIMIT=10/minute"
```

**Available Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | development | `production` or `development` |
| `ALLOWED_ORIGINS` | localhost:* | Comma-separated list of allowed CORS origins |
| `RATE_LIMIT` | 5/minute | Rate limit (e.g., `10/minute`, `100/hour`) |
| `PORT` | 8001 | Port (Cloud Run sets this automatically) |

### Update Existing Deployment

To update environment variables without redeploying:

```bash
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://yourfrontend.com,https://staging.yourfrontend.com"
```

To redeploy with code changes:

```bash
# Just run the deploy command again
gcloud run deploy sandbox-api --source . --region us-central1
```

---

## Cost Estimate

**Google Cloud Run Free Tier (per month):**
- 2 million requests
- 360,000 GB-seconds compute
- 180,000 vCPU-seconds
- 1 GB network egress

**For research use (low traffic):**
- Typical usage: ~100-500 requests/month
- Cost: **$0** (stays within free tier)

**If you exceed free tier:**
- CPU: $0.00002400/vCPU-second
- Memory: $0.00000250/GiB-second
- Estimated: $10-30/month for moderate usage

**User AWS Costs (they pay, not you):**
- ~$0.10-0.20 per pipeline run (Bedrock Claude usage)

---

## Monitoring & Logs

### View Logs

**In Web Console:**
1. Go to https://console.cloud.google.com/run
2. Click on `sandbox-api`
3. Click "LOGS" tab

**Via CLI:**
```bash
# Stream logs in real-time
gcloud run services logs tail sandbox-api --region us-central1

# View recent logs
gcloud run services logs read sandbox-api --region us-central1 --limit 50
```

### Monitor Performance

**In Web Console:**
1. Go to https://console.cloud.google.com/run
2. Click on `sandbox-api`
3. Click "METRICS" tab

Shows: Request count, latency, CPU/memory usage

---

## Updating CORS Origins

Your frontend needs to be in the allowed origins list.

**Method 1: Update via CLI**
```bash
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://yourfrontend.vercel.app,http://localhost:5173"
```

**Method 2: Update via Web Console**
1. Go to https://console.cloud.google.com/run
2. Click on `sandbox-api`
3. Click "EDIT & DEPLOY NEW REVISION"
4. Scroll to "Environment variables"
5. Add/edit `ALLOWED_ORIGINS`
6. Click "DEPLOY"

---

## Troubleshooting

### Issue: "Permission denied" when deploying

**Solution:**
```bash
# Re-authenticate
gcloud auth login

# Ensure project is set
gcloud config set project YOUR_PROJECT_ID
```

### Issue: "API not enabled"

**Solution:**
```bash
# Enable required APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com
```

### Issue: Deployment times out

**Solution:**
```bash
# Increase timeout
gcloud run deploy sandbox-api \
  --source . \
  --region us-central1 \
  --timeout 900
```

### Issue: "CORS policy" error from frontend

**Solution:**
Add your frontend URL to `ALLOWED_ORIGINS`:
```bash
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://your-frontend-url.com"
```

### Issue: Tests failing with "Invalid AWS credentials"

This is expected! Users must provide valid AWS credentials. The test client needs:
```bash
export AWS_ACCESS_KEY_ID="your-actual-key"
export AWS_SECRET_ACCESS_KEY="your-actual-secret"
```

---

## Testing the API

### 1. Health Check

```bash
curl https://YOUR_URL/health
```

**Expected Response:**
```json
{"status":"ok"}
```

### 2. Test with curl (IAM credentials)

```bash
curl -X POST https://YOUR_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "policy_text": "Delete messages containing spam",
    "aws_access_key_id": "YOUR_KEY",
    "aws_secret_access_key": "YOUR_SECRET",
    "aws_region": "us-east-1"
  }'
```

### 2b. Test with curl (Bearer token)

```bash
curl -X POST https://YOUR_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "policy_text": "Delete messages containing spam",
    "aws_bearer_token": "YOUR_BEARER_TOKEN",
    "aws_region": "us-east-2"
  }'
```

### 3. Test with Python Client

```bash
cd client
pip install -r requirements.txt

export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"

python test_client.py --url https://YOUR_URL --test basic
```

---

## Sharing with Your Researcher

Once deployed, share these details with your frontend researcher:

**API Endpoint:**
```
https://YOUR_CLOUD_RUN_URL/execute
```

**Request Format (Option 1: IAM credentials):**
```javascript
fetch('https://YOUR_URL/execute', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    policy_text: "Delete spam messages",
    aws_access_key_id: "user-provided",
    aws_secret_access_key: "user-provided",
    aws_region: "us-east-1"
  })
})
```

**Request Format (Option 2: Bearer token):**
```javascript
fetch('https://YOUR_URL/execute', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    policy_text: "Delete spam messages",
    aws_bearer_token: "user-provided-bearer-token",
    aws_region: "us-east-2"
  })
})
```

**Response Format:**
```json
{
  "success": true,
  "script": "def setup(ctx):\n    ...",
  "error": null
}
```

**Note:** The API supports both AWS IAM credentials and bearer tokens. Users should provide one or the other (not both).

---

## Local Development

For local testing before deploying:

```bash
# Install dependencies
cd sandboxengine
pip install -r requirements.txt

# Run locally
uvicorn sandboxengine.urls:app --reload --port 8001

# Test
cd ../client
python test_client.py --url http://localhost:8001 --test basic
```

---

## Deleting the Deployment

To remove the service and stop all charges:

```bash
# Delete the service
gcloud run services delete sandbox-api --region us-central1

# (Optional) Delete the entire project
gcloud projects delete YOUR_PROJECT_ID
```

---

## Next Steps

1. **Get your API URL** after deployment
2. **Test with test client** to verify it works
3. **Share API URL with frontend researcher**
4. **Update CORS origins** to allow your frontend domain
5. **Monitor usage** in Google Cloud Console

---

## Support

If you encounter issues:

1. Check logs: `gcloud run services logs tail sandbox-api --region us-central1`
2. Verify APIs are enabled: `gcloud services list --enabled`
3. Check deployment status: `gcloud run services describe sandbox-api --region us-central1`

---

## Summary

**Total Setup Time:** ~10 minutes  
**Total Cost:** $0 (free tier)  
**Maintenance:** Zero (auto-scales, auto-deploys on code push)

This is perfect for research collaboration - deploy once, use forever, pay nothing.
