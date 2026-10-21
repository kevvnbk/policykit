# Sandbox Policy API Reference

This document is injected into LLM prompts during script and test generation.
It defines the full API surface available to generated policy scripts.

---

## Script Structure

Scripts use **function registration** (not class inheritance):

```python
def setup(ctx):
    """Called once when the policy is installed. Register event handlers here."""
    ctx.on("message_posted", handle_message)
    ctx.schedule(3600, check_quiet_channels)

def handle_message(event, ctx):
    """Called each time a message_posted event fires."""
    # Get channel ID from the event (NOT by name lookup)
    channel_id = event.data.get("channel_id")
    text = event.data.get("text", "").lower()
    
    # Compare channel IDs directly, or retrieve channel metadata
    if channel_id == "ch-announcements":  # Using the actual ID
        # Alternative: ch = ctx.get_channel(channel_id) to get channel.name
        if "spam" in text:
            ctx.emit_action("delete_message", message_id=event.data["message_id"])

def check_quiet_channels(event, ctx):
    """Scheduled handlers ALSO receive (event, ctx) — event.type will be '__tick__'."""
    # Check for quiet channels every hour
    pass
```

Every script MUST define a `setup(ctx)` function. All other functions are registered
as event handlers or scheduled tasks within `setup()`.

**IMPORTANT**: ALL handlers (both event handlers registered with `ctx.on()` and scheduled
handlers registered with `ctx.schedule()`) receive `(event, ctx)` parameters. Scheduled 
handlers receive a `__tick__` event with no data fields.

---

## PolicyContext (`ctx`)

The `ctx` object is passed to `setup()` and all handlers. It provides:

### Event Registration

| Method | Description |
|--------|-------------|
| `ctx.on(event_type: str, handler)` | Register a handler for an event type |
| `ctx.schedule(interval: float, handler, recurring=True)` | Schedule a handler to fire every `interval` seconds |

### Actions

| Method | Description |
|--------|-------------|
| `ctx.emit_action(action_type: str, **kwargs)` | **Propose** a governance action (status=PROPOSED). Returns the action object. **Does NOT execute or log the action yet** - only adds to governance log when executed. **Does NOT create visible messages** - use `post_message()` for that. |
| `ctx.execute_action(action: GovernableAction)` | **Execute** a governance action immediately (marks as PASSED and adds to action log). Use this when you want to execute an action without voting. |
| `ctx.post_message(channel_id: str, text: str, author_id="__system__")` | Post a message to a channel or user. **Creates visible messages** that tests can verify. To send a DM to a user, pass their user ID as the channel_id. |

**CRITICAL - Action Execution Model**:
- `ctx.emit_action()` creates actions with status=**PROPOSED** (not executed yet)
- Actions are **NOT added to the action log** until executed
- When a vote **passes**, call `ctx.execute_action(action)` to execute the proposal's action
- When a vote **fails** or **expires**, do NOT execute - the action remains proposed only
- Tests checking `action_taken` will ONLY find **executed** actions (status=PASSED)

### Community Queries

| Method | Description |
|--------|-------------|
| `ctx.get_user(user_id: str)` | Get a CommunityUser by ID. Returns None if not found. |
| `ctx.get_channel(channel_id: str)` | Get a Channel by **ID** (NOT name). Returns None if not found. |
| `ctx.get_channels()` | Get all channels as a list |
| `ctx.get_members()` | Get all community users as a list |

**IMPORTANT**: `ctx.get_channel()` accepts channel **IDs** only, not channel names. Events contain channel IDs (e.g., `"ch-ann"`), and you should use these IDs directly. To find a channel by name, use `ctx.get_channels()` and iterate. Compare `event.data.get("channel_id")` directly against known channel IDs, or use `ctx.get_channel(channel_id)` to retrieve channel metadata.

### Data Store (persistent key-value storage)

