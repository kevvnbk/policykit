"""
HTTP client for communicating with the sandbox API.

The agent uses this client to execute and validate scripts without
directly importing sandbox code. This enables clean separation and
distributed deployment.

The sandbox must be installed as a package:
    pip install -e ../sandbox
"""

import requests
from typing import List
import logging

# Import scenario types - use local stubs if sandbox package not available
try:
    from sandbox.sandboxengine.policyengine.scenarios import Scenario, ScenarioResult
    from sandbox.sandboxengine.policyengine.validation import ValidationResult
except ImportError:
    from types_stub import Scenario, ScenarioResult, ValidationResult

logger = logging.getLogger(__name__)


class SandboxClient:
    """
    Client for the sandbox HTTP API.

    Provides methods to execute scripts and validate code against
    the sandbox without direct imports.
    """

    def __init__(self, sandbox_url: str = "http://localhost:8001"):
        """
        Initialize sandbox client.

        Args:
            sandbox_url: Base URL of the sandbox API (default: http://localhost:8001)
        """
        self.base_url = sandbox_url.rstrip("/")

    def execute(self, script: str, scenarios: List[Scenario]) -> List[ScenarioResult]:
        """
        Execute a script against test scenarios.

        Args:
            script: Python policy script
            scenarios: List of test scenarios

        Returns:
            List of scenario results

        Raises:
            requests.RequestException: If HTTP request fails
            RuntimeError: If sandbox returns an error
        """
        url = f"{self.base_url}/sandbox/execute"

        payload = {
            "script": script,
            "scenarios": [s.to_dict() for s in scenarios]
        }

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()

            data = response.json()
            results = [ScenarioResult.from_dict(r) for r in data["results"]]

            logger.info(
                f"Sandbox executed {len(scenarios)} scenarios. "
                f"Passed: {sum(1 for r in results if r.passed)}/{len(results)}"
            )

            return results

        except requests.RequestException as e:
            logger.error(f"Sandbox execution request failed: {e}")
            raise RuntimeError(f"Failed to execute in sandbox: {e}") from e

    def validate(self, script: str) -> "ValidationResult":
        """
        Validate a script's structure without executing it.

        Args:
            script: Python policy script

        Returns:
            Validation result with errors and warnings

        Raises:
            requests.RequestException: If HTTP request fails
            RuntimeError: If sandbox returns an error
        """
        url = f"{self.base_url}/sandbox/validate"

        payload = {"script": script}

        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Reconstruct ValidationResult from response
            # Note: We import ValidationResult for type hints but construct from dict
            return ValidationResult.from_dict(data)

        except requests.RequestException as e:
            logger.error(f"Sandbox validation request failed: {e}")
            raise RuntimeError(f"Failed to validate in sandbox: {e}") from e

    def get_api_reference(self) -> str:
        """
        Get the sandbox API reference documentation.

        This is used to inject into LLM prompts to teach the model
        how to write scripts.

        Returns:
            API reference as markdown text

        Raises:
            requests.RequestException: If HTTP request fails
        """
        url = f"{self.base_url}/sandbox/api-reference"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data.get("content", "")

        except requests.RequestException as e:
            logger.error(f"Failed to fetch API reference: {e}")
            raise RuntimeError(f"Failed to get API reference: {e}") from e

    def health_check(self) -> bool:
        """
        Check if sandbox is reachable and healthy.

        Returns:
            True if sandbox is healthy, False otherwise
        """
        url = f"{self.base_url}/sandbox/health"

        try:
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False
