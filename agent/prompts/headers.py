"""
Stage 1: Generate function headers from natural language policy.

This module contains the prompts for generating function signatures
that define the structure of a governance script.
"""

SYSTEM_PROMPT = """\
You are an expert in governance policy design for online communities.

Your task is to translate a natural language governance policy into a set of Python \
function signatures (headers) that will form the implementation.

IMPORTANT: Follow the policy authoring guidelines for Slack sandbox policies. A good \
policy specifies: triggers (supported events), explicit conditions (boolean, measurable), \
concrete actions (available API calls), edge cases, timing constraints, and state tracking.

RULES:
1. Every script MUST have a `setup(ctx)` function.
2. Additional functions are event handlers or scheduled tasks.
3. Include type hints and a one-line docstring for each function.
4. Function names should clearly reflect their governance purpose.
5. Return ONLY the function signatures — no implementation bodies.
6. Use the sandbox API reference to determine what ctx methods/events are available.
7. If the policy requests unsupported events/actions, add a comment flagging the limitation.

Output format — return ONLY Python code with function stubs (pass bodies):
```python
def setup(ctx):
    \"\"\"Register event handlers and scheduled tasks.\"\"\"
    pass

def handle_event_name(event, ctx):
    \"\"\"One-line description of what this handler does.

    NOTE: If policy has ambiguity or unsupported features, document here.
    \"\"\"
    pass
```
"""

USER_TEMPLATE = """\
## Governance Policy

{policy_text}

## Sandbox API Reference

{api_reference}

## Supported Slack Events (Triggers)
- message (posted): data fields: initiator, text, channel, timestamp
- message (subtype: channel_name): data fields: initiator, channel, name, previous_name
- member_joined_channel: data fields: initiator, inviter, channel, users
- pin_added: data fields: initiator, channel, timestamp

NOT SUPPORTED: reaction_added, reaction_removed, message_edited, message_deleted, \
channel_created, channel_deleted, member_left_channel, file events, thread_created

## Available Actions
- Post message (reversible: delete)
- Delete message (NOT reversible)
- Rename channel (reversible: rename back)
- Invite to channel (reversible: kick)
- Kick from channel (NOT reversible)
- Pin message (reversible: unpin)

Generate Python function headers (signatures + docstrings, pass bodies) for \
implementing this policy. If the policy requests unsupported events or actions, \
add comments flagging the limitation and proposing workarounds. Return ONLY the Python code."""


def format_prompt(policy_text: str, api_reference: str, document_schemas: dict | None = None) -> tuple[str, str]:
    """
    Format the headers generation prompt.

    Args:
        policy_text: Natural language governance policy
        api_reference: Sandbox API reference documentation
        document_schemas: Optional document schemas (currently unused for headers)

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = USER_TEMPLATE.format(
        policy_text=policy_text,
        api_reference=api_reference,
    )

    # Document context could be added here if needed for headers stage
    # Currently headers generation doesn't need document details

    return (SYSTEM_PROMPT, user_prompt)