| Method | Description |
|--------|-------------|
| `ctx.store.get(key: str, default=None)` | Get a value by key |
| `ctx.store.set(key: str, value)` | Store a value |
| `ctx.store.remove(key: str)` | Remove a key. Returns True if removed. |
| `ctx.store.has(key: str)` | Check if a key exists |

### Voting

| Method | Description |
|--------|-------------|
| `ctx.start_vote(proposal_id: str, action)` | Create a proposal for vote-based governance. `action` must be a GovernableAction (returned by `ctx.emit_action()`). |
| `ctx.cast_vote(proposal_id: str, voter_id: str, value, vote_type="boolean")` | Record a vote. **Must be called in your `vote_cast` event handler** to register votes. |
| `ctx.votes.get_proposal(proposal_id: str)` | Get a proposal object |

**IMPORTANT**: The complete voting workflow:

**Creating a proposal:**
```python
action = ctx.emit_action("post_announcement", channel_id=ann_id, text=text)  # Proposed only
ctx.start_vote(proposal_id, action)
```

**Handling votes (in vote_cast handler):**
1. Extract `proposal_id`, `voter_id` (from `event.actor_id`), and `value` (from `event.data`)
2. Call `ctx.cast_vote(proposal_id, voter_id, value)` to register the vote
3. Check if threshold is met: `proposal.get_yes_votes() >= 2`
4. **If passed**: Call `ctx.execute_action(proposal.action)` to execute
5. **If failed/expired**: Do nothing - action remains proposed (never executes)

**Key points:**
- Without `ctx.cast_vote()`, votes are never recorded
- Without `ctx.execute_action()`, approved actions never execute
- Tests checking `action_taken` only find **executed** actions

**Proposal ID Pattern**: Use consistent, unique IDs like `"proposal_" + message_id` (e.g., `"proposal_m1"`). 
Tests must send `vote_cast` events with the same proposal_id format your script creates.

### Time

| Property | Description |
|----------|-------------|
| `ctx.current_time` | Current simulated time (float, seconds since scenario start) |

---

## Event Object

Handlers receive `(event, ctx)`. The `event` object has:

| Field | Type | Description |
|-------|------|-------------|
| `event.type` | `str` | Event type (e.g., "message_posted") |
| `event.data` | `dict` | Event-specific payload |
| `event.actor_id` | `str \| None` | ID of the user who triggered the event |
| `event.timestamp` | `float` | When the event occurred |

Access data fields via `event.data.get("key")` or `event.data["key"]`.

---

## Available Event Types

### Implemented Events (Sandbox + PolicyKit)

These events are currently implemented and can be used in policies:

| Type | Data Fields | Description |
|------|-------------|-------------|
| `message_posted` | `message_id`, `text`, `channel_id` | A message was posted |
| `member_joined` | `channel_id` | A user joined a channel |
| `vote_cast` | `proposal_id`, `value` | A vote was cast (sandbox-only, synthetic event) |

### Sandbox-Only Events (Testing/Prototyping)

These events are available in the sandbox for testing but not in PolicyKit/Slack:

| Type | Data Fields | Description | Status |
|------|-------------|-------------|--------|
| `message_edited` | `message_id`, `text`, `channel_id`, `old_text` | A message was edited | Slack API supports `message_changed` - could be added to PolicyKit |
| `message_deleted` | `message_id`, `channel_id` | A message was deleted | Slack API supports - could be added to PolicyKit |
| `reaction_added` | `message_id`, `emoji`, `channel_id` | A reaction was added | Slack API supports - could be added to PolicyKit |
| `reaction_removed` | `message_id`, `emoji`, `channel_id` | A reaction was removed | Slack API supports - could be added to PolicyKit |
| `member_left` | `channel_id` | A user left a channel | Slack API supports `member_left_channel` - could be added to PolicyKit |
| `channel_created` | `channel_id`, `name` | A channel was created | Slack API supports - could be added to PolicyKit |
| `role_assigned` | `role_name`, `target_id` | A role was assigned | Sandbox-only concept for testing role-based policies |
| `role_removed` | `role_name`, `target_id` | A role was removed | Sandbox-only concept for testing role-based policies |

