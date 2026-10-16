# Channel Lifecycle Management - Example Explanation

## Overview

This example demonstrates a complex, real-world policy that combines:
- **External document integration** (Google Sheets for channel requests)
- **Scheduled execution** (daily noon checks, monthly inactive channel checks)
- **Multi-step approval workflows** (moderator voting via reactions)
- **Time-based actions** (24-hour windows, expiry dates)
- **Channel management** (creation, archival)
- **Multi-channel communication** (DMs to moderators, channel announcements)

## Policy Components

### Rule 1: Create New Temporary Channels

**Trigger**: Daily scheduled check at noon

**Data Source**: Google Sheets spreadsheet with columns:
- Timestamp
- email (requester)
- proposed channel name
- purpose of channel
- temporary? (yes/no)
- proposed expiry date
- additional comments

**Workflow**:
1. Read new rows from spreadsheet (rows not yet processed)
2. Filter malformed data (missing required fields)
3. Select 3 random moderators
4. Send each moderator a DM with request details
5. Wait 24 hours for thumbs-up reactions (👍)
6. If 3/3 approve → create channel
7. Post welcome message in new channel
8. DM requester with outcome
9. Schedule archival at expiry date (if configured)

**Edge Cases**:
- Malformed rows (missing data)
- Not enough moderators available
- Ties or partial approvals
- Duplicate channel names
- Invalid expiry dates
- Channels with no expiry date

### Rule 2: Remove Inactive Temporary Channels

**Trigger**: Monthly scheduled check (1st of month)

**Conditions**:
- Channel is marked as temporary
- No configured expiry date (open-ended temporary)
- No messages in last 30 days

**Workflow**:
1. Query all temporary channels
2. Check message activity for last 30 days
3. Post 24-hour notice in inactive channels
4. DM all moderators with list of channels
5. Monitor for "overruled" responses
6. After 24 hours, archive non-overruled channels

**Edge Cases**:
- Moderator overrules during 24-hour window
- Channel becomes active during notice period
- Multiple moderators overrule same channel

## API Request Structure

### Key Fields

**`nl_policy`** (string):
- Full text of the natural language policy
- Includes WHEN/PROCEDURE sections
- Documents edge cases and timing constraints
- References spreadsheet columns by name

**`documents`** (array):
- Each document includes:
  - `source_type`: "google_sheets"
  - `source_url`: Full URL to spreadsheet
  - `structure`: Metadata (title, sheet names, columns)
  - `sample_data`: 5 example rows showing data format
  - `metadata`: Technical details (IDs, row counts)

**`options`** (object):
- `generate_document_tests`: true (create document-specific tests)
- `complexity`: "high" (hint to LLM about script complexity)
- `description`: Human-readable summary

## Expected Generated Script Structure

```python
PROPOSALS_URL = "https://docs.google.com/spreadsheets/d/..."

def setup(ctx):
    # Schedule daily noon check for new proposals
    ctx.schedule(86400, check_new_proposals, recurring=True)
    
    # Schedule monthly check for inactive channels (first of month)
    ctx.schedule(2592000, check_inactive_channels, recurring=True)
    
    # Listen for moderator overrules
    ctx.on("message", handle_overrule)

def check_new_proposals(ctx):
    # Read spreadsheet
    proposals = ctx.read_document(PROPOSALS_URL)
    
    # Filter unprocessed rows
    new_proposals = [p for p in proposals if not is_processed(ctx, p)]
    
    # Filter malformed data
    valid_proposals = [p for p in new_proposals if is_valid(p)]
    
    for proposal in valid_proposals:
        # Select 3 random moderators
        moderators = select_random_moderators(ctx, 3)
        
        # Send approval requests
        for mod in moderators:
            ctx.post_message(
                channel=mod['dm_channel'],
                text=format_approval_request(proposal)
            )
        
        # Track proposal in datastore
        ctx.store.set(f"proposal_{proposal['Timestamp']}", {
            "status": "pending_approval",
            "moderators": moderators,
            "timestamp": ctx.current_time
        })

def check_inactive_channels(ctx):
    # Get all temporary channels
    channels = [c for c in ctx.get_channels() if is_temporary(c)]
    
    # Filter: no expiry date + no activity in 30 days
    inactive = [c for c in channels 
                if not has_expiry(c) and not has_recent_activity(ctx, c, days=30)]
    
    for channel in inactive:
        # Post 24-hour notice
        ctx.post_message(
            channel=channel['id'],
            text=f"⚠️ This channel will be archived in 24 hours due to inactivity. "
                 f"Moderators can reply 'overruled' to prevent archival."
        )
        
        # Track pending removal
        ctx.store.set(f"pending_removal_{channel['id']}", {
            "channel": channel,
            "notice_time": ctx.current_time,
            "overruled": False
        })
    
    # Notify moderators
    moderators = get_moderators(ctx)
    for mod in moderators:
        ctx.post_message(
            channel=mod['dm_channel'],
            text=format_inactive_list(inactive)
        )

def handle_overrule(event, ctx):
    # Check if message is "overruled" from a moderator
    if event.data['text'].lower() == 'overruled':
        user = ctx.get_user(event.data['author'])
        if 'moderator' in user.roles:
            channel_id = event.data['channel']
            key = f"pending_removal_{channel_id}"
            if ctx.store.get(key):
                # Mark as overruled
                ctx.store.set(key, {
                    **ctx.store.get(key),
                    "overruled": True
                })
```

