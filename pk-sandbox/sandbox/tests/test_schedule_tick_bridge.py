"""
Test to verify that ctx.schedule() and __tick__ events work together.

This test demonstrates the bridging logic:
- Scripts can use ctx.schedule() for production code
- Tests can use __tick__ events to advance time
- Both mechanisms trigger the appropriate handlers
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "sandboxengine"))

from policyengine.engine import SandboxRunner, Scenario, ScenarioEvent, Assertion


def test_schedule_fires_on_tick_events():
    """Verify scheduled tasks fire when __tick__ events advance time."""

    script = """
def setup(ctx):
    ctx.store.set("schedule_count", 0)
    ctx.store.set("tick_count", 0)

    # Scheduled task - should fire at time 60, 120, 180, etc.
    def scheduled_handler(event, ctx):
        count = ctx.store.get("schedule_count", 0)
        ctx.store.set("schedule_count", count + 1)

    ctx.schedule(60, scheduled_handler)

    # Registered __tick__ handler - should fire when scheduled tasks fire
    def tick_handler(event, ctx):
        count = ctx.store.get("tick_count", 0)
        ctx.store.set("tick_count", count + 1)

    ctx.on("__tick__", tick_handler)
"""

    scenario = Scenario(
        name="test_schedule_tick_bridge",
        description="Verify scheduled tasks and __tick__ handlers both fire",
        community_setup={"users": [], "channels": [], "roles": []},
        events=[
            # Advance time to 200 seconds - should fire scheduled task 3 times (60, 120, 180)
            ScenarioEvent(type="__tick__", at=200.0),
        ],
        assertions=[
            # Scheduled handler should have fired 3 times
            Assertion(
                type="store_equals",
                expected={"key": "schedule_count", "value": 3},
                description="Scheduled handler fired 3 times (at 60, 120, 180)"
            ),
            # Tick handler should also have fired 3 times (bridged from scheduled tasks)
            Assertion(
                type="store_equals",
                expected={"key": "tick_count", "value": 3},
                description="Tick handler fired 3 times (bridged from scheduled tasks)"
            ),
        ],
    )

    runner = SandboxRunner()
    result = runner.run(script, scenario)

    print(f"\n{'='*60}")
    print(f"Scenario: {result.scenario_name}")
    print(f"Passed: {result.passed}")
    print(f"{'='*60}")

    for assertion in result.assertion_results:
        status = "PASS" if assertion["passed"] else "FAIL"
        print(f"[{status}] {assertion['assertion']}: {assertion['detail']}")

    if result.error:
        print(f"\nError: {result.error}")

    assert result.passed, f"Test failed: {result.assertion_results}"


def test_schedule_without_tick_handlers():
    """Verify scripts using only ctx.schedule() work correctly."""

    script = """
def setup(ctx):
    ctx.store.set("deadline_checked", False)

    def check_deadlines(event, ctx):
        # Simulate checking a 2-day deadline
        if ctx.current_time >= 172800:  # 2 days in seconds
            ctx.store.set("deadline_checked", True)

    # Only use schedule, no __tick__ handler registration
    ctx.schedule(60, check_deadlines)
"""

    scenario = Scenario(
        name="test_schedule_only",
        description="Scripts using only schedule() should work",
        community_setup={"users": [], "channels": [], "roles": []},
        events=[
            # Advance time to 2 days
            ScenarioEvent(type="__tick__", at=172800.0),
        ],
        assertions=[
            Assertion(
                type="store_equals",
                expected={"key": "deadline_checked", "value": True},
                description="Deadline check ran via scheduled task"
            ),
        ],
    )

    runner = SandboxRunner()
    result = runner.run(script, scenario)

    print(f"\n{'='*60}")
    print(f"Scenario: {result.scenario_name}")
    print(f"Passed: {result.passed}")
    print(f"{'='*60}")

    for assertion in result.assertion_results:
        status = "PASS" if assertion["passed"] else "FAIL"
        print(f"[{status}] {assertion['assertion']}: {assertion['detail']}")

    assert result.passed, f"Test failed: {result.assertion_results}"


if __name__ == "__main__":
    print("Testing schedule/tick bridging logic...\n")

    try:
        test_schedule_fires_on_tick_events()
        print("\n[PASS] Bridge test passed!\n")
    except AssertionError as e:
        print(f"\n[FAIL] Bridge test failed: {e}\n")

    try:
        test_schedule_without_tick_handlers()
        print("\n[PASS] Schedule-only test passed!\n")
    except AssertionError as e:
        print(f"\n[FAIL] Schedule-only test failed: {e}\n")

    print("\nAll tests completed!")