**Note**: The sandbox provides these additional event types for comprehensive policy testing. Scripts using these events will need adaptation when deployed to PolicyKit.

### Scheduled Event

| Type | Data Fields | Description |
|------|-------------|-------------|
| `__tick__` | (none) | Fired by scheduled handlers |

---

## Available Action Types

Actions emitted via `ctx.emit_action(action_type, **kwargs)`:

### Implemented in PolicyKit + Sandbox

These actions work in both the sandbox and PolicyKit:

| Action Type | Kwargs | Description | Slack API Method |
|-------------|--------|-------------|------------------|
| `delete_message` | `message_id` | Delete a message | `chat.delete` |
| `kick_user` | `user_id`, `channel_id` | Remove user from channel | `conversations.kick` |
| `pin_message` | `message_id`, `channel_id` | Pin a message | `pins.add` |

### Sandbox-Only Actions (Testing/Prototyping)

These actions are available for sandbox testing but have varying levels of real-world support:

| Action Type | Kwargs | Description | Status |
|-------------|--------|-------------|--------|
| `mute_user` | `user_id`, `duration` (optional) | Mute a user | ❌ Slack API doesn't support - truly impossible |
| `unmute_user` | `user_id` | Unmute a user | ❌ Slack API doesn't support - truly impossible |
| `ban_user` | `user_id`, `reason` (optional) | Ban a user from workspace | ⚠️ Enterprise only via SCIM API |
| `assign_role` | `user_id`, `role_name` | Assign a role | ⚠️ No standard API - admin UI only |
| `remove_role` | `user_id`, `role_name` | Remove a role | ⚠️ No standard API - admin UI only |
| `lock_channel` | `channel_id` | Make channel read-only | ❌ Slack API doesn't support - truly impossible |
| `unlock_channel` | `channel_id` | Unlock a channel | ❌ Slack API doesn't support - truly impossible |
| `archive_channel` | `channel_id` | Archive a channel | ✅ Slack API supports `conversations.archive` - could be added to PolicyKit |
| `warn_user` | `user_id`, `reason` | Issue a warning | Custom action - requires external tracking |
| `post_announcement` | `channel_id`, `text` | Post a system announcement | Use `ctx.post_message()` instead |

### Custom Action Types

You may emit custom action types as needed for application-specific governance logic:

```python
ctx.emit_action("custom_action_name", param1="value1", param2="value2")
```

Custom actions are logged in the sandbox but won't have automatic execution semantics in PolicyKit unless you implement the corresponding action model.

---

## CommunityUser Object

Returned by `ctx.get_user()` and `ctx.get_members()`:

| Field/Method | Description |
|-------------|-------------|
| `user.id` | User ID string |
| `user.readable_name` | Display name |
| `user.roles` | List of role name strings |
| `user.has_role(role_name)` | Returns True if user has the role |
| `user.get_roles()` | Returns list of role names |

---

## Channel Object

Returned by `ctx.get_channel(channel_id)`:

| Field | Description |
|-------|-------------|
| `channel.id` | Channel ID string (e.g., "ch-ann") |
| `channel.name` | Channel name (e.g., "announcements") |
| `channel.is_private` | Boolean |
| `channel.members` | List of user IDs |

**Note**: Channels are looked up by ID. Events provide `channel_id` fields, which you should use directly. To find a specific channel by name, iterate through channels or store channel IDs during setup.

---

## Proposal Object

Returned by `ctx.votes.get_proposal()`:

| Field/Method | Description |
|-------------|-------------|
| `proposal.id` | Proposal ID |
| `proposal.status` | "proposed", "passed", or "failed" |
| `proposal.get_yes_votes()` | Count of True votes |
| `proposal.get_no_votes()` | Count of False votes |
| `proposal.get_vote_count()` | Total votes cast |

