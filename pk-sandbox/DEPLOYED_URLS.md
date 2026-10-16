# Deployed Services

## Google Cloud Run Deployment

**Project:** pk-sandbox-pipeline  
**Region:** us-central1  
**Deployed:** 2026-10-07

---

## Service URLs

### Sandbox API
**URL:** https://sandbox-api-695390404745.us-central1.run.app  
**Port:** 8001 (internal)  
**Health:** https://sandbox-api-695390404745.us-central1.run.app/health

**Endpoints:**
- `POST /sandbox/execute` - Execute scripts with scenarios
- `POST /sandbox/validate` - Validate script structure  
- `GET /sandbox/api-reference` - Get API documentation
- `GET /credentials/aws` - Get AWS credentials (local only)
- `GET /health` - Health check

### Agent API  
**URL:** https://agent-api-695390404745.us-central1.run.app  
**Port:** 8002 (internal)  
**Health:** https://agent-api-695390404745.us-central1.run.app/health

**Endpoints:**
- `POST /pipeline/start` - Start a new generation pipeline
- `GET /pipeline/{id}/status` - Poll for pipeline status
- `WS /pipeline/{id}/ws` - Real-time updates via WebSocket
- `GET /health` - Health check

---

## Configuration

### Model
- **Current:** Claude Sonnet 4.6 (`anthropic.claude-sonnet-4-6`)
- To change: Edit `agent/llm_client.py` line 26 and redeploy

### Environment Variables

**Sandbox:**
- `ENVIRONMENT=production`

**Agent:**
- `ENVIRONMENT=production`
- `SANDBOX_URL=https://sandbox-api-695390404745.us-central1.run.app`

---

## Testing Deployed Services

### Quick Health Check
```bash
# Sandbox
curl https://sandbox-api-695390404745.us-central1.run.app/health

# Agent
curl https://agent-api-695390404745.us-central1.run.app/health
```

### Test Full Pipeline
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

## Updating Deployments

### Redeploy Sandbox
```bash
cd pk-sandbox/sandbox
gcloud run deploy sandbox-api --source . --region us-central1
```

### Redeploy Agent
```bash
cd pk-sandbox/agent
gcloud run deploy agent-api --source . --region us-central1
```

### Or Use Deployment Script
```bash
cd pk-sandbox
export GCP_PROJECT_ID=pk-sandbox-pipeline
./deploy.sh both  # Deploy both services
```

---

## Frontend Integration

Update your frontend to use these URLs:

```javascript
// In frontend config
const AGENT_URL = 'https://agent-api-695390404745.us-central1.run.app';
const SANDBOX_URL = 'https://sandbox-api-695390404745.us-central1.run.app';
```

For the sandbox frontend at `pk-sandbox/sandbox/frontend/src/App.jsx`:
- Line ~48: Change agent URL
- Line ~109: Change credentials endpoint (or remove - won't work in production)

---

## Costs

With Google Cloud Run free tier:
- **2M requests/month free**
- **360,000 GB-seconds compute**
- **180,000 vCPU-seconds**

Typical research usage: **$0/month** (stays within free tier)

AWS Bedrock costs (user pays via their credentials):
- ~$0.10-0.20 per pipeline run

---

## Monitoring

### View Logs
```bash
# Sandbox logs
gcloud run services logs tail sandbox-api --region us-central1

# Agent logs
gcloud run services logs tail agent-api --region us-central1
```

### View in Console
- Sandbox: https://console.cloud.google.com/run/detail/us-central1/sandbox-api
- Agent: https://console.cloud.google.com/run/detail/us-central1/agent-api

---

## Troubleshooting

### "CORS error" in frontend
Update CORS origins:
```bash
gcloud run services update sandbox-api \
  --region us-central1 \
  --set-env-vars="ALLOWED_ORIGINS=https://your-frontend-url.com,http://localhost:5174"
```

### Update agent's sandbox URL
```bash
gcloud run services update agent-api \
  --region us-central1 \
  --set-env-vars="SANDBOX_URL=https://sandbox-api-695390404745.us-central1.run.app"
```

### View deployment status
```bash
gcloud run services describe sandbox-api --region us-central1
gcloud run services describe agent-api --region us-central1
```

---

**Deployment Complete!** ✅

Both services are live and ready to use.
