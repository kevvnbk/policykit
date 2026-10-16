"""
Quick test to verify revision debugging output structure.
"""
from sandboxengine.policyengine.tasks import PipelineOrchestrator
from sandboxengine.policyengine.engine import Scenario, ScenarioEvent, Assertion


def test_revision_debug_structure():
    """Verify that revision attempts include debugging information."""
    orchestrator = PipelineOrchestrator(max_revisions=2)

    # Create a simple run
    run = orchestrator.create_run(policy_text="Test policy")

    # Simulate a revision stage output
    mock_revision_output = {
        "attempts": [
            {
                "attempt": 1,
                "passed": False,
                "failures": 2,
                "tokens_used": 1234,
                "latency_ms": 567.8,
                "prompt_elements": {
                    "policy_text": "Delete spam messages",
                    "previous_script": "def setup(ctx): pass",
                    "error_summary": "SCENARIO: test\n  Error: AssertionError",
                },
                "revised_script": "def setup(ctx):\n    ctx.on('message', handle)\ndef handle(e, ctx): pass",
                "diff": "--- previous\n+++ revised\n@@ -1 +1,3 @@\n-def setup(ctx): pass\n+def setup(ctx):\n+    ctx.on('message', handle)\n+def handle(e, ctx): pass",
                "failing_scenarios": [
                    {
                        "name": "spam detection",
                        "error": "AssertionError: Expected action not taken",
                        "failed_assertions": [
                            {"assertion": "action_taken", "detail": "Expected delete_message"},
                        ],
                    }
                ],
            }
        ],
        "final_passed": False,
        "final_script": "def setup(ctx):\n    ctx.on('message', handle)\ndef handle(e, ctx): pass",
        "original_script": "def setup(ctx): pass",
    }

    # Verify structure
    attempt = mock_revision_output["attempts"][0]

    assert "prompt_elements" in attempt, "Missing prompt_elements"
    assert "policy_text" in attempt["prompt_elements"]
    assert "previous_script" in attempt["prompt_elements"]
    assert "error_summary" in attempt["prompt_elements"]

    assert "revised_script" in attempt, "Missing revised_script"
    assert "diff" in attempt, "Missing diff"
    assert "failing_scenarios" in attempt, "Missing failing_scenarios"

    failing = attempt["failing_scenarios"][0]
    assert "name" in failing
    assert "error" in failing
    assert "failed_assertions" in failing
    assert len(failing["failed_assertions"]) > 0

    print("✓ Revision debug structure validated")
    print(f"  - Prompt elements: {list(attempt['prompt_elements'].keys())}")
    print(f"  - Has diff: {bool(attempt['diff'])}")
    print(f"  - Failing scenarios: {len(attempt['failing_scenarios'])}")


if __name__ == "__main__":
    test_revision_debug_structure()