---

## Test Scenario Schema

Tests are defined as JSON scenarios:

```json
{
  "name": "Scenario name",
  "description": "What this tests",
  "community_setup": {
    "users": [{"id": "user-1", "name": "Alice", "roles": ["member"]}],
    "channels": [{"id": "general", "name": "general", "members": ["user-1"]}],
    "roles": [{"name": "member", "is_base_role": true}]
  },
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "Hello"}, "actor_id": "user-1", "at": 1.0}
  ],
  "assertions": [
    {"type": "action_taken", "expected": {"action_type": "delete_message"}, "description": "Message deleted"}
  ]
}
```

### Assertion Types

| Type | Expected Fields | Checks |
|------|----------------|--------|
| `action_taken` | `action_type` | At least one action of this type was emitted |
| `no_action_taken` | `action_type` | Zero actions of this type were emitted |
| `action_count` | `action_type`, `count` | Exactly N actions of this type |
| `store_equals` | `key`, `value` | DataStore has this key=value |
| `message_posted` | `channel_id`, `contains` | A message containing text was posted to channel |
| `event_count` | `event_type`, `count` | Exactly N events of this type in the log |

**IMPORTANT**: When testing time-based expiry with scheduled handlers:
- If `ctx.schedule(60, handler)` checks every 60 seconds and deadline is at `t = 86400`
- Test must use `__tick__` event at `t >= 86461` (deadline + interval + 1)
- Otherwise scheduler last runs at `t = 86400` (before deadline), missing the expiry

---

## Common Mistakes to Avoid

### ❌ WRONG: Scheduled handler with only (ctx) parameter
```python
def check_pending_votes(ctx):  # ❌ Missing event parameter!
    # This will crash with "takes 1 positional argument but 2 were given"
    pending = ctx.store.get("pending_list", [])
    # ...
```

### ✅ CORRECT: All handlers need (event, ctx)
```python
def check_pending_votes(event, ctx):  # ✅ Correct signature
    # Scheduled handlers also receive an event (type will be "__tick__")
    pending = ctx.store.get("pending_list", [])
    # ...
```

### ❌ WRONG: Looking up channels by name
```python
def get_announcements_channel_id(ctx):
    # This will fail! ctx.get_channel() expects an ID, not a name
    ch = ctx.get_channel("announcements")  # Returns None
    return ch.id if ch else "announcements"
```

### ✅ CORRECT: Use channel IDs directly from events
```python
def handle_message_posted(event, ctx):
    # Events provide channel_id as an ID string
    channel_id = event.data.get("channel_id")  # e.g., "ch-ann"
    
    # Option 1: Compare IDs directly (if you know specific channels)
    if channel_id == "ch-announcements":
        handle_announcement(event, ctx)
    
    # Option 2: Get channel metadata using the ID
    channel = ctx.get_channel(channel_id)
    if channel and channel.name == "announcements":
        handle_announcement(event, ctx)
```

### ✅ CORRECT: Store channel IDs during setup
```python
def setup(ctx):
    # If you need to find channels by name, do it once in setup
    for channel in ctx.get_channels():
        if channel.name == "announcements":
            ctx.store.set("announcements_channel_id", channel.id)
        elif channel.name in ("moderator-channel", "moderators"):
            ctx.store.set("mod_channel_id", channel.id)
    
    ctx.on("message_posted", handle_message)

def handle_message(event, ctx):
    channel_id = event.data.get("channel_id")
    announcements_id = ctx.store.get("announcements_channel_id")
    
    if channel_id == announcements_id:
        # Process announcement
        pass
```

### ❌ WRONG: Forgetting to record votes in vote_cast handler
```python
def handle_vote_cast(event, ctx):
    proposal_id = event.data.get("proposal_id")
    proposal = ctx.votes.get_proposal(proposal_id)
    
    # ❌ Checking votes but never recording them!
    if proposal.get_yes_votes() >= 2:  # Always 0
        approve_proposal(proposal_id, ctx)
```

