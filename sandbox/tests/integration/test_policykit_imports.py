"""
Test script to verify PolicyKit imports work correctly.
Run this to ensure the migration to direct PolicyKit imports is successful.
"""
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).parent.parent.parent.parent
POLICYKIT_DIR = REPO_ROOT / "policykit"

if not POLICYKIT_DIR.exists():
    print(f"ERROR: PolicyKit not found at {POLICYKIT_DIR}")
    sys.exit(1)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

print("Testing PolicyKit imports...")
print(f"PolicyKit path: {POLICYKIT_DIR}")
print("=" * 60)

# Test 1: Import from PolicyKit's policyengine.safe_exec_code
print("\n1. Testing safe_exec_code imports from PolicyKit...")
try:
    from policykit.policyengine.safe_exec_code import (
        execute_user_code,
        policykit_builtins,
        STATIC_GLOBAL_VARIABLES,
        OwnRestrictingNodeTransformer,
    )
    print("   [OK] execute_user_code imported")
    print("   [OK] policykit_builtins imported")
    print("   [OK] STATIC_GLOBAL_VARIABLES imported")
    print("   [OK] OwnRestrictingNodeTransformer imported")

    # Verify types
    assert callable(execute_user_code), "execute_user_code should be callable"
    assert isinstance(policykit_builtins, dict), "policykit_builtins should be a dict"
    assert isinstance(STATIC_GLOBAL_VARIABLES, dict), "STATIC_GLOBAL_VARIABLES should be a dict"
    assert isinstance(OwnRestrictingNodeTransformer, type), "OwnRestrictingNodeTransformer should be a class"

    print("   [OK] All type checks passed")
except Exception as e:
    print(f"   [X] Failed: {e}")
    sys.exit(1)

# Test 2: Verify policykit_builtins contents
print("\n2. Testing policykit_builtins contents...")
try:
    expected_builtins = ['datetime', 'base64', 'itertools', 'json']
    for builtin in expected_builtins:
        assert builtin in policykit_builtins, f"{builtin} should be in policykit_builtins"
        print(f"   [OK] {builtin} found in policykit_builtins")
except Exception as e:
    print(f"   [X] Failed: {e}")
    sys.exit(1)

# Test 3: Verify STATIC_GLOBAL_VARIABLES
print("\n3. Testing STATIC_GLOBAL_VARIABLES...")
try:
    assert STATIC_GLOBAL_VARIABLES.get("PASSED") == "passed"
    assert STATIC_GLOBAL_VARIABLES.get("PROPOSED") == "proposed"
    assert STATIC_GLOBAL_VARIABLES.get("FAILED") == "failed"
    print("   [OK] PASSED constant defined")
    print("   [OK] PROPOSED constant defined")
    print("   [OK] FAILED constant defined")
except Exception as e:
    print(f"   [X] Failed: {e}")
    sys.exit(1)

# Test 4: Test execute_user_code functionality
print("\n4. Testing execute_user_code functionality...")
try:
    test_code = """
def test_func(x, y):
    return x + y
"""
    result = execute_user_code(test_code, "test_func", x=5, y=3)
    assert result == 8, f"Expected 8, got {result}"
    print(f"   [OK] execute_user_code returned correct result: {result}")
except Exception as e:
    print(f"   [X] Failed: {e}")
    sys.exit(1)

# Test 5: Test that restricted imports fail
print("\n5. Testing RestrictedPython import restrictions...")
try:
    bad_code = """
def bad_func():
    import os
    return os.getcwd()
"""
    try:
        execute_user_code(bad_code, "bad_func")
        print("   [X] Failed: Import restriction not working!")
        sys.exit(1)
    except SyntaxError as e:
        if "Import statements are not allowed" in str(e):
            print("   [OK] Import restriction working correctly")
        else:
            print(f"   [X] Unexpected error: {e}")
            sys.exit(1)
except Exception as e:
    print(f"   [X] Failed: {e}")
    sys.exit(1)

# Test 6: Optional - Test engine imports (if needed)
print("\n6. Testing optional engine imports...")
try:
    from policykit.policyengine.engine import AttrDict
    print("   [OK] AttrDict imported from policyengine.engine")

    # Test AttrDict functionality
    test_dict = AttrDict({"a": 1, "b": 2})
    assert test_dict.a == 1, "AttrDict attribute access failed"
    assert test_dict["b"] == 2, "AttrDict dict access failed"
    print("   [OK] AttrDict functionality verified")
except Exception as e:
    print(f"   [!] Optional: Could not import from policyengine.engine: {e}")
    print("   [i] This is OK if the sandbox doesn't use these imports")

print("\n" + "=" * 60)
print("[OK] All PolicyKit import tests passed!")
print("\nPolicyKit integration is working correctly.")
print("The sandbox can now use PolicyKit classes and functions directly.")
