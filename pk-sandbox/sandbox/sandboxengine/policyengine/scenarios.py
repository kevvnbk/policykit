"""
Scenario and result types for sandbox testing.

These are the shared types used by both the agent (to generate tests)
and the sandbox (to execute tests). They define the contract between
the agent and sandbox APIs.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioEvent:
    """A single event in a scenario timeline."""
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for HTTP transport."""
        return {
            "type": self.type,
            "data": self.data,
            "actor_id": self.actor_id,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioEvent:
        """Deserialize from HTTP transport."""
        return cls(
            type=data["type"],
            data=data.get("data", {}),
            actor_id=data.get("actor_id"),
            at=data.get("at", 0.0),
        )


@dataclass
class Assertion:
    """A check to run after scenario execution."""
    type: str
    expected: Any = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for HTTP transport."""
        return {
            "type": self.type,
            "expected": self.expected,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assertion:
        """Deserialize from HTTP transport."""
        return cls(
            type=data["type"],
            expected=data.get("expected"),
            description=data.get("description", ""),
        )


@dataclass
class Scenario:
    """
    Declarative test format for sandbox execution.

    Used by both agent (to generate tests) and sandbox (to execute tests).
    This is the contract between agent and sandbox APIs.
    """
    name: str
    description: str = ""
    community_setup: dict[str, Any] = field(default_factory=dict)
    events: list[ScenarioEvent] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    time_limit: float = 3600.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for HTTP transport."""
        return {
            "name": self.name,
            "description": self.description,
            "community_setup": self.community_setup,
            "events": [e.to_dict() for e in self.events],
            "assertions": [a.to_dict() for a in self.assertions],
            "time_limit": self.time_limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        """Deserialize from HTTP transport."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            community_setup=data.get("community_setup", {}),
            events=[ScenarioEvent.from_dict(e) for e in data.get("events", [])],
            assertions=[Assertion.from_dict(a) for a in data.get("assertions", [])],
            time_limit=data.get("time_limit", 3600.0),
        )


@dataclass
class ScenarioResult:
    """
    Results from executing a scenario in the sandbox.

    Returned by sandbox to agent after execution.
    """
    scenario_name: str
    passed: bool
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    events_emitted: int = 0
    execution_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for HTTP transport."""
        return {
            "scenario_name": self.scenario_name,
            "passed": self.passed,
            "assertion_results": self.assertion_results,
            "error": self.error,
            "actions_taken": self.actions_taken,
            "events_emitted": self.events_emitted,
            "execution_time": self.execution_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioResult:
        """Deserialize from HTTP transport."""
        return cls(
            scenario_name=data["scenario_name"],
            passed=data["passed"],
            assertion_results=data.get("assertion_results", []),
            error=data.get("error"),
            actions_taken=data.get("actions_taken", []),
            events_emitted=data.get("events_emitted", 0),
            execution_time=data.get("execution_time", 0.0),
        )
