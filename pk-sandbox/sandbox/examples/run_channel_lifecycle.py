#!/usr/bin/env python3
"""
Run the channel lifecycle example through the sandbox pipeline.

Usage:
    python examples/run_channel_lifecycle.py

Requires AWS credentials configured (via environment or .aws/credentials)
"""

import json
import sys
from pathlib import Path

# Add sandboxengine to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sandboxengine.policyengine.tasks import PipelineOrchestrator
from sandboxengine.policyengine.datasources import DocumentSchema


def load_example():
    """Load the channel lifecycle API request."""
    example_path = Path(__file__).parent / "channel_lifecycle_api_request.json"
    with open(example_path) as f:
        return json.load(f)


def convert_documents_to_schemas(documents):
    """Convert API document format to DocumentSchema objects."""
    schemas = {}
    for doc in documents:
        schema = DocumentSchema(
            source_type=doc["source_type"],
            source_url=doc["source_url"],
            structure=doc["structure"],
            sample_data=doc["sample_data"],
            metadata=doc["metadata"]
        )
        schemas[doc["source_url"]] = schema
    return schemas


def main():
    print("="*70)
    print("Channel Lifecycle Management - Sandbox Pipeline Test")
    print("="*70)
    print()

    # Load example
    print("Loading example...")
    data = load_example()
    print(f"  Policy length: {len(data['nl_policy'])} characters")
    print(f"  Documents: {len(data['documents'])}")
    print()

    # Convert documents
    print("Converting documents to schemas...")
    document_schemas = convert_documents_to_schemas(data["documents"])
    print(f"  Converted {len(document_schemas)} document(s)")
    print()

    # Show document info
    for url, schema in document_schemas.items():
        print(f"  Document: {schema.structure.get('spreadsheet_title', 'Untitled')}")
        print(f"    Columns: {len(schema.structure.get('columns', []))}")
        print(f"    Sample data rows: {len(schema.sample_data)}")
        print()

    # Create orchestrator
    print("Creating pipeline orchestrator...")
    orchestrator = PipelineOrchestrator(max_revisions=3)

    # Create run
    print("Creating pipeline run...")
    run = orchestrator.create_run(data["nl_policy"], document_schemas)
    print(f"  Run ID: {run.id}")
    print()

    # Check for credentials
    import os
    has_bearer = os.getenv("AWS_BEARER_TOKEN")
    has_profile = os.getenv("AWS_PROFILE")
    has_keys = os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")

    if not (has_bearer or has_profile or has_keys):
        print("WARNING: No AWS credentials found!")
        print()
        print("To run the pipeline, you need AWS Bedrock credentials.")
        print("Options:")
        print("  1. Set AWS_BEARER_TOKEN environment variable")
        print("  2. Set AWS_PROFILE environment variable")
        print("  3. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        print("  4. Configure ~/.aws/credentials with [bedrock] profile")
        print()
        print("Example:")
        print('  export AWS_BEARER_TOKEN="your-token-here"')
        print(f'  python {sys.argv[0]}')
        print()
        sys.exit(1)

    # Prepare credentials
    credentials = None
    if has_bearer:
        print("Using bearer token authentication")
        credentials = {
            "bearer_token": os.getenv("AWS_BEARER_TOKEN"),
            "region": os.getenv("AWS_REGION", "us-east-1")
        }
    elif has_keys:
        print("Using IAM credentials")
        credentials = {
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region": os.getenv("AWS_REGION", "us-east-1")
        }
        if os.getenv("AWS_SESSION_TOKEN"):
            credentials["session_token"] = os.getenv("AWS_SESSION_TOKEN")
    else:
        print("Using AWS profile")
        credentials = None  # Will use default profile

    print()
    print("-"*70)
    print("EXECUTING PIPELINE")
    print("-"*70)
    print()

    # Execute pipeline
    try:
        print("Stage 1: Generating function headers...")
        print("Stage 2: Generating script implementation...")
        print("Stage 3: Generating test scenarios...")
        print("Stage 4: Executing tests...")
        print()
        print("This may take 30-60 seconds...")
        print()

        final_run = orchestrator.execute_full_sync(
            run_id=run.id,
            credentials=credentials,
            timeout=600.0
        )

        print()
        print("="*70)
        print("PIPELINE RESULTS")
        print("="*70)
        print()
        print(f"Status: {final_run.status}")
        print(f"Revisions: {final_run.revision_count}")
        print()

        # Show stage results
        for stage_name, stage in final_run.stages.items():
            if stage.status.value == "completed":
                print(f"  ✓ {stage_name}: {stage.status.value}")
            elif stage.status.value == "failed":
                print(f"  ✗ {stage_name}: {stage.status.value}")
                if stage.error:
                    print(f"      Error: {stage.error}")
            elif stage.status.value == "skipped":
                print(f"  - {stage_name}: {stage.status.value}")

        print()

        # Extract script
        script_stage = final_run.stages.get("script")
        if script_stage and script_stage.output:
            script = script_stage.output.get("script", "")

            print("-"*70)
            print("GENERATED SCRIPT")
            print("-"*70)
            print()
            print(script)
            print()

            # Save to file
            output_path = Path(__file__).parent / "channel_lifecycle_generated.py"
            with open(output_path, 'w') as f:
                f.write(script)
            print(f"Script saved to: {output_path}")
            print()

        # Show test results
        execute_stage = final_run.stages.get("execute")
        if execute_stage and execute_stage.output:
            results = execute_stage.output.get("results", [])
            print("-"*70)
            print(f"TEST RESULTS ({len(results)} scenarios)")
            print("-"*70)
            print()

            for result in results:
                status = "✓ PASS" if result.get("passed") else "✗ FAIL"
                print(f"  {status}: {result.get('scenario_name')}")
                if not result.get("passed"):
                    print(f"      Error: {result.get('error', 'Unknown error')}")
            print()

        # Overall success
        if final_run.status == "completed":
            print("="*70)
            print("✅ SUCCESS - Pipeline completed successfully!")
            print("="*70)
        else:
            print("="*70)
            print(f"❌ FAILED - Pipeline status: {final_run.status}")
            print("="*70)

    except TimeoutError:
        print()
        print("❌ ERROR: Pipeline timed out after 10 minutes")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
