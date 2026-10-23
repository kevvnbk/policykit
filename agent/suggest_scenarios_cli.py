"""
Try the scenario suggestion endpoint from the command line.

AWS credentials are taken from the environment (AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, optional AWS_SESSION_TOKEN, AWS_REGION/AWS_DEFAULT_REGION).
If those aren't set, or --profile is given, they come from the boto3 credential
chain, so an SSO login (`aws sso login --profile X`) works.

Usage:
    python suggest_scenarios_cli.py "policy text..."
    python suggest_scenarios_cli.py --policy-file policy.txt
    python suggest_scenarios_cli.py --policy-file policy.txt --script-file script.py
    python suggest_scenarios_cli.py --policy-file policy.txt --json
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_FALLBACK_PROFILE = "bedrock"


def resolve_credentials(profile: str | None) -> dict:
    """
    Resolve AWS credentials: env vars first, then the boto3 credential chain
    (profiles, SSO login via `aws sso login`, etc.).
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    if not profile and os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        creds = {
            "aws_access_key_id": os.environ["AWS_ACCESS_KEY_ID"],
            "aws_secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        }
        if os.environ.get("AWS_SESSION_TOKEN"):
            creds["aws_session_token"] = os.environ["AWS_SESSION_TOKEN"]
        creds["aws_region"] = region or "us-east-1"
        return creds

    import boto3

    # Explicit --profile, else AWS_PROFILE/default chain, else the "bedrock"
    # profile (same fallback as llm_client.py).
    candidates = [profile] if profile else [None, DEFAULT_FALLBACK_PROFILE]
    session = frozen = None
    errors = []
    for name in candidates:
        try:
            session = boto3.Session(profile_name=name)
            found = session.get_credentials()
            frozen = found.get_frozen_credentials() if found else None
        except Exception as e:
            errors.append(f"{name or 'default'}: {e}")
            continue
        if frozen:
            break

    if not frozen:
        detail = f" ({'; '.join(errors)})" if errors else ""
        sys.exit(
            f"No AWS credentials found{detail}. Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, "
            "or run `aws sso login --profile <name>` and pass --profile <name> (or set AWS_PROFILE)."
        )

    creds = {
        "aws_access_key_id": frozen.access_key,
        "aws_secret_access_key": frozen.secret_key,
        "aws_region": region or session.region_name or "us-east-1",
    }
    if frozen.token:
        creds["aws_session_token"] = frozen.token
    return creds


def build_request_body(policy_text: str, script: str | None, profile: str | None) -> dict:
    body = {"policy_text": policy_text, **resolve_credentials(profile)}
    if script:
        body["script"] = script
    return body


def post_json(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {url}: {e.reason}")


def print_result(result: dict) -> None:
    print("FOCUS AREAS")
    for f in result["focus_areas"]:
        print(f"  [{f.get('id')}] {f.get('title')}: {f.get('why')}")

    for i, s in enumerate(result["scenarios"], 1):
        print(f"\n{'=' * 70}\nScenario {i}: {s.get('title')}  (covers {', '.join(s.get('covers', []))})")
        print(f"{s.get('summary')}")
        print(f"Participants: {s.get('participants')}")
        if s.get("prerequisites"):
            print(f"Prerequisites: {s['prerequisites']}")
        print(f"Duration: {s.get('estimated_duration')}")
        print("Steps:")
        for n, step in enumerate(s.get("steps", []), 1):
            print(f"  {n}. {step.get('actor')}: {step.get('action')}")
        print(f"Expected outcome: {s.get('expected_outcome')}")
        print(f"Look for: {s.get('what_to_look_for')}")

    print(f"\n{len(result['scenarios'])} scenarios, "
          f"{result['tokens_used']} tokens, {result['latency_ms']:.0f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("policy", nargs="?", help="Policy text (or use --policy-file)")
    parser.add_argument("--policy-file", help="Read policy text from this file")
    parser.add_argument("--script-file", help="Optional script to make scenarios implementation-specific")
    parser.add_argument("--profile", help="AWS profile to use (e.g. your SSO profile); default: env vars, then AWS_PROFILE/default")
    parser.add_argument("--url", default="http://localhost:8002", help="Agent base URL")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of formatted text")
    parser.add_argument("--timeout", type=float, default=300, help="Request timeout in seconds")
    args = parser.parse_args()

    if args.policy_file:
        with open(args.policy_file, encoding="utf-8") as f:
            policy_text = f.read().strip()
    elif args.policy:
        policy_text = args.policy
    else:
        parser.error("provide policy text or --policy-file")

    script = None
    if args.script_file:
        with open(args.script_file, encoding="utf-8") as f:
            script = f.read()

    body = build_request_body(policy_text, script, args.profile)
    result = post_json(f"{args.url.rstrip('/')}/scenarios/suggest", body, args.timeout)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
