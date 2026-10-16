# Test Scenario Quick Reference

One-page cheat sheet for writing sandbox test scenarios.

---

## Scenario Template

```json
{
  "name": "Short descriptive name",
  "description": "One-line explanation",
  "community_setup": {
    "users": [{"id": "u1", "name": "Alice", "roles": ["member"]}],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1"]}],
    "roles": [{"name": "member", "is_base_role": true}]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {"message_id": "m1", "text": "Hello", "channel": "ch1"},
      "actor_id": "u1",
      "at": 1.0
    }
  ],
  "assertions": [
    {
      "type": "action_taken",
      "expected": {"action_type": "delete_message"},
      "description": "Message deleted"
    }
  ],
  "time_limit": 3600.0
}
```

---

## Event Types

| Type | Data Fields | Usage |
|------|-------------|-------|
| `message_posted` | `message_id`, `text`, `channel` | User posts message |
| `message_renamed` | `channel`, `name`, `previous_name` | Channel renamed |
| `member_joined_channel` | `channel`, `users`, `inviter?` | User joins channel |
| `pin_added` | `channel`, `message_id`, `timestamp?` | Message pinned |
| `vote_cast` | `proposal_id`, `value` | Vote on proposal |

**⚠️ proposal_id**: Most scripts use `"proposal_" + message_id` pattern!

---

## Assertion Types

### Actions

| Type | Expected Fields | Checks |
|------|----------------|--------|
| `action_taken` | `action_type` | Action executed (status=PASSED) |
| `no_action_taken` | `action_type` | Action NOT executed |
| `action_count` | `action_type`, `count` | Exact count |

**Critical**: Only `ctx.execute_action()` adds to action log. `ctx.emit_action()` alone won't pass `action_taken`.

### Messages

| Type | Expected Fields | Checks |
|------|----------------|--------|
| `message_posted` | `channel_id?`, `contains?` | Message posted |

**DM to user**: Use user ID as `channel_id`.

### Data

| Type | Expected Fields | Checks |
|------|----------------|--------|
| `store_equals` | `key`, `value` | Data store value |
| `event_count` | `event_type`, `count` | Event count |

### Documents

| Type | Expected Fields | Checks |
|------|----------------|--------|
| `document_written` | `url` | Write occurred |
| `document_contains` | `url`, `conditions` | Contains matching data |
| `document_row_count` | `url`, `count` | Row count |
| `document_row_matches_schema` | `url`, `required_columns` | Schema validation |

---

## Common Patterns

### Vote Approval (2 votes needed)

```json
{
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "Proposal", "channel": "ch1"}, "actor_id": "u1", "at": 1.0},
    {"type": "vote_cast", "data": {"proposal_id": "proposal_m1", "value": "yes"}, "actor_id": "mod1", "at": 5.0},
    {"type": "vote_cast", "data": {"proposal_id": "proposal_m1", "value": "yes"}, "actor_id": "mod2", "at": 10.0}
  ],
  "assertions": [
    {"type": "message_posted", "expected": {"contains": "vote"}, "description": "Vote prompt"},
    {"type": "action_taken", "expected": {"action_type": "approve_proposal"}, "description": "Executed"}
  ]
}
```

### Vote Rejection

```json
{
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "Proposal", "channel": "ch1"}, "actor_id": "u1", "at": 1.0},
    {"type": "vote_cast", "data": {"proposal_id": "proposal_m1", "value": "no"}, "actor_id": "mod1", "at": 5.0}
  ],
  "assertions": [
    {"type": "no_action_taken", "expected": {"action_type": "approve_proposal"}, "description": "Not executed"}
  ]
}
```

### Scheduled Expiry (24 hours)

```json
{
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "Proposal", "channel": "ch1"}, "actor_id": "u1", "at": 1.0}
    // Advance to 86461.0 (86400 + 61s buffer for scheduler that checks every 60s)
  ],
  "assertions": [
    {"type": "message_posted", "expected": {"channel_id": "u1", "contains": "expired"}, "description": "User notified"},
    {"type": "no_action_taken", "expected": {"action_type": "execute_proposal"}, "description": "Not executed"}
  ],
  "time_limit": 87000.0
}
```

### User Notification (DM)

```json
{
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "u1",  // User ID = DM
        "contains": "Your proposal was rejected"
      },
      "description": "User notified via DM"
    }
  ]
}
```

