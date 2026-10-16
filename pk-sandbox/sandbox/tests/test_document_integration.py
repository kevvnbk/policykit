"""
Integration tests for external document support in policy execution.
"""

import pytest
from sandboxengine.policyengine.engine import (
    PolicyContext,
    Scenario,
    ScenarioEvent,
    Assertion,
    SandboxRunner,
)
from sandboxengine.policyengine.datasources import DocumentSchema
from sandboxengine.policyengine.handlers import EventBus
from sandboxengine.policyengine.models import Community


def test_policy_context_with_documents():
    """Test that PolicyContext can access documents."""
    community = Community()
    event_bus = EventBus()

    # Create a context with document access
    ctx = PolicyContext(community, event_bus)

    # Manually register a document
    schema = DocumentSchema(
        source_type="test",
        source_url="test://members",
        structure={"columns": ["name", "role"]},
        sample_data=[],
        metadata={}
    )

    from sandboxengine.policyengine.datasources import InMemoryDataSource
    source = InMemoryDataSource(schema, [
        {"name": "Alice", "role": "admin"},
        {"name": "Bob", "role": "member"}
    ])
    ctx.data.register_source("test://members", source)

    # Test reading
    data = ctx.read_document("test://members")
    assert len(data) == 2
    assert data[0]["name"] == "Alice"

    # Test querying
    admins = ctx.query_document("test://members", {"role": "admin"})
    assert len(admins) == 1
    assert admins[0]["name"] == "Alice"

    # Test writing
    ctx.write_document("test://members", [
        {"name": "Charlie", "role": "member"}
    ], mode="append")

    data = ctx.read_document("test://members")
    assert len(data) == 3


def test_sandbox_runner_with_document_scenario():
    """Test SandboxRunner with a scenario that includes documents."""

    # Script that reads and writes to a document
    script = """
MEMBERS_URL = "test://members"

def setup(ctx):
    ctx.on("member_join", handle_member_join)

def handle_member_join(event, ctx):
    user_id = event.data.get("user_id")
    user_name = event.data.get("user_name")

    # Add to members document
    ctx.write_document(MEMBERS_URL, [{
        "id": user_id,
        "name": user_name,
        "joined_at": ctx.current_time,
        "status": "active"
    }], mode="append")
"""

    # Scenario with document setup
    scenario = Scenario(
        name="member_join_tracking",
        description="Test tracking member joins in a document",
        community_setup={
            "users": [{"id": "alice", "name": "Alice"}],
            "channels": [{"id": "general", "name": "general"}],
            "documents": {
                "test://members": {
                    "schema": {
                        "source_type": "test",
                        "source_url": "test://members",
                        "structure": {"columns": ["id", "name", "joined_at", "status"]},
                        "sample_data": [],
                        "metadata": {}
                    },
                    "initial_data": []
                }
            }
        },
        events=[
            ScenarioEvent(
                type="member_join",
                data={"user_id": "bob", "user_name": "Bob"},
                at=100.0
            )
        ],
        assertions=[
            Assertion(
                type="document_written",
                expected={"url": "test://members"},
                description="Member should be added to document"
            ),
            Assertion(
                type="document_contains",
                expected={
                    "url": "test://members",
                    "conditions": {"id": "bob", "status": "active"}
                },
                description="Document should contain new member"
            ),
            Assertion(
                type="document_row_count",
                expected={"url": "test://members", "count": 1},
                description="Document should have 1 row"
            )
        ]
    )

    # Run the scenario
    runner = SandboxRunner()
    result = runner.run(script, scenario)

    # Check results
    assert result.passed, f"Scenario failed: {result.error}"
    assert len(result.assertion_results) == 3
    assert all(r["passed"] for r in result.assertion_results)


def test_sandbox_runner_document_schema_validation():
    """Test that document writes are validated against schema."""

    script = """
ROSTER_URL = "test://roster"

def setup(ctx):
    ctx.on("add_member", add_to_roster)

def add_to_roster(event, ctx):
    ctx.write_document(ROSTER_URL, [{
        "name": event.data["name"],
        "email": event.data["email"],
        "role": event.data["role"]
    }], mode="append")
"""

    scenario = Scenario(
        name="schema_validation",
        description="Verify written data matches schema",
        community_setup={
            "users": [{"id": "admin"}],
            "channels": [],
            "documents": {
                "test://roster": {
                    "schema": {
                        "source_type": "test",
                        "source_url": "test://roster",
                        "structure": {"columns": ["name", "email", "role"]},
                        "sample_data": [],
                        "metadata": {}
                    },
                    "initial_data": []
                }
            }
        },
        events=[
            ScenarioEvent(
                type="add_member",
                data={"name": "Alice", "email": "alice@example.com", "role": "admin"},
                at=50.0
            )
        ],
        assertions=[
            Assertion(
                type="document_row_matches_schema",
                expected={
                    "url": "test://roster",
                    "required_columns": ["name", "email", "role"]
                },
                description="Written data should match schema"
            )
        ]
    )

    runner = SandboxRunner()
    result = runner.run(script, scenario)

    assert result.passed
    assert result.assertion_results[0]["passed"]


def test_sandbox_runner_document_query_in_policy():
    """Test policy that queries a document."""

    script = """
PROPOSALS_URL = "test://proposals"

def setup(ctx):
    ctx.on("check_pending", report_pending)

def report_pending(event, ctx):
    # Query for pending proposals
    pending = ctx.query_document(PROPOSALS_URL, {"status": "pending"})

    if len(pending) > 0:
        ctx.post_message(
            "general",
            f"There are {len(pending)} pending proposals",
            author_id="__system__"
        )
"""

    scenario = Scenario(
        name="document_query",
        description="Test querying document data",
        community_setup={
            "users": [],
            "channels": [{"id": "general", "name": "general"}],
            "documents": {
                "test://proposals": {
                    "schema": {
                        "source_type": "test",
                        "source_url": "test://proposals",
                        "structure": {"columns": ["id", "title", "status"]},
                        "sample_data": [],
                        "metadata": {}
                    },
                    "initial_data": [
                        {"id": "1", "title": "Proposal 1", "status": "pending"},
                        {"id": "2", "title": "Proposal 2", "status": "approved"},
                        {"id": "3", "title": "Proposal 3", "status": "pending"}
                    ]
                }
            }
        },
        events=[
            ScenarioEvent(
                type="check_pending",
                data={},
                at=100.0
            )
        ],
        assertions=[
            Assertion(
                type="message_posted",
                expected={
                    "channel_id": "general",
                    "contains": "2 pending proposals"
                },
                description="Should report count of pending proposals"
            )
        ]
    )

    runner = SandboxRunner()
    result = runner.run(script, scenario)

    assert result.passed
    assert result.assertion_results[0]["passed"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
