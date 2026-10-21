# Revision Stage Debugging

## Overview

The revision stage now includes comprehensive debugging information to help diagnose why scripts fail and how the LLM attempts to fix them.

## Changes Made

### Backend (`sandboxengine/policyengine/tasks.py`)

Enhanced the revision loop to capture detailed debugging information for each attempt:

1. **Prompt Elements** — The exact inputs sent to the LLM:
   - Original policy text (natural language)
   - Previous script version (before this revision)
   - Structured error summary

2. **Script Diff** — Unified diff showing changes between previous and revised script versions

3. **Failing Scenarios** — Detailed breakdown of which scenarios failed and why:
   - Scenario name
   - Exception error (if script crashed)
   - Failed assertions with details

4. **Metadata** — Token usage and latency per attempt

### Frontend (`frontend/src/App.jsx`)

Added new React components for displaying revision details:

#### `RevisionInspector`
Main component that displays:
- Revision summary (number of attempts, final pass/fail status)
- List of all revision attempts

#### `RevisionAttempt`
Component for each individual revision attempt with collapsible sections:

1. **Prompt Elements** (collapsible)
   - Shows the policy text, previous script, and error summary sent to LLM
   - Helps understand what context the LLM was working with

2. **Script Changes (Diff)** (collapsible)
   - Unified diff view showing exactly what changed
   - Color-coded for additions/deletions
   - Easier than comparing full scripts side-by-side

3. **Failing Scenarios** (collapsible, only shown if attempt failed)
   - Lists each failing scenario
   - Shows exception errors
   - Displays failed assertions with details

4. **Revised Script (Full)** (collapsible)
   - Complete revised script after this attempt
   - Useful for copying/testing

#### `CollapsibleSection`
Reusable component for expandable/collapsible content sections

### Styling (`frontend/src/App.css`)

- Added border-left color coding (green for passed, red for failed)
- Added styles for h5 headings in inspector sections
- Maintained consistent spacing and readability

## How to Use

1. **Run a policy** that will likely fail on first execution
2. **Select the "Revise" stage** in the pipeline
3. **Expand each attempt** to see:
   - What the LLM was told (prompt elements)
   - What it changed (diff)
   - Whether it passed or failed
   - If failed, which scenarios and assertions

## Example Workflow

```
Run pipeline with policy: "Delete messages containing spam"
  ↓
Headers generated → Script generated → Tests generated
  ↓
Execute stage FAILS (script has a bug)
  ↓
Revise stage starts
  ↓
Attempt 1:
  - Prompt shows: original policy + buggy script + error summary
  - Diff shows: added spam detection logic
  - Result: FAILED (2 scenarios still failing)
  ↓
Attempt 2:
  - Prompt shows: original policy + script from attempt 1 + new error summary
  - Diff shows: fixed event handler registration
  - Result: PASSED (all scenarios pass)
  ↓
Pipeline completes successfully
```

## Benefits

### For Debugging
- **See exactly what the LLM received** — no guessing about prompt construction
- **Track changes across attempts** — understand the revision trajectory
- **Identify stuck patterns** — if diff shows minimal changes across attempts, prompt may need adjustment

### For Development
- **Test prompt effectiveness** — see if error summaries are clear enough
- **Validate diff computation** — ensure changes are being tracked correctly
- **Improve error categorization** — see which errors lead to successful fixes

### For Users
- **Understand failures** — transparency into why a policy didn't work
- **Learn from revisions** — see how the system corrects itself
- **Report issues** — can copy exact prompt elements when filing bug reports

## Technical Details

### Diff Computation
Uses Python's `difflib.unified_diff()` to generate standard unified diffs:
- `---` lines show the "before" version
- `+++` lines show the "after" version
- `-` prefix = line removed
- `+` prefix = line added
- ` ` (space) prefix = unchanged context line

### Data Flow
```
PipelineOrchestrator._run_full_pipeline()
  ↓
Stage 5: Revise loop
  ↓
For each attempt:
  1. Capture previous_script before revision
  2. Call revise_script() with error summary
  3. Compute diff (previous → new)
  4. Execute scenarios with new script
  5. Build revision_history entry with all debug info
  6. Append to attempts array
  ↓
Store in run.stages["revise"].output
  ↓
Frontend polls /sandbox/run/{id}/status
  ↓
RevisionInspector renders attempts
```

### Memory Considerations
Each revision attempt stores:
- Policy text (~100-500 chars)
- Previous script (~500-2000 chars)
- Error summary (~200-1000 chars)
- Revised script (~500-2000 chars)
- Diff (~300-1500 chars)
- Failing scenarios (~100-500 chars each)

**Total per attempt: ~2-8 KB**

For 3 attempts (max default): ~6-24 KB total

This is negligible compared to the overall run data and provides significant debugging value.

## Future Enhancements

1. **Syntax highlighting** for diffs (use a library like react-diff-viewer)
2. **Side-by-side diff view** option in addition to unified
3. **Prompt versioning** — save which prompt template version was used
4. **LLM reasoning export** — if using extended thinking models, capture reasoning
5. **Revision replay** — ability to re-run a specific revision attempt with modified inputs
6. **Diff statistics** — lines added/removed, files changed (for multi-file future)
7. **Error pattern detection** — flag common error patterns across runs
8. **Comparison view** — compare revision attempts side-by-side

## Related Files

- `sandbox/sandboxengine/policyengine/tasks.py` — Backend orchestrator with revision logic
- `sandbox/sandboxengine/policyengine/llm.py` — LLM call functions and prompts
- `sandbox/sandboxengine/policyengine/utils.py` — Error classification helpers
- `sandbox/frontend/src/App.jsx` — Frontend components
- `sandbox/frontend/src/App.css` — Styling
- `sandbox/docs/pipeline-implementation.md` — Overall pipeline architecture
