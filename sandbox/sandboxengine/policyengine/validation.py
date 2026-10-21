"""
Script validation for the sandbox pipeline.

Implements P0 and P1 recommendations:
- P0.1: Detect generation truncation
- P0.2: Validate completeness before execution
- P0.3: Validate API method usage
- P1.4: Improved revision error context
- P1.5: Regenerate vs patch decision
"""

from __future__ import annotations
import ast
import re
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ValidationErrorType(str, Enum):
    """Categories of validation errors."""
    TRUNCATION = "truncation"
    UNDEFINED_FUNCTION = "undefined_function"
    UNDEFINED_CONSTANT = "undefined_constant"
    INVALID_API_METHOD = "invalid_api_method"
    SYNTAX_ERROR = "syntax_error"
    STRUCTURAL_ERROR = "structural_error"


class ErrorSeverity(str, Enum):
    """Severity levels for validation errors."""
    BLOCKING = "blocking"       # Must fix before execution
    WARNING = "warning"          # Should fix but not blocking


@dataclass
class ValidationError:
    """A single validation error."""
    type: ValidationErrorType
    severity: ErrorSeverity
    message: str
    line: int | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationError":
        return cls(
            type=ValidationErrorType(data["type"]),
            severity=ErrorSeverity(data["severity"]),
            message=data["message"],
            line=data.get("line"),
            context=data.get("context", {}),
        )


