"""
Application settings.

PolicyKit equivalent: policykit/policykit/settings.py
Replaces Django settings with plain Python configuration.
"""
import os

# Server
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8001))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

# Frontend / CORS
# For production, set ALLOWED_ORIGINS env var with comma-separated origins
ALLOWED_ORIGINS_STR = os.environ.get("ALLOWED_ORIGINS", "")
if ALLOWED_ORIGINS_STR:
    CORS_ORIGINS = ALLOWED_ORIGINS_STR.split(",")
else:
    # Default for development
    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
    ]

# Rate limiting
RATE_LIMIT = os.environ.get("RATE_LIMIT", "5/minute")

# LLM (AWS Bedrock model IDs)
LLM_MODEL = "us.anthropic.claude-sonnet-4-6"
LLM_MAX_TOKENS = 8192  # Increased for complex policies with many handlers

# Sandbox execution
MAX_EXECUTION_TIME = 30  # seconds per scenario
MAX_REVISION_ATTEMPTS = 3

# Pipeline
PIPELINE_STAGES = [
    "headers",
    "script",
    "tests",
    "execute",
    "revise",
    "report",
]
