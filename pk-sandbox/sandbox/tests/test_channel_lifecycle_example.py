"""
Test the channel lifecycle management example end-to-end.

This test demonstrates the full pipeline with external document integration.
"""

import json
import pytest
from pathlib import Path

from sandboxengine.policyengine.datasources import DocumentSchema
from sandboxengine.policyengine.engine import (
    PolicyContext,
    Scenario,
    ScenarioEvent,
    Assertion,
    SandboxRunner,
)
from sandboxengine.policyengine.handlers import EventBus
from sandboxengine.policyengine.models import Community


# Load the example API request
EXAMPLE_PATH = Path(__file__).parent.parent / "examples" / "channel_lifecycle_api_request.json"


def load_example_request():
    """Load the channel lifecycle example."""
    with open(EXAMPLE_PATH) as f:
        return json.load(f)


def create_document_schema_from_example(doc_data):
    """Convert API document data to DocumentSchema."""
    return DocumentSchema(
        source_type=doc_data["source_type"],
        source_url=doc_data["source_url"],
        structure=doc_data["structure"],
        sample_data=doc_data["sample_data"],
        metadata=doc_data["metadata"]
    )


def test_example_loads_correctly():
    """Test that the example file loads and has expected structure."""
    data = load_example_request()

    assert "nl_policy" in data
    assert "documents" in data
    assert len(data["documents"]) == 1

    doc = data["documents"][0]
    assert doc["source_type"] == "google_sheets"
    assert doc["source_url"]
    assert "columns" in doc["structure"]
    assert len(doc["structure"]["columns"]) == 7

    # Check columns are correct
    expected_columns = [
        "Timestamp",
        "email",
        "proposed channel name",
        "purpose of channel",
        "temporary?",
        "proposed expiry date",
        "additional comments"
    ]
    assert doc["structure"]["columns"] == expected_columns


def test_document_schema_creation():
    """Test creating DocumentSchema from example data."""
    data = load_example_request()
    doc_data = data["documents"][0]

    schema = create_document_schema_from_example(doc_data)

    assert schema.source_type == "google_sheets"
    assert schema.source_url == doc_data["source_url"]
    assert len(schema.structure["columns"]) == 7
    assert len(schema.sample_data) == 5  # 5 sample rows


def test_policy_context_with_example_document():
    """Test that PolicyContext can access the example document."""
    data = load_example_request()
    doc_data = data["documents"][0]

    # Create document schema
    schema = create_document_schema_from_example(doc_data)

    # Setup context
    community = Community()
    event_bus = EventBus()
    ctx = PolicyContext(community, event_bus)

    # Register document with initial data from example
    from sandboxengine.policyengine.datasources import InMemoryDataSource
    source = InMemoryDataSource(schema, doc_data["sample_data"].copy())
    ctx.data.register_source(doc_data["source_url"], source)

    # Test reading
    proposals = ctx.read_document(doc_data["source_url"])
    assert len(proposals) == 5
    assert proposals[0]["proposed channel name"] == "project-hackathon-2024"

    # Test querying - find temporary proposals
    temp_proposals = ctx.query_document(doc_data["source_url"], {"temporary?": "yes"})
    assert len(temp_proposals) == 4  # 4 out of 5 are temporary

    # Test querying - find non-temporary
    perm_proposals = ctx.query_document(doc_data["source_url"], {"temporary?": "no"})
    assert len(perm_proposals) == 1
    assert perm_proposals[0]["proposed channel name"] == "working-group-ai-policy"

    # Test writing - add new proposal
    ctx.write_document(doc_data["source_url"], [{
        "Timestamp": "2024-03-18 10:00:00",
        "email": "frank@community.org",
        "proposed channel name": "test-channel",
        "purpose of channel": "Testing purposes",
        "temporary?": "yes",
        "proposed expiry date": "2024-04-01",
        "additional comments": "This is a test"
    }], mode="append")

    # Verify it was added
    all_proposals = ctx.read_document(doc_data["source_url"])
    assert len(all_proposals) == 6