@dataclass
class ValidationResult:
    """Result of script validation."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # For additional context

    @property
    def blocking_errors(self) -> list[ValidationError]:
        """Return only blocking errors."""
        return [e for e in self.errors if e.severity == ErrorSeverity.BLOCKING]

    @property
    def has_structural_errors(self) -> bool:
        """Check if errors are structural (require regeneration, not revision)."""
        structural_types = {
            ValidationErrorType.TRUNCATION,
            ValidationErrorType.UNDEFINED_FUNCTION,
            ValidationErrorType.INVALID_API_METHOD,
        }
        return any(e.type in structural_types for e in self.blocking_errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "blocking_count": len(self.blocking_errors),
            "has_structural_errors": self.has_structural_errors,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationResult":
        """Deserialize ValidationResult from dict."""
        return cls(
            is_valid=data["is_valid"],
            errors=[ValidationError.from_dict(e) for e in data.get("errors", [])],
            warnings=[ValidationError.from_dict(w) for w in data.get("warnings", [])],
            metadata=data.get("metadata", {}),
        )


# Known sandbox API methods
ALLOWED_CTX_METHODS = {
    # Event registration
    'on', 'schedule',

    # State management
    'store',

    # Queries
    'get_user', 'get_channel', 'get_channels', 'get_members',

    # Actions
    'emit_action', 'execute_action',

    # Messages
    'post_message',

    # Time
    'current_time',

    # Community integration
    'community',

    # Voting
    'cast_vote', 'start_vote',

    # Proposals
    'votes',
}

ALLOWED_COMMUNITY_METHODS = {
    'post_message',
    'initiate_vote',
    'initiate_advanced_vote',
    'get_users_in_channel',
    'get_conversations',
}

ALLOWED_STORE_METHODS = {
    'get', 'set', 'remove', 'has',
}

ALLOWED_VOTES_METHODS = {
    'get_proposal',
}

# Methods that don't exist but are commonly hallucinated
HALLUCINATED_METHODS = {
    'send_dm',          # Use post_message instead
    'notify_user',      # Use post_message instead
    'create_channel',   # Not available in sandbox
    'archive_channel',  # Not available in sandbox
    'delete_channel',   # Not available in sandbox
    'add_role',         # Not available in sandbox
    'remove_role',      # Not available in sandbox
    'restrict_user',    # Not available in sandbox
    'mute_user',        # Not available in sandbox
}


class ScriptValidator:
    """Validates generated scripts for completeness and API correctness."""

    def validate(self, script: str) -> ValidationResult:
        """
        Run all validation checks on a script.

        Returns ValidationResult with errors and warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # P0.1: Check for truncation
        truncation_errors = self._check_truncation(script)
        errors.extend(truncation_errors)

        # P0.2: Validate completeness
        completeness_errors = self._check_completeness(script)
        errors.extend(completeness_errors)

        # Check for undefined constants
        constant_errors = self._check_undefined_constants(script)
        errors.extend(constant_errors)

        # P0.3: Validate API methods
        api_errors, api_warnings = self._check_api_methods(script)
        errors.extend(api_errors)
        warnings.extend(api_warnings)

        # Basic syntax check
        syntax_errors = self._check_syntax(script)
        errors.extend(syntax_errors)

        is_valid = len([e for e in errors if e.severity == ErrorSeverity.BLOCKING]) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
        )

    def _check_truncation(self, script: str) -> list[ValidationError]:
        """P0.1: Detect if script generation was truncated."""
        errors: list[ValidationError] = []

        # Check for unterminated strings
        single_quotes = script.count("'")
        double_quotes = script.count('"')

        if single_quotes % 2 != 0:
            errors.append(ValidationError(
                type=ValidationErrorType.TRUNCATION,
                severity=ErrorSeverity.BLOCKING,
                message="Script has unterminated single-quoted string (odd number of ' characters)",
                context={"quote_type": "single", "count": single_quotes}
            ))

        if double_quotes % 2 != 0:
            errors.append(ValidationError(
                type=ValidationErrorType.TRUNCATION,
                severity=ErrorSeverity.BLOCKING,
                message="Script has unterminated double-quoted string (odd number of \" characters)",
                context={"quote_type": "double", "count": double_quotes}
            ))

        # Check for unbalanced parentheses
        open_parens = script.count('(')
        close_parens = script.count(')')

        if open_parens != close_parens:
            errors.append(ValidationError(
                type=ValidationErrorType.TRUNCATION,
                severity=ErrorSeverity.BLOCKING,
                message=f"Script has unbalanced parentheses ({open_parens} open, {close_parens} close)",
                context={"open": open_parens, "close": close_parens}
            ))

        # Check if script ends mid-line (no newline at end and last line looks incomplete)
        if script and not script.endswith('\n'):
            last_line = script.split('\n')[-1].strip()
            # Incomplete indicators: ends with operator, comma, open paren, or keyword
            incomplete_endings = ('=', ',', '(', '[', '{', 'and', 'or', 'if', 'def', 'class')
            if any(last_line.endswith(ending) for ending in incomplete_endings):
                errors.append(ValidationError(
                    type=ValidationErrorType.TRUNCATION,
                    severity=ErrorSeverity.BLOCKING,
                    message=f"Script appears to end mid-line: '{last_line}'",
                    context={"last_line": last_line}
                ))

        return errors

    def _check_completeness(self, script: str) -> list[ValidationError]:
        """P0.2: Check that all referenced functions are defined."""
        errors: list[ValidationError] = []

        # Extract function definitions
        defined_funcs = set(re.findall(r'^def (\w+)\(', script, re.MULTILINE))

        # Extract function references in setup()
        setup_match = re.search(r'^def setup\([^)]+\):(.*?)(?=^def |\Z)', script, re.MULTILINE | re.DOTALL)
        if not setup_match:
            errors.append(ValidationError(
                type=ValidationErrorType.STRUCTURAL_ERROR,
                severity=ErrorSeverity.BLOCKING,
                message="No setup() function found in script",
            ))
            return errors

        setup_body = setup_match.group(1)

        # Find handlers registered with ctx.on() and ctx.schedule()
        on_handlers = re.findall(r'ctx\.on\([^,]+,\s*(\w+)', setup_body)
        scheduled_handlers = re.findall(r'ctx\.schedule\([^,]+,\s*(\w+)', setup_body)

        referenced_funcs = set(on_handlers + scheduled_handlers)

        # Find missing functions
        missing_funcs = referenced_funcs - defined_funcs

        for func_name in missing_funcs:
            errors.append(ValidationError(
                type=ValidationErrorType.UNDEFINED_FUNCTION,
                severity=ErrorSeverity.BLOCKING,
                message=f"Function '{func_name}' is referenced in setup() but never defined",
                context={
                    "function": func_name,
                    "defined": list(defined_funcs),
                    "referenced": list(referenced_funcs),
                }
            ))

        return errors

    def _check_undefined_constants(self, script: str) -> list[ValidationError]:
        """Check for uppercase identifiers (constants) that are never defined."""
        errors: list[ValidationError] = []

        # Find all uppercase identifiers used in the script (potential constants)
        # Match: word boundaries, starts with uppercase, has at least one more uppercase or underscore
        used_constants = set(re.findall(r'\b([A-Z][A-Z_0-9]{2,})\b', script))

        # Find defined constants (assignments at module level, before first def)
        # Extract everything before the first function definition
        first_def_match = re.search(r'^def\s+\w+', script, re.MULTILINE)
        if first_def_match:
            header = script[:first_def_match.start()]
        else:
            header = script

        defined = set(re.findall(r'^([A-Z][A-Z_0-9]{2,})\s*=', header, re.MULTILINE))

        # Find imported modules (they might export constants)
        imports = set(re.findall(r'^import (\w+)', script, re.MULTILINE))

        # Framework constants provided by sandbox execution environment
        # These are available in the namespace and don't need to be defined in scripts
        framework_constants = {'YES', 'NO', 'PASSED', 'PROPOSED', 'FAILED'}

        # Filter out known builtins, Python keywords, and framework constants
        builtins = {'True', 'False', 'None'}

        # Find undefined constants (excluding framework constants)
        undefined = used_constants - defined - imports - builtins - framework_constants

        # Report each undefined constant
        for const in sorted(undefined):
            # Find first usage for line number
            pattern = r'\b' + re.escape(const) + r'\b'
            match = re.search(pattern, script)
            line_num = script[:match.start()].count('\n') + 1 if match else None

            errors.append(ValidationError(
                type=ValidationErrorType.UNDEFINED_CONSTANT,
                severity=ErrorSeverity.BLOCKING,
                message=f"Constant '{const}' is used but never defined",
                line=line_num,
                context={
                    "constant": const,
                    "suggestion": f"Add '{const} = <value>' at the top of the script before function definitions"
                }
            ))

        return errors

    def _check_api_methods(self, script: str) -> tuple[list[ValidationError], list[ValidationError]]:
        """P0.3: Validate that only allowed API methods are used."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Find all ctx.method() calls
        ctx_calls = re.findall(r'ctx\.(\w+)\(', script)

        for method in set(ctx_calls):
            if method not in ALLOWED_CTX_METHODS:
                if method in HALLUCINATED_METHODS:
                    # Known hallucination - blocking error with suggestion
                    suggestion = self._get_hallucination_fix(method)
                    errors.append(ValidationError(
                        type=ValidationErrorType.INVALID_API_METHOD,
                        severity=ErrorSeverity.BLOCKING,
                        message=f"ctx.{method}() does not exist. {suggestion}",
                        context={"method": method, "suggestion": suggestion}
                    ))
                else:
                    # Unknown method - warning (might be valid but not in our list)
                    warnings.append(ValidationError(
                        type=ValidationErrorType.INVALID_API_METHOD,
                        severity=ErrorSeverity.WARNING,
                        message=f"ctx.{method}() is not in the known API method list",
                        context={"method": method}
                    ))

        # Find all ctx.community.method() calls
        community_calls = re.findall(r'ctx\.community\.(\w+)\(', script)

        for method in set(community_calls):
            if method not in ALLOWED_COMMUNITY_METHODS:
                errors.append(ValidationError(
                    type=ValidationErrorType.INVALID_API_METHOD,
                    severity=ErrorSeverity.BLOCKING,
                    message=f"ctx.community.{method}() is not a valid community method",
                    context={"method": method, "allowed": list(ALLOWED_COMMUNITY_METHODS)}
                ))

        # Find all ctx.store.method() calls
        store_calls = re.findall(r'ctx\.store\.(\w+)\(', script)

        for method in set(store_calls):
            if method not in ALLOWED_STORE_METHODS:
                errors.append(ValidationError(
                    type=ValidationErrorType.INVALID_API_METHOD,
                    severity=ErrorSeverity.BLOCKING,
                    message=f"ctx.store.{method}() is not a valid store method",
                    context={"method": method, "allowed": list(ALLOWED_STORE_METHODS)}
                ))

        # Find all ctx.votes.method() calls
        votes_calls = re.findall(r'ctx\.votes\.(\w+)\(', script)

        for method in set(votes_calls):
            if method not in ALLOWED_VOTES_METHODS:
                errors.append(ValidationError(
                    type=ValidationErrorType.INVALID_API_METHOD,
                    severity=ErrorSeverity.BLOCKING,
                    message=f"ctx.votes.{method}() is not a valid votes method",
                    context={"method": method, "allowed": list(ALLOWED_VOTES_METHODS)}
                ))

        return errors, warnings

    def _check_syntax(self, script: str) -> list[ValidationError]:
        """Basic Python syntax validation."""
        errors: list[ValidationError] = []

        try:
            ast.parse(script)
        except SyntaxError as e:
            errors.append(ValidationError(
                type=ValidationErrorType.SYNTAX_ERROR,
                severity=ErrorSeverity.BLOCKING,
                message=f"SyntaxError: {e.msg}",
                line=e.lineno,
                context={"text": e.text, "offset": e.offset}
            ))

        return errors

    def _get_hallucination_fix(self, method: str) -> str:
        """Get suggestion for common hallucinated methods."""
        fixes = {
            'send_dm': "Use ctx.post_message(user_id, text) instead",
            'notify_user': "Use ctx.post_message(user_id, text) instead",
            'create_channel': "Channel creation not available in sandbox",
            'archive_channel': "Channel archiving not available in sandbox",
            'delete_channel': "Channel deletion not available in sandbox",
            'add_role': "Role assignment not available in sandbox",
            'remove_role': "Role removal not available in sandbox",
            'restrict_user': "Use ctx.emit_action('kick_conversation', ...) instead",
            'mute_user': "User muting not available in sandbox",
        }
        return fixes.get(method, "Check API reference for correct method")


def build_revision_context(
    validation_result: ValidationResult,
    scenario_errors: str,
) -> str:
    """
    P1.4: Build enriched error context for revision prompt.

    Combines validation errors with scenario execution errors to give
    LLM complete picture of what went wrong.
    """
    parts = []

    # Add validation errors first (these are structural)
    if validation_result.blocking_errors:
        parts.append("STRUCTURAL ERRORS (must fix before script can execute):")
        parts.append("=" * 60)

        for error in validation_result.blocking_errors:
            parts.append(f"\n[{error.type.value.upper()}] {error.message}")

            if error.type == ValidationErrorType.UNDEFINED_FUNCTION:
                ctx = error.context
                parts.append(f"  Referenced in setup() but not defined: {ctx.get('function')}")
                parts.append(f"  Defined functions: {', '.join(ctx.get('defined', []))}")
                parts.append(f"  You need to IMPLEMENT this function, not just reference it.")

            elif error.type == ValidationErrorType.UNDEFINED_CONSTANT:
                ctx = error.context
                const_name = ctx.get('constant', 'UNKNOWN')
                parts.append(f"  Constant used but never defined: {const_name}")
                parts.append(f"  Add at the TOP of the script (before function definitions):")
                parts.append(f"  {const_name} = <extract_value_from_policy>")
                parts.append(f"  Extract the value from the policy text (e.g., timeouts, thresholds, URLs)")

            elif error.type == ValidationErrorType.INVALID_API_METHOD:
                ctx = error.context
                if 'suggestion' in ctx:
                    parts.append(f"  Suggestion: {ctx['suggestion']}")

            elif error.type == ValidationErrorType.TRUNCATION:
                parts.append(f"  The generation was cut off. You need to complete the missing code.")

            parts.append("")

    # Add scenario execution errors
    if scenario_errors:
        if parts:
            parts.append("\n" + "=" * 60)
        parts.append("SCENARIO EXECUTION ERRORS:")
        parts.append("=" * 60)
        parts.append(scenario_errors)

    return "\n".join(parts)


def should_regenerate(validation_result: ValidationResult) -> bool:
    """
    P1.5: Decide whether to regenerate from scratch or attempt revision.

    Regenerate if:
    - Script has structural errors (truncation, missing functions, wrong API)

    Revise if:
    - Only behavioral/logic errors
    - Syntax errors are localized and fixable
    """
    return validation_result.has_structural_errors


def analyze_token_limit_impact(
    script: str,
    tokens_used: int,
    max_tokens: int,
    validation_result: ValidationResult,
) -> dict[str, Any]:
    """
    Analyze if token limit is likely causing validation failures.

    Returns diagnostic information about token usage and suggestions.
    """
    token_usage_pct = (tokens_used / max_tokens) * 100 if max_tokens > 0 else 0
    hit_limit = tokens_used >= max_tokens
    near_limit = token_usage_pct >= 95

    # Count how many functions are defined vs referenced
    defined_count = len(validation_result.blocking_errors[0].context.get("defined", [])) if validation_result.blocking_errors else 0
    referenced_count = len(validation_result.blocking_errors[0].context.get("referenced", [])) if validation_result.blocking_errors else 0
    missing_count = referenced_count - defined_count

    # Estimate if missing functions could fit in remaining tokens
    # Average function is ~200 tokens
    avg_tokens_per_function = 200
    tokens_needed = missing_count * avg_tokens_per_function
    tokens_available = max_tokens - tokens_used

    likely_token_limit_issue = hit_limit and missing_count > 0 and tokens_needed > tokens_available

    analysis = {
        "tokens_used": tokens_used,
        "max_tokens": max_tokens,
        "token_usage_pct": round(token_usage_pct, 1),
        "hit_limit": hit_limit,
        "near_limit": near_limit,
        "missing_function_count": missing_count,
        "defined_function_count": defined_count,
        "estimated_tokens_needed": tokens_needed,
        "tokens_available": tokens_available,
        "likely_token_limit_issue": likely_token_limit_issue,
    }

    # Add suggestions
    if likely_token_limit_issue:
        analysis["suggestion"] = (
            f"Script hit token limit with {missing_count} functions missing. "
            f"Estimated {tokens_needed} tokens needed but only {tokens_available} available. "
            f"Consider: (1) Increasing max_tokens in settings.py, "
            f"(2) Simplifying the policy, or (3) Splitting into multiple policies."
        )
    elif near_limit and not validation_result.is_valid:
        analysis["suggestion"] = (
            f"Script used {token_usage_pct}% of token limit. "
            f"Near-limit usage may have contributed to validation errors."
        )

    return analysis
