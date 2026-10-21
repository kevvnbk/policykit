"""
Demo test for the new validation module.

Demonstrates how the validation catches issues that caused the voting policy failure.
"""

from sandboxengine.policyengine.validation import (
    ScriptValidator,
    ValidationErrorType,
    build_revision_context,
    should_regenerate,
)


def test_truncation_detection():
    """Test P0.1: Detect truncated scripts."""
    print("\n" + "=" * 60)
    print("TEST 1: Truncation Detection")
    print("=" * 60)

    validator = ScriptValidator()

    # Simulates the original voting policy failure - unterminated string
    truncated_script = '''def setup(ctx):
    ctx.on('message', handle_message)
    ctx.schedule(60, check_expiry)

def handle_message(event, ctx):
    is_admin = user and (user.has_role("admin'''

    result = validator.validate(truncated_script)

    print(f"\nIs valid: {result.is_valid}")
    print(f"Blocking errors: {len(result.blocking_errors)}")
    print(f"Has structural errors: {result.has_structural_errors}")
    print(f"Should regenerate: {should_regenerate(result)}")

    for error in result.blocking_errors:
        print(f"\n  [{error.type.value}] {error.message}")

    assert not result.is_valid, "Should detect truncation"
    assert result.has_structural_errors, "Truncation is structural"
    assert should_regenerate(result), "Should regenerate, not revise"

    print("\n✓ Truncation detected correctly")


def test_missing_functions():
    """Test P0.2: Detect undefined functions."""
    print("\n" + "=" * 60)
    print("TEST 2: Missing Function Detection")
    print("=" * 60)

    validator = ScriptValidator()

    # Simulates revision 2 failure - function referenced but not defined
    incomplete_script = '''def setup(ctx):
    ctx.on('message', handle_message)
    ctx.schedule(60, check_policy_activation_date)
    ctx.schedule(60, check_temporary_policy_expiry)

def handle_message(event, ctx):
    pass'''

    result = validator.validate(incomplete_script)

    print(f"\nIs valid: {result.is_valid}")
    print(f"Blocking errors: {len(result.blocking_errors)}")
    print(f"Should regenerate: {should_regenerate(result)}")

    for error in result.blocking_errors:
        print(f"\n  [{error.type.value}] {error.message}")
        if error.context:
            print(f"    Referenced: {error.context.get('function')}")
            print(f"    Defined: {error.context.get('defined')}")

    assert not result.is_valid, "Should detect missing functions"
    assert result.has_structural_errors, "Missing functions are structural"
    assert len(result.blocking_errors) == 2, "Should find both missing functions"

    print("\n✓ Missing functions detected correctly")


def test_hallucinated_api_methods():
    """Test P0.3: Detect hallucinated API methods."""
    print("\n" + "=" * 60)
    print("TEST 3: Hallucinated API Method Detection")
    print("=" * 60)

    validator = ScriptValidator()

    # Common hallucinations in voting policies
    hallucinated_script = '''def setup(ctx):
    ctx.on('message', handle_message)

def handle_message(event, ctx):
    # Hallucinated method 1
    ctx.start_vote(proposal_id, action)

    # Hallucinated method 2
    ctx.send_dm(user_id, "message")

    # Hallucinated method 3
    ctx.create_channel("new-channel")'''

    result = validator.validate(hallucinated_script)

    print(f"\nIs valid: {result.is_valid}")
    print(f"Blocking errors: {len(result.blocking_errors)}")
    print(f"Should regenerate: {should_regenerate(result)}")

    for error in result.blocking_errors:
        print(f"\n  [{error.type.value}] {error.message}")
        if 'suggestion' in error.context:
            print(f"    Suggestion: {error.context['suggestion']}")

    assert not result.is_valid, "Should detect hallucinated methods"
    assert result.has_structural_errors, "Hallucinated methods are structural"
    assert len(result.blocking_errors) == 3, "Should find all 3 hallucinated methods"

    print("\n✓ Hallucinated methods detected correctly")


