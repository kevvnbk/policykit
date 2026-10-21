"""
Sandbox-specific API endpoints.

These endpoints expose the sandbox as a standalone testing service
that the agent can call via HTTP.

Endpoints:
  POST /sandbox/execute    — Execute script against scenarios
  POST /sandbox/validate   — Validate script structure
  GET  /sandbox/api-reference — Get API documentation for prompt injection
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import logging
import time

from sandbox.sandboxengine.policyengine.engine import SandboxRunner
from sandbox.sandboxengine.policyengine.scenarios import Scenario, ScenarioResult
from sandbox.sandboxengine.policyengine.validation import ScriptValidator
from pathlib import Path

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
logger = logging.getLogger(__name__)

sandbox_runner = SandboxRunner()
script_validator = ScriptValidator()


# ============================================================================
# Request/Response Models
# ============================================================================

class ExecuteScriptRequest(BaseModel):
    """Request to execute a script against test scenarios."""
    script: str = Field(..., description="Python policy script to execute")
    scenarios: List[Dict[str, Any]] = Field(..., description="Test scenarios in dict format")


class ExecuteScriptResponse(BaseModel):
    """Response from script execution."""
    results: List[Dict[str, Any]] = Field(..., description="Results for each scenario")
    execution_time: float = Field(..., description="Total execution time in seconds")


class ValidateScriptRequest(BaseModel):
    """Request to validate a script's structure."""
    script: str = Field(..., description="Python policy script to validate")


class ValidateScriptResponse(BaseModel):
    """Response from script validation."""
    is_valid: bool = Field(..., description="Whether the script is valid")
    blocking_errors: List[Dict[str, Any]] = Field(default_factory=list, description="Errors that prevent execution")
    warnings: List[Dict[str, Any]] = Field(default_factory=list, description="Non-blocking warnings")


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/execute", response_model=ExecuteScriptResponse)
def execute_script(request: ExecuteScriptRequest) -> ExecuteScriptResponse:
    """
    Execute a policy script against test scenarios.

    This is the core sandbox execution endpoint that the agent calls
    to test generated scripts.

    Args:
        request: Script and scenarios to execute

    Returns:
        Results for each scenario including pass/fail, errors, actions taken

    Raises:
        HTTPException: If execution fails unexpectedly
    """
    start_time = time.time()

    try:
        # Parse scenarios from dicts
        scenarios = [Scenario.from_dict(s) for s in request.scenarios]

        # Execute each scenario
        results = []
        for scenario in scenarios:
            result = sandbox_runner.run(request.script, scenario)
            results.append(result.to_dict())

        execution_time = time.time() - start_time

        logger.info(
            f"Executed {len(scenarios)} scenarios in {execution_time:.2f}s. "
            f"Passed: {sum(1 for r in results if r['passed'])}/{len(results)}"
        )

        return ExecuteScriptResponse(
            results=results,
            execution_time=execution_time
        )

    except Exception as e:
        logger.exception("Sandbox execution failed")
        raise HTTPException(
            status_code=500,
            detail=f"Sandbox execution failed: {type(e).__name__}: {e}"
        )


@router.post("/validate", response_model=ValidateScriptResponse)
def validate_script(request: ValidateScriptRequest) -> ValidateScriptResponse:
    """
    Validate a policy script's structure without executing it.

    Checks for:
    - Syntax errors
    - Missing required functions (setup)
    - Undefined constants
    - Invalid handler signatures

    Args:
        request: Script to validate

    Returns:
        Validation result with errors and warnings
    """
    try:
        validation_result = script_validator.validate(request.script)

        return ValidateScriptResponse(
            is_valid=validation_result.is_valid,
            blocking_errors=[e.to_dict() for e in validation_result.blocking_errors],
            warnings=[w.to_dict() for w in validation_result.warnings]
        )

    except Exception as e:
        logger.exception("Script validation failed")
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {type(e).__name__}: {e}"
        )


@router.get("/api-reference")
def get_api_reference() -> Dict[str, str]:
    """
    Get the sandbox API reference documentation.

    This endpoint returns the API documentation that the agent
    injects into LLM prompts to teach the model how to write scripts.

    Returns:
        API reference as markdown text
    """
    try:
        # Path to API reference document
        api_ref_path = Path(__file__).parent.parent.parent / "docs" / "guides" / "api_reference.md"

        if not api_ref_path.exists():
            logger.warning(f"API reference not found at {api_ref_path}")
            return {
                "content": "API reference not found",
                "error": f"File not found: {api_ref_path}"
            }

        content = api_ref_path.read_text(encoding="utf-8")

        return {
            "content": content
        }

    except Exception as e:
        logger.exception("Failed to load API reference")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load API reference: {type(e).__name__}: {e}"
        )


@router.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint for the sandbox service."""
    return {
        "status": "ok",
        "service": "sandbox",
        "message": "Sandbox is running"
    }
