"""
Sandboxed execution tests.

PolicyKit equivalent: tests/test_exec_code.py
Tests the RestrictedPython sandbox:
- Permitted operations (math, string manipulation, json)
- Blocked operations (import, file access, __builtins__ escape)
- Guard functions (writable hook, getattr guard)

Sandbox: Same tests apply since we use the same borrowed code.
"""

# TODO: Port relevant tests from PolicyKit's test_exec_code.py