def test_behavioral_errors_should_revise():
    """Test P1.5: Behavioral errors should revise, not regenerate."""
    print("\n" + "=" * 60)
    print("TEST 4: Behavioral Errors (Should Revise)")
    print("=" * 60)

    validator = ScriptValidator()

    # Valid structure but wrong logic - should revise, not regenerate
    behavioral_error_script = '''def setup(ctx):
    ctx.on('message', handle_message)

def handle_message(event, ctx):
    # Valid API usage, but wrong threshold (logic bug)
    if len(event.data.get('text', '')) > 100:  # Should be > 10
        ctx.emit_action('delete_message', message_id=event.data['message_id'])
        ctx.execute_action(action)'''

    result = validator.validate(behavioral_error_script)

    print(f"\nIs valid: {result.is_valid}")
    print(f"Blocking errors: {len(result.blocking_errors)}")
    print(f"Has structural errors: {result.has_structural_errors}")
    print(f"Should regenerate: {should_regenerate(result)}")

    assert result.is_valid, "Structure is valid"
    assert not result.has_structural_errors, "No structural issues"
    assert not should_regenerate(result), "Should revise, not regenerate"

    print("\n✓ Correctly identifies behavioral issues as non-structural")


def test_enriched_error_context():
    """Test P1.4: Enriched error context for revisions."""
    print("\n" + "=" * 60)
    print("TEST 5: Enriched Error Context")
    print("=" * 60)

    validator = ScriptValidator()

    incomplete_script = '''def setup(ctx):
    ctx.on('message', handle_message)
    ctx.schedule(60, check_expiry)

def handle_message(event, ctx):
    ctx.start_vote(proposal_id, action)'''

    result = validator.validate(incomplete_script)

    scenario_errors = """SCENARIO: vote passes and admin approval requested
Error: NameError: name 'check_expiry' is not defined"""

    enriched_context = build_revision_context(result, scenario_errors)

    print("\nEnriched error context:")
    print("-" * 60)
    print(enriched_context)
    print("-" * 60)

    assert "STRUCTURAL ERRORS" in enriched_context, "Should have structural errors section"
    assert "check_expiry" in enriched_context, "Should mention missing function"
    assert "IMPLEMENT" in enriched_context, "Should tell LLM to implement, not rename"
    assert "SCENARIO EXECUTION ERRORS" in enriched_context, "Should include scenario errors"
    assert "ctx.start_vote()" in enriched_context or "start_vote" in enriched_context, "Should mention hallucinated method"

    print("\n✓ Enriched context provides complete error picture")


def test_valid_script_passes():
    """Test that a valid script passes validation."""
    print("\n" + "=" * 60)
    print("TEST 6: Valid Script Passes")
    print("=" * 60)

    validator = ScriptValidator()

    valid_script = '''def setup(ctx):
    ctx.on('message', handle_message)
    ctx.schedule(60, check_pending)

def handle_message(event, ctx):
    text = event.data.get('text', '')
    if 'spam' in text.lower():
        action = ctx.emit_action('delete_message', message_id=event.data['message_id'])
        ctx.execute_action(action)
        ctx.post_message(event.actor_id, "Your message was flagged as spam")

def check_pending(event, ctx):
    proposals = ctx.store.get('proposals', {})
    for proposal_id, proposal in proposals.items():
        if proposal.get('status') == 'pending':
            ctx.post_message('mod-log', f"Pending proposal: {proposal_id}")'''

    result = validator.validate(valid_script)

    print(f"\nIs valid: {result.is_valid}")
    print(f"Blocking errors: {len(result.blocking_errors)}")
    print(f"Warnings: {len(result.warnings)}")

    if result.warnings:
        print("\nWarnings (non-blocking):")
        for warning in result.warnings:
            print(f"  [{warning.type.value}] {warning.message}")

    assert result.is_valid, "Valid script should pass"
    assert len(result.blocking_errors) == 0, "No blocking errors"
    assert not should_regenerate(result), "No need to regenerate"

    print("\n✓ Valid script passes all checks")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 80)
    print("VALIDATION MODULE TEST SUITE")
    print("=" * 80)
    print("\nDemonstrating fixes for the voting policy failure cascade\n")

    try:
        test_truncation_detection()
        test_missing_functions()
        test_hallucinated_api_methods()
        test_behavioral_errors_should_revise()
        test_enriched_error_context()
        test_valid_script_passes()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nThe validation module successfully:")
        print("  • Detects truncated scripts (P0.1)")
        print("  • Catches missing function implementations (P0.2)")
        print("  • Identifies hallucinated API methods (P0.3)")
        print("  • Provides enriched error context (P1.4)")
        print("  • Decides regenerate vs revise correctly (P1.5)")
        print("  • Allows valid scripts to pass\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise


if __name__ == "__main__":
    run_all_tests()