### Rate Limiting

```json
{
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "1", "channel": "ch1"}, "actor_id": "u1", "at": 1.0},
    {"type": "message_posted", "data": {"message_id": "m2", "text": "2", "channel": "ch1"}, "actor_id": "u1", "at": 5.0},
    {"type": "message_posted", "data": {"message_id": "m3", "text": "3", "channel": "ch1"}, "actor_id": "u1", "at": 10.0},
    {"type": "message_posted", "data": {"message_id": "m4", "text": "4", "channel": "ch1"}, "actor_id": "u1", "at": 15.0},
    {"type": "message_posted", "data": {"message_id": "m5", "text": "5", "channel": "ch1"}, "actor_id": "u1", "at": 20.0}
  ],
  "assertions": [
    {"type": "action_taken", "expected": {"action_type": "mute_user"}, "description": "User muted"}
  ]
}
```

### External Document

```json
{
  "community_setup": {
    "documents": {
      "https://docs.google.com/spreadsheets/d/abc": {
        "schema": {
          "source_type": "google_sheets",
          "source_url": "https://docs.google.com/spreadsheets/d/abc",
          "structure": {"columns": ["timestamp", "user", "text"]},
          "sample_data": [],
          "metadata": {}
        },
        "initial_data": [
          {"timestamp": "2024-01-01", "user": "Alice", "text": "Initial data"}
        ]
      }
    }
  },
  "assertions": [
    {"type": "document_written", "expected": {"url": "https://docs.google.com/spreadsheets/d/abc"}},
    {"type": "document_contains", "expected": {"url": "https://docs.google.com/spreadsheets/d/abc", "conditions": {"user": "Bob"}}}
  ]
}
```

---

## Best Practices

### ✅ Do
- Use short IDs: `u1`, `ch1`, `m1`
- Keep setup minimal (only what's needed)
- Test ONE rule per scenario
- Add assertion descriptions
- Buffer scheduled checks (+61s if checking every 60s)
- Match proposal_id pattern (`"proposal_" + message_id`)

### ❌ Don't
- Long IDs: `"user_12345_alice_smith"`
- Unnecessary data: emails, metadata
- Multiple concerns in one scenario
- Forget time buffers for scheduled tasks
- Use `action_taken` for messages (use `message_posted`)
- Assume proposal_id patterns (check script!)

---

## Critical Reminders

1. **Actions vs Messages**
   - `ctx.emit_action()` → action PROPOSED (not in log yet)
   - `ctx.execute_action()` → action PASSED (in log, `action_taken` passes)
   - `ctx.post_message()` → message posted (use `message_posted` assertion)

2. **Proposal IDs**
   - Scripts use: `ctx.start_vote(f"proposal_{message_id}", action)`
   - Tests must use: `{"proposal_id": "proposal_m1"}`
   - NOT: `{"proposal_id": "m1"}`

3. **DMs to Users**
   - Script: `ctx.post_message(user_id, "text")`
   - Test: `{"type": "message_posted", "expected": {"channel_id": "u1"}}`

4. **Scheduled Task Timing**
   - If checking every 60s and deadline is 86400s
   - Advance to 86461s (deadline + 61s buffer)
   - Set `time_limit` higher than longest `at` timestamp

5. **Document Setup**
   - Include in `community_setup.documents`
   - Provide `schema` + `initial_data`
   - Use document assertions to verify writes

---

## Script API Reference

| Method | Usage |
|--------|-------|
| `ctx.on(event_type, handler)` | Register event handler |
| `ctx.schedule(interval, handler)` | Schedule recurring task |
| `ctx.emit_action(type, **kwargs)` | Create action (PROPOSED) |
| `ctx.execute_action(action)` | Execute action (→ log) |
| `ctx.start_vote(proposal_id, action)` | Start vote |
| `ctx.cast_vote(proposal_id, voter, value)` | Cast vote |
| `ctx.post_message(channel_id, text)` | Post message |
| `ctx.read_document(url)` | Read document |
| `ctx.write_document(url, data, mode)` | Write document |
| `ctx.query_document(url, conditions)` | Query document |
| `ctx.store.get(key)` | Get from store |
| `ctx.store.set(key, value)` | Set in store |

---

## Full Guide

See [test-scenario-guide.md](test-scenario-guide.md) for detailed documentation with complete examples.
