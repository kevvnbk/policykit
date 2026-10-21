"""
Type stubs for sandbox types used by the agent.

When deploying the agent separately from sandbox, use these stubs instead
of importing from the actual sandbox package.

For local development with sandbox installed, import from:
    from sandbox.sandboxengine.policyengine.scenarios import Scenario, ScenarioResult
    from sandbox.sandboxengine.policyengine.validation import ValidationResult

For production deployment (agent only), import from here:
    from types_stub import Scenario, ScenarioResult, ValidationResult
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioEvent:
    """Event to trigger during scenario execution."""
    type: str
    data: dict[str, Any]
    actor_id: str | None = None
    at: float = 0.0


@dataclass
class Assertion:
    """Assertion to verify after scenario execution."""
    type: str
    expected: Any
    description: str = ""


@dataclass
class Scenario:
    """Test scenario for governance script."""
    name: str
    description: str
    community_setup: dict[str, Any]
    events: list[ScenarioEvent]
    assertions: list[Assertion]
    time_limit: float = 3600.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for HTTP serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "community_setup": self.community_setup,
            "events": [
                {
                    "type": e.type,
                    "data": e.data,
                    "actor_id": e.actor_id,
                    "at": e.at,
                }
                for e in self.events
            ],
            "assertions": [
                {
                    "type": a.type,
                    "expected": a.expected,
                    "description": a.description,
                }
                for a in self.assertions
            ],
            "time_limit": self.time_limit,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Scenario":
        """Create from dictionary."""
        return Scenario(
            name=data.get("name", ""),
            description=data.get("description", ""),
            community_setup=data.get("community_setup", {}),
            events=[
                ScenarioEvent(
                    type=e.get("type", ""),
                    data=e.get("data", {}),
                    actor_id=e.get("actor_id"),
                    at=e.get("at", 0.0),
                )
                for e in data.get("events", [])
            ],
            assertions=[
                Assertion(
                    type=a.get("type", ""),
                    expected=a.get("expected"),
                    description=a.get("description", ""),
                )
                for a in data.get("assertions", [])
            ],
            time_limit=data.get("time_limit", 3600.0),
        )


@dataclass
class ScenarioResult:
    """Result of scenario execution."""
    scenario_name: str
    passed: bool
    error: str | None = None
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    execution_time: float = 0.0

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ScenarioResult":
        """Create from dictionary."""
        return ScenarioResult(
            scenario_name=data.get("scenario_name", ""),
            passed=data.get("passed", False),
            error=data.get("error"),
            assertion_results=data.get("assertion_results", []),
            actions_taken=data.get("actions_taken", []),
            execution_time=data.get("execution_time", 0.0),
        )


@dataclass
class ValidationError:
    """Validation error details."""
    type: str
    message: str
    line: int | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ValidationError":
        """Create from dictionary."""
        return ValidationError(
            type=data.get("type", ""),
            message=data.get("message", ""),
            line=data.get("line"),
            context=data.get("context", {}),
        )


@dataclass
class ValidationResult:
    """Script validation result."""
    is_valid: bool
    blocking_errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ValidationResult":
        """Create from dictionary."""
        return ValidationResult(
            is_valid=data.get("is_valid", False),
            blocking_errors=[
                ValidationError.from_dict(e) for e in data.get("blocking_errors", [])
            ],
            warnings=[ValidationError.from_dict(w) for w in data.get("warnings", [])],
        )
