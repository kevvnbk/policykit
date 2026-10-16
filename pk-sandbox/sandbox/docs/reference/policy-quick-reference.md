# Natural Language Policy Quick Reference

> **Full Guide**: See [policy-authoring-guide.md](./policy-authoring-guide.md) for comprehensive details.

---

## ✅ Supported Slack Events

| Event | Data Fields | Example Trigger |
|-------|-------------|-----------------|
| `message` (posted) | `initiator`, `text`, `channel`, `timestamp` | "When a message is posted containing 'spam'" |
| `message` (subtype: channel_name) | `initiator`, `channel`, `name`, `previous_name` | "When a channel is renamed" |
| `member_joined_channel` | `initiator`, `inviter`, `channel`, `users` | "When a user joins #general" |
| `pin_added` | `initiator`, `channel`, `timestamp` | "When a message is pinned" |

---

## ✅ Available Actions

| Action | Parameters | Reversible? | Use Case |
|--------|------------|-------------|----------|
| Post message | `text`, `channel`, `thread` | ✅ (delete) | Notifications, warnings, logs |
| Delete message | `message_id` | ❌ No | Remove spam, violations |
| Rename channel | `channel`, `name` | ✅ (rename back) | Enforce naming conventions |
| Invite to channel | `channel`, `users` | ✅ (kick) | Add approved users |
| Kick from channel | `channel`, `user` | ❌ No | Remove violators |
| Pin message | `channel`, `timestamp` | ✅ (unpin) | Highlight important content |

---

## ❌ NOT Supported (Important!)

- ❌ Reaction events as general triggers (`reaction_added`, `reaction_removed`)
  - ✅ **BUT:** Emoji voting via `initiate_vote()` IS supported (Metagov tracks votes)
- ❌ Edit/delete events (`message_edited`, `message_deleted`)
- ❌ Channel lifecycle (`channel_created`, `channel_deleted`, `channel_archived`)
- ❌ File events (`file_uploaded`, `file_deleted`)
- ❌ Thread events (`thread_created`)
- ❌ User profile changes
- ❌ Temporary muting (no duration-based user muting at all)
- ❌ Message editing (can delete, not edit)
- ❌ Preventing message send (only react after posted)

---

## 📋 Policy Template

```
TRIGGER: [Specific event: "When a message is posted in #general"]

CONDITIONS:
- [Explicit boolean: "text contains 'spam' (case-insensitive)"]
- [Role check: "user does NOT have 'moderator' role"]
- [Timing: "current time is between 09:00-17:00 UTC"]

ACTIONS:
1. [Primary action: "Delete the message"]
2. [Notification: "Send ephemeral DM: 'Your message violated rule X'"]
3. [Logging: "Post to #mod-log with details"]
4. [Escalation: "If 3+ violations within 24h, kick user"]

EDGE CASES:
- If user is admin: [allow/log/notify]
- If message is in thread: [different behavior]
- If concurrent events: [how to handle]

TIMING:
- [Immediate / delayed / scheduled]
- [Durations: "wait 5 minutes", "expires after 24 hours"]

DATA STORE:
- Key: "violation_count_{user_id}"
- Value: {count: int, last_violation: timestamp}
- Cleanup: "reset after 30 days"
```

---

## 🎯 Quality Checklist

- [ ] Trigger is a supported Slack event
- [ ] Conditions are explicit and boolean
- [ ] Actions map to available API calls
- [ ] Edge cases enumerated (admins, first offense, etc.)
- [ ] Timing specified (delays, durations, resets)
- [ ] State tracking defined (keys, values, cleanup)
- [ ] Notifications/transparency included
- [ ] Roles/channels use exact names
- [ ] Voting (if any) has threshold + timeout
- [ ] Unsupported features flagged/worked around

---

## 🚫 Common Pitfalls

| Bad | Good |
|-----|------|
| "Moderate bad messages" | "Delete messages containing words ['spam', 'scam'] unless user is admin" |
| "Notify moderators" | "Send DM to users with 'moderator' role" |
| "Give users a chance" | "Wait 5 minutes before kicking" |
| "Track violations" | "Store in ctx.store key 'violations_{user_id}', reset after 24h" |
| "When message is edited" | NOT SUPPORTED - use "when posted" instead |
| "If inappropriate content" | "If text matches regex pattern: ..." |

