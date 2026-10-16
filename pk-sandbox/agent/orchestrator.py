"""
Agent pipeline orchestrator.

Manages the full generation/testing/revision workflow by coordinating
between the LLM client and the sandbox client.

The orchestrator is responsible for:
1. Generating headers, scripts, and tests via LLM
2. Executing tests via sandbox
3. Revising failed scripts
4. Tracking pipeline state

The sandbox must be installed as a package:
    pip install -e ../sandbox
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time
import uuid
import logging
import difflib

# Import scenario types - use local stubs if sandbox package not available
try:
    from policyengine.scenarios import Scenario, ScenarioEvent, Assertion, ScenarioResult
except ImportError:
    from types_stub import Scenario, ScenarioEvent, Assertion, ScenarioResult

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    status: StageStatus = StageStatus.PENDING
    output: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class PipelineRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    policy_text: str = ""
    stages: dict[str, StageResult] = field(default_factory=lambda: {
        "headers": StageResult(),
        "script": StageResult(),
        "tests": StageResult(),
        "execute": StageResult(),
        "revise": StageResult(),
        "report": StageResult(),
    })
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    revision_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "policy_text": self.policy_text,
            "status": self.status,
            "created_at": self.created_at,
            "revision_count": self.revision_count,
            "stages": {
                name: {
                    "status": stage.status.value,
                    "output": stage.output,
                    "error": stage.error,
                }
                for name, stage in self.stages.items()
            },
        }


class PipelineOrchestrator:
    """
    Orchestrates the full LLM generation and testing pipeline.

    Uses:
    - llm_client to generate code
    - sandbox_client to execute and validate code
    """

    def __init__(self, llm_client, sandbox_client, max_revisions: int = 3):
        """
        Initialize orchestrator.

        Args:
            llm_client: LLM client for code generation
            sandbox_client: Sandbox client for execution
            max_revisions: Maximum number of revision attempts
        """
        self.llm = llm_client
        self.sandbox = sandbox_client
        self._max_revisions = max_revisions
        self._runs: dict[str, PipelineRun] = {}

    def create_run(self, policy_text: str) -> PipelineRun:
        """Create a new pipeline run."""
        run = PipelineRun(policy_text=policy_text)
        self._runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> PipelineRun | None:
        """Get a pipeline run by ID."""
        return self._runs.get(run_id)

    def list_runs(self) -> list[PipelineRun]:
        """List all pipeline runs."""
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def execute_pipeline(
        self,
        run_id: str,
        credentials: dict[str, str],
        document_schemas: dict | None = None
    ) -> PipelineRun:
        """
        Execute the full pipeline for a given run.

        Args:
            run_id: Pipeline run ID
            credentials: AWS credentials for LLM calls
            document_schemas: Optional document schemas for external data

        Returns:
            Completed pipeline run
        """
        run = self._runs[run_id]
        run.status = "running"

        # Get API reference from sandbox
        api_reference = self.sandbox.get_api_reference()

        try:
            # Stage 1: Generate Headers
            self._start_stage(run, "headers")
            headers_result = self.llm.generate_headers(
                run.policy_text,
                api_reference,
                credentials,
                document_schemas
            )
            headers = headers_result["headers"]
            self._complete_stage(run, "headers", {
                "headers": headers,
                "tokens_used": headers_result["tokens_used"],
                "latency_ms": headers_result["latency_ms"],
            })

            # Stage 2: Generate Script
            self._start_stage(run, "script")
            script_result = self.llm.generate_script(
                run.policy_text,
                headers,
                api_reference,
                credentials,
                document_schemas
            )
            script = script_result["script"]
            self._complete_stage(run, "script", {
                "script": script,
                "tokens_used": script_result["tokens_used"],
                "latency_ms": script_result["latency_ms"],
            })

            # Stage 3: Generate Tests
            self._start_stage(run, "tests")
            tests_result = self.llm.generate_tests(
                run.policy_text,
                headers,
                api_reference,
                credentials,
                document_schemas
            )
            raw_scenarios = tests_result["scenarios"]

            if not raw_scenarios:
                self._fail_stage(run, "tests", "LLM returned no valid test scenarios")
                run.status = "failed"
                return run

            scenarios = self._parse_raw_scenarios(raw_scenarios)
            self._complete_stage(run, "tests", {
                "scenario_names": [s.name for s in scenarios],
                "count": len(scenarios),
                "tokens_used": tests_result["tokens_used"],
                "latency_ms": tests_result["latency_ms"],
            })

            # Stage 4: Execute
            self._start_stage(run, "execute")
            results = self.sandbox.execute(script, scenarios)
            all_passed = all(r.passed for r in results)

            execute_output = [
                {
                    "scenario": r.scenario_name,
                    "passed": r.passed,
                    "error": r.error,
                    "assertions": r.assertion_results,
                    "actions": r.actions_taken,
                }
                for r in results
            ]

            if all_passed:
                self._complete_stage(run, "execute", execute_output)
                run.stages["revise"].status = StageStatus.SKIPPED
                self._report_stage(run, results)
                return run

            self._fail_stage(run, "execute", f"{sum(1 for r in results if not r.passed)} scenario(s) failed")
            run.stages["execute"].output = execute_output

            # Stage 5: Revise
            self._start_stage(run, "revise")
            revision_history = []
            original_script = script

            for attempt in range(1, self._max_revisions + 1):
                run.revision_count = attempt
                previous_script = script

                error_summary = self._build_error_summary_text(results)

                revision_result = self.llm.revise_script(
                    run.policy_text,
                    script,
                    error_summary,
                    api_reference,
                    credentials
                )
                script = revision_result["script"]

                # Test revised script
                results = self.sandbox.execute(script, scenarios)
                all_passed = all(r.passed for r in results)

                diff = self._compute_diff(previous_script, script)

                revision_history.append({
                    "attempt": attempt,
                    "passed": all_passed,
                    "failures": sum(1 for r in results if not r.passed),
                    "tokens_used": revision_result["tokens_used"],
                    "latency_ms": revision_result["latency_ms"],
                    "revised_script": script,
                    "diff": diff,
                })

                if all_passed:
                    break

            revise_output = {
                "attempts": revision_history,
                "final_passed": all_passed,
                "final_script": script,
                "original_script": original_script,
            }

            if all_passed:
                self._complete_stage(run, "revise", revise_output)
                run.stages["execute"].status = StageStatus.COMPLETED
            else:
                self._fail_stage(run, "revise", f"Failed after {self._max_revisions} revision attempts")
                run.stages["revise"].output = revise_output

            self._report_stage(run, results)

        except Exception as e:
            logger.exception(f"Pipeline failed for run {run.id}")
            for stage_name, stage in run.stages.items():
                if stage.status == StageStatus.RUNNING:
                    self._fail_stage(run, stage_name, f"Unexpected error: {type(e).__name__}: {e}")
                    break
            run.status = "failed"

        return run

    def _start_stage(self, run: PipelineRun, stage_name: str) -> None:
        stage = run.stages[stage_name]
        stage.status = StageStatus.RUNNING
        stage.started_at = time.time()

    def _complete_stage(self, run: PipelineRun, stage_name: str, output: Any) -> None:
        stage = run.stages[stage_name]
        stage.status = StageStatus.COMPLETED
        stage.output = output
        stage.completed_at = time.time()

    def _fail_stage(self, run: PipelineRun, stage_name: str, error: str) -> None:
        stage = run.stages[stage_name]
        stage.status = StageStatus.FAILED
        stage.error = error
        stage.completed_at = time.time()

    def _parse_raw_scenarios(self, raw: list[dict]) -> list[Scenario]:
        """Convert raw JSON scenario dicts to Scenario objects."""
        scenarios = []
        for s in raw:
            events = [
                ScenarioEvent(
                    type=e.get("type", "unknown"),
                    data=e.get("data", {}),
                    actor_id=e.get("actor_id"),
                    at=e.get("at", 0.0),
                )
                for e in s.get("events", [])
            ]
            assertions = [
                Assertion(
                    type=a.get("type", "unknown"),
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

    def _build_error_summary_text(self, results: list[ScenarioResult]) -> str:
        """Build error summary for revision prompt."""
        parts = []
        for r in results:
            if r.passed:
                continue

            parts.append(f"SCENARIO: {r.scenario_name}")
            parts.append("=" * 60)

            if r.error:
                parts.append(f"Runtime Error: {r.error}")
                parts.append("")

            if r.assertion_results:
                failed_assertions = [a for a in r.assertion_results if not a.get("passed")]
                if failed_assertions:
                    parts.append("Failed Assertions:")
                    for a in failed_assertions:
                        parts.append(f"  - {a.get('assertion', 'unknown')}: {a.get('detail', '')}")
                    parts.append("")

            parts.append("")

        return "\n".join(parts)

    def _compute_diff(self, old_script: str, new_script: str) -> str:
        """Generate unified diff between two scripts."""
        old_lines = old_script.splitlines(keepends=True)
        new_lines = new_script.splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="previous",
            tofile="revised",
            lineterm="",
        )
        return "".join(diff_lines)

    def _report_stage(self, run: PipelineRun, results: list[ScenarioResult]) -> None:
        report_stage = run.stages["report"]
        report_stage.status = StageStatus.COMPLETED
        report_stage.completed_at = time.time()

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        report_stage.output = {
            "summary": f"{passed}/{total} scenarios passed",
            "passed": passed,
            "failed": failed,
            "total": total,
            "all_passed": failed == 0,
            "revision_count": run.revision_count,
        }

        run.status = "completed" if failed == 0 else "failed"
