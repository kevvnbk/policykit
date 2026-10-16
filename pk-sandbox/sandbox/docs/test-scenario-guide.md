# Test Scenario Writing Guide

Comprehensive guide to writing test scenarios for the sandbox policy execution engine.

---

## Table of Contents

1. [Overview](#overview)
2. [Scenario Structure](#scenario-structure)
3. [Community Setup](#community-setup)
4. [Events](#events)
5. [Assertions](#assertions)
6. [External Documents](#external-documents)
7. [Common Patterns](#common-patterns)
8. [Best Practices](#best-practices)
9. [Complete Examples](#complete-examples)

---

## Overview

### What Are Test Scenarios?

Test scenarios are **declarative test definitions** that specify:
- Initial community state (users, channels, roles)
- A sequence of events that trigger the policy
- Assertions to verify the policy behaved correctly

Scenarios are executed by the `SandboxRunner`, which:
1. Sets up the community state
2. Loads and executes your policy script's `setup()` function
3. Replays the event timeline
4. Checks all assertions

### Format

Scenarios are defined as **JSON arrays**:

```json
[
  {
    "name": "Delete spam messages",
    "description": "Messages containing 'spam' are deleted",
    "community_setup": { ... },
    "events": [ ... ],
    "assertions": [ ... ],
    "time_limit": 3600.0
  }
]
```

---

## Scenario Structure

### Schema

```typescript
interface Scenario {
  name: string;                    // Short name (e.g., "Delete spam")
  description?: string;             // One-line explanation
  community_setup: CommunitySetup;  // Initial state
  events: ScenarioEvent[];          // Event timeline
  assertions: Assertion[];          // Checks to verify
  time_limit?: number;              // Max seconds (default: 3600)
}
```

### Minimal Example

```json
{
  "name": "Welcome new member",
  "description": "Post welcome message when user joins",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]}
    ],
    "channels": [
      {"id": "ch-general", "name": "general", "members": ["u1"]}
    ]
  },
  "events": [
    {
      "type": "member_joined_channel",
      "data": {
        "channel": "ch-general",
        "users": ["u1"]
      },
      "actor_id": "u1",
      "at": 1.0
    }
  ],
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "ch-general",
        "contains": "welcome"
      },
      "description": "Welcome message posted"
    }
  ]
}
```

---

## Community Setup

### Structure

```typescript
interface CommunitySetup {
  users?: User[];
  channels?: Channel[];
  roles?: Role[];
  documents?: Record<string, DocumentSetup>;  // For external docs
}
```

### Users

```json
{
  "users": [
    {
      "id": "u1",              // Required: unique user ID
      "name": "Alice",         // Required: display name
      "roles": ["member"]      // Optional: role names
    },
    {
      "id": "mod1",
      "name": "Bob",
      "roles": ["moderator"]
    }
  ]
}
```

### Channels

```json
{
  "channels": [
    {
      "id": "ch-ann",          // Required: unique channel ID
      "name": "announcements", // Required: display name
      "members": ["u1", "mod1"] // Optional: member IDs
    }
  ]
}
```

### Roles

```json
{
  "roles": [
    {
      "name": "member",        // Required: role name
      "is_base_role": true     // Optional: default role for all users
    },
    {
      "name": "moderator",
      "is_base_role": false
    }
  ]
}
```

### Keep It Minimal

**✅ Good** (only what's needed):
```json
{
  "users": [
    {"id": "u1", "name": "Alice", "roles": ["member"]}
  ],
  "channels": [
    {"id": "ch1", "name": "general", "members": ["u1"]}
  ]
}
```

**❌ Bad** (unnecessary data):
```json
{
  "users": [
    {"id": "user_12345", "name": "Alice Smith", "roles": ["member", "verified", "premium"], "email": "alice@example.com"}
  ],
  "channels": [
    {"id": "channel_general_67890", "name": "general-discussion", "members": ["user_12345", "user_99999"], "topic": "General chat"}
  ]
}
```

**Use short IDs**: `u1`, `ch1`, `m1` instead of long descriptive IDs.

---

## Events

### Event Structure

```typescript
interface ScenarioEvent {
  type: string;           // Event type (see supported events below)
  data: Record<string, any>;  // Event-specific data
  actor_id?: string;      // Who triggered the event
  at: number;             // Timestamp (seconds from scenario start)
}
```

### Supported Event Types

#### 1. `message_posted`

User posts a message in a channel.

```json
{
  "type": "message_posted",
  "data": {
    "message_id": "m1",       // Required: unique message ID
    "text": "Hello world",    // Required: message content
    "channel": "ch-general",  // Required: channel ID
    "timestamp": 100.5        // Optional: override timestamp
  },
  "actor_id": "u1",
  "at": 1.0
}
```

#### 2. `message_renamed` (channel rename)

Channel name is changed.

```json
{
  "type": "message_renamed",
  "data": {
    "channel": "ch-proj",     // Required: channel ID
    "name": "new-name",       // Required: new name
    "previous_name": "old-name"  // Optional: previous name
  },
  "actor_id": "mod1",
  "at": 5.0
}
```

**Note**: Despite the name "message_renamed", this is for channel rename events. This mirrors Slack's event naming.

#### 3. `member_joined_channel`

User(s) join a channel.

```json
{
  "type": "member_joined_channel",
  "data": {
    "channel": "ch-general",  // Required: channel ID
    "users": ["u2"],          // Required: array of user IDs
    "inviter": "mod1"         // Optional: who invited them
  },
  "actor_id": "u2",           // Who joined (first user if multiple)
  "at": 10.0
}
```

#### 4. `pin_added`

Message is pinned in a channel.

```json
{
  "type": "pin_added",
  "data": {
    "channel": "ch-ann",      // Required: channel ID
    "message_id": "m5",       // Required: message being pinned
    "timestamp": 123.4        // Optional: when pinned
  },
  "actor_id": "mod1",
  "at": 15.0
}
```

#### 5. `vote_cast`

User casts a vote on a proposal.

```json
{
  "type": "vote_cast",
  "data": {
    "proposal_id": "proposal_m1",  // Required: matches script's proposal ID
    "value": "yes"                 // Required: vote value (yes/no/number)
  },
  "actor_id": "mod1",
  "at": 20.0
}
```

**⚠️ CRITICAL**: `proposal_id` must match how your script creates proposals!

Most scripts use: `"proposal_" + message_id`

```python
# Script creates proposal like this:
ctx.start_vote(f"proposal_{message_id}", action)

# So your test event MUST use:
{"proposal_id": "proposal_m1"}  # ✅ Correct
{"proposal_id": "m1"}           # ❌ Wrong - won't match
```

### Event Timing

Events are executed at specific timestamps (`at` field, in seconds):

```json
{
  "events": [
    {"type": "message_posted", "data": {...}, "at": 1.0},    // t=1s
    {"type": "vote_cast", "data": {...}, "at": 5.0},         // t=5s
    {"type": "vote_cast", "data": {...}, "at": 10.0}         // t=10s
  ]
}
```

**For scheduled tasks**: If policy checks expiry every 60 seconds and deadline is 86400s (24 hours), advance time to **86461** (deadline + buffer) to ensure scheduler runs after deadline:

```json
{
  "events": [
    {"type": "message_posted", "data": {...}, "at": 1.0},
    // 24 hours later + 61s buffer for scheduled check
    {"type": "advance_time", "at": 86461.0}
  ]
}
```

---

## Assertions

Assertions verify that the policy behaved correctly. All assertions must pass for the scenario to succeed.

### Assertion Structure

```typescript
interface Assertion {
  type: string;             // Assertion type (see below)
  expected: any;            // Expected value/criteria
  description?: string;     // Human-readable description
}
```

---

### Action Assertions

#### `action_taken`

Verify an action was **executed** (status = PASSED, in action log).

```json
{
  "type": "action_taken",
  "expected": {
    "action_type": "delete_message"
  },
  "description": "Message was deleted"
}
```

**⚠️ CRITICAL**: Only checks **executed** actions!

Actions are only executed when script calls `ctx.execute_action(action)`.

- ✅ Script calls `ctx.execute_action()` → action is logged → `action_taken` passes
- ❌ Script only calls `ctx.emit_action()` → action stays PROPOSED → `action_taken` fails
- ❌ Vote fails/expires → action not executed → `action_taken` fails

#### `no_action_taken`

Verify an action was **not** executed.

```json
{
  "type": "no_action_taken",
  "expected": {
    "action_type": "post_announcement"
  },
  "description": "Announcement was not posted (vote failed)"
}
```

Use this for:
- Failed votes
- Expired proposals
- Rejected actions

#### `action_count`

Verify exact number of actions of a specific type.

```json
{
  "type": "action_count",
  "expected": {
    "action_type": "delete_message",
    "count": 3
  },
  "description": "Exactly 3 messages deleted"
}
```

---

### Message Assertions

#### `message_posted`

Verify a message was posted (checks `ctx.post_message()` calls).

```json
{
  "type": "message_posted",
  "expected": {
    "channel_id": "ch-mods",     // Optional: specific channel
    "contains": "requires approval"  // Optional: text substring (case-insensitive)
  },
  "description": "Vote prompt posted to moderators"
}
```

**Common uses**:
- Vote prompts: `"Vote on this proposal"`
- User notifications (DMs): Use user ID as `channel_id`
- Announcements: Check announcement channel

**For DMs**: `channel_id` is the user ID:

```json
{
  "type": "message_posted",
  "expected": {
    "channel_id": "u1",           // Send to user u1
    "contains": "Your proposal expired"
  },
  "description": "User notified about expiry"
}
```

---

### Data Store Assertions

#### `store_equals`

Verify data store key has expected value.

```json
{
  "type": "store_equals",
  "expected": {
    "key": "last_check_time",
    "value": 86461.0
  },
  "description": "Last check time recorded"
}
```

Scripts use: `ctx.store.set(key, value)` / `ctx.store.get(key)`

---

### Event Bus Assertions

#### `event_count`

Verify number of events emitted.

```json
{
  "type": "event_count",
  "expected": {
    "event_type": "action_executed",
    "count": 2
  },
  "description": "Two actions executed"
}
```

Useful for verifying internal events, but most scenarios use action/message assertions instead.

---

### Document Assertions

For policies using external documents (Google Sheets, etc.).

#### `document_written`

Verify a write occurred to the document.

```json
{
  "type": "document_written",
  "expected": {
    "url": "https://docs.google.com/spreadsheets/d/abc123"
  },
  "description": "Data written to sheet"
}
```

#### `document_contains`

Verify document contains matching data.

```json
{
  "type": "document_contains",
  "expected": {
    "url": "https://docs.google.com/spreadsheets/d/abc123",
    "conditions": {
      "status": "pending",
      "votes": ">5"
    }
  },
  "description": "Sheet contains pending proposal with >5 votes"
}
```

#### `document_row_count`

Verify exact row count.

```json
{
  "type": "document_row_count",
  "expected": {
    "url": "https://docs.google.com/spreadsheets/d/abc123",
    "count": 5
  },
  "description": "Sheet has 5 rows"
}
```

#### `document_row_matches_schema`

Verify written rows have required columns.

```json
{
  "type": "document_row_matches_schema",
  "expected": {
    "url": "https://docs.google.com/spreadsheets/d/abc123",
    "required_columns": ["Timestamp", "channel_name", "purpose"]
  },
  "description": "All rows have required columns"
}
```

---

## External Documents

### Setup

Include documents in `community_setup`:

```json
{
  "community_setup": {
    "users": [...],
    "channels": [...],
    "documents": {
      "https://docs.google.com/spreadsheets/d/abc123": {
        "schema": {
          "source_type": "google_sheets",
          "source_url": "https://docs.google.com/spreadsheets/d/abc123",
          "structure": {
            "spreadsheet_title": "Channel Proposals",
            "columns": ["Timestamp", "email", "proposed channel name", "purpose", "temporary?"]
          },
          "sample_data": [],
          "metadata": {}
        },
        "initial_data": [
          {
            "Timestamp": "2024-01-01 12:00:00",
            "email": "alice@example.com",
            "proposed channel name": "data-science",
            "purpose": "Discuss data science topics",
            "temporary?": "no"
          }
        ]
      }
    }
  }
}
```

### Scripts Access Documents

Scripts use:
- `ctx.read_document(url)` - Read all rows
- `ctx.query_document(url, conditions)` - Filter rows
- `ctx.write_document(url, data, mode)` - Write rows

### Document Assertion Example

```json
{
  "name": "Record proposal in spreadsheet",
  "community_setup": {
    "users": [{"id": "u1", "name": "Alice", "roles": ["member"]}],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1"]}],
    "documents": {
      "https://docs.google.com/spreadsheets/d/proposals": {
        "schema": {
          "source_type": "google_sheets",
          "source_url": "https://docs.google.com/spreadsheets/d/proposals",
          "structure": {
            "columns": ["timestamp", "user", "proposal_text"]
          },
          "sample_data": [],
          "metadata": {}
        },
        "initial_data": []
      }
    }
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "I propose we add a new channel",
        "channel": "ch1"
      },
      "actor_id": "u1",
      "at": 1.0
    }
  ],
  "assertions": [
    {
      "type": "document_written",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/proposals"
      },
      "description": "Proposal recorded in spreadsheet"
    },
    {
      "type": "document_contains",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/proposals",
        "conditions": {
          "user": "Alice",
          "proposal_text": "I propose we add a new channel"
        }
      },
      "description": "Proposal data matches"
    }
  ]
}
```

---

## Common Patterns

### Pattern 1: Vote Approval

Test that a proposal requires votes and executes when threshold is met.

```json
{
  "name": "Approve with 2 yes votes",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]},
      {"id": "mod1", "name": "Bob", "roles": ["moderator"]},
      {"id": "mod2", "name": "Carol", "roles": ["moderator"]}
    ],
    "channels": [
      {"id": "ch-ann", "name": "announcements", "members": ["u1", "mod1", "mod2"]}
    ]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "Important announcement",
        "channel": "ch-ann"
      },
      "actor_id": "u1",
      "at": 1.0
    },
    {
      "type": "vote_cast",
      "data": {
        "proposal_id": "proposal_m1",
        "value": "yes"
      },
      "actor_id": "mod1",
      "at": 5.0
    },
    {
      "type": "vote_cast",
      "data": {
        "proposal_id": "proposal_m1",
        "value": "yes"
      },
      "actor_id": "mod2",
      "at": 10.0
    }
  ],
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "contains": "vote"
      },
      "description": "Vote prompt posted"
    },
    {
      "type": "action_taken",
      "expected": {
        "action_type": "post_announcement"
      },
      "description": "Announcement posted after approval"
    }
  ]
}
```

### Pattern 2: Vote Rejection

Test that action is NOT taken when vote fails.

```json
{
  "name": "Reject with 1 yes, 1 no",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]},
      {"id": "mod1", "name": "Bob", "roles": ["moderator"]},
      {"id": "mod2", "name": "Carol", "roles": ["moderator"]}
    ],
    "channels": [
      {"id": "ch-ann", "name": "announcements", "members": ["u1", "mod1", "mod2"]}
    ]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "Announcement",
        "channel": "ch-ann"
      },
      "actor_id": "u1",
      "at": 1.0
    },
    {
      "type": "vote_cast",
      "data": {"proposal_id": "proposal_m1", "value": "yes"},
      "actor_id": "mod1",
      "at": 5.0
    },
    {
      "type": "vote_cast",
      "data": {"proposal_id": "proposal_m1", "value": "no"},
      "actor_id": "mod2",
      "at": 10.0
    }
  ],
  "assertions": [
    {
      "type": "no_action_taken",
      "expected": {
        "action_type": "post_announcement"
      },
      "description": "Announcement not posted (vote failed)"
    }
  ]
}
```

### Pattern 3: Scheduled Expiry

Test time-based expiry with scheduled handlers.

```json
{
  "name": "Proposal expires after 24 hours",
  "community_setup": {
    "users": [{"id": "u1", "name": "Alice", "roles": ["member"]}],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1"]}]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "Proposal",
        "channel": "ch1"
      },
      "actor_id": "u1",
      "at": 1.0
    }
    // Advance time past 24 hours (86400s) + buffer for scheduler (61s)
    // Scheduler checks every 60s, so we need to go past the deadline check
    // No explicit event needed - just wait until 86461.0
  ],
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "u1",
        "contains": "expired"
      },
      "description": "User notified about expiry"
    },
    {
      "type": "no_action_taken",
      "expected": {
        "action_type": "execute_proposal"
      },
      "description": "Proposal not executed (expired)"
    }
  ],
  "time_limit": 87000.0
}
```

**Note**: Set `time_limit` higher than the longest `at` timestamp.

### Pattern 4: Rate Limiting

Test that user is muted after exceeding rate limit.

```json
{
  "name": "Mute user after 5 messages in 60 seconds",
  "community_setup": {
    "users": [{"id": "u1", "name": "Alice", "roles": ["member"]}],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1"]}]
  },
  "events": [
    {"type": "message_posted", "data": {"message_id": "m1", "text": "1", "channel": "ch1"}, "actor_id": "u1", "at": 1.0},
    {"type": "message_posted", "data": {"message_id": "m2", "text": "2", "channel": "ch1"}, "actor_id": "u1", "at": 5.0},
    {"type": "message_posted", "data": {"message_id": "m3", "text": "3", "channel": "ch1"}, "actor_id": "u1", "at": 10.0},
    {"type": "message_posted", "data": {"message_id": "m4", "text": "4", "channel": "ch1"}, "actor_id": "u1", "at": 15.0},
    {"type": "message_posted", "data": {"message_id": "m5", "text": "5", "channel": "ch1"}, "actor_id": "u1", "at": 20.0}
  ],
  "assertions": [
    {
      "type": "action_taken",
      "expected": {
        "action_type": "mute_user"
      },
      "description": "User muted after 5 messages"
    }
  ]
}
```

### Pattern 5: User Notification (DM)

Test that user receives a direct message.

```json
{
  "name": "Notify author when proposal is rejected",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]},
      {"id": "mod1", "name": "Bob", "roles": ["moderator"]}
    ],
    "channels": [{"id": "ch1", "name": "general", "members": ["u1", "mod1"]}]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {"message_id": "m1", "text": "Proposal", "channel": "ch1"},
      "actor_id": "u1",
      "at": 1.0
    },
    {
      "type": "vote_cast",
      "data": {"proposal_id": "proposal_m1", "value": "no"},
      "actor_id": "mod1",
      "at": 5.0
    }
  ],
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "u1",              // DM to user u1
        "contains": "rejected"
      },
      "description": "User notified about rejection"
    }
  ]
}
```

---

## Best Practices

### ✅ Do

1. **Keep scenarios focused**: Test ONE policy rule per scenario
2. **Use short IDs**: `u1`, `ch1`, `m1` instead of long descriptive IDs
3. **Minimal setup**: Only include users/channels needed for the test
4. **Descriptive names**: `"Approve with 2 votes"` not `"Test 1"`
5. **Add descriptions**: Explain what each assertion checks
6. **Buffer scheduled checks**: Add 61s after deadline if checking every 60s
7. **Match proposal IDs**: Use `"proposal_" + message_id` pattern
8. **Test edge cases**: Zero votes, tied votes, expired proposals
9. **Verify both actions and messages**: Check `action_taken` AND `message_posted`

### ❌ Don't

1. **Don't test implementation details**: Test WHAT happens, not HOW
2. **Don't use long IDs**: `"user_12345_alice"` → `"u1"`
3. **Don't add unnecessary data**: Extra fields, emails, metadata
4. **Don't skip descriptions**: Makes failures hard to debug
5. **Don't assume proposal IDs**: Check script to see actual pattern
6. **Don't forget time buffers**: Scheduled tasks need time to run
7. **Don't mix concerns**: Keep each scenario focused on one rule
8. **Don't use `action_taken` for messages**: Use `message_posted` instead

### Common Mistakes

#### ❌ Wrong proposal_id

```json
// Script uses: ctx.start_vote(f"proposal_{message_id}", action)
{"type": "vote_cast", "data": {"proposal_id": "m1", "value": "yes"}}  // Wrong!
```

✅ Correct:
```json
{"type": "vote_cast", "data": {"proposal_id": "proposal_m1", "value": "yes"}}
```

#### ❌ Checking messages with action_taken

```json
// Scripts use ctx.post_message() which creates messages, NOT actions
{"type": "action_taken", "expected": {"action_type": "post_message"}}  // Wrong!
```

✅ Correct:
```json
{"type": "message_posted", "expected": {"contains": "vote on this"}}
```

#### ❌ No time buffer for scheduled tasks

```json
// Policy checks every 60s, deadline at 86400s
{"at": 86400.0}  // Wrong - scheduler hasn't run yet!
```

✅ Correct:
```json
{"at": 86461.0}  // 86400 + 61s buffer
```

---

## Complete Examples

### Example 1: Spam Detection

```json
{
  "name": "Delete spam messages",
  "description": "Messages containing 'spam' word are automatically deleted",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]}
    ],
    "channels": [
      {"id": "ch-gen", "name": "general", "members": ["u1"]}
    ]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "Check out this spam offer!",
        "channel": "ch-gen"
      },
      "actor_id": "u1",
      "at": 1.0
    }
  ],
  "assertions": [
    {
      "type": "action_taken",
      "expected": {
        "action_type": "delete_message"
      },
      "description": "Spam message deleted"
    }
  ]
}
```

### Example 2: Moderator Voting

```json
{
  "name": "Ban requires 3 moderator votes",
  "description": "Ban action executes only after 3 moderators approve",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Spammer", "roles": ["member"]},
      {"id": "mod1", "name": "Alice", "roles": ["moderator"]},
      {"id": "mod2", "name": "Bob", "roles": ["moderator"]},
      {"id": "mod3", "name": "Carol", "roles": ["moderator"]}
    ],
    "channels": [
      {"id": "ch-mods", "name": "moderators", "members": ["mod1", "mod2", "mod3"]},
      {"id": "ch-gen", "name": "general", "members": ["u1", "mod1", "mod2", "mod3"]}
    ],
    "roles": [
      {"name": "member", "is_base_role": true},
      {"name": "moderator", "is_base_role": false}
    ]
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "!ban u1 spamming",
        "channel": "ch-mods"
      },
      "actor_id": "mod1",
      "at": 1.0
    },
    {
      "type": "vote_cast",
      "data": {
        "proposal_id": "ban_u1",
        "value": "yes"
      },
      "actor_id": "mod1",
      "at": 5.0
    },
    {
      "type": "vote_cast",
      "data": {
        "proposal_id": "ban_u1",
        "value": "yes"
      },
      "actor_id": "mod2",
      "at": 10.0
    },
    {
      "type": "vote_cast",
      "data": {
        "proposal_id": "ban_u1",
        "value": "yes"
      },
      "actor_id": "mod3",
      "at": 15.0
    }
  ],
  "assertions": [
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "ch-mods",
        "contains": "vote"
      },
      "description": "Vote prompt posted to moderators"
    },
    {
      "type": "action_taken",
      "expected": {
        "action_type": "ban_user"
      },
      "description": "User banned after 3 votes"
    },
    {
      "type": "message_posted",
      "expected": {
        "channel_id": "ch-gen",
        "contains": "banned"
      },
      "description": "Ban announcement posted"
    }
  ]
}
```

### Example 3: External Document Integration

```json
{
  "name": "Record channel proposal in spreadsheet",
  "description": "New channel proposals are automatically recorded in Google Sheets",
  "community_setup": {
    "users": [
      {"id": "u1", "name": "Alice", "roles": ["member"]}
    ],
    "channels": [
      {"id": "ch-meta", "name": "meta", "members": ["u1"]}
    ],
    "documents": {
      "https://docs.google.com/spreadsheets/d/proposals123": {
        "schema": {
          "source_type": "google_sheets",
          "source_url": "https://docs.google.com/spreadsheets/d/proposals123",
          "structure": {
            "spreadsheet_title": "Channel Proposals",
            "columns": ["Timestamp", "email", "proposed channel name", "purpose", "temporary?"]
          },
          "sample_data": [],
          "metadata": {}
        },
        "initial_data": []
      }
    }
  },
  "events": [
    {
      "type": "message_posted",
      "data": {
        "message_id": "m1",
        "text": "I want to create #data-science for data discussions",
        "channel": "ch-meta"
      },
      "actor_id": "u1",
      "at": 1.0
    }
  ],
  "assertions": [
    {
      "type": "document_written",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/proposals123"
      },
      "description": "Proposal written to spreadsheet"
    },
    {
      "type": "document_contains",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/proposals123",
        "conditions": {
          "proposed channel name": "data-science"
        }
      },
      "description": "Spreadsheet contains channel name"
    },
    {
      "type": "document_row_matches_schema",
      "expected": {
        "url": "https://docs.google.com/spreadsheets/d/proposals123",
        "required_columns": ["Timestamp", "email", "proposed channel name", "purpose", "temporary?"]
      },
      "description": "Row has all required columns"
    }
  ]
}
```

---

## Quick Reference

### Event Types
- `message_posted` - User posts message
- `message_renamed` - Channel renamed (despite name)
- `member_joined_channel` - User joins channel
- `pin_added` - Message pinned
- `vote_cast` - Vote cast on proposal

### Assertion Types
- `action_taken` - Action executed
- `no_action_taken` - Action NOT executed
- `action_count` - Exact action count
- `message_posted` - Message posted (includes DMs)
- `store_equals` - Data store value check
- `event_count` - Event count
- `document_written` - Document write occurred
- `document_contains` - Document contains data
- `document_row_count` - Document row count
- `document_row_matches_schema` - Document schema validation

### Script API (for reference)
- `ctx.on(event_type, handler)` - Register event handler
- `ctx.schedule(interval, handler)` - Schedule recurring task
- `ctx.emit_action(type, **kwargs)` - Create action (PROPOSED)
- `ctx.execute_action(action)` - Execute action (→ action log)
- `ctx.start_vote(proposal_id, action)` - Start vote
- `ctx.cast_vote(proposal_id, voter_id, value)` - Cast vote
- `ctx.post_message(channel_id, text)` - Post message
- `ctx.read_document(url)` - Read external document
- `ctx.write_document(url, data, mode)` - Write external document
- `ctx.query_document(url, conditions)` - Query document

---

## See Also

- [Sandbox API Reference](api_reference.md) - Complete API documentation
- [Policy Authoring Guide](policy-authoring-guide.md) - Writing policy scripts
- [External Documents Guide](guides/external-documents-guide.md) - Google Sheets integration