def test_simple_proposal_handling_script():
    """Test a simple script that reads proposals from the document."""
    data = load_example_request()
    doc_data = data["documents"][0]

    # Simple script that counts temporary proposals
    script = f"""
PROPOSALS_URL = "{doc_data["source_url"]}"

def setup(ctx):
    ctx.on("check_proposals", handle_check)

def handle_check(event, ctx):
    # Read all proposals
    proposals = ctx.read_document(PROPOSALS_URL)

    # Count temporary ones
    temp_count = len([p for p in proposals if p.get("temporary?") == "yes"])

    # Post result
    ctx.post_message(
        "general",
        f"Found {{temp_count}} temporary channel proposals",
        author_id="__system__"
    )
"""

    # Create scenario
    scenario = Scenario(
        name="count_temporary_proposals",
        description="Test reading proposals and counting temporary ones",
        community_setup={
            "users": [],
            "channels": [{"id": "general", "name": "general"}],
            "documents": {
                doc_data["source_url"]: {
                    "schema": {
                        "source_type": doc_data["source_type"],
                        "source_url": doc_data["source_url"],
                        "structure": doc_data["structure"],
                        "sample_data": doc_data["sample_data"],
                        "metadata": doc_data["metadata"]
                    },
                    "initial_data": doc_data["sample_data"].copy()
                }
            }
        },
        events=[
            ScenarioEvent(
                type="check_proposals",
                data={},
                at=100.0
            )
        ],
        assertions=[
            Assertion(
                type="message_posted",
                expected={
                    "channel_id": "general",
                    "contains": "4 temporary channel proposals"
                },
                description="Should report 4 temporary proposals"
            )
        ]
    )

    # Run the scenario
    runner = SandboxRunner()
    result = runner.run(script, scenario)

    # Check results
    assert result.passed, f"Scenario failed: {result.error}"
    assert len(result.assertion_results) == 1
    assert result.assertion_results[0]["passed"]


def test_filter_malformed_proposals():
    """Test script that filters out malformed proposals."""
    data = load_example_request()
    doc_data = data["documents"][0]

    script = f"""
PROPOSALS_URL = "{doc_data["source_url"]}"

def setup(ctx):
    ctx.on("process_proposals", process)

def process(event, ctx):
    proposals = ctx.read_document(PROPOSALS_URL)

    # Filter malformed (missing required fields)
    valid = []
    malformed_count = 0

    for p in proposals:
        # Check required fields
        if not p.get("proposed channel name") or not p.get("purpose of channel"):
            malformed_count += 1
        else:
            valid.append(p)

    # Store results
    ctx.store.set("valid_proposals", len(valid))
    ctx.store.set("malformed_count", malformed_count)
"""

    # Scenario with some malformed data
    malformed_data = doc_data["sample_data"].copy()
    # Add a malformed row
    malformed_data.append({
        "Timestamp": "2024-03-19 12:00:00",
        "email": "test@example.com",
        "proposed channel name": "",  # Missing!
        "purpose of channel": "",  # Missing!
        "temporary?": "yes",
        "proposed expiry date": "",
        "additional comments": ""
    })

    scenario = Scenario(
        name="filter_malformed",
        description="Test filtering malformed proposals",
        community_setup={
            "users": [],
            "channels": [],
            "documents": {
                doc_data["source_url"]: {
                    "schema": {
                        "source_type": doc_data["source_type"],
                        "source_url": doc_data["source_url"],
                        "structure": doc_data["structure"],
                        "sample_data": [],
                        "metadata": doc_data["metadata"]
                    },
                    "initial_data": malformed_data
                }
            }
        },
        events=[
            ScenarioEvent(type="process_proposals", data={}, at=50.0)
        ],
        assertions=[
            Assertion(
                type="store_equals",
                expected={"key": "valid_proposals", "value": 5},
                description="Should have 5 valid proposals"
            ),
            Assertion(
                type="store_equals",
                expected={"key": "malformed_count", "value": 1},
                description="Should have 1 malformed proposal"
            )
        ]
    )

    runner = SandboxRunner()
    result = runner.run(script, scenario)

    assert result.passed
    assert all(a["passed"] for a in result.assertion_results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
