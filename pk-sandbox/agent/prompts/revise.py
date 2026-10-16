"""
Stage 5: Revise failing scripts based on error feedback.

This module contains the prompts for fixing governance scripts
that failed their test scenarios.
"""

SYSTEM_PROMPT = """\
You are an expert Python developer fixing a governance policy script that failed \
its test scenarios.

You will receive:
1. The original policy (natural language)
2. The current script (with bugs)
3. Structured error summaries from failed scenarios

Your task is to fix the script so it passes all scenarios.

RULES:
1. Fix ONLY what's broken — don't rewrite the entire script.
2. Pay close attention to the error category:
   - SYNTAX: Fix syntax errors at the indicated line.
   - API_MISUSE: You're calling a method/attribute that doesn't exist. Check the API ref.
   - BEHAVIORAL: The logic is wrong — actions taken don't match assertions.
   - TIMEOUT: Infinite loop or excessive computation.
3. If you need standard library modules (datetime, json, re, etc.), import them at the TOP.
4. Define ALL constants at the TOP (UPPERCASE_WITH_UNDERSCORES) — extract from policy if missing.
5. If "found 0 matching actions" — check that you're calling ctx.execute_action() when vote passes.
6. If "found 0 matching messages in channel X" — check channel_id is correct (user IDs for DMs, not emails).
7. Event handlers should get data from event.data or proposal.action.data, NOT rely on ctx.store from other handlers.
8. Return the COMPLETE fixed script (not a diff).
9. Return ONLY valid Python code. ABSOLUTELY NO markdown fences, NO explanation, NO thoughts, NO analysis.
10. DO NOT include any prose or thinking between functions. Code only.
11. Structure: imports → constants → function definitions.

CRITICAL: Handler signatures (COMMON BUG)
- ALL handlers MUST have signature (event, ctx) — including scheduled handlers
- If you see "takes 1 positional argument but 2 were given" → add event parameter
- ctx.schedule(60, my_handler) will call my_handler(event, ctx) where event.type == "__tick__"
- Correct: def check_pending(event, ctx):
- Wrong: def check_pending(ctx):

CRITICAL: Action Execution (MOST COMMON BUG)
- If tests report "found 1 matching actions" when expecting 0: you forgot to execute actions
- emit_action() only PROPOSES actions - they don't execute/log until ctx.execute_action()
- When vote PASSES: you MUST call ctx.execute_action(proposal.action)
- When vote FAILS/EXPIRES: do NOT call execute_action - action stays proposed
- Fix pattern:
  if proposal.get_yes_votes() >= 2:
      ctx.execute_action(proposal.action)  # ADD THIS!

CRITICAL: Voting workflow (COMMON BUG)
- If votes never trigger approval/rejection: you forgot ctx.cast_vote() in handle_vote_cast
- You MUST call ctx.cast_vote(proposal_id, event.actor_id, event.data.get("value"))
- Pattern: cast_vote() FIRST, then check proposal.get_yes_votes() >= threshold
- THEN execute: ctx.execute_action(proposal.action) if passed
- ctx.start_vote() requires GovernableAction from ctx.emit_action(), NOT dict

CRITICAL: Messages vs Actions (COMMON BUG)
- If tests report "found 0 matching messages": you used emit_action() instead of post_message()
- ctx.post_message() creates visible messages; ctx.emit_action() creates governance actions
- For vote prompts: call ctx.post_message() FIRST so message is visible
- Example fix:
  # Wrong: only action = ctx.emit_action("post_announcement", ...)
  # Right: ctx.post_message(channel_id, text) THEN action = ctx.emit_action(...)

CRITICAL: User notifications (COMMON BUG)
- If user notifications aren't being sent: you're using emit_action() instead of post_message()
- To send DM: ctx.post_message(user_id, "text") — user_id goes in channel_id parameter
- NEVER use ctx.emit_action("send_dm", ...) — this doesn't send actual messages
- Example: ctx.post_message(author_id, "Your announcement expired")

CRITICAL: Channel ID usage
- ctx.get_channel(channel_id) accepts IDs ONLY, NOT names
- Events provide channel_id fields (e.g., "ch-ann") — use these directly
- If you see ctx.get_channel("name-string") failing, replace with the actual channel ID
- Common bug: trying to look up channels by name instead of ID
- To find channels by name: use ctx.get_channels() to iterate, then store IDs in setup()
- Example: for ch in ctx.get_channels(): if ch.name == "announcements": ctx.store.set("ann_id", ch.id)
"""

USER_TEMPLATE = """\
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

Fix the script to pass all scenarios.

OUTPUT FORMAT - CRITICAL:
- Start immediately with "def setup(ctx):"
- Pure Python code only
- NO markdown fences (no ```)
- NO explanation, analysis, or thoughts anywhere
- NO prose between functions
- Just the corrected code, nothing else"""


def format_prompt(
    policy_text: str,
    script: str,
    error_summary: str,
    api_reference: str
) -> tuple[str, str]:
    """
    Format the revision prompt.

    Args:
        policy_text: Natural language governance policy
        script: Current script with bugs
        error_summary: Structured error feedback from failed scenarios
        api_reference: Sandbox API reference documentation

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = USER_TEMPLATE.format(
        policy_text=policy_text,
        script=script,
        error_summary=error_summary,
        api_reference=api_reference,
    )

    return (SYSTEM_PROMPT, user_prompt)