### ✅ CORRECT: Always call ctx.cast_vote() to record votes
```python
def handle_vote_cast(event, ctx):
    proposal_id = event.data.get("proposal_id")
    voter_id = event.actor_id
    value = event.data.get("value")
    
    # ✅ MUST call cast_vote to register the vote
    ctx.cast_vote(proposal_id, voter_id, value)
    
    # Now check if threshold reached
    proposal = ctx.votes.get_proposal(proposal_id)
    if proposal and proposal.get_yes_votes() >= 2:
        approve_proposal(proposal_id, ctx)
```

### ❌ WRONG: Passing dict to start_vote
```python
ctx.start_vote("prop-1", {"type": "some_action"})  # ❌ Dict not allowed
```

### ✅ CORRECT: Pass GovernableAction to start_vote
```python
action = ctx.emit_action("post_message", channel_id="ch1", text="Vote?")
ctx.start_vote("prop-1", action)  # ✅ Action object
```

### ❌ WRONG: Using custom action for user notifications
```python
# ❌ Creates an action but doesn't send a message
ctx.emit_action("send_dm", user_id=author_id, text="Your proposal expired")
```

### ✅ CORRECT: Use post_message with user ID for DMs
```python
# ✅ Sends a DM by using user_id as channel_id
ctx.post_message(author_id, "Your proposal expired")
```

### ❌ WRONG: Only using emit_action for vote prompts
```python
# ❌ No visible message - tests checking for messages will fail
action = ctx.emit_action("post_announcement", channel_id=mod_ch, text="Vote?")
ctx.start_vote(proposal_id, action)
```

### ✅ CORRECT: Post message THEN emit action
```python
# ✅ Message is visible, governance action is logged
ctx.post_message(mod_channel_id, "Should we approve this announcement?")
action = ctx.emit_action("post_announcement", channel_id=ann_id, text=text)
ctx.start_vote(proposal_id, action)
```

### ❌ WRONG: Forgetting to execute approved actions
```python
def handle_vote_cast(event, ctx):
    ctx.cast_vote(proposal_id, voter_id, value)
    proposal = ctx.votes.get_proposal(proposal_id)
    if proposal.get_yes_votes() >= 2:
        # ❌ Action never executes! Tests will fail - no action found
        pass  
```

### ✅ CORRECT: Execute action when vote passes
```python
def handle_vote_cast(event, ctx):
    ctx.cast_vote(proposal_id, voter_id, value)
    proposal = ctx.votes.get_proposal(proposal_id)
    if proposal.get_yes_votes() >= 2:
        # ✅ Action executes and appears in action log
        ctx.execute_action(proposal.action)
```

---

## Available Modules (No Import Needed)

The following modules are **pre-imported** and available in all scripts:
- `datetime` - Date and time operations
- `json` - JSON encoding/decoding  
- `random` - Random number generation
- `math` - Mathematical functions
- `itertools` - Iterator tools
- `string` - String utilities
- `base64` - Base64 encoding/decoding

**Available Constants**:
- `PASSED`, `PROPOSED`, `FAILED` - Action statuses
- `YES` = `True`, `NO` = `False` - Vote values (optional, prefer `True`/`False`)

**Example** (no imports needed):
```python
# Constants extracted from policy
TIMEOUT_SECONDS = 86400

def check_expiry(event, ctx):
    now = datetime.datetime.utcfromtimestamp(ctx.current_time)  # datetime is available!
    selected = random.sample(moderators, 3)  # random is available!
```

## Constraints

- **DO NOT write import statements** - modules listed above are pre-loaded
- No file I/O, network, or subprocess access
- All state must go through `ctx.store` (persists within scenario, not across scenarios)
- Scripts execute synchronously — no async/await
