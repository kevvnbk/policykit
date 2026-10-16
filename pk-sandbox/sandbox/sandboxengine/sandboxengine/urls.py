"""
Route registration and FastAPI app creation.

PolicyKit equivalent: policykit/policykit/urls.py
Replaces Django URL patterns with FastAPI router mounting.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

from sandboxengine.settings import CORS_ORIGINS, RATE_LIMIT
from sandboxengine.api_views import router as api_router
from sandboxengine.sandbox_api import router as sandbox_router
from sandboxengine.credentials_api import router as credentials_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Sandbox Pipeline API",
    version="1.0.0",
    description="Execute PolicyKit script generation pipeline with user-provided AWS credentials",
)

# CORS middleware
import re
from starlette.middleware.cors import CORSMiddleware as StarletteMiddleware

# Allow all origins if set to "*", otherwise use specific list
if CORS_ORIGINS == ["*"] or "*" in CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# Rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount routes
app.include_router(api_router)
app.include_router(sandbox_router)
app.include_router(credentials_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "sandbox-pipeline", "version": "1.0.0"}
