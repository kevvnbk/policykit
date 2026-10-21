"""
Core policy evaluation engine.

PolicyKit equivalent: policyengine/engine.py
Contains: PolicyContext (the API surface scripts interact with),
          Scenario (declarative test format), SandboxRunner (executor).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import (
    Community, GovernableAction, ActionStatus, VoteType,
)
from .handlers import Event, EventBus
from .datasources import DataSourceRegistry, DocumentSchema, InMemoryDataSource
from .scenarios import Scenario, ScenarioEvent, Assertion, ScenarioResult


class PolicyContext:
    """
    The API surface available to generated policy scripts.

    Scripts call ctx.on(), ctx.schedule(), ctx.emit_action(), etc.
    This is what replaces PolicyKit's EvaluationContext.
    """

    def __init__(
        self,
        community: Community,
        event_bus: EventBus,
        data_registry: Optional[DataSourceRegistry] = None
    ):
        self.community = community
        self.store = community.store
        self.votes = community.votes
        self.data = data_registry or DataSourceRegistry()  # External document access
        self._bus = event_bus
        self._action_counter = 0

    @property
    def current_time(self) -> float:
        return self._bus.current_time

    def on(self, event_type: str, handler) -> None:
        self._bus.register(event_type, handler)

    def schedule(self, interval: float, handler, recurring: bool = True) -> None:
        self._bus.schedule(interval, handler, recurring=recurring)

    def emit_action(self, action_type: str, **kwargs) -> GovernableAction:
        """Create a governance action. By default, actions are PROPOSED (not executed).

        Use execute_action() to immediately execute, or pass to start_vote() to execute on approval.
        """
        self._action_counter += 1
        action = GovernableAction(
            id=f"action-{self._action_counter}",
            action_type=action_type,
            actor_id=kwargs.pop("actor_id", "__system__"),
            data=kwargs,
            status=ActionStatus.PROPOSED,  # Actions start as proposed, not executed
            timestamp=self._bus.current_time,
        )
        # Do NOT add to community.actions yet - only when executed
        return action

    def execute_action(self, action: GovernableAction) -> None:
        """Execute a governance action immediately (mark as PASSED and add to log)."""
        action.status = ActionStatus.PASSED
        action.timestamp = self._bus.current_time
        self.community.actions.append(action)
        self._bus.emit(Event(type="action_executed", data={"action": action}), ctx=self)

    def start_vote(self, proposal_id: str, action: GovernableAction) -> None:
        """Start a vote for a proposed action. Action executes only if vote passes."""
        self.votes.create_proposal(proposal_id, action)

    def cast_vote(self, proposal_id: str, voter_id: str, value: Any, vote_type: VoteType = VoteType.BOOLEAN) -> None:
        self.votes.cast_vote(proposal_id, voter_id, value, vote_type)

    def get_user(self, user_id: str):
        return self.community.get_user(user_id)

    def get_channel(self, channel_id: str):
        return self.community.get_channel(channel_id)

    def get_channels(self):
        return self.community.get_channels()

    def get_members(self):
        return self.community.get_members()

    def post_message(self, channel_id: str, text: str, author_id: str = "__system__") -> None:
        msg_id = f"msg-{len(self.community.messages) + 1}"
        self.community.post_message(msg_id, channel_id, author_id, text, self._bus.current_time)

    # External document access methods
    def read_document(
        self,
        source_url: str,
        query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Read data from an external document.

        Parameters
        ----------
        source_url : str
            URL of the document (e.g., Google Sheets URL)
        query : dict, optional
            Query parameters (limit, filter, sheet, offset)

        Returns
        -------
        List[Dict[str, Any]]
            Rows as list of dicts
        """
        source = self.data.get_source(source_url)
        return source.read(query)

    def write_document(
        self,
        source_url: str,
        data: List[Dict[str, Any]],
        mode: str = "append"
    ) -> None:
        """
        Write data to an external document.

        Parameters
        ----------
        source_url : str
            URL of the document
        data : List[Dict[str, Any]]
            Rows to write
        mode : str
            Write mode: "append", "replace", or "update"
        """
        source = self.data.get_source(source_url)
        source.write(data, mode)

    def query_document(
        self,
        source_url: str,
        conditions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Query an external document with filter conditions.

        Parameters
        ----------
        source_url : str
            URL of the document
        conditions : Dict[str, Any]
            Filter conditions (column: value pairs)

        Returns
        -------
        List[Dict[str, Any]]
            Matching rows
        """
        source = self.data.get_source(source_url)
        return source.query(conditions)


class SandboxRunner:
    """Executes a policy script against a scenario."""

    def run(self, script: str, scenario: Scenario) -> ScenarioResult:
        community = self._build_community(scenario.community_setup)
        event_bus = EventBus()

        # Build document registry from scenario
        data_registry = self._build_document_registry(
            scenario.community_setup.get("documents", {})
        )

        ctx = PolicyContext(community, event_bus, data_registry)

        try:
            self._execute_setup(script, ctx)
        except Exception as e:
            return ScenarioResult(
                scenario_name=scenario.name,
                passed=False,
                error=f"Setup failed: {type(e).__name__}: {e}",
            )

        try:
            self._replay_events(scenario.events, event_bus, ctx)
        except Exception as e:
            return ScenarioResult(
                scenario_name=scenario.name,
                passed=False,
                error=f"Event replay failed: {type(e).__name__}: {e}",
            )

        assertion_results = self._check_assertions(
            scenario.assertions, community, event_bus, data_registry
        )
        all_passed = all(r["passed"] for r in assertion_results)

        return ScenarioResult(
            scenario_name=scenario.name,
            passed=all_passed,
            assertion_results=assertion_results,
            actions_taken=[
                {"type": a.action_type, "data": a.data, "actor": a.actor_id}
                for a in community.actions
            ],
            events_emitted=len(event_bus.log),
        )

    def _build_community(self, setup: dict[str, Any]) -> Community:
        community = Community()
        for user in setup.get("users", []):
            community.add_user(user["id"], user.get("name", user["id"]), user.get("roles", []))
        for channel in setup.get("channels", []):
            community.add_channel(channel["id"], channel.get("name", channel["id"]), channel.get("members", []))
        for role in setup.get("roles", []):
            community.add_role(role["name"], role.get("description", ""), role.get("is_base_role", False))
        return community

    def _build_document_registry(self, documents_config: dict[str, Any]) -> DataSourceRegistry:
        """
        Build in-memory document registry from test scenario.

        Format:
        {
          "URL": {
            "schema": {...},
            "initial_data": [...]
          }
        }
        """
        registry = DataSourceRegistry()

        for url, config in documents_config.items():
            schema = DocumentSchema(**config["schema"])
            initial_data = config.get("initial_data", [])

            # Create in-memory mock
            source = InMemoryDataSource(schema, initial_data.copy())
            registry.register_source(url, source)

        return registry

    def _execute_setup(self, script: str, ctx: PolicyContext) -> None:
        # Provide the same modules and constants that PolicyKit's RestrictedPython provides
        # This makes scripts forward-compatible and eliminates the need for import statements
        # Reference: PolicyKit's policyengine/safe_exec_code.py - policykit_builtins
        import datetime
        import json
        import itertools
        import random
        import math
        import string
        import base64

        namespace = {
            # Modules (available without import - matches PolicyKit)
            'datetime': datetime,
            'json': json,
            'itertools': itertools,
            'random': random,
            'math': math,
            'string': string,
            'base64': base64,
            # Framework constants (matches PolicyKit's STATIC_GLOBAL_VARIABLES)
            'PASSED': 'passed',
            'PROPOSED': 'proposed',
            'FAILED': 'failed',
            # Additional vote constants (not in PolicyKit but useful)
            'YES': True,
            'NO': False,
        }
        exec(script, namespace)
        setup_fn = namespace.get("setup")
        if setup_fn is None:
            raise ValueError("Script must define a setup(ctx) function")
        setup_fn(ctx)

    def _replay_events(self, events: list[ScenarioEvent], bus: EventBus, ctx: PolicyContext) -> None:
        for scenario_event in events:
            event = Event(
                type=scenario_event.type,
                data=scenario_event.data,
                actor_id=scenario_event.actor_id,
                timestamp=scenario_event.at,
            )
            # Advance time first - this fires scheduled tasks and __tick__ handlers
            bus.advance_time(scenario_event.at, ctx)

            # Skip emitting explicit __tick__ events since advance_time already handled them
            # This prevents duplicate handler calls for __tick__ events
            if scenario_event.type != "__tick__":
                bus.emit(event, ctx)

    def _check_assertions(
        self,
        assertions: list[Assertion],
        community: Community,
        bus: EventBus,
        data_registry: DataSourceRegistry
    ) -> list[dict[str, Any]]:
        results = []
        for assertion in assertions:
            result = self._evaluate_assertion(assertion, community, bus, data_registry)
            results.append(result)
        return results

    def _evaluate_assertion(
        self,
        assertion: Assertion,
        community: Community,
        bus: EventBus,
        data_registry: DataSourceRegistry
    ) -> dict[str, Any]:
        atype = assertion.type

        if atype == "action_taken":
            action_type = assertion.expected.get("action_type")
            matching = [a for a in community.actions if a.action_type == action_type]
            passed = len(matching) > 0
            return {"assertion": assertion.description or atype, "passed": passed, "detail": f"found {len(matching)} matching actions"}

        if atype == "no_action_taken":
            action_type = assertion.expected.get("action_type")
            matching = [a for a in community.actions if a.action_type == action_type]
            passed = len(matching) == 0
            return {"assertion": assertion.description or atype, "passed": passed, "detail": f"found {len(matching)} matching actions"}

        if atype == "action_count":
            action_type = assertion.expected.get("action_type")
            count = assertion.expected.get("count", 0)
            matching = [a for a in community.actions if a.action_type == action_type]
            passed = len(matching) == count
            return {"assertion": assertion.description or atype, "passed": passed, "detail": f"expected {count}, got {len(matching)}"}

        if atype == "store_equals":
            key = assertion.expected.get("key")
            value = assertion.expected.get("value")
            actual = community.store.get(key)
            passed = actual == value
            return {"assertion": assertion.description or atype, "passed": passed, "detail": f"expected {value!r}, got {actual!r}"}

        if atype == "message_posted":
            channel_id = assertion.expected.get("channel_id")
            contains = assertion.expected.get("contains", "")
            matching = [
                m for m in community.messages.values()
                if (channel_id is None or m.channel_id == channel_id) and contains.lower() in m.text.lower()
            ]
            passed = len(matching) > 0
            detail = f"found {len(matching)} matching messages"
            if channel_id:
                detail += f" in channel {channel_id}"
            return {"assertion": assertion.description or atype, "passed": passed, "detail": detail}

        if atype == "event_count":
            event_type = assertion.expected.get("event_type")
            count = assertion.expected.get("count", 0)
            matching = bus.log.query(event_type=event_type)
            passed = len(matching) == count
            return {"assertion": assertion.description or atype, "passed": passed, "detail": f"expected {count}, got {len(matching)}"}

        # Document-specific assertions
        if atype == "document_written":
            url = assertion.expected.get("url")
            try:
                source = data_registry.get_source(url)
                if isinstance(source, InMemoryDataSource):
                    passed = source.get_write_count() > 0
                    return {
                        "assertion": assertion.description or "Document was written to",
                        "passed": passed,
                        "detail": f"{source.get_write_count()} write(s) performed"
                    }
            except Exception as e:
                return {
                    "assertion": assertion.description or "Document was written to",
                    "passed": False,
                    "detail": f"Error accessing document: {e}"
                }

        if atype == "document_contains":
            url = assertion.expected.get("url")
            conditions = assertion.expected.get("conditions", {})
            try:
                source = data_registry.get_source(url)
                matching = source.query(conditions)
                passed = len(matching) > 0
                return {
                    "assertion": assertion.description or "Document contains matching data",
                    "passed": passed,
                    "detail": f"found {len(matching)} matching row(s)"
                }
            except Exception as e:
                return {
                    "assertion": assertion.description or "Document contains matching data",
                    "passed": False,
                    "detail": f"Error: {e}"
                }

        if atype == "document_row_matches_schema":
            url = assertion.expected.get("url")
            required_columns = assertion.expected.get("required_columns", [])
            try:
                source = data_registry.get_source(url)
                if isinstance(source, InMemoryDataSource):
                    # Check if all written data has required columns
                    all_match = True
                    missing_details = []
                    for write_entry in source.write_log:
                        for row in write_entry["data"]:
                            missing_cols = [col for col in required_columns if col not in row]
                            if missing_cols:
                                all_match = False
                                missing_details.append(f"Row missing: {missing_cols}")

                    return {
                        "assertion": assertion.description or "Written data matches schema",
                        "passed": all_match,
                        "detail": "All rows have required columns" if all_match else "; ".join(missing_details[:3])
                    }
            except Exception as e:
                return {
                    "assertion": assertion.description or "Written data matches schema",
                    "passed": False,
                    "detail": f"Error: {e}"
                }

        if atype == "document_row_count":
            url = assertion.expected.get("url")
            expected_count = assertion.expected.get("count", 0)
            try:
                source = data_registry.get_source(url)
                if isinstance(source, InMemoryDataSource):
                    actual_count = source.get_row_count()
                    passed = actual_count == expected_count
                    return {
                        "assertion": assertion.description or "Document has expected row count",
                        "passed": passed,
                        "detail": f"expected {expected_count}, got {actual_count}"
                    }
            except Exception as e:
                return {
                    "assertion": assertion.description or "Document has expected row count",
                    "passed": False,
                    "detail": f"Error: {e}"
                }

        return {"assertion": assertion.description or atype, "passed": False, "detail": f"unknown assertion type: {atype}"}
