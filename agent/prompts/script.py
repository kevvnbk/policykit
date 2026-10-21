"""
Stage 2: Generate implementation script from headers + policy.

This module contains the prompts for generating the complete
implementation of a governance script.
"""

import json
from typing import Any

SYSTEM_PROMPT = """\
You are an expert Python developer implementing governance automation scripts.

IMPORTANT: The following modules are PRE-IMPORTED and available without import statements:
- datetime, json, random, math, itertools, string, base64
- Constants: PASSED, PROPOSED, FAILED, YES, NO
DO NOT write "import datetime" or "import random" - they are already available!

STEP 1: EXTRACT AND DEFINE CONSTANTS FIRST
Before writing any functions, scan the policy text and extract ALL numeric values, timeouts, URLs, \
and field lists. Define them as constants at the top of the script.

Extract these types of constants:
- Time periods: "24 hours" → APPROVAL_TIMEOUT_SECONDS = 86400
- Counts: "3 moderators" → REQUIRED_MODERATOR_VOTES = 3
- Days: "30 days" → INACTIVE_THRESHOLD_SECONDS = 2592000
- URLs: From document metadata → CHANNEL_PROPOSALS_URL = "https://..."
- Field lists: From spreadsheet columns → REQUIRED_FIELDS = ["Timestamp", "email", ...]
- Check intervals: For ctx.schedule() → SCHEDULE_INTERVAL_SECONDS = 3600

MANDATORY OUTPUT STRUCTURE:
```python
# NO IMPORTS NEEDED - modules are pre-loaded!

# Constants extracted from policy
CHANNEL_PROPOSALS_URL = "exact_url_from_document_metadata"
REQUIRED_MODERATOR_VOTES = 3  # "3 randomly selected moderators"
APPROVAL_TIMEOUT_SECONDS = 86400  # "24 hours" for approval
REMOVAL_NOTICE_SECONDS = 86400  # "24 hour notice"
INACTIVE_THRESHOLD_SECONDS = 2592000  # "30 days" of inactivity
REQUIRED_FIELDS = ["Timestamp", "email", "proposed channel name", "purpose of channel", "temporary?"]
SCHEDULE_INTERVAL_SECONDS = 3600  # Run checks every hour

def setup(ctx):
    # ... rest of code
```

CRITICAL RULES:
1. DO NOT write import statements - modules are pre-loaded
2. Constants MUST be defined at the top, before ANY functions
3. DO NOT leave blank lines where constants should be - WRITE THE CONSTANTS
4. Extract ALL numbers from the policy text and define them as constants
5. If you skip constants, the script will fail validation
6. Return ONLY Python code - no markdown fences, no explanations

ADDITIONAL REQUIREMENTS:
- Implement ALL functions from the provided headers
- setup() must register handlers via ctx.on() and/or ctx.schedule()
- Event handlers should be SELF-CONTAINED (get data from event.data or proposal.action.data)
- Use ctx.emit_action() for governance actions
- Keep code CONCISE

CRITICAL: Handler signatures
- ALL handlers MUST have signature (event, ctx) — including scheduled handlers
- ctx.schedule(60, my_handler) will call my_handler(event, ctx) where event.type == "__tick__"
- NEVER write def my_scheduled_handler(ctx): — it will crash with "takes 1 argument but 2 given"
- Correct: def check_pending(event, ctx):
- Wrong: def check_pending(ctx):

CRITICAL: Action Execution Model (VERY IMPORTANT - PolicyKit pattern)
- ctx.emit_action() creates PROPOSED actions (NOT executed yet!)
- Actions are NOT added to action log until you call ctx.execute_action()
- When vote PASSES: call ctx.execute_action(proposal.action) to execute
- When vote FAILS or EXPIRES: do NOT execute - action remains proposed only
- Tests checking action_taken will ONLY find executed actions
- Example:
  if proposal.get_yes_votes() >= 2:
      ctx.execute_action(proposal.action)  # NOW it executes!

CRITICAL: Voting workflow
- When handle_vote_cast fires, you MUST call ctx.cast_vote() to register the vote
- Without ctx.cast_vote(), votes are never recorded and thresholds never reached
- Pattern: ctx.cast_vote(proposal_id, event.actor_id, event.data.get("value"))
- THEN check: proposal.get_yes_votes() >= threshold
- THEN execute: ctx.execute_action(proposal.action) if threshold met
- ctx.start_vote() requires GovernableAction (from ctx.emit_action()), NOT a dict

CRITICAL: Messages vs Actions (VERY IMPORTANT)
- ctx.post_message() creates visible messages (checkable by tests, readable by users)
- ctx.emit_action() creates governance actions (logged but not visible as messages)
- To post a vote prompt: use ctx.post_message() so users/tests can see it
- THEN use ctx.emit_action() + ctx.start_vote() for the governance workflow
- Example:
  ctx.post_message(mod_channel_id, "Should we approve this?")
  action = ctx.emit_action("post_announcement", channel_id=ann_id, text=text)
  ctx.start_vote(proposal_id, action)

CRITICAL: User notifications (DMs)
- To send a DM to a user: ctx.post_message(user_id, "message text")
- Pass user_id as the channel_id parameter — this sends a direct message
- NEVER use ctx.emit_action("send_dm", ...) — use ctx.post_message() instead
- Example: ctx.post_message(author_id, "Your proposal expired")

CRITICAL: Channel ID usage
- ctx.get_channel(channel_id) accepts IDs ONLY, NOT names
- Events provide channel_id fields (e.g., "ch-ann") — use these directly
- Compare event.data.get("channel_id") against known IDs
- NEVER assume ctx.get_channel("name") will work — it will return None
- To find channels by name: use ctx.get_channels() to iterate all channels, then store IDs in setup()
- Example: for ch in ctx.get_channels(): if ch.name == "announcements": store_id = ch.id
"""

