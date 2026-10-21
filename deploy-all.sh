#!/bin/bash
set -e

# Master deployment script for all PolicyKit services
# Deploys PolicyKit (Django), Sandbox (FastAPI), and Agent (FastAPI) to Google Cloud Run

PROJECT_ID=${GCP_PROJECT_ID:-""}
REGION=${GCP_REGION:-"us-central1"}

echo "========================================================="
echo "PolicyKit + Sandbox + Agent Deployment"
echo "========================================================="
echo ""

# Check if project ID is set
if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID not set"
    echo "Usage: GCP_PROJECT_ID=your-project-id ./deploy-all.sh [policykit|sandbox|agent|all]"
    echo ""
    echo "Examples:"
    echo "  GCP_PROJECT_ID=my-project ./deploy-all.sh all      # Deploy all services"
    echo "  GCP_PROJECT_ID=my-project ./deploy-all.sh sandbox  # Deploy sandbox only"
    exit 1
fi

# Check which service to deploy
DEPLOY_TARGET=${1:-"all"}

echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Deploy: $DEPLOY_TARGET"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Function to deploy PolicyKit (Django)
deploy_policykit() {
    echo ""
    echo "========================================================="
    echo "Deploying PolicyKit (Django)"
    echo "========================================================="
    cd policykit

    gcloud run deploy policykit-api \
      --source . \
      --region $REGION \
      --platform managed \
      --allow-unauthenticated \
      --memory 2Gi \
      --cpu 2 \
      --timeout 300 \
      --max-instances 10 \
      --min-instances 1 \
      --port 8000 \
      --set-env-vars="ENVIRONMENT=production"

    POLICYKIT_URL=$(gcloud run services describe policykit-api \
        --region $REGION \
        --format 'value(status.url)')

    echo ""
    echo "✓ PolicyKit deployed: $POLICYKIT_URL"
    cd ..

    echo "$POLICYKIT_URL" > .policykit-url
}

# Function to deploy sandbox
deploy_sandbox() {
    echo ""
    echo "========================================================="
    echo "Deploying Sandbox Service"
    echo "========================================================="
    cd sandbox

    gcloud run deploy sandbox-api \
      --source . \
      --region $REGION \
      --platform managed \
      --allow-unauthenticated \
      --memory 2Gi \
      --cpu 2 \
      --timeout 900 \
      --max-instances 10 \
      --min-instances 0 \
      --port 8001 \
      --set-env-vars="ENVIRONMENT=production"

    SANDBOX_URL=$(gcloud run services describe sandbox-api \
        --region $REGION \
        --format 'value(status.url)')

    echo ""
    echo "✓ Sandbox deployed: $SANDBOX_URL"
    cd ..

    echo "$SANDBOX_URL" > .sandbox-url
}

# Function to deploy agent
deploy_agent() {
    echo ""
    echo "========================================================="
    echo "Deploying Agent Service"
    echo "========================================================="

    # Get sandbox URL
    if [ -f .sandbox-url ]; then
        SANDBOX_URL=$(cat .sandbox-url)
    else
        echo "Warning: Sandbox URL not found. Deploy sandbox first or provide URL."
        read -p "Enter sandbox URL (or press Enter to skip): " SANDBOX_URL
        if [ -z "$SANDBOX_URL" ]; then
            SANDBOX_URL="http://localhost:8001"
        fi
    fi

    echo "Agent will connect to sandbox at: $SANDBOX_URL"

    cd agent

    gcloud run deploy agent-api \
      --source . \
      --region $REGION \
      --platform managed \
      --allow-unauthenticated \
      --memory 1Gi \
      --cpu 1 \
      --timeout 900 \
      --max-instances 5 \
      --min-instances 0 \
      --port 8002 \
      --set-env-vars="ENVIRONMENT=production,SANDBOX_URL=$SANDBOX_URL"

    AGENT_URL=$(gcloud run services describe agent-api \
        --region $REGION \
        --format 'value(status.url)')

    echo ""
    echo "✓ Agent deployed: $AGENT_URL"
    cd ..

    echo "$AGENT_URL" > .agent-url
}

# Deploy based on target
case $DEPLOY_TARGET in
    policykit)
        deploy_policykit
        ;;
    sandbox)
        deploy_sandbox
        ;;
    agent)
        deploy_agent
        ;;
    all)
        deploy_policykit
        deploy_sandbox
        deploy_agent
        ;;
    *)
        echo "Error: Invalid deploy target '$DEPLOY_TARGET'"
        echo "Valid options: policykit, sandbox, agent, all"
        exit 1
        ;;
esac

echo ""
echo "========================================================="
echo "✓ Deployment Complete!"
echo "========================================================="

if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "policykit" ]; then
    echo "PolicyKit URL: $(cat .policykit-url)"
fi

if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "sandbox" ]; then
    echo "Sandbox URL:   $(cat .sandbox-url)"
fi

if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "agent" ]; then
    echo "Agent URL:     $(cat .agent-url)"
fi

echo ""
echo "Test your deployment:"
if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "policykit" ]; then
    echo "  curl \$(cat .policykit-url)/health"
fi
if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "sandbox" ]; then
    echo "  curl \$(cat .sandbox-url)/sandbox/health"
fi
if [ "$DEPLOY_TARGET" = "all" ] || [ "$DEPLOY_TARGET" = "agent" ]; then
    echo "  curl \$(cat .agent-url)/health"
fi
echo ""
