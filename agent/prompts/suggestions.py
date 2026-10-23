"""
Stage 7: Suggest real-community test scenarios.

Unlike the sandbox test scenarios (stage 3), these are written for HUMANS to
try out in their actual community so they can see how the policy behaves in
practice. They are plain natural language, independent of the sandbox tests,
and are never executed by the sandbox.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You help community members see a governance policy work in practice. A policy has \
been turned into an automated script that now runs in their real community (e.g. a \
Slack workspace). Your job is to suggest scenarios the members can act out in that \
community to visualise how the policy behaves.

@@CONTEXT_GUIDANCE@@

PROCESS (do both steps):
1. Decide which parts of the policy are worth the community actually seeing work in \
practice. Each part is a distinct behaviour, rule, or situation, e.g. the normal \
flow, a threshold boundary, a timeout, a permission restriction, an attempt to game \
the rule, interactions between simultaneous cases. Favour what members would really \
care about over exhaustive branch coverage. Do not pad the list, and do not skip \
important parts to keep it short.
2. Design scenarios that together cover every part on your list. If the parts are \
independent, use one scenario per part. If several parts can naturally be seen in \
one run, combine them into a single scenario. There is no target number of \
scenarios.

SCENARIO GUIDELINES:
- Written for real people: plain language, concrete steps, no code, no test \
framework terms, no sandbox terms.
- Say who is needed (e.g. "3 regular members and 1 moderator") and what must exist \
beforehand (channel, role), without assuming setup beyond what the policy implies.
- Steps are ordered and name who does what. Include waiting periods where the policy \
has time-based behaviour, and state how long the scenario takes. If it is long, \
suggest a safe way to shorten it only if the policy is clearly configurable that way.
- State the expected outcome and what members should look for in the community.
- Prefer safe actions in a test channel where possible; note any step with real \
consequences (e.g. a message being deleted, a user being removed).
- Vary length: include quick scenarios where possible, and clearly mark slow ones.

Return ONLY valid JSON (no markdown fences, no commentary, no trailing commas) in \
this shape:
{"focus_areas": [{"id": "f1", "title": "short name", "why": "why this is worth \
seeing"}], "scenarios": [{"title": "short name", "summary": "one or two sentences", \
"covers": ["f1"], "participants": "who is needed", "prerequisites": "what must be \
set up, or empty string", "estimated_duration": "e.g. 5 minutes, 24 hours", \
"steps": [{"actor": "who", "action": "what they do"}], "expected_outcome": "what \
should happen", "what_to_look_for": "what to observe in the community"}]}

Every focus area id must appear in the "covers" list of at least one scenario."""

CONTEXT_WITH_SCRIPT = """\
You receive the natural language policy and the final implemented script. Use the \
policy for intent and expected behaviour; use the script to learn the concrete \
details (thresholds, time windows, who is allowed to do what, what messages the \
community will see). If the script resolves something the policy left ambiguous, \
describe what the script does so members know what to expect."""

CONTEXT_POLICY_ONLY = """\
You receive only the natural language policy. Base the scenarios on what the policy \
says. Where the policy leaves a detail unspecified (e.g. an exact threshold or time \
window), do not invent one: describe the expected behaviour in general terms and \
tell members to check how their deployment is configured."""

USER_TEMPLATE_WITH_SCRIPT = """\
## Policy

{policy_text}

## Implemented script

```python
{script}
```

Identify the parts worth visualising, then design scenarios covering them. Return \
ONLY the JSON object."""

USER_TEMPLATE_POLICY_ONLY = """\
## Policy

{policy_text}

Identify the parts worth visualising, then design scenarios covering them. Return \
ONLY the JSON object."""


def format_prompt(policy_text: str, script: str | None = None) -> tuple[str, str]:
    """
    Format the scenario suggestion prompt.

    Args:
        policy_text: Natural language governance policy
        script: Optional final implemented governance script. When omitted,
            scenarios are derived from the policy text alone.

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    if script:
        context = CONTEXT_WITH_SCRIPT
        user_prompt = USER_TEMPLATE_WITH_SCRIPT.format(policy_text=policy_text, script=script)
    else:
        context = CONTEXT_POLICY_ONLY
        user_prompt = USER_TEMPLATE_POLICY_ONLY.format(policy_text=policy_text)
    return (SYSTEM_PROMPT.replace("@@CONTEXT_GUIDANCE@@", context), user_prompt)
