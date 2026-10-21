# Policy Authoring Guide Documentation

This directory contains comprehensive guidance for writing natural language governance policies for the Slack sandbox.

---

## Documents

### 1. [policy-authoring-guide.md](./policy-authoring-guide.md)
**Comprehensive guide for humans and LLMs**

- **Purpose**: Teach policy authors (human and AI) how to write effective governance policies
- **Audience**: Policy authors, LLM generators, developers
- **Length**: ~500 lines, detailed examples
- **Sections**:
  - Quick Start (good vs. bad examples)
  - For Human Policy Authors (templates, clarity guidelines)
  - For LLM/Agent Policy Generation (extraction checklist, ambiguity handling)
  - Slack Platform Capabilities (supported events, actions, limitations)
  - Common Pitfalls (10+ anti-patterns with fixes)
  - Examples (5 complete good vs. bad policy comparisons)
  - Quality Checklist

### 2. [policy-quick-reference.md](./policy-quick-reference.md)
**At-a-glance reference for experienced users**

- **Purpose**: Quick lookup for supported features, common patterns, checklists
- **Audience**: Policy authors who already understand basics
- **Length**: ~200 lines, table-heavy format
- **Sections**:
  - Supported/unsupported events and actions (tables)
  - Policy template
  - Quality checklist
  - Common pitfalls (comparison table)
  - Message post types
  - Voting patterns
  - Data store patterns
  - Complete example policy

### 3. [api_reference.md](./api_reference.md)
**Technical API specification for generated code**

- **Purpose**: Injected into LLM prompts during code generation
- **Audience**: LLM generators, developers debugging generated code
- **Sections**:
  - Script structure (function registration pattern)
  - PolicyContext API surface
  - Event types and data fields
  - Action types
  - Model objects (User, Channel, Proposal)
  - Test scenario schema
  - Execution constraints (RestrictedPython, no imports)

---

## Usage

### For Human Policy Authors
1. Start with [policy-quick-reference.md](./policy-quick-reference.md) if you know the basics
2. Refer to [policy-authoring-guide.md](./policy-authoring-guide.md) for:
   - First-time policy writing
   - Understanding common mistakes
   - Learning what Slack actions are available
   - Seeing good vs. bad examples

### For LLM/Agent Generation
The LLM prompts in [../sandboxengine/policyengine/llm.py](../sandboxengine/policyengine/llm.py) automatically inject:
- Supported/unsupported events list
- Available actions with reversibility
- Instructions to flag limitations and propose workarounds

When generating policies:
1. Extract triggers, conditions, actions, edge cases, timing from NL input
2. Map to supported Slack events (see quick reference)
3. Use available actions only (see quick reference)
4. Flag unsupported requests with comments and workarounds
5. Follow quality checklist before finalizing

### For Developers
- [api_reference.md](./api_reference.md) — what `ctx` methods are available in generated scripts
- [policy-authoring-guide.md](./policy-authoring-guide.md) — understand policy design constraints
- Check generated code against the supported events/actions tables

---

## Integration Points

### 1. LLM Pipeline
**File**: `sandbox/sandboxengine/policyengine/llm.py`

**Stage 1 (Generate Headers)**: 
- System prompt references policy authoring guidelines
- User prompt includes supported/unsupported events/actions
- Instructs LLM to flag limitations in docstrings

**Stage 2 (Generate Script)**:
- Receives headers + NL policy + API reference
- (Could be enhanced to include quick reference summary)

**Stage 3 (Generate Tests)**:
- Receives headers + NL policy + API reference
- (Could be enhanced to include edge case patterns from guide)

### 2. Documentation Links
**File**: `sandbox/docs/sandbox-plan.md`

Added section linking to policy authoring guide under "Policy Authoring Guide" heading.

### 3. Memory System
**File**: `C:\Users\brian\.claude\projects\c--Users-brian-projects-pkwrapper\memory\MEMORY.md`

Added reference: `reference-policy-guide.md` pointing to these documents.

---

## Future Enhancements

### Potential Additions
1. **Interactive Policy Builder** (UI)
   - Dropdowns for event types
   - Action selector with capability hints
   - Real-time validation against supported features

2. **Policy Examples Library**
   - Categorized by use case (moderation, welcome, naming, voting)
   - Searchable by event type or action type
   - Testable one-click examples

3. **Linter/Validator**
   - Pre-check NL policy before sending to LLM
   - Flag unsupported events/actions immediately
   - Suggest alternatives from quick reference

4. **Agent-Specific Guide**
   - Separate section optimized for LLM consumption
   - Structured extraction prompts
   - JSON schema for policy intent representation

5. **Platform-Specific Guides**
   - When Discord/GitHub/etc. integrations added
   - Per-platform capabilities matrices
   - Cross-platform policy patterns

---

## Maintenance

### When to Update

**Add to quick reference**:
- New Slack API actions integrated
- New event types supported
- New data store patterns identified
- New common pitfalls discovered

**Add to comprehensive guide**:
- New policy examples (especially from user submissions)
- Clarifications on ambiguous sections
- New edge case patterns
- Expanded explanations of limitations

**Update API reference**:
- New `ctx` methods added to PolicyContext
- New action types in sandbox
- Schema changes to test scenarios
- Constraint changes (imports, builtins, etc.)

### Version Control
Documents track "Last updated" date at bottom. Update when making substantive changes (not typo fixes).

---

## Feedback Loop

### From Users
- Collect policies that generate incorrect code → add to pitfalls section
- Collect policies that work well → add to examples section
- Track common misunderstandings → expand guide sections

### From LLM Pipeline
- Monitor revision logs for repeated errors → add to pitfalls
- Track unsupported feature requests → document workarounds
- Analyze ambiguity flags in generated code → improve NL extraction guidance

---

*Created: 2026-07-28*
*Last Updated: 2026-07-28*
