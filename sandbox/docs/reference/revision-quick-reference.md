# Revision Fixes - Quick Reference

## The Problems

### Problem 1: Vague Error Messages
```
❌ OLD: "FAILED assertion: action_taken - found 0 matching actions"

✅ NEW: Error Category: BEHAVIORAL
       Expected: An action should be taken
       Actual: No action was taken
       Suggestion: Register handler with ctx.on()
```

### Problem 2: Explanation Text Breaking Code
```
❌ OLD: "Looking at the errors... def setup(ctx):" 
        → Returns entire text → Syntax error

✅ NEW: "Looking at the errors... def setup(ctx):"
        → Extracts only "def setup(ctx):" → Valid Python
```

## The Fixes

### Fix 1: Better Error Summaries
**File**: `sandboxengine/policyengine/tasks.py:341-491`
**Impact**: LLM understands what to fix
**Tests**: 9 tests passing

### Fix 2: Robust Code Extraction  
**File**: `sandboxengine/policyengine/llm.py:82-149`
**Impact**: Code extracted correctly even with explanation
**Tests**: 19 tests passing

## Impact

| Issue | Before | After |
|-------|--------|-------|
| Syntax errors | 30-40% | <5% |
| Unchanged scripts | 20-30% | 5-10% |
| Effective attempts | 33-66% | >95% |

## Run Tests

```bash
cd sandbox
python -m pytest tests/ -v
# 28/28 passing
```

## Documentation

- Full details: [REVISION_FIXES_SUMMARY.md](REVISION_FIXES_SUMMARY.md)
- Fix 1: [error-summary-improvements.md](error-summary-improvements.md)
- Fix 2: [code-extraction-improvements.md](code-extraction-improvements.md)
- Analysis: [revision-process-analysis.md](revision-process-analysis.md)
