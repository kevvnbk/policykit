#!/usr/bin/env python3
"""
Standalone test client for deployed Sandbox Pipeline API.

Usage:
    # With IAM credentials (boto3 credential chain)
    python test_client.py --url https://api.yourdomain.com --test basic
    python test_client.py --url https://api.yourdomain.com --test comprehensive
    python test_client.py --url https://api.yourdomain.com --policy "Your custom policy"

    # With AWS bearer token
    python test_client.py --url https://api.yourdomain.com --bearer-token YOUR_TOKEN --test basic
    python test_client.py --url https://api.yourdomain.com --bearer-token YOUR_TOKEN --region us-east-2 --policy "Delete spam"
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    import requests
except ImportError:
    print("Error: requests library not found")
    print("Install with: pip install requests")
    sys.exit(1)

try:
    import boto3
except ImportError:
    print("Error: boto3 library not found")
    print("Install with: pip install boto3")
    sys.exit(1)


class TestResult(Enum):
    PASS = "✓ PASS"
    FAIL = "✗ FAIL"


@dataclass
class TestCase:
    name: str
    policy_text: str
    expected_success: bool
    should_have_script: bool
    description: str


class SandboxTestClient:
    """Test client for deployed Sandbox Pipeline API."""

    def __init__(self, base_url: str, aws_credentials: Dict[str, str]):
        self.base_url = base_url.rstrip('/')
        self.credentials = aws_credentials
        self.results = []

    def run_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        print(f"\n{'='*70}")
        print(f"Test: {test_case.name}")
        print(f"Description: {test_case.description}")
        print(f"Policy: {test_case.policy_text[:100]}...")
        print(f"{'='*70}")

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.base_url}/execute",
                json={
                    "policy_text": test_case.policy_text,
                    **self.credentials
                },
                timeout=600
            )

            elapsed = time.time() - start_time

            if response.status_code != 200:
                print(f"{TestResult.FAIL.value}: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                self.results.append((test_case.name, TestResult.FAIL, f"HTTP {response.status_code}"))
                return TestResult.FAIL

            data = response.json()

            # Validate response structure
            if "success" not in data:
                print(f"{TestResult.FAIL.value}: Missing 'success' field")
                self.results.append((test_case.name, TestResult.FAIL, "Invalid response structure"))
                return TestResult.FAIL

            # Check success expectation
            if data["success"] != test_case.expected_success:
                print(f"{TestResult.FAIL.value}: Expected success={test_case.expected_success}, got {data['success']}")
                print(f"Error: {data.get('error')}")
                self.results.append((test_case.name, TestResult.FAIL, f"Success mismatch"))
                return TestResult.FAIL

            # Check script expectation
            has_script = data.get("script") is not None
            if has_script != test_case.should_have_script:
                print(f"{TestResult.FAIL.value}: Expected script={test_case.should_have_script}, got {has_script}")
                self.results.append((test_case.name, TestResult.FAIL, "Script expectation mismatch"))
                return TestResult.FAIL

            # Additional validations for successful cases
            if data["success"]:
                script = data.get("script", "")
                if not script or len(script) < 50:
                    print(f"{TestResult.FAIL.value}: Script too short or empty")
                    self.results.append((test_case.name, TestResult.FAIL, "Invalid script"))
                    return TestResult.FAIL

                # Check for required script patterns
                if "def setup(ctx)" not in script:
                    print(f"{TestResult.FAIL.value}: Script missing setup function")
                    self.results.append((test_case.name, TestResult.FAIL, "Invalid script structure"))
                    return TestResult.FAIL

            # Print results
            print(f"\n{TestResult.PASS.value}: Test passed in {elapsed:.1f}s")
            print(f"Success: {data['success']}")
            print(f"Has Script: {has_script}")
            if data.get("script"):
                print(f"Script Length: {len(data['script'])} chars")
                print(f"\nScript Preview (first 300 chars):")
                print("-" * 70)
                print(data["script"][:300])
                if len(data["script"]) > 300:
                    print("...")
                print("-" * 70)
            if data.get("error"):
                print(f"Error: {data['error']}")

            self.results.append((test_case.name, TestResult.PASS, f"{elapsed:.1f}s"))
            return TestResult.PASS

        except requests.exceptions.Timeout:
            print(f"{TestResult.FAIL.value}: Request timeout")
            self.results.append((test_case.name, TestResult.FAIL, "Timeout"))
            return TestResult.FAIL
        except Exception as e:
            print(f"{TestResult.FAIL.value}: {type(e).__name__}: {e}")
            self.results.append((test_case.name, TestResult.FAIL, str(e)))
            return TestResult.FAIL

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        for name, result, detail in self.results:
            print(f"{result.value:12} | {name:30} | {detail}")

        passed = sum(1 for _, r, _ in self.results if r == TestResult.PASS)
        failed = sum(1 for _, r, _ in self.results if r == TestResult.FAIL)

        print("="*70)
        print(f"Total: {len(self.results)} | Passed: {passed} | Failed: {failed}")
        print("="*70)

        return failed == 0


# Test cases
TEST_CASES = {
    "basic": [
        TestCase(
            name="Simple Spam Filter",
            policy_text="Delete any message that contains the word 'spam'",
            expected_success=True,
            should_have_script=True,
            description="Basic message filtering policy"
        ),
    ],

    "comprehensive": [
        TestCase(
            name="Simple Spam Filter",
            policy_text="Delete any message that contains the word 'spam'",
            expected_success=True,
            should_have_script=True,
            description="Basic message filtering policy"
        ),
        TestCase(
            name="Voting Policy",
            policy_text="When someone posts a message with 'propose:', start a vote. If the vote passes with 60% approval, post a confirmation message.",
            expected_success=True,
            should_have_script=True,
            description="Voting-based governance"
        ),
        TestCase(
            name="Time-based Policy",
            policy_text="Every 24 hours, check all channels. If a channel has had no messages for 7 days, post a reminder to the channel.",
            expected_success=True,
            should_have_script=True,
            description="Scheduled task with state tracking"
        ),
    ]
}


def test_health(base_url: str):
    """Test health endpoint."""
    print(f"\nTesting health endpoint: {base_url}/health")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print(f"✓ Health check passed: {response.json()}")
            return True
        else:
            print(f"✗ Health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test deployed Sandbox Pipeline API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick basic test (IAM credentials)
  python test_client.py --url https://api.example.com --test basic

  # Full test suite (IAM credentials)
  python test_client.py --url https://api.example.com --test comprehensive

  # Custom policy test (IAM credentials)
  python test_client.py --url https://api.example.com --policy "Delete spam"

  # Using bearer token
  python test_client.py --url https://api.example.com --bearer-token YOUR_TOKEN --test basic

  # Bearer token with custom region
  python test_client.py --url https://api.example.com --bearer-token YOUR_TOKEN --region us-east-2 --test basic

  # Local testing
  python test_client.py --url http://localhost:8001 --test basic

AWS Authentication:
  Option 1: IAM Credentials (boto3 credential chain)
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - AWS credentials file (~/.aws/credentials with [bedrock] profile)
    - AWS_PROFILE environment variable to override profile name

  Option 2: Bearer Token
    - Use --bearer-token flag with your AWS bearer token
    - Optionally specify --region (default: us-east-1)
        """
    )

    parser.add_argument("--url", required=True, help="Base URL of deployed API")
    parser.add_argument("--test", choices=["basic", "comprehensive", "all"],
                       help="Run predefined test suite")
    parser.add_argument("--policy", help="Test a custom policy")
    parser.add_argument("--skip-health", action="store_true", help="Skip health check")
    parser.add_argument("--bearer-token", help="Use AWS bearer token instead of IAM credentials")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")

    args = parser.parse_args()

    # Get AWS credentials
    if args.bearer_token:
        # Bearer token authentication
        credentials = {
            "aws_bearer_token": args.bearer_token,
            "aws_region": args.region
        }
        credential_display = f"Bearer token: {args.bearer_token[:10]}..."
        aws_region = args.region
    else:
        # IAM credential authentication using boto3's credential chain
        # This will automatically use: env vars, ~/.aws/credentials, IAM roles, etc.
        try:
            profile = os.environ.get("AWS_PROFILE", "bedrock")
            session = boto3.Session(profile_name=profile)
            credentials_obj = session.get_credentials()

            if credentials_obj is None:
                print("Error: AWS credentials not found")
                print("\nOptions:")
                print("1. Set environment variables:")
                print("   export AWS_ACCESS_KEY_ID='your-key'")
                print("   export AWS_SECRET_ACCESS_KEY='your-secret'")
                print("\n2. Configure AWS CLI:")
                print("   aws configure --profile bedrock")
                print("\n3. Use existing AWS credentials file:")
                print("   ~/.aws/credentials should contain [bedrock] profile")
                print("\n4. Use bearer token:")
                print("   python test_client.py --bearer-token YOUR_TOKEN --url ...")
                sys.exit(1)

            credentials = {
                "aws_access_key_id": credentials_obj.access_key,
                "aws_secret_access_key": credentials_obj.secret_key,
                "aws_region": session.region_name or args.region
            }

            # Add session token if present (AWS SSO uses temporary credentials)
            if credentials_obj.token:
                credentials["aws_session_token"] = credentials_obj.token

            credential_display = f"IAM Access Key: {credentials_obj.access_key[:10]}..."
            aws_region = credentials["aws_region"]

        except Exception as e:
            print(f"Error loading AWS credentials: {e}")
            print("\nPlease configure AWS credentials using one of:")
            print("1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
            print("2. AWS credentials file (~/.aws/credentials)")
            print("3. AWS CLI: aws configure --profile bedrock")
            print("4. Bearer token: --bearer-token YOUR_TOKEN")
            sys.exit(1)

    print("="*70)
    print("SANDBOX PIPELINE API TEST CLIENT")
    print("="*70)
    print(f"Target URL: {args.url}")
    print(f"AWS Region: {aws_region}")
    print(f"Auth Method: {credential_display}")

    # Health check
    if not args.skip_health:
        if not test_health(args.url):
            print("\nWarning: Health check failed. Continue? (y/n): ", end="")
            if input().lower() != 'y':
                sys.exit(1)

    # Initialize client
    client = SandboxTestClient(args.url, credentials)

    # Run tests
    if args.policy:
        # Custom policy test
        test_case = TestCase(
            name="Custom Policy",
            policy_text=args.policy,
            expected_success=True,
            should_have_script=True,
            description="User-provided custom policy"
        )
        client.run_test(test_case)

    elif args.test:
        # Run predefined test suite
        if args.test == "all":
            # Run all test suites
            for suite_name, test_cases in TEST_CASES.items():
                print(f"\n{'#'*70}")
                print(f"# Running {suite_name.upper()} test suite")
                print(f"{'#'*70}")
                for test_case in test_cases:
                    client.run_test(test_case)
        else:
            # Run specific suite
            test_cases = TEST_CASES.get(args.test, [])
            for test_case in test_cases:
                client.run_test(test_case)

    else:
        print("\nError: Must specify --test or --policy")
        parser.print_help()
        sys.exit(1)

    # Print summary
    success = client.print_summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
