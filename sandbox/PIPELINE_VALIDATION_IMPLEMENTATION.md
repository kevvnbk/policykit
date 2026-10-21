# Pipeline Validation Implementation

Implementation of P0 and P1 recommendations to fix script generation failures.

## Problem Analysis

The voting policy pipeline failed with cascading errors:

1. **Revision 1**: `SyntaxError: unterminated string literal (detected at line 293)`
   - Generation truncated mid-string: `is_admin = user and (user.has_role("admin`
   - Functions referenced in `setup()` were never defined: `check_policy_activation_date`, `check_temporary_policy_expiry`

2. **Revision 2**: `NameError: name 'check_policy_activation_date' is not defined`
   - Revision fixed syntax locally but missed missing functions

3. **Revision 3**: `NameError: name 'check_policy_expiry' is not defined`
   - Revision consolidated function names but still didn't implement them

**Root causes:**
- Generation truncation (token limit or early stopping)
- Missing structural validation before execution
- Revision attempting to patch structural incompleteness
- Hallucinated API methods (`ctx.start_vote()` instead of `ctx.community.initiate_vote()`)

## Implementation

### New File: `validation.py`

Comprehensive script validation module implementing:

#### P0.1: Detect Generation Truncation

```python
def _check_truncation(self, script: str) -> list[ValidationError]:
    """Detect if script generation was truncated."""
    # Check unterminated strings (odd number of quotes)
    # Check unbalanced parentheses
    # Check if last line looks incomplete (ends with =, comma, etc.)
```

**Detects:**
- Unterminated single/double-quoted strings
- Unbalanced parentheses, brackets, braces
- Lines ending mid-expression

#### P0.2: Validate Completeness

```python
def _check_completeness(self, script: str) -> list[ValidationError]:
    """Check that all referenced functions are defined."""
    # Extract function definitions
    # Extract function references in setup()
    # Find missing functions
```

**Detects:**
- Functions referenced in `ctx.on()` that don't exist
- Functions referenced in `ctx.schedule()` that don't exist
- Missing `setup()` function

**Example error:**
```
Function 'check_policy_activation_date' is referenced in setup() but never defined
  Defined functions: setup, handle_proposal_submission, handle_vote_cast
  Referenced functions: check_policy_activation_date, check_vote_expiry
  You need to IMPLEMENT this function, not just reference it.
```

#### P0.3: Validate API Methods

```python
def _check_api_methods(self, script: str) -> tuple[list[ValidationError], list[ValidationError]]:
    """Validate that only allowed API methods are used."""
    # Check ctx.method() calls
    # Check ctx.community.method() calls
    # Check ctx.store.method() calls
    # Check ctx.votes.method() calls
```

**Allowed methods:**
- `ctx`: on, schedule, get_user, get_channel, emit_action, execute_action, post_message, etc.
- `ctx.community`: initiate_vote, initiate_advanced_vote, post_message, get_users_in_channel, etc.
- `ctx.store`: get, set, remove, has
- `ctx.votes`: get_proposal

**Hallucinated methods detected:**
- `ctx.send_dm()` → "Use ctx.post_message(user_id, text) instead"
- `ctx.start_vote()` → "Use ctx.community.initiate_vote() instead"
- `ctx.create_channel()` → "Channel creation not available in sandbox"

### P1.4: Improved Revision Error Context

```python
def build_revision_context(
    validation_result: ValidationResult,
    scenario_errors: str,
) -> str:
    """Build enriched error context for revision prompt."""
    # Combine structural validation errors
    # Add scenario execution errors
    # Provide actionable suggestions
```

**Before:**
```
SCENARIO: vote passes and admin approval requested
Error: NameError: name 'check_policy_activation_date' is not defined
```

**After:**
```
STRUCTURAL ERRORS (must fix before script can execute):
============================================================

[UNDEFINED_FUNCTION] Function 'check_policy_activation_date' is referenced in setup() but never defined
  Referenced in setup() but not defined: check_policy_activation_date
  Defined functions: setup, handle_proposal_submission, handle_vote_cast
  You need to IMPLEMENT this function, not just reference it.

[UNDEFINED_FUNCTION] Function 'check_temporary_policy_expiry' is referenced in setup() but never defined
  Referenced in setup() but not defined: check_temporary_policy_expiry
  Defined functions: setup, handle_proposal_submission, handle_vote_cast
  You need to IMPLEMENT this function, not just reference it.

============================================================
SCENARIO EXECUTION ERRORS:
...
```

### P1.5: Regenerate vs Patch Decision

```python
def should_regenerate(validation_result: ValidationResult) -> bool:
    """Decide whether to regenerate from scratch or attempt revision."""
    return validation_result.has_structural_errors
```

