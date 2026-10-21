"""
Agent API server.

Exposes REST API for the LLM agent that generates governance scripts.
The frontend calls this API to start pipeline runs, and the agent
orchestrates LLM generation and sandbox testing.

Run with:
    uvicorn agent.main:app --port 8002 --reload
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Any
import logging
import asyncio
import os

from orchestrator import PipelineOrchestrator
from sandbox_client import SandboxClient
import llm_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Agent API",
    version="1.0.0",
    description="LLM agent for generating and testing governance scripts"
)

# CORS middleware - allow frontend to call from different port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Initialize clients and orchestrator
# Use environment variable for sandbox URL (defaults to localhost for local dev)
SANDBOX_URL = os.getenv("SANDBOX_URL", "http://localhost:8001")
logger.info(f"Connecting to sandbox at: {SANDBOX_URL}")

sandbox_client = SandboxClient(sandbox_url=SANDBOX_URL)
orchestrator = PipelineOrchestrator(
    llm_client=llm_client,
    sandbox_client=sandbox_client,
    max_revisions=3
)


# ============================================================================
# Request/Response Models
# ============================================================================

class DocumentSchema(BaseModel):
    """External document schema."""
    source_type: str
    source_url: str
    structure: Dict[str, Any]
    sample_data: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StartPipelineRequest(BaseModel):
    """Request to start a new pipeline run."""
    policy_text: str = Field(..., min_length=10, max_length=10000)
    document_schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    aws_access_key_id: str = Field(..., description="AWS Access Key ID")
    aws_secret_access_key: str = Field(..., description="AWS Secret Access Key")
    aws_session_token: str | None = Field(None, description="AWS Session Token (optional)")
    aws_region: str = Field(default="us-east-1")


class StartPipelineResponse(BaseModel):
    """Response from starting a pipeline."""
    run_id: str
    status: str


class PipelineStatusResponse(BaseModel):
    """Response for pipeline status."""
    run_id: str
    status: str
    current_stage: str | None = None
    stages: Dict[str, Any]
    revision_count: int = 0


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "service": "agent",
        "version": "1.0.0",
        "sandbox_healthy": sandbox_client.health_check()
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    sandbox_healthy = sandbox_client.health_check()

    return {
        "status": "ok" if sandbox_healthy else "degraded",
        "agent": "ok",
        "sandbox": "ok" if sandbox_healthy else "unreachable"
    }


@app.post("/pipeline/start", response_model=StartPipelineResponse)
async def start_pipeline(request: StartPipelineRequest) -> StartPipelineResponse:
    """
    Start a new pipeline run.

    This endpoint creates a new pipeline run and starts executing it
    in the background. Use the /pipeline/{run_id}/status endpoint or
    WebSocket to monitor progress.

    Args:
        request: Pipeline request with policy text and credentials

    Returns:
        Run ID and initial status
    """
    # Check sandbox health
    if not sandbox_client.health_check():
        raise HTTPException(
            status_code=503,
            detail="Sandbox is not reachable. Ensure sandbox is running on port 8001."
        )

    # Create run
    run = orchestrator.create_run(request.policy_text)

    # Build credentials dict
    credentials = {
        "access_key_id": request.aws_access_key_id,
        "secret_access_key": request.aws_secret_access_key,
        "region": request.aws_region,
    }
    if request.aws_session_token:
        credentials["session_token"] = request.aws_session_token

    # Start pipeline in background task
    asyncio.create_task(_run_pipeline_async(
        run.id,
        credentials,
        request.document_schemas
    ))

    logger.info(f"Started pipeline run {run.id}")

    return StartPipelineResponse(
        run_id=run.id,
        status="running"
    )


async def _run_pipeline_async(
    run_id: str,
    credentials: dict,
    document_schemas: dict | None
):
    """Run pipeline in background task."""
    try:
        logger.info(f"Executing pipeline {run_id}")
        orchestrator.execute_pipeline(run_id, credentials, document_schemas)
        logger.info(f"Pipeline {run_id} completed")
    except Exception as e:
        logger.exception(f"Pipeline {run_id} failed with exception")


@app.get("/pipeline/{run_id}/status", response_model=PipelineStatusResponse)
def get_pipeline_status(run_id: str) -> PipelineStatusResponse:
    """
    Get the status of a pipeline run.

    Args:
        run_id: Pipeline run ID

    Returns:
        Current status and stage information

    Raises:
        HTTPException: If run ID not found
    """
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Find current stage
    current_stage = None
    for stage_name, stage in run.stages.items():
        if stage.status.value == "running":
            current_stage = stage_name
            break

    return PipelineStatusResponse(
        run_id=run.id,
        status=run.status,
        current_stage=current_stage,
        stages=run.to_dict()["stages"],
        revision_count=run.revision_count
    )


@app.get("/pipeline/{run_id}/stages/{stage_name}")
def get_stage_output(run_id: str, stage_name: str) -> Dict[str, Any]:
    """
    Get detailed output for a specific stage.

    Args:
        run_id: Pipeline run ID
        stage_name: Stage name (headers, script, tests, execute, revise, report)

    Returns:
        Stage output

    Raises:
        HTTPException: If run ID or stage not found
    """
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if stage_name not in run.stages:
        raise HTTPException(status_code=404, detail=f"Stage {stage_name} not found")

    stage = run.stages[stage_name]

    return {
        "stage": stage_name,
        "status": stage.status.value,
        "output": stage.output,
        "error": stage.error,
        "started_at": stage.started_at,
        "completed_at": stage.completed_at,
    }


@app.get("/pipeline/history")
def get_pipeline_history() -> List[Dict[str, Any]]:
    """
    Get history of pipeline runs.

    Returns:
        List of all pipeline runs (most recent first)
    """
    runs = orchestrator.list_runs()
    return [
        {
            "run_id": run.id,
            "status": run.status,
            "created_at": run.created_at,
            "revision_count": run.revision_count,
            "policy_preview": run.policy_text[:100] + "..." if len(run.policy_text) > 100 else run.policy_text
        }
        for run in runs
    ]


@app.websocket("/pipeline/{run_id}/ws")
async def pipeline_websocket(websocket: WebSocket, run_id: str):
    """
    WebSocket for real-time pipeline updates.

    Connects to a pipeline run and streams status updates as they happen.
    This is more efficient than polling /status endpoint.

    Args:
        websocket: WebSocket connection
        run_id: Pipeline run ID
    """
    await websocket.accept()

    try:
        # Send initial status
        run = orchestrator.get_run(run_id)
        if not run:
            await websocket.send_json({"error": f"Run {run_id} not found"})
            await websocket.close()
            return

        # Poll for updates and send to client
        last_status = None
        while True:
            run = orchestrator.get_run(run_id)
            current_status = run.to_dict()

            # Send update if status changed
            if current_status != last_status:
                await websocket.send_json(current_status)
                last_status = current_status

            # Stop if pipeline completed or failed
            if run.status in ["completed", "failed"]:
                break

            # Wait before next poll
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for run {run_id}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
