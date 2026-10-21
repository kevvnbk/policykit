"""
Credentials API for sandbox frontend.

Provides an endpoint for the frontend to fetch AWS credentials from
the local environment (AWS profile or environment variables).

This allows the sandbox frontend running on localhost to get credentials
and send them to the agent API.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import boto3
import os
import logging

router = APIRouter(prefix="/credentials", tags=["credentials"])
logger = logging.getLogger(__name__)


class CredentialsResponse(BaseModel):
    """AWS credentials fetched from local environment."""
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str | None = None
    aws_region: str
    source: str  # "profile", "environment", or "iam_role"


@router.get("/aws", response_model=CredentialsResponse)
def get_aws_credentials() -> CredentialsResponse:
    """
    Get AWS credentials from the local environment.

    Attempts to fetch credentials in this order:
    1. AWS profile (specified by AWS_PROFILE env var or default profile)
    2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    3. IAM role (if running on EC2/ECS)

    This endpoint is only meant for localhost development where the sandbox
    frontend needs to forward local AWS credentials to the agent API.

    Returns:
        AWS credentials that can be sent to agent API

    Raises:
        HTTPException: If no valid credentials are found
    """
    try:
        # Try to get credentials from boto3 session (handles all sources)
        profile = os.environ.get("AWS_PROFILE", "bedrock")
        region = os.environ.get("AWS_REGION", "us-east-1")

        session = boto3.Session(profile_name=profile, region_name=region)
        credentials = session.get_credentials()

        if credentials is None:
            raise HTTPException(
                status_code=404,
                detail="No AWS credentials found. Please configure AWS CLI or set environment variables."
            )

        # Get frozen credentials (resolves any temporary credentials)
        frozen_creds = credentials.get_frozen_credentials()

        # Determine source
        source = "profile"
        if os.environ.get("AWS_ACCESS_KEY_ID"):
            source = "environment"
        elif os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
            source = "iam_role"

        logger.info(f"Credentials fetched from {source} (profile: {profile}, region: {region})")

        return CredentialsResponse(
            aws_access_key_id=frozen_creds.access_key,
            aws_secret_access_key=frozen_creds.secret_key,
            aws_session_token=frozen_creds.token,  # May be None for permanent credentials
            aws_region=region,
            source=source
        )

    except Exception as e:
        logger.exception("Failed to fetch AWS credentials")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch AWS credentials: {str(e)}"
        )


@router.get("/test")
def test_credentials():
    """
    Test if AWS credentials are valid by making a simple Bedrock API call.

    Returns:
        Status of credential validation
    """
    try:
        credentials = get_aws_credentials()

        # Test credentials by listing foundation models
        client = boto3.client(
            'bedrock',
            aws_access_key_id=credentials.aws_access_key_id,
            aws_secret_access_key=credentials.aws_secret_access_key,
            aws_session_token=credentials.aws_session_token,
            region_name=credentials.aws_region
        )

        # Make a simple API call
        response = client.list_foundation_models()

        return {
            "valid": True,
            "source": credentials.source,
            "region": credentials.aws_region,
            "models_available": len(response.get("modelSummaries", []))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Credentials test failed")
        return {
            "valid": False,
            "error": str(e)
        }