## Expected Test Scenarios

### Standard Tests (3-5)

1. **New proposal approval flow**
   - Setup: Empty spreadsheet
   - Event: Add proposal row
   - Assert: 3 moderators receive DMs

2. **Unanimous approval creates channel**
   - Setup: Pending proposal with 3 moderators
   - Event: 3 thumbs-up reactions
   - Assert: Channel created, requester notified

3. **Partial approval rejects proposal**
   - Setup: Pending proposal
   - Event: 2 thumbs-up, 1 no reaction
   - Assert: Channel not created, requester notified

4. **Inactive channel gets archived**
   - Setup: Temporary channel, no messages in 30 days
   - Event: Monthly check trigger
   - Assert: Notice posted, scheduled for archival

5. **Moderator overrule prevents archival**
   - Setup: Channel pending removal
   - Event: Moderator posts "overruled"
   - Assert: Channel not archived

### Document Tests (2-3)

1. **Read new proposals from spreadsheet**
   - Setup: Spreadsheet with 3 new rows
   - Event: Daily check
   - Assert: 3 proposals read correctly

2. **Write processing status back to spreadsheet**
   - Setup: Spreadsheet with unprocessed proposals
   - Event: Process proposals
   - Assert: Status column updated

3. **Query unprocessed proposals only**
   - Setup: Mixed processed/unprocessed proposals
   - Event: Query for unprocessed
   - Assert: Only unprocessed returned

## Complexity Indicators

**High complexity due to**:
- Multiple scheduling requirements (daily, monthly)
- External data source reads/writes
- Multi-step approval workflows
- Time-based windows (24 hours)
- State tracking (pending approvals, pending removals)
- Role-based permissions (moderators)
- Reaction-based voting
- Channel lifecycle management
- Error handling (malformed data, missing moderators)

**Estimated script size**: 300-400 lines

**Estimated test scenarios**: 8-10 total (5 standard + 3 document)

## Usage

```bash
# Send this to the sandbox API
POST http://localhost:8001/api/generate_policy
Content-Type: application/json

<contents of channel_lifecycle_api_request.json>
```

## Expected Response

```json
{
  "pipeline_id": "pipe-abc123",
  "status": "success",
  "script": "... generated Python code ...",
  "scenarios": [
    {
      "name": "new_proposal_approval",
      "type": "standard",
      "passed": true,
      ...
    },
    {
      "name": "document_read_proposals",
      "type": "document",
      "passed": true,
      ...
    }
  ],
  "document_usage": {
    "https://docs.google.com/.../1wrNwj5SVu_...": {
      "reads": 5,
      "writes": 2,
      "queries": 3
    }
  },
  "validation": {
    "syntax_valid": true,
    "imports_valid": true,
    "all_tests_passed": true
  }
}
```
