"""Simple event bus for decoupled module communication."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    """Publish-subscribe event system.

    Usage:
        bus = EventBus()
        bus.on("model_updated", lambda solid: print("Updated!"))
        bus.emit("model_updated", my_solid)
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable) -> None:
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for cb in self._listeners.get(event, []):
            cb(*args, **kwargs)

    def clear(self, event: str | None = None) -> None:
        if event:
            self._listeners.pop(event, None)
        else:
            self._listeners.clear()
