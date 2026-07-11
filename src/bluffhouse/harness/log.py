"""The append-only ground-truth event stream for one game.

The log stamps every event with a sequence number and id, fans it out to
subscribers (the harness subscribes agent projection), and round-trips to
JSONL. Log bytes are deterministic: same config, same agents, same bytes.
"""

from collections.abc import Callable
from pathlib import Path

from pydantic import TypeAdapter

from bluffhouse.models import GameEvent

_event_adapter: TypeAdapter[GameEvent] = TypeAdapter(GameEvent)


class EventLog:
    def __init__(self) -> None:
        self.events: list[GameEvent] = []
        self._subscribers: list[Callable[[GameEvent], None]] = []

    def subscribe(self, fn: Callable[[GameEvent], None]) -> None:
        self._subscribers.append(fn)

    def emit(self, event: GameEvent) -> GameEvent:
        n = len(self.events) + 1
        stamped = event.model_copy(update={"seq": n, "event_id": f"e{n:06d}"})
        self.events.append(stamped)
        for fn in self._subscribers:
            fn(stamped)
        return stamped

    def to_jsonl(self) -> str:
        return "".join(e.model_dump_json() + "\n" for e in self.events)

    def write_jsonl(self, path: str | Path) -> None:
        Path(path).write_text(self.to_jsonl(), encoding="utf-8")

    @classmethod
    def read_jsonl(cls, path: str | Path) -> "EventLog":
        log = cls()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                log.events.append(_event_adapter.validate_json(line))
        return log