**Regenerate when:**
- Truncation detected
- Missing function implementations
- Hallucinated API methods

**Revise when:**
- Only behavioral/logic errors
- Localized syntax errors

**Implementation in pipeline:**
```python
if should_regenerate(validation_result):
    # Structural errors - regenerate script
    script_result = generate_script(run.policy_text, headers)
    revision_type = "regenerate"
else:
    # Behavioral errors - revise existing script
    revision_result = revise_script(run.policy_text, script, enriched_context)
    revision_type = "revise"
```

### Modified Files

#### `tasks.py` Changes

**Stage 2 (Script Generation):**
- Added validation loop with up to 2 generation attempts
- Validates script immediately after generation
- Regenerates if structural errors detected
- Fails stage if validation fails after max attempts

```python
for attempt in range(1, max_generation_attempts + 1):
    script_result = generate_script(run.policy_text, headers)
    script = script_result["script"]
    
    validation_result = validator.validate(script)
    
    if validation_result.is_valid:
        break  # Success!
    
    if attempt == max_generation_attempts:
        # Failed after retries
        self._fail_stage(run, "script", f"Validation failed: {errors}")
        return
    
    # Regenerate on next iteration
```

**Stage 5 (Revision):**
- Validates failed script to detect structural issues
- Decides regenerate vs revise based on error type
- Uses enriched error context for revisions
- Tracks revision type in history

```python
validation_result = validator.validate(script)

if should_regenerate(validation_result):
    # Regenerate instead of revising
    script_result = generate_script(run.policy_text, headers)
    new_script = script_result["script"]
    revision_type = "regenerate"
else:
    # Attempt revision with enriched context
    enriched_context = build_revision_context(validation_result, scenario_errors)
    revision_result = revise_script(run.policy_text, script, enriched_context)
    new_script = revision_result["script"]
    revision_type = "revise"
```

#### `llm.py` Changes

**P0.3: Added Voting API Documentation**

**In SCRIPT_SYSTEM_PROMPT:**
```
CRITICAL: Voting API (CORRECT USAGE)
DO NOT HALLUCINATE VOTING METHODS. Use these EXACT methods:

1. To START a vote:
   ctx.community.initiate_vote(
       proposal=proposal_metadata_dict,
       users=None,
       post_type="channel",
       text="Vote on this proposal",
       channel=channel_id,
       options=["👍", "👎"]
   )

2. To RECORD a vote:
   ctx.cast_vote(proposal_id, event.actor_id, event.data.get("value"))

3. To CHECK results:
   proposal = ctx.votes.get_proposal(proposal_id)
   yes_count = proposal.get_yes_votes()

4. To EXECUTE if passed:
   if yes_count >= threshold:
       ctx.execute_action(proposal.action)

NEVER use: ctx.start_vote(), ctx.initiate_vote(), proposal.execute()
```

**In REVISE_SYSTEM_PROMPT:**
- Added same voting API clarification with error context
- Explicitly flags common mistakes and shows correct replacements

## How This Fixes The Original Failure

### Original Failure Cascade

**Generation → Truncation → Invalid script → Execution fails → Revision fixes syntax only → Still fails on structure → Revision renames missing functions → Still fails**

### New Flow

**Generation → Validation detects truncation/missing functions → Regenerate → Validation passes → Execute**

### Specific Fixes for Voting Policy

1. **Truncation Detection:**
   - Would catch: `is_admin = user and (user.has_role("admin` (unterminated string)
   - Action: Regenerate script

2. **Completeness Validation:**
   - Would catch: `check_policy_activation_date` referenced but not defined
   - Action: Regenerate script (structural error)
   - Error context: "You need to IMPLEMENT this function, not just reference it"

