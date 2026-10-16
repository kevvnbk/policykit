# Natural Language Policy Authoring Guide

## Overview

This guide explains how to write effective natural language governance policies for the Slack sandbox. A well-written policy clearly expresses governance intent while respecting the capabilities and constraints of the Slack platform API.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [For Human Policy Authors](#for-human-policy-authors)
3. [For LLM/Agent Policy Generation](#for-llmagent-policy-generation)
4. [Slack Platform Capabilities](#slack-platform-capabilities)
5. [Common Pitfalls and How to Avoid Them](#common-pitfalls-and-how-to-avoid-them)
6. [Examples: Good vs. Bad Policies](#examples-good-vs-bad-policies)

---

## Quick Start

### What Makes a Good Policy?

A good natural language policy:

✅ **Specifies clear triggers** — what events should the policy respond to?
✅ **Defines explicit conditions** — when should actions be taken?
✅ **Lists concrete actions** — what should happen?
✅ **Handles edge cases** — what about corner scenarios?
✅ **Uses available Slack actions only** — respects platform limitations
✅ **Specifies timing constraints** — delays, durations, scheduling windows

### Bad Policy Example
```
"Moderate bad messages."
```
**Problems**: Too vague. What is "bad"? What action should be taken? When?

### Good Policy Example
```
"When a message is posted containing the words 'spam' or 'phishing':
1. Delete the message immediately
2. Send a DM to the user who posted it with a warning
3. Log the incident to a 'moderation-log' channel
4. If the same user posts 3+ flagged messages within 24 hours, kick them from the channel"
```
**Why it's good**: Clear trigger, specific conditions, concrete actions, edge case handling, uses available Slack capabilities.

---

## For Human Policy Authors

### Structure Your Policy

Use this template:

```
TRIGGER: [When does this policy activate?]
CONDITIONS: [What conditions must be true?]
ACTIONS: [What should happen?]
EDGE CASES: [What about special scenarios?]
TIMING: [Any delays, expirations, or schedules?]
```

### Example: Channel Naming Policy

```
TRIGGER: When a channel is renamed

CONDITIONS: 
- The new name does not start with "team-" or "project-"
- The user who renamed it is not an admin

ACTIONS:
1. Rename the channel back to its previous name
2. Post an ephemeral message to the user explaining the naming convention
3. Post a notification in the "mod-log" channel

EDGE CASES:
- If an admin renames a channel, allow it unconditionally
- If the channel name is being corrected from a previous violation, allow it

TIMING:
- Reversion should happen immediately (within the event handler)
```

### Specify Users, Channels, and Roles Clearly

❌ **Vague**: "notify moderators"
✅ **Specific**: "send a DM to users with the 'moderator' role"

❌ **Vague**: "post to the log"
✅ **Specific**: "post a message to the '#mod-log' channel"

### State Your Intent for Voting/Proposals

If your policy involves community voting, be explicit:

✅ "Start a vote in #general with 👍/👎 reactions. If 5+ votes and >60% are 👍 within 24 hours, approve. Otherwise, reject."

❌ "Let the community vote on it."

### Describe Data Persistence Needs

If your policy needs to remember things between events:

✅ "Track the count of warnings per user in the data store. Reset the count after 7 days of no violations."

❌ "Remember who has been warned." (How long? What data structure?)

---

## For LLM/Agent Policy Generation

### Input Format

When generating code from natural language, you will receive policies in freeform text. Your job is to:

1. **Extract the structured intent** (triggers, conditions, actions, edge cases, timing)
2. **Map to available Slack API actions** (see [Slack Platform Capabilities](#slack-platform-capabilities))
3. **Generate function headers first** (Step 1 of pipeline) before implementation
4. **Generate test scenarios independently** (Step 3) from headers, not from implementation

### Pipeline Context

You are part of a 6-stage pipeline:

```
[1] Generate Headers → [2] Generate Script → [3] Generate Tests → [4] Execute → [5] Revise → [6] Report
```

**Key constraint**: Steps 2 (script) and 3 (tests) both receive the headers from Step 1 but **never see each other's output**. This prevents bias where tests match implementation instead of specification.

### Extraction Checklist

For each policy, identify:

- [ ] **Event types** — what triggers this? (message, rename, join, pin, etc.)
- [ ] **Data access patterns** — what fields from the event are needed?
- [ ] **Conditions** — boolean logic, thresholds, role checks, time windows
- [ ] **Actions to emit** — map to `ctx.emit_action()` calls with correct action types
- [ ] **State tracking** — what needs to persist in `ctx.store`?
- [ ] **Scheduled tasks** — any periodic checks via `ctx.schedule()`?
- [ ] **Edge cases** — explicitly call them out in docstrings/comments
- [ ] **Voting mechanics** — if any, specify vote type, threshold, timeout

### Handling Ambiguity

If the policy is ambiguous, **infer reasonable defaults** but **flag the ambiguity** in generated code comments:

```python
def handle_message(event, ctx):
    """
    Delete messages containing spam keywords.
    
    AMBIGUITY: Policy did not specify which keywords. Using: ['spam', 'phishing', 'scam'].
    AMBIGUITY: Policy did not specify whether to notify the user. Assuming yes.
    """
    # ... implementation
```

### Unsupported Actions

If the policy requests something outside Slack's API, **flag it prominently**:

```python
def setup(ctx):
    """
    WARNING: Policy requested 'temporarily mute user for 10 minutes'.
    Slack API does not support temporary muting or user muting at all.
    WORKAROUND: Implemented as channel kick instead (closest available action).
    """
    # ...
```

---

## Slack Platform Capabilities

### Supported Events (Triggers)

These events can trigger policies:

| Event Type | Data Fields Available | Description |
|------------|----------------------|-------------|
| `message` (no subtype) | `initiator`, `text`, `channel`, `timestamp` | A message was posted |
| `message` (subtype: `channel_name`) | `initiator`, `channel`, `name`, `previous_name` | A channel was renamed |
| `member_joined_channel` | `initiator`, `inviter`, `channel`, `users` | User joined/invited to channel |
| `pin_added` | `initiator`, `channel`, `timestamp` | A message was pinned |

### Supported Actions

These actions can be emitted via `ctx.emit_action()` or platform-specific methods:

| Action | Method/Type | Parameters | Reversible? | Auth Required |
|--------|-------------|------------|-------------|---------------|
| **Post Message** | `ctx.post_message()` or `slack.post_message` | `text`, `channel`, `thread` (optional) | ✅ Yes (delete) | admin_bot |
| **Delete Message** | `delete_message` | `message_id` | ❌ No | admin_bot |
| **Rename Channel** | `slack.rename_conversation` | `channel`, `name` | ✅ Yes (rename back) | admin_user |
| **Invite to Channel** | `slack.join_conversation` | `channel`, `users` | ✅ Yes (kick) | admin_user |
| **Kick from Channel** | `slack.kick_conversation` | `channel`, `user` | ❌ No | user (initiator) |
| **Pin Message** | `pin_message` | `channel`, `timestamp` | ✅ Yes (unpin) | bot |
| **Schedule Message** | `slack.schedule_message` | `text`, `channel`, `post_at` | ❓ Unclear | (default) |

### Message Posting

The sandbox provides a simple message posting API:

**Signature**: `ctx.post_message(channel_id: str, text: str, author_id: str = "__system__")`

**Examples**:
```python
# Post a message to a channel
ctx.post_message("ch-general", "This is a notification from the policy engine")

# Send a direct message to a user (use user_id as channel_id)
ctx.post_message("user-123", "Your message violated policy X.")

# Post as a specific user
ctx.post_message("ch-announcements", "Vote results posted", author_id="bot-001")
```

**Note**: In the sandbox, all messages are posted as simple text. PolicyKit's Slack integration supports additional features like ephemeral messages, threading, and emoji reactions through the Slack API, but these are not simulated in the sandbox.

### Community Query Methods

Available for checking state:

| Method | Returns | Use Case |
|--------|---------|----------|
| `ctx.get_user(user_id)` | `CommunityUser` or `None` | Get user details, check roles |
| `ctx.get_channel(channel_id)` | `Channel` or `None` | Get channel info, check privacy (ID-based lookup only) |
| `ctx.get_channels()` | List of `Channel` objects | Iterate all channels in the community |
| `ctx.get_members()` | List of `CommunityUser` objects | Iterate all community members |

**Note**: To check channel membership, iterate through a channel's `members` list:
```python
channel = ctx.get_channel("ch-general")
if channel and "user-123" in channel.members:
    # User is in the channel
    pass
```

### Voting Mechanisms

The sandbox provides a simple voting system:

#### Creating a Vote Proposal

```python
# 1. Create a governance action (this will be executed if vote passes)
action = ctx.emit_action("post_announcement", channel_id="ch-announcements", text="New policy approved!")

# 2. Start a vote for this action
ctx.start_vote(proposal_id="proposal-001", action=action)

# 3. Post a message to notify users about the vote
ctx.post_message("ch-general", "Vote now on proposal-001! Reply with your vote.")
```

#### Handling Vote Casting

Your policy must listen for `vote_cast` events and register votes:

```python
def setup(ctx):
    ctx.on("vote_cast", handle_vote_cast)

def handle_vote_cast(event, ctx):
    # Extract vote data from event
    proposal_id = event.data.get("proposal_id")
    voter_id = event.actor_id
    value = event.data.get("value")  # True for yes, False for no
    
    # CRITICAL: Must call ctx.cast_vote() to register the vote
    ctx.cast_vote(proposal_id, voter_id, value)
    
    # Check if threshold is met
    proposal = ctx.votes.get_proposal(proposal_id)
    if proposal and proposal.get_yes_votes() >= 2:
        # Vote passed - execute the action
        ctx.execute_action(proposal.action)
        ctx.post_message("ch-general", f"Proposal {proposal_id} passed!")
    elif proposal and proposal.get_no_votes() >= 2:
        # Vote failed - do not execute
        ctx.post_message("ch-general", f"Proposal {proposal_id} rejected.")
```

#### Proposal Object Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `proposal.get_yes_votes()` | `int` | Count of True votes |
| `proposal.get_no_votes()` | `int` | Count of False votes |
| `proposal.get_vote_count()` | `int` | Total votes cast |
| `proposal.status` | `str` | "proposed", "passed", or "failed" |
| `proposal.action` | `GovernableAction` | The action to execute if vote passes |

**Important**: 
- PolicyKit uses Metagov for emoji-based voting on Slack, which is a much richer system
- The sandbox's voting system is a simplified prototype for testing governance logic
- In production PolicyKit, votes come through Metagov signals, not synthetic `vote_cast` events

### Platform Limitations

This section distinguishes between what's **truly impossible** (Slack API doesn't support it) versus what's **not yet implemented** (Slack supports it, but PolicyKit/sandbox hasn't added the code).

#### ✅ Slack API Supports (But Not Yet Implemented in PolicyKit/Sandbox)

These events and actions ARE available in the official Slack API and **could be added** to PolicyKit:

**Events:**
- 🔧 `message_edited` - Slack Events API: `message_changed`
- 🔧 `message_deleted` - Slack Events API: `message_deleted`
- 🔧 `reaction_added` - Slack Events API: `reaction_added`
- 🔧 `reaction_removed` - Slack Events API: `reaction_removed`
- 🔧 `member_left_channel` - Slack Events API: `member_left_channel`
- 🔧 `channel_created` - Slack Events API: `channel_created`
- 🔧 `channel_archived` - Slack Events API: `channel_archive`

**Actions:**
- 🔧 Edit message - Slack Web API: `chat.update`
- 🔧 Archive channel - Slack Web API: `conversations.archive`
- 🔧 Unarchive channel - Slack Web API: `conversations.unarchive`
- 🔧 Set channel topic - Slack Web API: `conversations.setTopic`
- 🔧 Set channel purpose - Slack Web API: `conversations.setPurpose`

**Note**: PolicyKit currently only implements 4 event types (message, channel_rename, member_joined, pin_added). The Slack Events API provides many more that could be wired up in future versions.

#### ❌ Truly Impossible (Slack API Doesn't Support)

These features are **NOT available** in the Slack API and cannot be implemented:

- ❌ **User-level muting** - Slack has no API to mute users (temporary or permanent)
- ❌ **Workspace-level banning** - Only available via SCIM API for Enterprise Grid customers
- ❌ **Channel locking (read-only mode)** - No API to make a channel read-only
- ❌ **Pre-send message filtering** - All Slack events are post-facto; cannot prevent a message before it's posted
- ❌ **Assign/remove workspace roles** - Requires workspace admin permissions via web UI; no standard API

**Workarounds:**
- For "muting", track muted users in `ctx.store` and immediately delete their messages
- For "banning", kick user from all channels they're in
- For "locking", kick all non-approved users and immediately remove anyone who joins

#### ⚠️ Special Cases

**Emoji Voting:**
- Slack does provide `reaction_added`/`reaction_removed` events
- PolicyKit uses **Metagov** to track reactions for governance votes (more reliable than raw events)
- The sandbox simulates this with synthetic `vote_cast` events (see Voting Mechanisms section above)

### Authentication Constraints

Actions have different auth requirements:

- **admin_bot** — Requires admin bot token (most message actions)
- **admin_user** — Requires admin user token (channel management)
- **user** — Uses initiator's token (kicks)
- **bot** — Standard bot token (pins)

**Implication**: If a policy requires an admin action (like renaming), ensure the bot has admin privileges or the policy will fail at execution.

---

## Common Pitfalls and How to Avoid Them

### 1. Vague Trigger Conditions

❌ **Bad**: "When inappropriate content is posted"
✅ **Good**: "When a message contains any of these keywords: ['hate', 'spam', 'scam']"

**Why**: The sandbox cannot interpret "inappropriate" — it needs explicit boolean conditions.

---

### 2. Missing Edge Case Handling

❌ **Bad**: "Delete spam messages"
✅ **Good**: "Delete spam messages, but only if the sender is not an admin or moderator. If an admin posts a flagged message, log it but take no action."

**Why**: Edge cases prevent false positives and policy abuse.

---

### 3. Ambiguous Timing

❌ **Bad**: "Give users a chance to respond before kicking them"
✅ **Good**: "Send a warning DM. Wait 5 minutes. If the user has not apologized in #general, kick them."

**Why**: "A chance" is not machine-interpretable. Specify exact durations.

---

### 4. Requesting Unsupported Events

❌ **Bad**: "When a user edits their message to remove spam keywords"
✅ **Good**: "When a message is posted with spam keywords, delete it. (Note: Slack does not support edit events)"

**Why**: The Slack API does not emit `message_edited` events that PolicyKit can intercept.

---

### 5. Assuming Stateful Context Without Specifying Storage

❌ **Bad**: "If a user violates the policy 3 times, ban them"
✅ **Good**: "Track violations in `ctx.store` keyed by user ID. Increment on each violation. If count >= 3, ban the user. Reset counts after 30 days."

**Why**: The system needs to know **where** and **how** to track state.

---

### 6. Conflating Actions with Events

❌ **Bad**: "When a message is deleted, notify the moderators"
✅ **Good**: "When a message containing spam keywords is posted, delete it AND notify moderators in #mod-log"

**Why**: Deleting a message is an **action** the policy takes, not an **event** that triggers it. If you want to detect deletions, you need to track them yourself (Slack doesn't emit `message_deleted` as a triggerable event).

---

### 7. Over-relying on Human Judgment

❌ **Bad**: "Moderators should review and decide"
✅ **Good**: "Post the flagged message to #mod-review with 👍/👎 reactions. If 3+ mods vote 👎 within 1 hour, delete the original message."

**Why**: Policies must be executable by code. If humans are involved, specify the voting/approval mechanism.

---

### 8. Unclear Role/Permission Checks

❌ **Bad**: "Only allow trusted users to rename channels"
✅ **Good**: "When a channel is renamed, check if the initiator has the 'admin' or 'channel-manager' role. If not, revert the rename."

**Why**: "Trusted" is ambiguous. Specify exact roles or conditions.

---

### 9. Missing Notification/Transparency

❌ **Bad**: "Delete messages silently"
✅ **Good**: "Delete the message and send an ephemeral DM to the author explaining why, and log to #mod-log for transparency."

**Why**: Silent actions can confuse users and reduce trust. Policies should be transparent.

---

### 10. Not Handling Concurrent Events

❌ **Bad**: "If 5 messages are posted in 10 seconds, lock the channel"
✅ **Good**: "Track message timestamps per channel in `ctx.store`. On each message, count messages in the last 10 seconds. If count >= 5, lock the channel and clear the count."

**Why**: Without explicit state tracking and timing logic, concurrent events may not be handled correctly.

---

## Examples: Good vs. Bad Policies

### Example 1: Spam Moderation

#### ❌ Bad Policy
```
"Delete spam and warn users."
```

**Problems**:
- What is "spam"? (no definition)
- Warn how? (DM? Public message?)
- Any exemptions? (admins? first offense?)

#### ✅ Good Policy
```
TRIGGER: When a message is posted

CONDITIONS:
- Message text contains any of: ['buy now', 'click here', 'limited offer', 'free money']
- Case-insensitive match
- User does not have 'admin' or 'moderator' role

ACTIONS:
1. Delete the message immediately
2. Send an ephemeral DM to the user: "Your message was flagged as spam. Please review our guidelines."
3. Increment spam count in data store (key: "spam_count_{user_id}")
4. If spam count >= 3 within 24 hours:
   a. Kick the user from the channel
   b. Post to #mod-log: "User {username} kicked for repeated spam (3+ offenses)"

EDGE CASES:
- If user is admin/moderator: log the event but take no action
- If message is in a thread: delete but don't kick (threads are more forgiving)

TIMING:
- Deletion: immediate
- Kick: immediate after 3rd offense
- Reset spam count: after 24 hours of no new spam
```

---

### Example 2: Channel Naming Convention

#### ❌ Bad Policy
```
"Channels should follow naming conventions."
```

**Problems**:
- What are the conventions? (not specified)
- What happens if violated? (no action)
- Who enforces? (no trigger)

#### ✅ Good Policy
```
TRIGGER: When a channel is renamed (message with subtype "channel_name")

CONDITIONS:
- New name does NOT match pattern: ^(team-|project-|wg-).*$
- Initiator is not an admin

ACTIONS:
1. Rename channel back to previous name
2. Post ephemeral message to initiator:
   "Channel names must start with 'team-', 'project-', or 'wg-'. 
   Please contact an admin if you need to rename."
3. Log to #governance-log: 
   "Channel rename reverted: {old_name} → {new_name} by {user}"

EDGE CASES:
- If initiator is admin: allow unconditionally
- If channel was previously misnamed and being corrected: 
  check if old name also violated (allow if correcting violation)

TIMING:
- Rename reversion: immediate (within handler)
```

---

### Example 3: Welcome New Members

#### ❌ Bad Policy
```
"Greet new members."
```

**Problems**:
- How? (DM? Public?)
- What message?
- Any personalization?

#### ✅ Good Policy
```
TRIGGER: When a user joins a channel (member_joined_channel)

CONDITIONS:
- Channel is one of: ['#general', '#introductions', '#help']
- User has joined in the last 5 seconds (to avoid duplicate greetings)

ACTIONS:
1. Send a DM to the new user:
   "Welcome to {channel_name}! 👋
   Please introduce yourself in #introductions.
   Need help? Ask in #help."
2. Post in the channel (public):
   "Welcome @{username} to {channel_name}!"

EDGE CASES:
- If user rejoins after being kicked: send a different message:
  "Welcome back, @{username}. Please review our guidelines."
- If user was invited by admin (not self-join): skip public greeting (avoid spam)

TIMING:
- DM: immediate
- Public greeting: 2-second delay (to batch if multiple join at once)

DATA:
- Track last greeting timestamp per user+channel in data store
- Key: "last_greeting_{user_id}_{channel_id}"
- Avoid re-greeting if <1 hour since last greeting
```

---

### Example 4: Pin Message Policy

#### ❌ Bad Policy
```
"Let the community vote on pinning messages."
```

**Problems**:
- How is vote initiated? (who can propose?)
- What's the threshold?
- How long is voting open?

#### ✅ Good Policy
```
TRIGGER: When a message receives a 📌 reaction (NOT SUPPORTED — see workaround)

WORKAROUND: Since Slack does not emit reaction events, use this trigger instead:
TRIGGER: When a message is posted containing exactly "!pin {message_id}"

CONDITIONS:
- Initiator has 'moderator' role
- Message ID is valid and in the same channel

ACTIONS:
1. Start an emoji vote in the channel with 📌 and ❌ reactions
2. Vote text: "Pin this message? 📌 Yes | ❌ No"
3. Vote duration: 10 minutes
4. Vote threshold: 5+ votes, >60% 📌
5. If vote passes:
   a. Pin the message
   b. Post: "Message pinned by community vote (X pins, Y rejections)"
6. If vote fails:
   a. Post ephemeral to initiator: "Vote did not pass (X pins, Y rejections)"

EDGE CASES:
- If message is already pinned: skip and notify initiator
- If channel already has 10 pinned messages (Slack limit): unpin oldest before pinning
- If initiator is admin: skip vote, pin directly

TIMING:
- Vote duration: 10 minutes
- Pin action: immediate after vote passes

DATA:
- Store active pin votes: key "pin_vote_{message_id}", value {start_time, status}
- Cleanup completed votes after 1 hour
```

---

### Example 5: Quiet Hours Enforcement

#### ❌ Bad Policy
```
"Don't allow messages during night time."
```

**Problems**:
- What time zone?
- What channels?
- What happens to messages sent?

#### ✅ Good Policy
```
TRIGGER: When a message is posted

CONDITIONS:
- Current time is between 22:00 and 08:00 (UTC)
- Channel is '#general' or '#random'
- User does not have 'on-call' role

ACTIONS:
1. Delete the message
2. Send ephemeral DM to user:
   "This channel is in quiet hours (22:00-08:00 UTC).
   Please use #night-chat for off-hours discussion.
   Urgent? Tag @on-call."
3. Store deleted message in data store for audit:
   Key: "quiet_hours_deleted_{timestamp}"
   Value: {user_id, channel, text, timestamp}

EDGE CASES:
- If user has 'on-call' role: allow unconditionally
- If message is a reply in a thread started during active hours: allow
- If channel is '#urgent' or '#incidents': allow regardless of time

TIMING:
- Check time on every message (use ctx.current_time)
- Deletion: immediate

DATA:
- Track quiet hours violations per user per day
- Key: "quiet_violations_{user_id}_{date}"
- If count > 3 in one day: DM user: "Reminder: please respect quiet hours"
```

---

## Summary: Policy Quality Checklist

Before submitting a policy, check:

- [ ] **Trigger** is one of the supported Slack events
- [ ] **Conditions** are explicit, boolean, measurable
- [ ] **Actions** map to available Slack API calls
- [ ] **Edge cases** are enumerated (admins? first offense? concurrent events?)
- [ ] **Timing** is specified (delays, durations, schedules)
- [ ] **State tracking** is defined (what data? where stored? how cleaned up?)
- [ ] **Notifications** are included (transparency, user feedback)
- [ ] **Role checks** use exact role names
- [ ] **Channel/user references** are explicit (IDs or names)
- [ ] **Voting** (if any) has threshold, timeout, and eligible voters specified
- [ ] **Unsupported features** are flagged or worked around
- [ ] **Ambiguities** are minimized or documented

---

## Appendix: Full Slack API Reference

For the complete technical specification of available actions, events, and methods, see the Explore agent's research summary or refer to:

- [sandbox/docs/api_reference.md](./api_reference.md) — Sandbox policy API
- [policykit/integrations/slack/models.py](../../policykit/policykit/policykit/integrations/slack/models.py) — PolicyKit Slack action definitions

---

## Feedback and Iteration

If the sandbox generates code that doesn't match your intent:

1. **Check the revision log** — see what errors were flagged
2. **Refine your policy** — add missing details from this guide's checklist
3. **Specify edge cases explicitly** — don't assume the system will infer
4. **Use examples** — "Like the spam moderation example, but for X"

Policies improve through iteration. Start simple, test, refine.
