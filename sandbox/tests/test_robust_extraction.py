"""
Test robust code extraction from LLM outputs with explanation text.
"""
import sys
import os

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, repo_root)

from sandbox.sandboxengine.policyengine.llm import _extract_python_code


def verify_extraction(name, llm_output, should_contain, should_not_contain):
    """Helper to verify extraction results."""
    result = _extract_python_code(llm_output)

    print(f"\n[TEST] {name}")
    print(f"  Input length: {len(llm_output)} chars")
    print(f"  Output length: {len(result)} chars")

    # Check required content
    missing = [item for item in should_contain if item not in result]
    if missing:
        print(f"  [FAIL] Missing required content: {missing}")
        print(f"  Extracted:\n{result[:200]}...")
        return False

    # Check excluded content
    present = [item for item in should_not_contain if item in result]
    if present:
        print(f"  [FAIL] Contains unwanted content: {present}")
        print(f"  Extracted:\n{result[:200]}...")
        return False

    print(f"  [PASS]")
    return True


def test_explanation_before_code_no_fences():
    """The main problematic case from the user's example."""
    llm_output = """Looking at the errors, all scenarios show "Actions Taken: None" which means the handler isn't being triggered.

def setup(ctx):
    ctx.on("message_posted", handle_message_posted)

def handle_message_posted(event, ctx):
    ctx.emit_action("delete_message", message_id=event.data.get("message_id"))"""

    return verify_extraction(
        "Explanation before code (no fences)",
        llm_output,
        should_contain=["def setup", "def handle_message_posted", "ctx.on"],
        should_not_contain=["Looking at", "which means", "handler isn't"]
    )


def test_real_world_complex_explanation():
    """Real example with multiple paragraphs of explanation."""
    llm_output = """Looking at the errors, all scenarios show "Actions Taken: None" which means the `handle_message_posted` function isn't being triggered. The issue is in `setup()` - it registers for `"message_posted"` but the event type might need to match exactly.

Wait, looking more carefully - the setup registers `ctx.on("message_posted", handle_message_posted)` which looks correct. But the scheduled handlers have signatures that might be wrong.

The fix: ensure handlers are properly registered and actions are emitted.

def setup(ctx):
    ctx.on("message_posted", handle_message_posted)
    ctx.on("vote_cast", handle_vote_cast)

def handle_message_posted(event, ctx):
    message_id = event.data.get("message_id")
    ctx.emit_action("delete_message", message_id=message_id)"""

    return verify_extraction(
        "Complex multi-paragraph explanation",
        llm_output,
        should_contain=["def setup", "def handle_message_posted", "ctx.emit_action"],
        should_not_contain=["Looking at", "Wait,", "The fix:"]
    )


def test_explanation_after_code():
    """Explanation text after the code."""
    llm_output = """def setup(ctx):
    ctx.on("message", handler)

def handler(event, ctx):
    ctx.emit_action("delete_message", message_id=event.data["id"])

This fixes the issue by properly registering the event handler and emitting the action."""

    return verify_extraction(
        "Explanation after code",
        llm_output,
        should_contain=["def setup", "def handler", "ctx.emit_action"],
        should_not_contain=["This fixes", "by properly"]
    )


def test_with_markdown_fences():
    """Should still work with markdown fences."""
    llm_output = """Here's the fixed code:

```python
def setup(ctx):
    ctx.on("message", handler)
```"""

    return verify_extraction(
        "With markdown fences",
        llm_output,
        should_contain=["def setup", "ctx.on"],
        should_not_contain=["Here's", "```"]
    )


def test_clean_code_only():
    """Clean code without any explanation."""
    llm_output = """def setup(ctx):
    ctx.on("message", handler)

def handler(event, ctx):
    pass"""

    result = _extract_python_code(llm_output)
    assert "def setup" in result
    assert "def handler" in result
    print("[TEST] Clean code only - [PASS]")
    return True


