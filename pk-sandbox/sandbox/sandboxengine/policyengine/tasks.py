"""
Pipeline orchestration (simplified for sandbox-only usage).

This module manages script execution in the sandbox. The LLM generation
pipeline has been moved to the agent service.

Execution mode:
- execute_with_script(): accepts pre-written script + scenarios, executes them
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time
import uuid
import logging

from .engine import SandboxRunner
from .scenarios import Scenario, ScenarioEvent, Assertion, ScenarioResult

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
    Runs script execution in the sandbox.

    The LLM generation pipeline has been moved to the agent service.
    This class now only handles script execution with pre-written scripts.
    """

    def __init__(self, max_revisions: int = 3):
        self._runs: dict[str, PipelineRun] = {}
        self._runner = SandboxRunner()
        self._max_revisions = max_revisions

    def create_run(self, policy_text: str, document_schemas: dict | None = None) -> PipelineRun:
        run = PipelineRun(policy_text=policy_text)
        self._runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[PipelineRun]:
        return list(self._runs.values())

    def execute_with_script(
        self,
        run_id: str,
        script: str,
        scenarios: list[Scenario],
    ) -> PipelineRun:
        """Execute a pre-written script against scenarios."""
        run = self._runs[run_id]
        run.status = "running"

        run.stages["headers"].status = StageStatus.SKIPPED
        run.stages["script"].status = StageStatus.COMPLETED
        run.stages["script"].output = script
        run.stages["tests"].status = StageStatus.COMPLETED
        run.stages["tests"].output = [s.name for s in scenarios]

        self._execute_stage(run, script, scenarios)
        return run

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_scenarios(self, script: str, scenarios: list[Scenario]) -> list[ScenarioResult]:
        results = []
        for scenario in scenarios:
            result = self._runner.run(script, scenario)
            results.append(result)
        return results

    def _execute_stage(self, run: PipelineRun, script: str, scenarios: list[Scenario]) -> None:
        """Execute stage for the pre-written script path."""
        stage = run.stages["execute"]
        stage.status = StageStatus.RUNNING
        stage.started_at = time.time()

        results = self._run_scenarios(script, scenarios)

        stage.completed_at = time.time()
        all_passed = all(r.passed for r in results)

        stage.output = [
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
            stage.status = StageStatus.COMPLETED
            run.stages["revise"].status = StageStatus.SKIPPED
            self._report_stage(run, results)
        else:
            stage.status = StageStatus.FAILED
            run.stages["revise"].status = StageStatus.COMPLETED
            run.stages["revise"].output = {
                "failures": [r.error or "assertion failure" for r in results if not r.passed],
                "revision_count": run.revision_count,
            }
            self._report_stage(run, results)

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
