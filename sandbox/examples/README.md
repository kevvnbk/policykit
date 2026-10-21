# Examples - Channel Lifecycle Management

This directory contains a complete example demonstrating external document integration with the sandbox.

## Files

- **`channel_lifecycle_api_request.json`** - Complete API request body
- **`EXAMPLE_EXPLANATION.md`** - Detailed explanation of the policy
- **`run_channel_lifecycle.py`** - Script to run the example through the pipeline

## Running the Example

### Prerequisites

You need AWS Bedrock credentials to run the pipeline. Choose one option:

**Option 1: Bearer Token (API Key)**
```bash
export AWS_BEARER_TOKEN="your-token-here"
export AWS_REGION="us-east-1"  # optional, defaults to us-east-1
```

**Option 2: IAM Credentials**
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

**Option 3: AWS Profile**
```bash
# Configure ~/.aws/credentials with a [bedrock] profile
export AWS_PROFILE="bedrock"
```

### Run the Pipeline

```bash
cd sandbox
python examples/run_channel_lifecycle.py
```

### What It Does

The script will:
1. Load the channel lifecycle policy (1,995 characters)
2. Load the Google Sheets document schema (7 columns, 5 sample rows)
3. Execute the full pipeline:
   - **Stage 1**: Generate function headers
   - **Stage 2**: Generate script implementation
   - **Stage 3**: Generate test scenarios
   - **Stage 4**: Execute tests
   - **Stage 5**: Revise if needed (up to 3 attempts)
4. Save the generated script to `channel_lifecycle_generated.py`
5. Show test results

### Expected Output

```
======================================================================
Channel Lifecycle Management - Sandbox Pipeline Test
======================================================================

Loading example...
  Policy length: 1995 characters
  Documents: 1

Converting documents to schemas...
  Converted 1 document(s)

  Document: Channel Proposals
    Columns: 7
    Sample data rows: 5

Creating pipeline orchestrator...
Creating pipeline run...
  Run ID: abc12345

----------------------------------------------------------------------
EXECUTING PIPELINE
----------------------------------------------------------------------

Stage 1: Generating function headers...
Stage 2: Generating script implementation...
Stage 3: Generating test scenarios...
Stage 4: Executing tests...

This may take 30-60 seconds...

======================================================================
PIPELINE RESULTS
======================================================================

Status: completed
Revisions: 0

  ✓ headers: completed
  ✓ script: completed
  ✓ tests: completed
  ✓ execute: completed
  - revise: skipped
  ✓ report: completed

----------------------------------------------------------------------
GENERATED SCRIPT
----------------------------------------------------------------------

CHANNEL_PROPOSALS_URL = "https://docs.google.com/spreadsheets/d/..."

def setup(ctx):
    # Schedule daily check at noon
    ctx.schedule(86400, check_new_proposals, recurring=True)
    # ... rest of script

Script saved to: examples/channel_lifecycle_generated.py

----------------------------------------------------------------------
TEST RESULTS (5 scenarios)
----------------------------------------------------------------------

  ✓ PASS: new_proposal_approval
  ✓ PASS: unanimous_approval_creates_channel
  ✓ PASS: partial_approval_rejects
  ✓ PASS: inactive_channel_notice
  ✓ PASS: moderator_overrule

======================================================================
✅ SUCCESS - Pipeline completed successfully!
======================================================================
```

### Estimated Time

- **Pipeline execution**: 30-60 seconds
- **Token usage**: ~8,000-12,000 tokens
- **Cost**: ~$0.02-0.05 (depending on model)

## Policy Details

### Input: Google Sheets Document

**Columns**:
- Timestamp
- email (requester)
- proposed channel name
- purpose of channel
- temporary? (yes/no)
- proposed expiry date
- additional comments

**Sample Data**: 5 realistic channel proposals

### Policy Rules

**Rule 1: Create New Temporary Channels**
- Daily check at noon
- Read new proposals from spreadsheet
- Filter malformed data
- Select 3 random moderators
- Collect thumbs-up reactions for 24 hours
- Create channel if unanimously approved (3/3)
- Schedule archival at expiry date

**Rule 2: Remove Inactive Temporary Channels**
- Monthly check on 1st of month
- Find temporary channels with no activity (30 days)
- Post 24-hour removal notice
- Notify moderators
- Allow "overruled" responses
- Archive non-overruled channels

### Generated Script Features

The pipeline will generate a script with:
- ✅ URL constants (`CHANNEL_PROPOSALS_URL`)
- ✅ Document reads (`ctx.read_document()`)
- ✅ Document writes (`ctx.write_document()`)
- ✅ Document queries (`ctx.query_document()`)
- ✅ Scheduled handlers (daily, monthly)
- ✅ Event handlers (message, vote_cast)
- ✅ State tracking (pending approvals, pending removals)
- ✅ Moderator selection logic
- ✅ Voting workflows with reactions
- ✅ Channel creation and archival

### Generated Tests

The pipeline will generate ~5-7 test scenarios:
- New proposal triggers moderator DMs
- Unanimous approval creates channel
- Partial approval rejects proposal
- Inactive channel gets removal notice
- Moderator overrule prevents archival
- Document reads work correctly
- Document writes work correctly

## Troubleshooting

### "No AWS credentials found"
- Set one of the credential options listed above
- Verify with: `aws sts get-caller-identity` (if using AWS CLI)

### "Pipeline timed out"
- Default timeout is 10 minutes
- LLM calls can be slow depending on load
- Try again or check AWS Bedrock service status

### "Generation failed"
- Check that the model ID in `sandboxengine/settings.py` is correct
- Verify credentials have Bedrock permissions
- Check AWS region matches where model is available

### "Tests failed"
- This is expected on first attempt sometimes
- Pipeline will auto-revise (up to 3 attempts)
- Check the error message for details

## Next Steps

After running the example:

1. **Review the generated script**: `examples/channel_lifecycle_generated.py`
2. **Check test results**: See which scenarios passed/failed
3. **Modify the policy**: Edit `channel_lifecycle_api_request.json` and re-run
4. **Try your own policy**: Create a new JSON file with your policy + documents

## Related Documentation

- **Implementation Summary**: `../docs/PHASE_2_3_IMPLEMENTATION_SUMMARY.md`
- **External Documents Plan**: `../docs/external-documents-plan.md`
- **Google Sheets Implementation**: `../docs/google-sheets-implementation.md`
- **Policy Authoring Guide**: `../docs/policy-authoring-guide.md`