def test_code_with_comments():
    """Code that includes Python comments should be preserved."""
    llm_output = """def setup(ctx):
    # Register the message handler
    ctx.on("message", handler)

def handler(event, ctx):
    # Check for spam
    if "spam" in event.data.get("text", ""):
        ctx.emit_action("delete_message", message_id=event.data["id"])"""

    result = _extract_python_code(llm_output)
    assert "# Register" in result
    assert "# Check for spam" in result
    print("[TEST] Code with comments - [PASS]")
    return True


def test_explanation_with_code_snippets():
    """Explanation that mentions code fragments but then has the actual code."""
    llm_output = """The issue is that ctx.on is not being called. I need to add ctx.on("message", handler) in the setup function.

def setup(ctx):
    ctx.on("message", handle_message)
    ctx.schedule(300, check_votes)

def handle_message(event, ctx):
    ctx.emit_action("delete_message", message_id=event.data["id"])

def check_votes(event, ctx):
    pass"""

    return verify_extraction(
        "Explanation with code mentions",
        llm_output,
        should_contain=["def setup", "def handle_message", "def check_votes"],
        should_not_contain=["The issue is", "I need to"]
    )


def test_trailing_explanation_sentence():
    """Code followed by a sentence of explanation."""
    llm_output = """def setup(ctx):
    ctx.on("message", handler)

def handler(event, ctx):
    ctx.emit_action("delete_message", message_id=event.data["id"])

Now the handler is properly registered."""

    return verify_extraction(
        "Trailing explanation sentence",
        llm_output,
        should_contain=["def setup", "def handler"],
        should_not_contain=["Now the handler"]
    )


def test_indented_code():
    """Ensure indented code blocks work."""
    llm_output = """def setup(ctx):
    ctx.on("message", handler)

def handler(event, ctx):
    if event.data.get("spam"):
        ctx.emit_action("delete_message", message_id=event.data["id"])
    else:
        pass"""

    result = _extract_python_code(llm_output)
    assert "    if event.data" in result  # Indentation preserved
    assert "    else:" in result
    print("[TEST] Indented code - [PASS]")
    return True


def test_multiple_functions():
    """Multiple function definitions."""
    llm_output = """Here's the complete fixed script:

def setup(ctx):
    ctx.on("message_posted", handle_message)
    ctx.schedule(300, check_pending)

def handle_message(event, ctx):
    ctx.emit_action("delete_message", message_id=event.data["id"])

def check_pending(event, ctx):
    pending = ctx.store.get("pending", [])
    for item in pending:
        process(item, ctx)

def process(item, ctx):
    ctx.emit_action("approve", item_id=item["id"])"""

    return verify_extraction(
        "Multiple functions",
        llm_output,
        should_contain=["def setup", "def handle_message", "def check_pending", "def process"],
        should_not_contain=["Here's the complete"]
    )


if __name__ == "__main__":
    print("=" * 80)
    print("ROBUST CODE EXTRACTION TESTS")
    print("=" * 80)
    print("\nTesting extraction with various explanation text patterns...")

    tests = [
        test_clean_code_only,
        test_code_with_comments,
        test_with_markdown_fences,
        test_explanation_before_code_no_fences,
        test_real_world_complex_explanation,
        test_explanation_after_code,
        test_explanation_with_code_snippets,
        test_trailing_explanation_sentence,
        test_indented_code,
        test_multiple_functions,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            results.append(False)

    print("\n" + "=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All extraction tests passed!")
        print("\nThe improved extraction function now:")
        print("  1. Strips explanation text before code")
        print("  2. Strips explanation text after code")
        print("  3. Handles markdown fences")
        print("  4. Preserves code comments")
        print("  5. Maintains indentation")
        print("  6. Works with multiple functions")
    else:
        print(f"\n[FAILURE] {total - passed} test(s) failed")

    print("=" * 80)
