"""
Event dispatch and handling.

PolicyKit equivalent: policyengine/handlers.py
Sandbox equivalent: EventBus with in-memory pub/sub and time simulation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    timestamp: float = 0.0

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


EventHandler = Callable[[Event, Any], None]


class EventLog:
    """Queryable event history."""

    def __init__(self):
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    def query(
        self,
        event_type: str | None = None,
        actor_id: str | None = None,
        after: float | None = None,
        before: float | None = None,
    ) -> list[Event]:
        results = self._events
        if event_type is not None:
            results = [e for e in results if e.type == event_type]
        if actor_id is not None:
            results = [e for e in results if e.actor_id == actor_id]
        if after is not None:
            results = [e for e in results if e.timestamp > after]
        if before is not None:
            results = [e for e in results if e.timestamp < before]
        return results

    def all(self) -> list[Event]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)


@dataclass
class ScheduledTask:
    interval: float
    handler: EventHandler
    next_fire: float
    recurring: bool = True


class EventBus:
    """In-memory pub/sub with simulated time."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._scheduled: list[ScheduledTask] = []
        self._time: float = 0.0
        self.log: EventLog = EventLog()

    @property
    def current_time(self) -> float:
        return self._time

    def register(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def schedule(self, interval: float, handler: EventHandler, recurring: bool = True) -> None:
        task = ScheduledTask(
            interval=interval,
            handler=handler,
            next_fire=self._time + interval,
            recurring=recurring,
        )
        self._scheduled.append(task)

    def emit(self, event: Event, ctx: Any = None) -> list[Any]:
        if event.timestamp == 0.0:
            event.timestamp = self._time
        else:
            self._time = max(self._time, event.timestamp)

        self.log.append(event)

        results = []
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            result = handler(event, ctx)
            results.append(result)

        return results

    def advance_time(self, to: float, ctx: Any = None) -> None:
        """Fire any scheduled tasks whose next_fire <= to.

        This method serves as the bridge between scheduled tasks and __tick__ events:
        - Scheduled tasks (via ctx.schedule) are fired at their scheduled intervals
        - Each scheduled task execution also triggers registered __tick__ handlers
        - This allows scripts written for production (using schedule) to work in tests
        """
        while True:
            pending = [t for t in self._scheduled if t.next_fire <= to]
            if not pending:
                break
            pending.sort(key=lambda t: t.next_fire)
            task = pending[0]
            self._time = task.next_fire

            # Create tick event for this scheduled task firing
            tick_event = Event(type="__tick__", timestamp=self._time)

            # Call the scheduled task handler directly
            task.handler(tick_event, ctx)

            # Also emit the __tick__ event to trigger any registered __tick__ handlers
            # This bridges scheduled tasks with event-driven handlers
            self._emit_to_handlers(tick_event, ctx)

            if task.recurring:
                task.next_fire += task.interval
            else:
                self._scheduled.remove(task)
        self._time = to

    def _emit_to_handlers(self, event: Event, ctx: Any = None) -> list[Any]:
        """Internal: emit event to registered handlers without logging or time update.

        Used by advance_time to trigger __tick__ handlers when scheduled tasks fire.
        """
        results = []
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            result = handler(event, ctx)
            results.append(result)
        return results

    def reset(self) -> None:
        self._handlers.clear()
        self._scheduled.clear()
        self._time = 0.0
        self.log = EventLog()