3. **API Method Validation:**
   - Would catch: `ctx.start_vote()` (doesn't exist)
   - Action: Regenerate script
   - Error: "ctx.start_vote() does not exist. Use ctx.community.initiate_vote() instead"

4. **Enriched Revision Context:**
   - Shows all missing functions upfront
   - Explains what needs implementation vs what needs logic fixes
   - Provides correct API usage examples

5. **Regenerate vs Revise:**
   - Missing functions → Regenerate (can't patch a function that's not there)
   - Wrong vote logic → Revise (fix the implementation)

## Testing The Implementation

### Test Case 1: Truncated Script
```python
script = """
def setup(ctx):
    ctx.on('message', handle_message)

def handle_message(event, ctx):
    text = event.data.get('text', "incomplete string
"""

validation = validator.validate(script)
# Expected: TRUNCATION error (unterminated string)
# Action: Regenerate
```

### Test Case 2: Missing Function
```python
script = """
def setup(ctx):
    ctx.on('message', handle_message)
    ctx.schedule(60, check_expiry)  # Not defined!

def handle_message(event, ctx):
    pass
"""

validation = validator.validate(script)
# Expected: UNDEFINED_FUNCTION error
# Action: Regenerate
```

### Test Case 3: Hallucinated API
```python
script = """
def setup(ctx):
    ctx.on('message', handle_message)

def handle_message(event, ctx):
    ctx.start_vote(proposal_id, action)  # Wrong!
"""

validation = validator.validate(script)
# Expected: INVALID_API_METHOD error
# Suggestion: "Use ctx.community.initiate_vote() instead"
# Action: Regenerate
```

### Test Case 4: Behavioral Error (Should Revise, Not Regenerate)
```python
script = """
def setup(ctx):
    ctx.on('message', handle_message)

def handle_message(event, ctx):
    # Logic bug: wrong threshold
    if len(event.data.get('text', '')) > 100:  # Should be > 10
        ctx.emit_action('delete_message', message_id=event.data['message_id'])
"""

validation = validator.validate(script)
# Expected: Valid structure (passes validation)
# Execution: Fails assertions (wrong behavior)
# Action: Revise (not regenerate)
```

## Expected Impact

### Before Implementation
- **Voting policy**: Failed all revisions (0/5 tests)
- **Cause**: Truncation → Structural incompleteness → Revision can't fix
- **Outcome**: Complete failure

### After Implementation
- **Generation**: Catches truncation/missing functions immediately
- **Action**: Regenerates instead of proceeding to failed execution
- **Revision**: Distinguishes structural vs behavioral errors
- **Outcome**: Structural issues fixed before execution attempt

### Success Metrics
- ✅ Detect truncation before execution (not in revision)
- ✅ Catch missing functions before execution (not in revision)
- ✅ Flag hallucinated API methods immediately
- ✅ Regenerate for structural errors (don't attempt revision)
- ✅ Revise only for behavioral/logic errors
- ✅ Provide clear, actionable error messages

## Monitoring & Debugging

### Validation Results in Pipeline Output

```json
{
  "stages": {
    "script": {
      "status": "completed",
      "output": {
        "script": "...",
        "validation": {
          "is_valid": true,
          "errors": [],
          "warnings": [],
          "blocking_count": 0,
          "has_structural_errors": false
        }
      }
    },
    "revise": {
      "output": {
        "attempts": [
          {
            "attempt": 1,
            "revision_type": "regenerate",
            "validation": {
              "is_valid": false,
              "blocking_count": 2,
              "has_structural_errors": true,
              "errors": [
                {
                  "type": "undefined_function",
                  "message": "Function 'check_expiry' is referenced but not defined"
                }
              ]
            }
          }
        ]
      }
    }
  }
}
```

### Log Messages

```
[run_abc123] Script generated (4200 tokens, 8500ms)
[run_abc123] Script validation failed (attempt 1/2)
[run_abc123] Errors: ["Function 'check_policy_expiry' is referenced but not defined"]
[run_abc123] Regenerating script (structural errors detected)
[run_abc123] Script generated and validated successfully (attempt 2)
[run_abc123] Execute stage: 2/5 scenarios passed
[run_abc123] Structural errors detected in revision 1, regenerating script
[run_abc123] Revision 1 (regenerate): 5/5 scenarios passed
```

## Next Steps

### Recommended Follow-ups (Not in Scope)

1. **Increase max_tokens for script generation** - Current limit may be causing truncation
2. **Add token usage warnings** - Flag when generation approaches token limit
3. **Implement progressive generation** - Generate complex scripts in multiple passes
4. **Add API reference inline examples** - Show exact usage patterns in prompts
5. **Track regeneration success rate** - Measure how often regeneration fixes issues

### Configuration Options

Consider adding to `settings.py`:
```python
# Validation settings
MAX_SCRIPT_GENERATION_ATTEMPTS = 2
MAX_REVISION_ATTEMPTS = 3
ENABLE_VALIDATION = True
VALIDATION_STRICTNESS = "blocking"  # or "warning"

# Generation settings
SCRIPT_MAX_TOKENS = 4000  # May need increase
ENABLE_REGENERATE_ON_STRUCTURAL_ERROR = True
```

## Summary

This implementation addresses the root causes of the voting policy failure:

1. **P0.1 Truncation Detection** → Catches incomplete generation before execution
2. **P0.2 Completeness Validation** → Ensures all referenced functions exist
3. **P0.3 API Method Validation** → Prevents hallucinated methods from executing
4. **P1.4 Enriched Error Context** → Gives LLM complete picture for revision
5. **P1.5 Regenerate vs Revise** → Chooses correct fix strategy based on error type

The pipeline now validates scripts structurally before execution and makes intelligent decisions about whether to regenerate or revise, preventing the cascade of failures we saw with the voting policy.