USER_TEMPLATE = """\
## Function Headers to Implement

```python
{headers}
```

## Governance Policy (Natural Language)

{policy_text}

## Sandbox API Reference

{api_reference}

Implement the complete script. Fill in all function bodies with working governance \
logic.

CRITICAL - READ BEFORE WRITING ANY CODE:
Before you write the first line, scan the policy above and identify ALL of these to define as constants:
- Time periods mentioned ("24 hours", "30 days", etc.) → convert to seconds
- Counts mentioned ("3 moderators", etc.) → extract the number
- URLs from document metadata → copy exact URL
- Field lists from spreadsheet columns → copy exact column names
- Check intervals for ctx.schedule() → typically 3600 (1 hour)

OUTPUT FORMAT (MUST FOLLOW THIS EXACT ORDER):
1. Comment line: # Constants extracted from policy (NO IMPORTS - modules pre-loaded)
2. Blank line
3. ALL constants with values (DO NOT SKIP THIS - YOUR SCRIPT WILL FAIL WITHOUT THEM):
   CHANNEL_PROPOSALS_URL = "https://docs.google.com/..."  # from document metadata
   REQUIRED_MODERATOR_VOTES = 3  # "3 randomly selected moderators"
   APPROVAL_TIMEOUT_SECONDS = 86400  # "24 hours" approval period
   REMOVAL_NOTICE_SECONDS = 86400  # "24 hour notice"
   INACTIVE_THRESHOLD_SECONDS = 2592000  # "30 days" inactivity
   REQUIRED_FIELDS = ["Timestamp", "email", "proposed channel name", ...]
   SCHEDULE_INTERVAL_SECONDS = 3600
4. Blank line
5. def setup(ctx): and all other functions

DO NOT LEAVE BLANK LINES WHERE CONSTANTS SHOULD BE - WRITE THEM!
DO NOT WRITE IMPORT STATEMENTS - modules are pre-loaded!

RULES:
- Pure Python code only, NO markdown fences, NO explanation text
- NO import statements needed (datetime, random, etc. are pre-loaded)
- Constants MUST come at the top before ANY functions
- If you skip constants, validation will fail"""


def _format_document_schemas(document_schemas: dict[str, Any] | None) -> str:
    """
    Format document schemas for injection into prompts.

    Args:
        document_schemas: Dict mapping URLs to DocumentSchema objects

    Returns:
        Formatted string describing available documents
    """
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

        # Show sheet names if available
        sheet_names = schema.structure.get('sheet_names', [])
        if sheet_names and len(sheet_names) > 1:
            output += f"**Sheets**: {', '.join(sheet_names)}\n\n"

    output += "**How to Access Documents in Your Script**:\n\n"
    output += "```python\n"
    output += "# Read all data\n"
    output += 'data = ctx.read_document("URL")\n\n'
    output += "# Query with conditions\n"
    output += 'filtered = ctx.query_document("URL", {"status": "pending", "votes": ">5"})\n\n'
    output += "# Write data (append, replace, or update)\n"
    output += 'ctx.write_document("URL", [\n'
    output += '    {"column1": "value1", "column2": "value2"}\n'
    output += '], mode="append")\n'
    output += "```\n\n"
    output += "**Important**: Column names in your code must match the columns shown above exactly.\n"

    return output


def _generate_url_constants(document_schemas: dict[str, Any] | None) -> str:
    """Generate URL constant definitions for documents."""
    if not document_schemas:
        return ""

    url_constants = "\n\n**Define Document URL Constants**:\n\n"
    url_constants += "At the top of your script, define constants for document URLs:\n\n```python\n"

    for url, schema in document_schemas.items():
        title = schema.structure.get('spreadsheet_title', schema.structure.get('title', 'Document'))
        # Create constant name from title
        const_name = title.upper().replace(' ', '_').replace('-', '_')
        const_name = ''.join(c for c in const_name if c.isalnum() or c == '_')
        const_name += '_URL'
        url_constants += f'{const_name} = "{url}"\n'

    url_constants += "```\n"
    url_constants += "\nThen use these constants throughout your script (e.g., `ctx.read_document(PROPOSALS_URL)`).\n"

    return url_constants


def format_prompt(
    policy_text: str,
    headers: str,
    api_reference: str,
    document_schemas: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    Format the script generation prompt.

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
        url_constants = _generate_url_constants(document_schemas)
        user_prompt += document_context + url_constants

    return (SYSTEM_PROMPT, user_prompt)
