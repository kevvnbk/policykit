"""
Test improved error summary generation.
"""
import sys
import os

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, repo_root)

from sandbox.sandboxengine.policyengine.tasks import PipelineOrchestrator
from sandbox.sandboxengine.policyengine.engine import ScenarioResult


def test_error_categorization():
    """Test that errors are correctly categorized."""
    orchestrator = PipelineOrchestrator()

    # Test syntax error
    category = orchestrator._categorize_error("SyntaxError: invalid syntax")
    assert category == "SYNTAX", f"Expected SYNTAX, got {category}"
    print("[PASS] Syntax error categorized correctly")

    # Test API misuse
    category = orchestrator._categorize_error("AttributeError: 'PolicyContext' has no attribute 'foo'")
    assert category == "API_MISUSE", f"Expected API_MISUSE, got {category}"
    print("[PASS] AttributeError categorized correctly")

    # Test timeout
    category = orchestrator._categorize_error("TimeoutError: execution exceeded time limit")
    assert category == "TIMEOUT", f"Expected TIMEOUT, got {category}"
    print("[PASS] Timeout categorized correctly")

    # Test behavioral (no error)
    category = orchestrator._categorize_error(None)
    assert category == "BEHAVIORAL", f"Expected BEHAVIORAL, got {category}"
    print("[PASS] No error categorized as BEHAVIORAL")


def test_assertion_detail_parsing():
    """Test that expected vs actual are extracted correctly."""
    orchestrator = PipelineOrchestrator()

    # Test action_taken with 0 matches
    result = ScenarioResult(
        scenario_name="test",
        passed=False,
        assertion_results=[],
        actions_taken=[],
    )
    expected, actual = orchestrator._parse_assertion_detail(
        "action_taken",
        "found 0 matching actions",
        result
    )
    assert "No action was taken" in actual
    print(f"[PASS] Action not taken: expected='{expected}', actual='{actual}'")

    # Test count mismatch
    expected, actual = orchestrator._parse_assertion_detail(
        "action_count",
        "expected 2, got 1",
        result
    )
    # The detail is in actual, just verify it's there
    assert "expected" in expected.lower() or "expected" in actual.lower()
    print(f"[PASS] Count mismatch: expected='{expected}', actual='{actual}'")


def test_fix_suggestions():
    """Test that appropriate fixes are suggested."""
    orchestrator = PipelineOrchestrator()

    # Syntax error suggestion
    result = ScenarioResult(
        scenario_name="test",
        passed=False,
        error="SyntaxError: invalid syntax",
        assertion_results=[],
    )
    suggestion = orchestrator._suggest_fix(result, "SYNTAX")
    assert suggestion is not None
    assert "syntax" in suggestion.lower()
    print(f"[PASS] Syntax suggestion: {suggestion}")

    # API misuse suggestion
    result = ScenarioResult(
        scenario_name="test",
        passed=False,
        error="AttributeError: 'PolicyContext' has no attribute 'delete_msg'",
        assertion_results=[],
    )
    suggestion = orchestrator._suggest_fix(result, "API_MISUSE")
    assert suggestion is not None
    assert "API reference" in suggestion
    print(f"[PASS] API misuse suggestion: {suggestion}")

    # Behavioral - no actions taken
    result = ScenarioResult(
        scenario_name="test",
        passed=False,
        error=None,
        assertion_results=[
            {"assertion": "action_taken", "passed": False, "detail": "found 0 matching actions"}
        ],
        actions_taken=[],
    )
    suggestion = orchestrator._suggest_fix(result, "BEHAVIORAL")
    assert suggestion is not None
    assert "ctx.on()" in suggestion
    assert "ctx.emit_action()" in suggestion
    print(f"[PASS] No action suggestion: {suggestion}")


def test_full_error_summary():
    """Test complete error summary generation."""
    orchestrator = PipelineOrchestrator()

    # Create realistic failure scenarios
    results = [
        ScenarioResult(
            scenario_name="spam_detection",
            passed=False,
            error=None,
            assertion_results=[
                {
                    "assertion": "action_taken",
                    "passed": False,
                    "detail": "found 0 matching actions"
                }
            ],
            actions_taken=[],
        ),
        ScenarioResult(
            scenario_name="valid_message",
            passed=True,
            assertion_results=[],
        ),
        ScenarioResult(
            scenario_name="api_error_scenario",
            passed=False,
            error="AttributeError: 'PolicyContext' has no attribute 'delete_msg'",
            assertion_results=[],
        ),
    ]

    summary = orchestrator._build_error_summary_text(results)

    print("\n" + "=" * 60)
    print("FULL ERROR SUMMARY OUTPUT:")
    print("=" * 60)
    print(summary)
    print("=" * 60)

    # Verify key components are present
    assert "SCENARIO: spam_detection" in summary
    assert "ERROR CATEGORY:" in summary
    assert "Failed Assertions:" in summary
    assert "Expected:" in summary
    assert "Actual:" in summary
    assert "Actions Taken:" in summary
    assert "Suggested Fix:" in summary

    # Should not include passing scenario
    assert "valid_message" not in summary

    # Should include both scenarios
    assert "spam_detection" in summary
    assert "api_error_scenario" in summary

    print("\n[PASS] Full error summary contains all required components")


def test_error_summary_with_actions():
    """Test error summary when actions were taken but wrong."""
    orchestrator = PipelineOrchestrator()

    results = [
        ScenarioResult(
            scenario_name="wrong_action_taken",
            passed=False,
            error=None,
            assertion_results=[
                {
                    "assertion": "action_taken",
                    "passed": False,
                    "detail": "expected delete_message, got post_message"
                }
            ],
            actions_taken=[
                {"type": "post_message", "actor": "user_123", "data": {"text": "hello"}}
            ],
        ),
    ]

    summary = orchestrator._build_error_summary_text(results)

    print("\n" + "=" * 60)
    print("ERROR SUMMARY WITH WRONG ACTION:")
    print("=" * 60)
    print(summary)
    print("=" * 60)

    assert "Actions Taken: 1" in summary
    assert "post_message" in summary
    assert "Suggested Fix:" in summary
    assert "Actions were taken but don't match" in summary

    print("\n[PASS] Error summary with wrong actions formatted correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("ERROR SUMMARY IMPROVEMENT TESTS")
    print("=" * 60)
    print()

    test_error_categorization()
    print()

    test_assertion_detail_parsing()
    print()

    test_fix_suggestions()
    print()

    test_full_error_summary()
    print()

    test_error_summary_with_actions()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print("\nError summaries now include:")
    print("  1. Clear error categorization")
    print("  2. Expected vs Actual comparison")
    print("  3. Actions taken (or not taken)")
    print("  4. Context-specific fix suggestions")
