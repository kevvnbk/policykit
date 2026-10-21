"""
API endpoint definitions.

Provides REST endpoints for the sandbox pipeline.

Endpoints:
  POST /execute                  — Execute pipeline with user credentials (synchronous)
  POST /sandbox/run              — Start a pipeline run (async, for frontend)
  GET  /sandbox/run/{id}/status  — Poll pipeline progress
  GET  /sandbox/run/{id}/stage/{name} — Get output for specific stage
  GET  /sandbox/history          — List previous runs
  GET  /health                   — Health check
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Any
import logging
import time
import boto3
import requests
from botocore.exceptions import ClientError

from sandbox.sandboxengine.policyengine.tasks import PipelineOrchestrator, StageStatus
from sandbox.sandboxengine.policyengine.engine import Scenario, ScenarioEvent, Assertion
from sandbox.sandboxengine.policyengine.datasources import DocumentSchema

router = APIRouter()
logger = logging.getLogger(__name__)

orchestrator = PipelineOrchestrator()


# ============================================================================
# Models for external documents
# ============================================================================

class DocumentData(BaseModel):
    """External document data provided by frontend."""
    source_type: str = Field(..., description="Type of document source (e.g., 'google_sheets')")
    source_url: str = Field(..., description="URL of the document")
    structure: Dict[str, Any] = Field(..., description="Document structure (columns, sheet names, etc.)")
    sample_data: List[Dict[str, Any]] = Field(default_factory=list, description="Sample rows from the document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# ============================================================================
# Models for simplified /execute endpoint
# ============================================================================

class ExecuteRequest(BaseModel):
    """Request for simplified execute endpoint."""
    policy_text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language governance policy"
    )
    documents: List[DocumentData] = Field(
        default_factory=list,
        description="External documents referenced in the policy"
    )
    aws_access_key_id: str | None = Field(None, description="AWS Access Key ID (IAM auth)")
    aws_secret_access_key: str | None = Field(None, description="AWS Secret Access Key (IAM auth)")
    aws_session_token: str | None = Field(None, description="AWS Session Token (for temporary credentials like AWS SSO)")
    aws_bearer_token: str | None = Field(None, description="AWS Bearer Token / API Key (alternative to IAM credentials)")
    aws_region: str = Field(default="us-east-1", description="AWS region")


class ExecuteResponse(BaseModel):
    """Response from simplified execute endpoint."""
    success: bool
    script: str | None = Field(
        None,
        description="Generated script (latest version). None only if generation failed completely."
    )
    error: str | None = None


# ============================================================================
# Simplified /execute endpoint
# ============================================================================

@router.post("/execute")
def execute(request_body: ExecuteRequest) -> ExecuteResponse:
    """
    Execute the complete pipeline and return generated script.

    This is a synchronous blocking call that:
    1. Validates AWS credentials
    2. Generates script from policy text
    3. Tests and revises until passing
    4. Returns final script (or most recent version if failed)

    Timeout: 10 minutes max
    """
    request_id = f"req-{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] Starting pipeline for policy (length: {len(request_body.policy_text)})")

    try:
        # Step 1: Validate credentials
        if not _validate_credentials(request_body):
            return ExecuteResponse(
                success=False,
                script=None,
                error="Invalid AWS credentials. Please check your access key, secret key, or bearer token."
            )

        # Step 2: Convert documents to DocumentSchema format
        document_schemas = {}
        for doc in request_body.documents:
            schema = DocumentSchema(
                source_type=doc.source_type,
                source_url=doc.source_url,
                structure=doc.structure,
                sample_data=doc.sample_data,
                metadata=doc.metadata
            )
            document_schemas[doc.source_url] = schema

        # Step 3: Create pipeline run with documents
        run = orchestrator.create_run(request_body.policy_text, document_schemas)
        logger.info(f"[{request_id}] Created run {run.id} with {len(document_schemas)} document(s)")

        # Step 4: Execute pipeline synchronously
        credentials = _extract_credentials(request_body)
        final_run = orchestrator.execute_full_sync(
            run_id=run.id,
            credentials=credentials,
            timeout=600.0  # 10 minutes
        )

        # Step 5: Extract results
        script = _extract_final_script(final_run)

        if final_run.status == "completed":
            logger.info(f"[{request_id}] Pipeline completed successfully")
            return ExecuteResponse(success=True, script=script)
        else:
            error = _extract_error(final_run)
            logger.warning(f"[{request_id}] Pipeline failed: {error}")
            return ExecuteResponse(
                success=False,
                script=script,  # Return latest script even on failure
                error=error
            )

    except TimeoutError:
        logger.error(f"[{request_id}] Pipeline timeout")
        # Try to extract whatever script we have so far
        run = orchestrator.get_run(run.id) if 'run' in locals() else None
        script = _extract_final_script(run) if run else None
        return ExecuteResponse(
            success=False,
            script=script,
            error="Pipeline execution timed out after 10 minutes"
        )
    except Exception as e:
        logger.exception(f"[{request_id}] Unexpected error")
        # Try to extract whatever script we have
        run = orchestrator.get_run(run.id) if 'run' in locals() else None
        script = _extract_final_script(run) if run else None
        return ExecuteResponse(
            success=False,
            script=script,
            error=f"Unexpected error: {str(e)}"
        )


def _validate_credentials(request: ExecuteRequest) -> bool:
    """Quick validation that AWS credentials work."""
    try:
        # Check that either IAM credentials or bearer token is provided
        has_iam = request.aws_access_key_id and request.aws_secret_access_key
        has_bearer = request.aws_bearer_token

        if not has_iam and not has_bearer:
            logger.warning("Neither IAM credentials nor bearer token provided")
            return False

        if has_iam and has_bearer:
            logger.warning("Both IAM credentials and bearer token provided - use one or the other")
            return False

        # Bearer token validation: make a simple test request to Bedrock
        if has_bearer:
            # Use a minimal request to test the token
            url = f"https://bedrock-runtime.{request.aws_region}.amazonaws.com/model/us.anthropic.claude-3-5-sonnet-20241022-v2:0/converse"
            response = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {request.aws_bearer_token}"
                },
                json={
                    "messages": [{"role": "user", "content": [{"text": "hi"}]}]
                },
                timeout=30  # Increased timeout
            )
            # 200 = success, 400 might be bad request format but auth worked
            # Check for auth errors specifically
            if response.status_code in (200, 400):
                return True
            if response.status_code == 401 or response.status_code == 403:
                logger.warning(f"Bearer token auth failed: {response.status_code} {response.text[:200]}")
                return False
            # Other errors might not be auth-related
            logger.warning(f"Unexpected response during bearer token validation: {response.status_code}")
            return response.status_code < 500  # Server errors don't mean bad token

        # IAM credential validation using boto3
        client_kwargs = {
            'aws_access_key_id': request.aws_access_key_id,
            'aws_secret_access_key': request.aws_secret_access_key,
            'region_name': request.aws_region
        }
        if request.aws_session_token:
            client_kwargs['aws_session_token'] = request.aws_session_token

        client = boto3.client('bedrock', **client_kwargs)
        client.list_foundation_models()
        return True
    except ClientError as e:
        logger.warning(f"Credential validation failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"Credential validation error: {e}")
        return False


def _extract_credentials(request: ExecuteRequest) -> dict:
    """Extract credentials into dict for pipeline."""
    creds = {"region": request.aws_region}

    # Bearer token authentication
    if request.aws_bearer_token:
        creds["bearer_token"] = request.aws_bearer_token
    # IAM authentication
    else:
        creds["access_key_id"] = request.aws_access_key_id
        creds["secret_access_key"] = request.aws_secret_access_key
        if request.aws_session_token:
            creds["session_token"] = request.aws_session_token

    return creds


def _extract_final_script(run) -> str | None:
    """
    Get the most recent script from the run, even if pipeline failed.

    Priority:
    1. Revised script (if revisions were attempted)
    2. Original generated script (if script stage completed)
    3. None (if script generation never succeeded)
    """
    if not run:
        return None

    # Priority 1: Check revise stage for latest script
    revise_stage = run.stages.get("revise")
    if revise_stage and revise_stage.output:
        if isinstance(revise_stage.output, dict):
            if "final_script" in revise_stage.output:
                return revise_stage.output["final_script"]
            # Check attempts array for the last attempted script
            if "attempts" in revise_stage.output:
                attempts = revise_stage.output["attempts"]
                if attempts and len(attempts) > 0:
                    last_attempt = attempts[-1]
                    if "revised_script" in last_attempt:
                        return last_attempt["revised_script"]

    # Priority 2: Check script stage for original generated script
    script_stage = run.stages.get("script")
    if script_stage and script_stage.output:
        if isinstance(script_stage.output, dict):
            if "script" in script_stage.output:
                return script_stage.output["script"]
        elif isinstance(script_stage.output, str):
            return script_stage.output

    # Priority 3: No script was ever generated
    return None


def _extract_error(run) -> str:
    """Get first error message from failed stages."""
    for stage_name in ["headers", "script", "tests", "execute", "revise"]:
        stage = run.stages[stage_name]
        if stage.error:
            return f"{stage_name.title()} stage failed: {stage.error}"

    return "Pipeline failed for unknown reason"


# ============================================================================
# Async endpoints (for frontend polling)
# ============================================================================

class RunRequest(BaseModel):
    policy_text: str = Field(..., description="Natural language governance policy")
    documents: List[DocumentData] = Field(
        default_factory=list,
        description="External documents referenced in the policy"
    )
    script: str | None = Field(None, description="Pre-written script (skips LLM generation if provided)")
    scenarios: list[dict] | None = Field(None, description="Pre-written scenarios (required if script is provided)")
    aws_access_key_id: str | None = Field(None, description="AWS Access Key ID (IAM auth, required for LLM generation)")
    aws_secret_access_key: str | None = Field(None, description="AWS Secret Access Key (IAM auth, required for LLM generation)")
    aws_session_token: str | None = Field(None, description="AWS Session Token (for temporary IAM credentials)")
    aws_bearer_token: str | None = Field(None, description="AWS Bearer Token / API Key (alternative to IAM credentials)")
    aws_region: str = Field(default="us-east-1", description="AWS region")


class RunResponse(BaseModel):
    id: str
    status: str


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/sandbox/run")
def start_run(request: RunRequest) -> RunResponse:
    """
    Start a pipeline run.

    Two modes:
    - Full pipeline: provide policy_text + credentials + documents. LLM generates headers, script, tests.
      Returns immediately; pipeline runs in background. Poll /status to watch progress.
    - Pre-written: provide policy_text + script + scenarios. Executes synchronously.
      Useful for testing and the MVP flow.
    """
    # Convert documents to DocumentSchema format
    document_schemas = {}
    for doc in request.documents:
        schema = DocumentSchema(
            source_type=doc.source_type,
            source_url=doc.source_url,
            structure=doc.structure,
            sample_data=doc.sample_data,
            metadata=doc.metadata
        )
        document_schemas[doc.source_url] = schema

    # Create run with documents
    run = orchestrator.create_run(request.policy_text, document_schemas)

    if request.script and request.scenarios:
        scenarios = _parse_scenarios(request.scenarios)
        orchestrator.execute_with_script(run.id, request.script, scenarios)
    else:
        # Extract credentials if provided
        credentials = None
        if request.aws_bearer_token:
            credentials = {
                "bearer_token": request.aws_bearer_token,
                "region": request.aws_region,
            }
        elif request.aws_access_key_id and request.aws_secret_access_key:
            credentials = {
                "access_key_id": request.aws_access_key_id,
                "secret_access_key": request.aws_secret_access_key,
                "region": request.aws_region,
            }
            if request.aws_session_token:
                credentials["session_token"] = request.aws_session_token
        orchestrator.execute_full(run.id, credentials)

    return RunResponse(id=run.id, status=run.status)


@router.get("/sandbox/run/{run_id}/status")
def get_run_status(run_id: str):
    """
    Get the current status of a pipeline run.

    Frontend polls this endpoint every ~1s while status is "running".
    Stages transition through pending → running → completed/failed/skipped.
    """
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()


@router.get("/sandbox/run/{run_id}/stage/{stage_name}")
def get_stage(run_id: str, stage_name: str):
    """Get detailed output for a specific pipeline stage."""
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    stage = run.stages.get(stage_name)
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    return {
        "status": stage.status.value,
        "output": stage.output,
        "error": stage.error,
    }


@router.get("/sandbox/history")
def list_runs():
    """List all previous pipeline runs, most recent first."""
    runs = orchestrator.list_runs()
    return [
        {"id": r.id, "policy_text": r.policy_text[:100], "status": r.status, "created_at": r.created_at}
        for r in runs
    ]


def _parse_scenarios(raw: list[dict]) -> list[Scenario]:
    scenarios = []
    for s in raw:
        events = [
            ScenarioEvent(
                type=e["type"],
                data=e.get("data", {}),
                actor_id=e.get("actor_id"),
                at=e.get("at", 0.0),
            )
            for e in s.get("events", [])
        ]
        assertions = [
            Assertion(
                type=a["type"],
                expected=a.get("expected"),
                description=a.get("description", ""),
            )
            for a in s.get("assertions", [])
        ]
        scenarios.append(Scenario(
            name=s.get("name", "unnamed"),
            description=s.get("description", ""),
            community_setup=s.get("community_setup", {}),
            events=events,
            assertions=assertions,
            time_limit=s.get("time_limit", 3600.0),
        ))
    return scenarios
