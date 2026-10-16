#!/bin/bash
set -e

# Deployment script for Google Cloud Run

PROJECT_ID=${GCP_PROJECT_ID:-"your-project-id"}
REGION=${GCP_REGION:-"us-central1"}
SERVICE_NAME="sandbox-api"

echo "================================================="
echo "Deploying Sandbox Pipeline API to Google Cloud Run"
echo "================================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "Error: Not authenticated with gcloud"
    echo "Run: gcloud auth login"
    exit 1
fi

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Build and deploy using Cloud Build
echo ""
echo "Building and deploying (this may take 2-3 minutes)..."
gcloud run deploy $SERVICE_NAME \
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

# Get the deployed URL
echo ""
echo "Getting service URL..."
URL=$(gcloud run services describe $SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --format 'value(status.url)')

echo ""
echo "================================================="
echo "✓ Deployment complete!"
echo "================================================="
echo "API URL: $URL"
echo ""
echo "Test the deployment:"
echo "  curl $URL/health"
echo ""
echo "Or run the test client:"
echo "  cd ../client"
echo "  python test_client.py --url $URL --test basic"
