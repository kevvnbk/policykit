"""
Stage 3: Generate test scenarios from headers + policy.

This module contains the prompts for generating test scenarios that
validate governance scripts against their specifications.
"""

import json
from typing import Any

SYSTEM_PROMPT = """\
You are an expert test engineer for governance policy scripts.

Generate test SCENARIOS as a JSON array. You receive ONLY the function headers (not \
the implementation) and the natural language policy — tests must be derived from the \
POLICY SPEC, not implementation details.

REQUIREMENTS:
1. Generate 3-5 scenarios (prefer fewer, focused scenarios over many verbose ones).
2. Each scenario tests ONE specific policy rule or edge case.
3. Keep community_setup MINIMAL — only include users/channels/roles the scenario needs.
4. Keep event data fields minimal — only fields the policy actually checks.
5. Use SHORT string IDs (e.g. "u1", "ch1", "m1") and short names.
6. Return ONLY valid JSON — no markdown fences, no explanation, no trailing commas.
7. IMPORTANT: When testing scheduled handlers (e.g., expiry after N hours), add a buffer.
   If a policy checks expiry every 60 seconds and deadline is 24 hours (86400s),
   advance time to 86461 (deadline + 61) to ensure scheduler runs after deadline.
8. CRITICAL: proposal_id in vote_cast events must match how scripts create proposal IDs.
   Scripts typically use: "proposal_" + message_id (e.g., "proposal_m1").
   Your vote_cast events must use {"proposal_id": "proposal_m1"}, NOT {"proposal_id": "m1"}.
   If unsure, use pattern "proposal_" + message_id to match common implementations.

Scenario JSON schema:
[{"name": "short name", "description": "one line", "community_setup": {"users": \
[{"id": "u1", "name": "A", "roles": ["member"]}], "channels": [{"id": "ch1", \
"name": "general", "members": ["u1"]}], "roles": [{"name": "member", \
"is_base_role": true}]}, "events": [{"type": "message_posted", "data": \
{"message_id": "m1", "text": "hi"}, "actor_id": "u1", "at": 1.0}], \
"assertions": [{"type": "action_taken", "expected": {"action_type": \
"delete_message"}, "description": "deleted"}]}]

Assertion types: action_taken, no_action_taken, action_count, store_equals, \
message_posted, event_count.

CRITICAL ASSERTION GUIDANCE:
- action_taken assertions check EXECUTED actions (status=PASSED, in action log)
- Actions are only executed when ctx.execute_action() is called
- If a vote FAILS or EXPIRES, action stays PROPOSED (not in log) → no_action_taken succeeds
- For "vote posted in channel" / "prompt posted": use message_posted assertion
  (Scripts use ctx.post_message() which creates messages, not just actions)
- For "message deleted": use action_taken with action_type "delete_message"
- For "user notified" / "DM sent": use message_posted with user_id as channel_id
- For "announcement approved and executed": use action_taken with action_type "post_announcement"
- For "announcement rejected/expired": use no_action_taken with action_type "post_announcement"

Return ONLY the JSON array. No markdown. No explanation."""

USER_TEMPLATE = """\
## Policy

{policy_text}

## Headers

{headers}

## API Reference

{api_reference}

Generate 3-5 concise test scenarios as a JSON array. Use short IDs and minimal data. \
Return ONLY valid JSON — no fences, no explanation, no trailing commas."""


DOCUMENT_TEST_GUIDANCE = """

## Testing External Documents

When testing policies with external documents:

1. **Include documents in community_setup**:
   ```json
   {
     "community_setup": {
       "users": [...],
       "channels": [...],
       "documents": {
         "URL": {
           "schema": {
             "source_type": "google_sheets",
             "source_url": "URL",
             "structure": {"columns": ["col1", "col2"]},
             "sample_data": [],
             "metadata": {}
           },
           "initial_data": [
             {"col1": "value1", "col2": "value2"}
           ]
         }
       }
     }
   }
   ```

2. **Use document assertions**:
   - `document_written`: Verify write occurred
   - `document_contains`: Check for specific data
   - `document_row_matches_schema`: Validate column structure
   - `document_row_count`: Verify row count

3. **Example assertions**:
   ```json
   {
     "type": "document_contains",
     "expected": {
       "url": "URL",
       "conditions": {"status": "pending"}
     },
     "description": "Document should contain new row"
   }
   ```
"""


def _format_document_schemas(document_schemas: dict[str, Any] | None) -> str:
    """Format document schemas for test generation prompts."""
    if not document_schemas:
        return ""

    output = "\n\n## External Documents\n\n"
    output += "This policy references the following external documents:\n\n"

    for i, (url, schema) in enumerate(document_schemas.items(), 1):
        title = schema.structure.get('spreadsheet_title', schema.structure.get('title', 'Document'))
        output += f"### Document {i}: {title}\n\n"
        output += f"**Type**: {schema.source_type}\n"
        output += f"**URL**: `{url}`\n\n"

        # Show columns
        columns = schema.structure.get('columns', [])
        if columns:
            output += f"**Columns** ({len(columns)}):\n"
            for col in columns:
                output += f"  - `{col}`\n"
            output += "\n"

        # Show sample data
        if schema.sample_data:
            output += "**Sample Data** (first 3 rows):\n```json\n"
            output += json.dumps(schema.sample_data[:3], indent=2)
            output += "\n```\n\n"

    return output


def format_prompt(
    policy_text: str,
    headers: str,
    api_reference: str,
    document_schemas: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    Format the test generation prompt.

    Args:
        policy_text: Natural language governance policy
        headers: Function headers from stage 1
        api_reference: Sandbox API reference documentation
        document_schemas: Optional document schemas

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = USER_TEMPLATE.format(
        headers=headers,
        policy_text=policy_text,
        api_reference=api_reference,
    )

    # Append document context if present
    if document_schemas:
        document_context = _format_document_schemas(document_schemas)
        user_prompt += document_context + DOCUMENT_TEST_GUIDANCE

    return (SYSTEM_PROMPT, user_prompt)
