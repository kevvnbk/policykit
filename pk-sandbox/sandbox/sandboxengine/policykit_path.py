"""
PolicyKit Path Setup

This module ensures PolicyKit is available for import by adding it to sys.path.
Must be imported before any policyengine imports.

Usage:
    import policykit_path  # Must be first
    from policyengine.safe_exec_code import execute_user_code
"""
import sys
from pathlib import Path

# Get the path to the PolicyKit repository
# Assuming structure: pkwrapper/policykit/policykit/policykit/
REPO_ROOT = Path(__file__).parent.parent.parent
POLICYKIT_ROOT = REPO_ROOT / "policykit" / "policykit" / "policykit"

if not POLICYKIT_ROOT.exists():
    raise ImportError(
        f"PolicyKit not found at {POLICYKIT_ROOT}. "
        "Ensure the PolicyKit repository is cloned at the expected location."
    )

# Add PolicyKit to sys.path if not already there
policykit_path_str = str(POLICYKIT_ROOT)
if policykit_path_str not in sys.path:
    sys.path.insert(0, policykit_path_str)

# Verify import works
try:
    import policyengine  # noqa: F401
except ImportError as e:
    raise ImportError(
        f"Failed to import policyengine from {POLICYKIT_ROOT}. "
        f"Original error: {e}"
    )
