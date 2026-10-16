"""
Before/After comparison of error summaries.

Shows how the improvements make error messages clearer and more actionable.
"""
import sys
import os

sandbox_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(sandbox_dir, 'sandboxengine'))

from policyengine.engine import ScenarioResult


def old_error_summary(results):
    """Original error summary format (before improvements)."""
    parts = []
    for r in results:
        if r.passed:
            continue
        parts.append(f"SCENARIO: {r.scenario_name}")
        if r.error:
            parts.append(f"  Error: {r.error}")
        for a in r.assertion_results:
            if not a.get("passed"):
                parts.append(f"  FAILED assertion: {a.get('assertion', '?')} - {a.get('detail', '')}")
        parts.append("")
    return "\n".join(parts)


def new_error_summary(results):
    """New error summary format (after improvements)."""
    from policyengine.tasks import PipelineOrchestrator
    orchestrator = PipelineOrchestrator()
    return orchestrator._build_error_summary_text(results)


def print_comparison(title, results):
    """Print side-by-side comparison."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

    old = old_error_summary(results)
    new = new_error_summary(results)

    print("\nBEFORE (Old Format):")
    print("-" * 80)
    print(old if old else "(no output)")
    print("-" * 80)

    print("\nAFTER (New Format):")
    print("-" * 80)
    print(new if new else "(no output)")
    print("-" * 80)

    # Calculate improvement metrics
    old_lines = len(old.split('\n'))
    new_lines = len(new.split('\n'))
    print(f"\nLines: {old_lines} -> {new_lines} ({new_lines - old_lines:+d})")
    print(f"Characters: {len(old)} -> {len(new)} ({len(new) - len(old):+d})")


def test_comparison_no_actions():
    """Compare when no actions are taken."""
    results = [
        ScenarioResult(
            scenario_name="spam_detection",
            passed=False,
            error=None,
            assertion_results=[
                {"assertion": "action_taken", "passed": False, "detail": "found 0 matching actions"}
            ],
            actions_taken=[],
        ),
    ]

    print_comparison("Test 1: No Actions Taken", results)


def test_comparison_api_error():
    """Compare when API is misused."""
    results = [
        ScenarioResult(
            scenario_name="message_deletion",
            passed=False,
            error="AttributeError: 'PolicyContext' has no attribute 'delete_msg'",
            assertion_results=[],
            actions_taken=[],
        ),
    ]

    print_comparison("Test 2: API Misuse Error", results)


def test_comparison_wrong_action():
    """Compare when wrong action is taken."""
    results = [
        ScenarioResult(
            scenario_name="moderation",
            passed=False,
            error=None,
            assertion_results=[
                {"assertion": "action_taken", "passed": False, "detail": "expected delete_message, got post_message"}
            ],
            actions_taken=[
                {"type": "post_message", "actor": "bot_123", "data": {"text": "Warning!"}},
            ],
        ),
    ]

    print_comparison("Test 3: Wrong Action Taken", results)


def test_comparison_multiple_failures():
    """Compare with multiple failing scenarios."""
    results = [
        ScenarioResult(
            scenario_name="spam_check",
            passed=False,
            error=None,
            assertion_results=[
                {"assertion": "action_taken", "passed": False, "detail": "found 0 matching actions"}
            ],
            actions_taken=[],
        ),
        ScenarioResult(
            scenario_name="valid_message",
            passed=True,
            assertion_results=[],
        ),
        ScenarioResult(
            scenario_name="syntax_error_test",
            passed=False,
            error="SyntaxError: invalid syntax (line 5)",
            assertion_results=[],
        ),
    ]

    print_comparison("Test 4: Multiple Scenarios", results)


def print_summary():
    """Print summary of improvements."""
    print("\n" + "=" * 80)
    print("SUMMARY OF IMPROVEMENTS")
    print("=" * 80)
    print("""
The new error summary format provides:

1. ERROR CATEGORIZATION
   - Before: Generic "Error: ..." or "FAILED assertion: ..."
   - After: Clear category (SYNTAX, API_MISUSE, BEHAVIORAL, etc.)
   - Benefit: LLM immediately knows what type of fix is needed

2. EXPECTED VS ACTUAL
   - Before: "found 0 matching actions"
   - After: "Expected: An action should be taken
            Actual: No action was taken"
   - Benefit: Crystal clear what went wrong

3. ACTIONS TAKEN
   - Before: Not shown
   - After: Lists all actions or "None"
   - Benefit: LLM can see if handlers are triggering

4. SUGGESTED FIX
   - Before: No suggestions
   - After: Context-specific guidance
   - Benefit: LLM has clear direction for fix

5. BETTER FORMATTING
   - Before: Flat list with minimal structure
   - After: Sections with visual separators
   - Benefit: Easier to parse and understand

EXPECTED OUTCOMES:
- Fewer unchanged scripts on revision
- Higher first-attempt fix rate
- Faster convergence to passing tests
- Better debugging experience
""")


if __name__ == "__main__":
    print("=" * 80)
    print("ERROR SUMMARY FORMAT COMPARISON")
    print("=" * 80)
    print("\nThis test shows the difference between old and new error summaries.")
    print("The new format provides more context and actionable guidance.")

    test_comparison_no_actions()
    test_comparison_api_error()
    test_comparison_wrong_action()
    test_comparison_multiple_failures()
    print_summary()

    print("=" * 80)
    print("COMPARISON COMPLETE")
    print("=" * 80)