---

## 📚 Message Post Types

| Type | Description | Requires |
|------|-------------|----------|
| `channel` | Public channel post | `channel` |
| `im` | Individual DMs (one per user) | `users` (list) |
| `mpim` | Group DM | `users` (list) |
| `ephemeral` | Visible only to specific users | `users`, `channel` |

**Example**:
```python
# Warning visible only to violator
ctx.community.post_message(
    proposal=None,
    text="Policy violation warning",
    users=["user-123"],
    post_type="ephemeral",
    channel="general"
)
```

---

## 🗳️ Voting Patterns

### Boolean Vote (Yes/No)
```
"Start a vote in #general with 👍/👎 reactions.
If 5+ votes and >60% are 👍 within 24 hours, approve.
Otherwise, reject."
```

### Advanced Vote (Per-Candidate)
```
"Start a vote for 3 candidates: ['Alice', 'Bob', 'Carol'].
Options: {'approve': '✅', 'reject': '❌'}.
Each user can vote on all candidates.
Close after 48 hours. Candidates with >50% approve win."
```

---

## 💾 Data Store Patterns

### Counter with Reset
```python
key = f"spam_count_{user_id}"
count = ctx.store.get(key, 0) + 1
ctx.store.set(key, count)

# Reset after 24h (implement via scheduled task)
if time_since_last > 86400:
    ctx.store.remove(key)
```

### Timestamp Tracking
```python
key = f"last_warning_{user_id}"
last_time = ctx.store.get(key, 0)
if ctx.current_time - last_time < 3600:
    # Within 1 hour, take action
    pass
ctx.store.set(key, ctx.current_time)
```

### List Accumulation
```python
key = f"violations_{user_id}"
violations = ctx.store.get(key, [])
violations.append({"time": ctx.current_time, "reason": "spam"})
ctx.store.set(key, violations)

# Keep only recent (last 7 days)
violations = [v for v in violations if ctx.current_time - v["time"] < 604800]
```

---

## 🔍 Example: Complete Policy

```
TRIGGER: When a message is posted

CONDITIONS:
- Text contains ['spam', 'scam', 'phishing'] (case-insensitive)
- User does NOT have role 'moderator' or 'admin'
- Message is in channel (not thread)

ACTIONS:
1. Delete message immediately
2. Increment violation count in data store (key: "spam_{user_id}")
3. Send ephemeral DM: "Your message was flagged. Strike {count}/3."
4. Log to #mod-log: "Spam deleted: @{user} in #{channel}"
5. If count >= 3 within 24 hours:
   a. Kick user from channel
   b. DM: "You've been removed for repeated spam."
   c. Post to #mod-log: "User {user} kicked (3 strikes)"

EDGE CASES:
- If user is moderator/admin: log to #mod-log but take no action
- If message is in thread: log only, no deletion
- If user has <1 hour account age: auto-kick on first offense

TIMING:
- Deletion: immediate
- Kick: immediate on 3rd strike
- Violation count reset: 24 hours after last violation

DATA STORE:
- Key: "spam_{user_id}"
- Value: {"count": int, "last_time": float, "violations": [timestamps]}
- Cleanup: scheduled task runs hourly, removes entries >24h old
```

---

## 🔗 Full Documentation

- **Comprehensive Guide**: [policy-authoring-guide.md](./policy-authoring-guide.md)
- **Sandbox API Reference**: [api_reference.md](./api_reference.md)
- **Slack Integration Details**: See Explore agent research or PolicyKit source

---

## 💡 Pro Tips

1. **Start simple, iterate**: Begin with basic trigger + action, then add edge cases
2. **Be explicit**: Don't assume — spell out every condition
3. **Test edge cases**: Admins, concurrent events, timing boundaries
4. **Use data store liberally**: Track state for any multi-event logic
5. **Add transparency**: Log actions, notify users, explain decisions
6. **Flag ambiguities**: If unclear, document assumptions in comments
7. **Work around limitations**: If feature unsupported, propose closest alternative

---

*Last updated: 2026-07-28*
