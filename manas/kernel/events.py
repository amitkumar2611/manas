"""Typed in-process event bus. Agents talk ONLY through this."""
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass
class Event:
    topic: str                       # e.g. "task.created", "tool.executed"
    payload: dict[str, Any]
    source: str = "kernel"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._subs.get(event.topic, []) + self._subs.get("*", [])
        await asyncio.gather(*(h(event) for h in handlers))


bus = EventBus()
