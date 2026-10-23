"""
LLM client for the agent.

Provides stage-specific generation functions using AWS Bedrock (Claude).
Prompt templates are organized in the prompts/ subpackage.

The agent uses this module to generate governance scripts via LLM calls.
"""

from __future__ import annotations
import json
import os
import time
import logging
from typing import Any

import boto3
from botocore.config import Config

from prompts import headers, script, tests, revise, suggestions

logger = logging.getLogger(__name__)

# Default model and token settings (can be overridden per call)
# Using cross-region inference profile for Claude Sonnet 4.5
# This uses on-demand throughput across multiple regions
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8000

# Models that don't accept temperature/top_p (extended thinking models)
_NO_SAMPLING_PARAMS_PATTERNS = ("opus-4-7", "opus-4-8", "opus-5")


def _supports_sampling_params(model_id: str) -> bool:
    model_lower = model_id.lower()
    return not any(p in model_lower for p in _NO_SAMPLING_PARAMS_PATTERNS)


def _call_bedrock(
    system_prompt: str,
    user_prompt: str,
    credentials: dict[str, str] | None = None,
    model_id: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """
    Call AWS Bedrock with the Anthropic Messages API format.

    Args:
        credentials: Dict with keys:
            - For IAM auth: access_key_id, secret_access_key, region, session_token (optional)
            - For bearer token auth: bearer_token, region

    Returns: {"text": str, "tokens_used": int, "latency_ms": float}
    """
    # Check if bearer token authentication is being used
    if credentials and "bearer_token" in credentials:
        import requests

        region = credentials.get("region", "us-east-1")
        bearer_token = credentials["bearer_token"]

        # Build request body for Converse API
        request_body = {
            "messages": [{"role": "user", "content": [{"text": user_prompt}]}]
        }

        if system_prompt:
            request_body["system"] = [{"text": system_prompt}]

        # Call Bedrock Converse API with bearer token (API key)
        url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse"

        start = time.time()
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}"
            },
            json=request_body,
            timeout=300
        )
        latency_ms = (time.time() - start) * 1000

        if response.status_code != 200:
            raise RuntimeError(f"Bedrock API error {response.status_code}: {response.text}")

        data = response.json()

        # Extract text from response
        message = data.get("output", {}).get("message", {})
        content_blocks = message.get("content", [])
        text = "\n".join(block["text"] for block in content_blocks if "text" in block)

        # Extract token usage
        usage = data.get("usage", {})
        tokens_used = usage.get("outputTokens", 0)

        return {"text": text, "tokens_used": tokens_used, "latency_ms": latency_ms}

    # IAM authentication (boto3)
    config = Config(read_timeout=300, connect_timeout=10, retries={"max_attempts": 2})

    if credentials:
        # Use user-provided IAM credentials
        client_kwargs = {
            "aws_access_key_id": credentials["access_key_id"],
            "aws_secret_access_key": credentials["secret_access_key"],
            "region_name": credentials.get("region", "us-east-1"),
            "config": config
        }
        # Add session token if provided (AWS SSO uses temporary credentials)
        if "session_token" in credentials:
            client_kwargs["aws_session_token"] = credentials["session_token"]

        client = boto3.client("bedrock-runtime", **client_kwargs)
    else:
        # Fallback to profile for local development
        profile = os.environ.get("AWS_PROFILE", "bedrock")
        session = boto3.Session(profile_name=profile, region_name="us-east-1")
        client = session.client("bedrock-runtime", config=config)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
    }
    if system_prompt:
        body["system"] = system_prompt
    if _supports_sampling_params(model_id):
        body["temperature"] = temperature

    start = time.time()
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    latency_ms = (time.time() - start) * 1000

    response_body = json.loads(response["body"].read())
    text = response_body["content"][0]["text"]
    tokens_used = response_body.get("usage", {}).get("output_tokens", 0)

    return {"text": text, "tokens_used": tokens_used, "latency_ms": latency_ms}


