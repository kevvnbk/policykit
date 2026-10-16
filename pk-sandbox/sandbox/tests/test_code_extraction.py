"""
Test code extraction from various LLM output formats.

Tests edge cases where LLM includes explanation text before/after code.
"""
import sys
import os

sandbox_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(sandbox_dir, 'sandboxengine'))

from policyengine.llm import _extract_python_code


def test_clean_code():
    """Test extraction of clean code without any extra text."""
    code = """def setup(ctx):
    ctx.on('message', handler)

def handler(event, ctx):
    pass"""

    result = _extract_python_code(code)
    # Content should be preserved (whitespace normalization is OK)
    assert "def setup(ctx):" in result
    assert "def handler(event, ctx):" in result
    assert "ctx.on('message', handler)" in result
    print("[PASS] Clean code extracted correctly")


def test_code_with_markdown_fences():
    """Test extraction from markdown code blocks."""
    llm_output = """```python
def setup(ctx):
    ctx.on('message', handler)
```"""

    result = _extract_python_code(llm_output)
    assert "def setup(ctx):" in result
    assert "```" not in result
    print("[PASS] Markdown fences removed")


def test_explanation_before_code():
    """Test when LLM adds explanation before the code."""
    llm_output = """I've fixed the script by registering the event handler.

```python
def setup(ctx):
    ctx.on('message', handler)
```"""

    result = _extract_python_code(llm_output)
    assert "def setup(ctx):" in result
    assert "fixed the script" not in result
    print("[PASS] Explanation before code removed")


def test_explanation_after_code():
    """Test when LLM adds explanation after the code."""
    llm_output = """```python
def setup(ctx):
    ctx.on('message', handler)
```

This fixes the issue by properly registering the handler."""

    result = _extract_python_code(llm_output)
    assert "def setup(ctx):" in result
    assert "This fixes" not in result
    print("[PASS] Explanation after code removed")


def test_explanation_before_and_after():
    """Test when LLM adds explanation both before and after."""
    llm_output = """Here's the fixed script:

```python
def setup(ctx):
    ctx.on('message', handler)
```

The handler is now properly registered."""

    result = _extract_python_code(llm_output)
    assert "def setup(ctx):" in result
    assert "Here's" not in result
    assert "The handler" not in result
    print("[PASS] Explanations before and after removed")


def test_no_fences_with_explanation():
    """Test when LLM returns code without fences but with explanation.

    This is the problematic case - LLM returns explanation + code without fences.
    """
    llm_output = """I've fixed the script:

def setup(ctx):
    ctx.on('message', handler)

def handler(event, ctx):
    pass"""

    result = _extract_python_code(llm_output)

    print(f"\n[TEST] No fences with explanation:")
    print(f"  Input:\n{llm_output}")
    print(f"\n  Current extraction:\n{result}")

    # Current implementation will include the explanation!
    if "I've fixed" in result:
        print("  [FAIL] Explanation text included - this breaks execution!")
        return False
    else:
        print("  [PASS] Explanation removed")
        return True


def test_explanation_then_code_no_fences():
    """Another variant: explanation paragraph then code."""
    llm_output = """The issue was that the event handler wasn't registered.
I've added the ctx.on() call in the setup function.

def setup(ctx):
    ctx.on('message', handler)

def handler(event, ctx):
    if 'spam' in event.data.get('text', ''):
        ctx.emit_action('delete_message', message_id=event.data['id'])"""

    result = _extract_python_code(llm_output)

    print(f"\n[TEST] Explanation paragraph then code (no fences):")
    print(f"  Current extraction:\n{result[:100]}...")

    if "The issue was" in result:
        print("  [FAIL] Explanation text included!")
        return False
    else:
        print("  [PASS] Explanation removed")
        return True


def test_multiple_code_blocks():
    """Test when LLM includes multiple code blocks."""
    llm_output = """Here are the changes:

Before:
```python
def setup(ctx):
    pass
```

After:
```python
def setup(ctx):
    ctx.on('message', handler)

def handler(event, ctx):
    pass
```"""

    result = _extract_python_code(llm_output)

    print(f"\n[TEST] Multiple code blocks:")
    print(f"  Current extraction:\n{result[:100]}...")

    # Should extract the LAST/COMPLETE code block
    if "def handler" in result and "Before:" not in result:
        print("  [PASS] Extracted complete code block")
        return True
    else:
        print("  [FAIL] Extracted wrong block or included text")
        return False


def test_code_with_comments():
    """Test code that includes comments about the fix."""
    llm_output = """```python
def setup(ctx):
    # Fixed: Register the event handler
    ctx.on('message', handler)

def handler(event, ctx):
    # Check for spam keyword
    if 'spam' in event.data.get('text', ''):
        ctx.emit_action('delete_message', message_id=event.data['id'])
```"""

    result = _extract_python_code(llm_output)
    assert "def setup(ctx):" in result
    assert "# Fixed:" in result  # Comments should be kept!
    assert "```" not in result
    print("[PASS] Code with comments preserved")


if __name__ == "__main__":
    print("=" * 80)
    print("CODE EXTRACTION EDGE CASE TESTS")
    print("=" * 80)
    print()

    # These should pass with current implementation
    test_clean_code()
    test_code_with_markdown_fences()
    test_explanation_before_code()
    test_explanation_after_code()
    test_explanation_before_and_after()
    test_code_with_comments()

    print()
    print("-" * 80)
    print("PROBLEMATIC CASES:")
    print("-" * 80)

    # These reveal the issue
    result1 = test_no_fences_with_explanation()
    result2 = test_explanation_then_code_no_fences()
    result3 = test_multiple_code_blocks()

    print()
    print("=" * 80)

    if result1 and result2 and result3:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED - Extraction needs improvement")
        print("\nThe issue: When LLM returns code WITHOUT fences and includes")
        print("explanation text, the current extraction includes the explanation,")
        print("causing syntax errors during execution.")

    print("=" * 80)
