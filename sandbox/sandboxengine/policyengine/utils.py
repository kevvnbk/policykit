"""
Utility functions.

Error classification, structured error summaries, API reference loading.
"""

from __future__ import annotations
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    SYNTAX = "syntax"
    API_MISUSE = "api_misuse"
    BEHAVIORAL = "behavioral"
    TIMEOUT = "timeout"
    AMBIGUITY = "ambiguity"


def classify_error(exception: Exception, context: dict[str, Any] | None = None) -> ErrorCategory:
    if isinstance(exception, SyntaxError):
        return ErrorCategory.SYNTAX
    if isinstance(exception, (AttributeError, TypeError)):
        return ErrorCategory.API_MISUSE
    if isinstance(exception, TimeoutError):
        return ErrorCategory.TIMEOUT
    if isinstance(exception, (ValueError, KeyError)):
        return ErrorCategory.API_MISUSE
    return ErrorCategory.BEHAVIORAL


def build_error_summary(
    error: Exception,
    category: ErrorCategory,
    script: str | None = None,
    scenario_name: str | None = None,
) -> dict[str, Any]:
    summary = {
        "category": category.value,
        "error_type": type(error).__name__,
        "message": str(error),
    }
    if scenario_name:
        summary["scenario"] = scenario_name
    if hasattr(error, "lineno") and error.lineno:
        summary["line"] = error.lineno
    if script and category == ErrorCategory.SYNTAX:
        lines = script.splitlines()
        lineno = getattr(error, "lineno", None)
        if lineno and 0 < lineno <= len(lines):
            summary["context_line"] = lines[lineno - 1]
    return summary


def format_revision_prompt(errors: list[dict[str, Any]], script: str) -> str:
    """Build a structured prompt for the LLM revision step."""
    parts = ["The script failed with the following errors:\n"]
    for i, err in enumerate(errors, 1):
        parts.append(f"{i}. [{err['category']}] {err['error_type']}: {err['message']}")
        if "line" in err:
            parts.append(f"   at line {err['line']}")
        if "context_line" in err:
            parts.append(f"   > {err['context_line']}")
        if "scenario" in err:
            parts.append(f"   in scenario: {err['scenario']}")
        parts.append("")
    parts.append("Please fix the script to address these errors.")
    parts.append("Original script:\n```python")
    parts.append(script)
    parts.append("```")
    return "\n".join(parts)