def _extract_python_code(text: str) -> str:
    """
    Extract Python code from LLM output, stripping markdown fences and explanation text.

    Handles various formats:
    - Code with ```python fences
    - Code with ``` fences
    - Code with explanation text before/after
    - Clean code without fences

    CRITICAL: Filters out non-code lines (prose/thoughts) that appear between functions.
    """
    # Try markdown fences first (most reliable)
    if "```python" in text:
        start = text.find("```python") + len("```python")
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()

    # No markdown fences - need to extract code from potential explanation text
    lines = text.split('\n')

    # Find the first line that starts with a Python keyword
    code_start_idx = None
    code_keywords = ('def ', 'class ', 'import ', 'from ', '@', 'if __name__')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(kw) for kw in code_keywords):
            code_start_idx = i
            break
        # Check if line looks like a comment or blank (could be before code)
        if stripped.startswith('#') or not stripped:
            continue
        # If we see 'def ' anywhere in the line, consider it code start
        if 'def ' in stripped or 'class ' in stripped:
            code_start_idx = i
            break

    if code_start_idx is None:
        # No clear Python code found, return original
        return text.strip()

    # Find the end of code (last line that looks like code)
    code_end_idx = len(lines) - 1
    for i in range(len(lines) - 1, code_start_idx, -1):
        stripped = lines[i].strip()
        if not stripped:
            continue
        # Stop if we hit trailing explanation text
        if stripped.startswith(('The problem', 'Looking at', 'I need', 'This ', 'Now ', 'Note:')):
            code_end_idx = i - 1
            continue
        # If it looks like code, this is the end
        if any(c in stripped for c in ('(', ')', ':', '=', '[', ']', '{', '}')):
            code_end_idx = i
            break
        if stripped.startswith(('def ', 'class ', 'return', 'if ', 'else:', 'elif ')) or line.startswith(('    ', '\t')):
            code_end_idx = i
            break

    # Extract code lines and filter out prose between functions
    code_lines = []
    in_function = False
    for i in range(code_start_idx, code_end_idx + 1):
        line = lines[i]
        stripped = line.strip()

        # Start of a function definition
        if stripped.startswith('def ') or stripped.startswith('class '):
            in_function = True
            code_lines.append(line)
            continue

        # Inside a function: keep everything (including comments)
        if in_function:
            # End of function: no indentation and not a blank line
            if stripped and not line.startswith((' ', '\t')) and not stripped.startswith('#'):
                # Check if it's a new function or prose
                if not any(stripped.startswith(kw) for kw in ('def ', 'class ', 'import ', 'from ', '@')):
                    # Looks like prose, skip it
                    in_function = False
                    continue
                else:
                    # It's a new function
                    code_lines.append(line)
                    continue
            code_lines.append(line)
            continue

        # Outside function: only keep blank lines, comments, and new function definitions
        if not stripped or stripped.startswith('#'):
            code_lines.append(line)
        elif stripped.startswith(('def ', 'class ', 'import ', 'from ', '@')):
            in_function = True
            code_lines.append(line)

    extracted = '\n'.join(code_lines).strip()

    # Validate that we got something that looks like code
    if 'def ' in extracted or 'class ' in extracted:
        return extracted

    # Fallback to original if extraction seems wrong
    return text.strip()


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM output, handling markdown fences."""
    clean = text.strip()
    if "```json" in clean:
        start = clean.find("```json") + len("```json")
        end = clean.find("```", start)
        if end != -1:
            clean = clean[start:end].strip()
    elif "```" in clean:
        start = clean.find("```") + 3
        end = clean.find("```", start)
        if end != -1:
            clean = clean[start:end].strip()

    brace_start = clean.find("{")
    bracket_start = clean.find("[")
    if brace_start == -1 and bracket_start == -1:
        return json.loads(clean)

    if bracket_start != -1 and (brace_start == -1 or bracket_start < brace_start):
        end = clean.rfind("]")
        return json.loads(clean[bracket_start:end + 1])
    else:
        end = clean.rfind("}")
        return json.loads(clean[brace_start:end + 1])


def generate_headers(
    policy_text: str,
    api_reference: str,
    credentials: dict[str, str] | None = None,
    document_schemas: dict | None = None
) -> dict[str, Any]:
    """
    Stage 1: Generate function headers from natural language policy.

    Args:
        policy_text: Natural language governance policy
        api_reference: Sandbox API reference documentation
        credentials: AWS credentials dict (access_key_id, secret_access_key, region) or (bearer_token, region)
        document_schemas: Optional dict mapping URLs to DocumentSchema objects

    Returns: {"headers": str, "raw_output": str, "tokens_used": int, "latency_ms": float}
    """
    # Get prompts from module
    system_prompt, user_prompt = headers.format_prompt(
        policy_text, api_reference, document_schemas
    )

    result = _call_bedrock(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        credentials=credentials,
        temperature=0.3,
        max_tokens=2000,
    )

    headers_code = _extract_python_code(result["text"])

    return {
        "headers": headers_code,
        "raw_output": result["text"],
        "tokens_used": result["tokens_used"],
        "latency_ms": result["latency_ms"],
    }


def generate_script(
    policy_text: str,
    headers: str,
    api_reference: str,
    credentials: dict[str, str] | None = None,
    document_schemas: dict | None = None
) -> dict[str, Any]:
    """
    Stage 2: Generate implementation script from headers + policy + API ref.

    Args:
        policy_text: Natural language governance policy
        headers: Function headers from stage 1
        api_reference: Sandbox API reference documentation
        credentials: AWS credentials dict (access_key_id, secret_access_key, region) or (bearer_token, region)
        document_schemas: Optional dict mapping URLs to DocumentSchema objects

    Returns: {"script": str, "raw_output": str, "tokens_used": int, "latency_ms": float}
    """
    # Get prompts from module
    system_prompt, user_prompt = script.format_prompt(
        policy_text, headers, api_reference, document_schemas
    )

    result = _call_bedrock(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        credentials=credentials,
        temperature=0.2,
        max_tokens=8000,
    )

    script_code = _extract_python_code(result["text"])

    return {
        "script": script_code,
        "raw_output": result["text"],
        "tokens_used": result["tokens_used"],
        "latency_ms": result["latency_ms"],
    }


def generate_tests(
    policy_text: str,
    headers: str,
    api_reference: str,
    credentials: dict[str, str] | None = None,
    document_schemas: dict | None = None
) -> dict[str, Any]:
    """
    Stage 3: Generate test scenarios from headers + policy (never sees the script).

    Args:
        policy_text: Natural language governance policy
        headers: Function headers from stage 1
        api_reference: Sandbox API reference documentation
        credentials: AWS credentials dict (access_key_id, secret_access_key, region) or (bearer_token, region)
        document_schemas: Optional dict mapping URLs to DocumentSchema objects

    Returns: {"scenarios": list[dict], "raw_output": str, "tokens_used": int, "latency_ms": float}
    """
    # Get prompts from module
    system_prompt, user_prompt = tests.format_prompt(
        policy_text, headers, api_reference, document_schemas
    )

    result = _call_bedrock(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        credentials=credentials,
        temperature=0.3,
        max_tokens=8000,
    )

    parse_error = None
    try:
        scenarios_json = _extract_json(result["text"])
        if not isinstance(scenarios_json, list):
            scenarios_json = [scenarios_json]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse test scenarios JSON: {e}")
        parse_error = str(e)
        scenarios_json = []

    return {
        "scenarios": scenarios_json,
        "parse_error": parse_error,
        "raw_output": result["text"],
        "tokens_used": result["tokens_used"],
        "latency_ms": result["latency_ms"],
    }


def generate_scenario_suggestions(
    policy_text: str,
    script_code: str | None = None,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Stage 7: Suggest natural-language scenarios users can try in their real community.

    Independent of the sandbox test scenarios; the output is for humans only.

    Args:
        policy_text: Natural language governance policy
        script_code: Optional final implemented script (policy-only if omitted)
        credentials: AWS credentials dict (access_key_id, secret_access_key, region) or (bearer_token, region)

    Returns: {"focus_areas": list[dict], "scenarios": list[dict], "parse_error": str | None,
              "raw_output": str, "tokens_used": int, "latency_ms": float}
    """
    system_prompt, user_prompt = suggestions.format_prompt(policy_text, script_code)

    result = _call_bedrock(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        credentials=credentials,
        temperature=0.5,
        max_tokens=8000,
    )

    parse_error = None
    focus_areas: list[dict] = []
    scenarios: list[dict] = []
    try:
        parsed = _extract_json(result["text"])
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object with focus_areas and scenarios")
        focus_areas = parsed.get("focus_areas", [])
        scenarios = parsed.get("scenarios", [])
        if not isinstance(focus_areas, list) or not isinstance(scenarios, list):
            raise ValueError("focus_areas and scenarios must be lists")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse scenario suggestions JSON: {e}")
        parse_error = str(e)
        focus_areas, scenarios = [], []

    return {
        "focus_areas": focus_areas,
        "scenarios": scenarios,
        "parse_error": parse_error,
        "raw_output": result["text"],
        "tokens_used": result["tokens_used"],
        "latency_ms": result["latency_ms"],
    }


def revise_script(
    policy_text: str,
    script: str,
    error_summary: str,
    api_reference: str,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Stage 5: Revise a failing script given structured error feedback.

    Args:
        policy_text: Natural language governance policy
        script: Current script with bugs
        error_summary: Structured error feedback from failed test runs
        api_reference: Sandbox API reference documentation
        credentials: AWS credentials dict (access_key_id, secret_access_key, region) or (bearer_token, region)

    Returns: {"script": str, "raw_output": str, "tokens_used": int, "latency_ms": float}
    """
    # Get prompts from module
    system_prompt, user_prompt = revise.format_prompt(
        policy_text, script, error_summary, api_reference
    )

    result = _call_bedrock(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        credentials=credentials,
        temperature=0.2,
        max_tokens=8000,
    )

    fixed_script = _extract_python_code(result["text"])

    return {
        "script": fixed_script,
        "raw_output": result["text"],
        "tokens_used": result["tokens_used"],
        "latency_ms": result["latency_ms"],
    }
