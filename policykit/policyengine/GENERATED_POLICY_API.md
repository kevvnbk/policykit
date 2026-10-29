# Generated policy API (for script generators)

How an external script generator (e.g. pk-sandbox) learns what a PolicyKit
generated-policy script can use, and how scripts get deployed. Three pieces:

| What                                                       | Where                                          | Changes when             |
| ---------------------------------------------------------- | ---------------------------------------------- | ------------------------ |
| **Capabilities manifest**: `ctx` methods, events, actions  | `generated_policy_manifest.json` (this folder) | PolicyKit's code changes |
| **Deployment context**: platform, channels, roles, members | `GET /api/generated_policies/context`          | The community changes    |
| **Deploy**: install a generated script                     | `POST /api/generated_policies/deploy`          | n/a                      |

The manifest is generated from the runtime's code and is the source
of truth for those.

---

## 1. Capabilities manifest

### Getting it

Fetch it from GitHub, pinned to a commit so it only changes when you choose to update:

```
https://raw.githubusercontent.com/kevvnbk/policykit/<commit>/policykit/policyengine/generated_policy_manifest.json
```

It's regenerated with `python manage.py export_script_manifest`. A PolicyKit
test fails if the committed file doesn't match the code, so the file at any
commit is accurate for that commit.

### Shape

```jsonc
{
  "platform": "slack",
  "ctx_methods": [
    // everything on ctx and ctx.store
    {
      "name": "ctx.post_message",
      "signature": "ctx.post_message(target_id, text)",
      "description": "Post text to a channel ID, or DM a user by passing their user ID.",
    },
  ],
  "event_attributes": ["type", "data", "actor_id", "timestamp"],
  "events": [
    // what ctx.on(...) can subscribe to
    {
      "type": "message_posted",
      "data_fields": [
        "action_type",
        "text",
        "channel_id",
        "timestamp",
        "message_id",
      ],
    },
  ],
  "actions": [
    // what ctx.execute_action(...) can run
    {
      "type": "slackpinmessage",
      "description": "Pin Message",
      "params": [
        {
          "name": "channel",
          "label": "Channel",
          "required": true,
          "type": "string",
          "entity": "SlackChannel",
        },
        {
          "name": "timestamp",
          "label": "Timestamp of the pinned message",
          "required": true,
          "type": "timestamp",
          "entity": "Timestamp",
        },
      ],
    },
  ],
}
```

---

## 2. Deployment context

```
GET <POLICYKIT_URL>/api/generated_policies/context
X-Deploy-Secret: <shared secret>
```

```json
{
  "platform": "slack",
  "community_name": "Example Workspace",
  "channels": [
    { "id": "C0123ABCD", "name": "general" },
    { "id": "C0456EFGH", "name": "introductions" }
  ],
  "roles": ["Base User", "Integration Admin"],
  "member_count": 30
}
```

- **`channels`:** scripts must compare channel **IDs**, never names. Use this
  list to turn a channel name from the policy text into its ID. It currently
  covers public channels only, and only the first page Slack returns.
- **`roles`:** PolicyKit role names, which are what `ctx.get_user(...).roles`
  returns at runtime. These are **not** Slack's owner/admin/member. A script
  that checks `"member" in user.roles` will never match unless a PolicyKit role
  is literally named `member`.
- **`member_count`:** non-bot members of the Slack workspace, as reported by
  Slack. It includes deactivated accounts.

| Status | Meaning                                                         |
| ------ | --------------------------------------------------------------- |
| 200    | OK                                                              |
| 403    | Missing or wrong `X-Deploy-Secret`                              |
| 500    | Server not configured (secret or target community)              |
| 502    | PolicyKit couldn't reach the platform. Body: `{"error": "..."}` |

Request for the deploy secret. The target community is fixed by
server configuration (`POLICYKIT_DEPLOY_COMMUNITY_ID`).

---

## 3. Deploy (used by policy-llm today)

```
POST <POLICYKIT_URL>/api/generated_policies/deploy
X-Deploy-Secret: <shared secret>
Content-Type: application/json

{"name": "Spam filter", "script_code": "def setup(ctx):\n    ..."}
```

On success (`201`):

```json
{
  "success": true,
  "policy_id": 42,
  "action_types": ["slackpostmessage"],
  "unmapped_event_types": []
}
```

What deploying does:

- Creates the policy (always as a _platform_ policy) and runs `setup(ctx)`
  **once**, for real. If `setup(ctx)` raises, nothing is kept.
- `setup(ctx)` must register at least one handler for an event type listed in
  the manifest's `events`, otherwise the deploy is rejected. Event types that
  aren't in the manifest come back in `unmapped_event_types`, and those
  handlers will never fire.

Errors: `400` (`{"error": "script rejected: ..."}` or `"script failed to
install: ..."`), `403`, `500`, same meanings as above.
