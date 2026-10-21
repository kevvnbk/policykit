# Revision Process Analysis

## Problem Statement

During the revision stage, there are instances where the LLM returns an **unchanged script** even though tests are still failing. This results in:
- Empty diffs (no changes shown)
- Wasted revision attempts
- Failed pipelines even after multiple revision attempts

## Process Flow Investigation

### 1. Current Revision Flow

```
Execute Stage FAILS
  ↓
Revise Stage Starts (max 3 attempts by default)
  ↓
For each revision attempt:
  1. previous_script = script (capture current state)
  2. error_summary = _build_error_summary_text(results)
  3. revision_result = revise_script(policy_text, script, error_summary)
  4. new_script = revision_result["script"]
  5. diff = _compute_diff(previous_script, new_script)
  6. script = new_script
  7. results = _run_scenarios(script, scenarios)
  8. Store attempt data (prompt, diff, results, etc.)
  ↓
If all_passed: SUCCESS
Else: FAILURE after max attempts
```

**Key file**: [`sandboxengine/policyengine/tasks.py:231-273`](sandboxengine/policyengine/tasks.py#L231-L273)

### 2. Revision Function

The `revise_script()` function:

```python
def revise_script(policy_text: str, script: str, error_summary: str) -> dict:
    # Build prompt from template
    user_prompt = REVISE_USER_TEMPLATE.format(
        policy_text=policy_text,
        script=script,
        error_summary=error_summary,
        api_reference=api_ref,
    )
    
    # Call LLM
    result = _call_bedrock(
        system_prompt=REVISE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,  # ← LOW TEMPERATURE
        max_tokens=4000,
    )
    
    # Extract code from response
    fixed_script = _extract_python_code(result["text"])
    
    return {"script": fixed_script, ...}
```

**Key file**: [`sandboxengine/policyengine/llm.py:441-477`](sandboxengine/policyengine/llm.py#L441-L477)

### 3. Code Extraction

The `_extract_python_code()` function correctly handles:
- Code with markdown fences (`\`\`\`python`)
- Code without fences
- Code with explanatory text before/after

**Verified**: Code extraction is NOT the problem.

**Key file**: [`sandboxengine/policyengine/llm.py:82-94`](sandboxengine/policyengine/llm.py#L82-L94)

### 4. Diff Computation

The `_compute_diff()` function uses Python's `difflib.unified_diff()`:
- Returns empty string when scripts are identical
- Returns unified diff when scripts differ

**Verified**: Diff computation is NOT the problem.

**Key file**: [`sandboxengine/policyengine/tasks.py:356-367`](sandboxengine/policyengine/tasks.py#L356-L367)

## Root Cause Analysis

### Confirmed: LLM Returns Unchanged Script

The investigation confirms that the LLM sometimes returns the **exact same script** it received, resulting in:
- `previous_script == new_script`
- Empty diff
- No progress toward fixing the failing tests

### Possible Causes

#### 1. Prompt Issues

**Current System Prompt** ([`llm.py:395-416`](sandboxengine/policyengine/llm.py#L395-L416)):
```
You are an expert Python developer fixing a governance policy script that failed 
its test scenarios.

RULES:
1. Fix ONLY what's broken — don't rewrite the entire script.
2. Pay close attention to the error category:
   - SYNTAX: Fix syntax errors at the indicated line.
   - API_MISUSE: You're calling a method/attribute that doesn't exist. Check the API ref.
   - BEHAVIORAL: The logic is wrong — actions taken don't match assertions.
   - TIMEOUT: Infinite loop or excessive computation.
3. If you need standard library modules (datetime, json, re, etc.), import them at the TOP.
4. Return the COMPLETE fixed script (not a diff).
5. Return ONLY valid Python code. No markdown fences, no explanation.
```

**Potential Issues**:
- Rule #1 ("Fix ONLY what's broken") might be interpreted too conservatively
- Rule #4 ("No markdown fences, no explanation") might suppress helpful reasoning
- Doesn't explicitly say "YOU MUST MAKE CHANGES"

**Current User Prompt** ([`llm.py:418-438`](sandboxengine/policyengine/llm.py#L418-L438)):
```
## Original Policy
{policy_text}

## Current Script (with bugs)
```python
{script}
```

## Error Summary
{error_summary}

## Sandbox API Reference
{api_reference}

Fix the script to pass all scenarios. Return ONLY the complete fixed Python code — 
no fences, no explanation.
```

**Potential Issues**:
- Labels script as "with bugs" but errors might be ambiguous
- Asks for "complete fixed Python code" but might return original if LLM is confused
- No examples of before/after fixes

#### 2. Temperature Too Low

**Current**: `temperature=0.2` in [`llm.py:462`](sandboxengine/policyengine/llm.py#L462)

**Issue**: Very low temperature can cause:
- Repetitive outputs
- Conservative/no changes
- Following the most "obvious" pattern (which might be "return the same code")

**Typical ranges**:
- 0.0-0.3: Highly deterministic (current setting)
- 0.5-0.7: Balanced creativity
- 0.8-1.0: Very creative

For **code revision**, we might want slightly higher temperature (0.3-0.5) to encourage exploration of different fixes.

#### 3. Error Summary Not Clear Enough

The error summary is built by [`_build_error_summary_text()`](sandboxengine/policyengine/tasks.py#L341):

Example error summary structure:
```
SCENARIO: test_spam_detection
  BEHAVIORAL ERROR
  Failed assertions:
    - action_taken: Expected delete_message to be called
```

**Potential Issues**:
- Doesn't show **what actually happened** (only what was expected)
- No indication of **how to fix** the issue
- Missing context about event data or function calls

Better format might be:
```
SCENARIO: test_spam_detection
  BEHAVIORAL ERROR
  
  Expected behavior:
    - delete_message should be called with message ID
  
  Actual behavior:
    - No action was taken
    - handler function was not triggered
  
  Suggested fix:
    - Register event handler with ctx.on('message', handler)
    - Call ctx.delete_message(event.data['id']) in handler
```

#### 4. Insufficient API Context

The API reference is loaded from [`api-reference.md`](sandboxengine/policyengine/api-reference.md) and included in the prompt.

**Potential Issues**:
- API reference might not include **examples** of fixing common errors
- No indication of **common mistakes** and how to avoid them
- Missing **patterns** for event handling, action taking, etc.

#### 5. Retry Without Modified Prompt

Currently, all revision attempts use the **same prompt structure**:
- Attempt 1: policy + buggy_script + errors
- Attempt 2: policy + buggy_script (same!) + errors (possibly same!)
- Attempt 3: (same pattern)

**Issue**: If LLM fails to fix on attempt 1, attempts 2 and 3 will likely also fail because:
- Same input → same output (especially at low temperature)
- No additional context or hints provided
- No indication that this is a retry

**Better approach**:
- Attempt 1: Standard prompt
- Attempt 2: "Previous fix attempt failed. Try a different approach. Errors: ..."
- Attempt 3: "Two attempts failed. Be more aggressive with changes. Consider: ..."

## Recommended Fixes

### Priority 1: Detect and Handle Unchanged Scripts

Add detection for when LLM returns unchanged script:

```python
# In PipelineOrchestrator._run_full_pipeline(), after line 241
new_script = revision_result["script"]

# DETECT UNCHANGED SCRIPT
if new_script.strip() == script.strip():
    logger.warning(f"Revision attempt {attempt}: LLM returned unchanged script")
    
    # Option A: Skip running tests (we know it will fail)
    # Option B: Modify prompt and retry
    # Option C: Increase temperature and retry
    # Option D: Add hint to error summary
```

### Priority 2: Improve Error Summary

Enhance [`_build_error_summary_text()`](sandboxengine/policyengine/tasks.py#L341) to include:
- **What actually happened** (not just what was expected)
- **Suggested fixes** based on error patterns
- **Relevant API methods** that might help

Example:
```python
def _build_error_summary_text(self, results: list[ScenarioResult]) -> str:
    parts = []
    for r in results:
        if not r.passed:
            parts.append(f"SCENARIO: {r.scenario_name}")
            parts.append(f"  {self._categorize_error(r.error)}")
            
            # Add actual vs expected
            parts.append(f"  Expected: {self._format_expected(r)}")
            parts.append(f"  Actual: {self._format_actual(r)}")
            
            # Add suggested fix
            suggestion = self._suggest_fix(r)
            if suggestion:
                parts.append(f"  Suggestion: {suggestion}")
            
            parts.append("")
    
    return "\n".join(parts)
```

### Priority 3: Adjust Temperature Based on Attempt

Increase temperature for subsequent retry attempts:

```python
# In revise_script()
def revise_script(
    policy_text: str,
    script: str,
    error_summary: str,
    attempt_number: int = 1,  # NEW PARAMETER
) -> dict[str, Any]:
    # Increase temperature for retries
    temperature = 0.2 + (attempt_number - 1) * 0.15
    # Attempt 1: 0.2
    # Attempt 2: 0.35
    # Attempt 3: 0.5
    
    result = _call_bedrock(
        system_prompt=REVISE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=min(temperature, 0.7),  # Cap at 0.7
        max_tokens=4000,
    )
    ...
```

### Priority 4: Modify Prompt for Retries

Add context about retry attempts:

```python
# Modify REVISE_USER_TEMPLATE based on attempt
if attempt_number == 1:
    prompt = REVISE_USER_TEMPLATE.format(...)
elif attempt_number == 2:
    prompt = f"""SECOND ATTEMPT: Previous fix didn't work.
    
Try a DIFFERENT approach. The previous attempt may have been too conservative.

{REVISE_USER_TEMPLATE.format(...)}"""
else:
    prompt = f"""FINAL ATTEMPT: Two previous fixes failed.
    
Be AGGRESSIVE with changes. Common issues:
- Event handlers not registered properly
- Wrong event type or data access
- Logic bug in conditionals
- Missing action calls

{REVISE_USER_TEMPLATE.format(...)}"""
```

### Priority 5: Improve System Prompt

Update the system prompt to be more explicit:

```python
REVISE_SYSTEM_PROMPT = """\
You are an expert Python developer fixing a governance policy script that failed 
its test scenarios.

CRITICAL: You MUST make changes to fix the failing tests. Do NOT return the exact 
same script you received — that wastes a revision attempt.

You will receive:
1. The original policy (natural language)
2. The current script (with bugs)
3. Structured error summaries from failed scenarios

Your task is to identify the bugs and fix them.

RULES:
1. Fix what's broken. Don't be afraid to make significant changes if needed.
2. Pay close attention to the error category:
   - SYNTAX: Fix syntax errors at the indicated line.
   - API_MISUSE: You're calling a method/attribute that doesn't exist. Check the API ref.
   - BEHAVIORAL: The logic is wrong — actions taken don't match assertions.
   - TIMEOUT: Infinite loop or excessive computation.
3. Return the COMPLETE fixed script (not a diff).
4. If you're unsure what's wrong, try the most likely fix based on the error type.
5. Common fixes:
   - For "Expected action X": Call ctx.X(...) with appropriate arguments
   - For "Handler not called": Register handler with ctx.on(event_type, handler_fn)
   - For "Wrong data": Check event.data structure and access correct fields
"""
```

## Testing Approach

### Test 1: Verify Unchanged Script Detection

Create test that simulates LLM returning unchanged script and verifies detection.

### Test 2: Verify Temperature Escalation

Mock Bedrock calls and verify temperature increases across attempts.

### Test 3: Verify Prompt Modification

Verify that retry prompts include additional context.

### Test 4: Integration Test

Run full pipeline with intentionally bad initial script and verify:
- Revisions actually change the script
- Diffs are non-empty
- Tests eventually pass

## Metrics to Track

After implementing fixes, track:
1. **Unchanged script rate**: % of revision attempts with empty diff
2. **First-attempt fix rate**: % of revisions fixed on attempt 1
3. **Overall fix rate**: % of failed executions fixed after max revisions
4. **Average attempts to fix**: Mean number of attempts needed

## Related Files

- [`sandboxengine/policyengine/tasks.py`](sandboxengine/policyengine/tasks.py) — Pipeline orchestration
- [`sandboxengine/policyengine/llm.py`](sandboxengine/policyengine/llm.py) — LLM calls and prompts
- [`sandboxengine/policyengine/utils.py`](sandboxengine/policyengine/utils.py) — Error utilities
- [`sandbox/docs/revision-debugging.md`](docs/revision-debugging.md) — Debugging features
- [`test_revision_investigation.py`](../test_revision_investigation.py) — Investigation test

## Next Steps

1. Implement Priority 1 (detect unchanged scripts)
2. Implement Priority 3 (temperature escalation)
3. Run tests to measure improvement
4. Implement Priority 2 and 4 (better error summaries and prompts)
5. Implement Priority 5 (system prompt improvements)
6. Track metrics over time
