"""Tracing: nested spans across agent -> tool -> provider calls.

contextvars propagate the active span through async code; completed root
traces are persisted as JSONL (~/.manas/traces/) for `manas traces` and
future OpenTelemetry export. Attribute values are kept short and secrets
never belong in span attrs (log scrubbing is not a license to leak here).
"""
import contextvars
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from manas.kernel.config import settings

_current: contextvars.ContextVar["Span | None"] = \
    contextvars.ContextVar("manas_span", default=None)
MAX_TRACE_FILES = 200


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_id: str | None = None
    start: float = field(default_factory=time.time)
    end: float = 0.0
    status: str = "OK"
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "span_id": self.span_id,
                "parent_id": self.parent_id, "status": self.status,
                "ms": round((self.end - self.start) * 1000, 2),
                "attrs": self.attrs,
                "children": [c.to_dict() for c in self.children]}


def _persist(root: Span) -> None:
    settings.ensure_dirs()
    d = settings.home / "traces"
    d.mkdir(exist_ok=True)
    (d / f"{root.trace_id}.json").write_text(json.dumps(
        {"trace_id": root.trace_id, "root": root.to_dict()}, indent=1))
    files = sorted(d.glob("*.json"))
    for old in files[:-MAX_TRACE_FILES]:           # bounded disk usage
        old.unlink()


@contextmanager
def span(name: str, **attrs):
    parent = _current.get()
    s = Span(name=name,
             trace_id=parent.trace_id if parent else uuid.uuid4().hex[:12],
             parent_id=parent.span_id if parent else None,
             attrs={k: str(v)[:120] for k, v in attrs.items()})
    if parent:
        parent.children.append(s)
    token = _current.set(s)
    try:
        yield s
    except Exception:
        s.status = "ERROR"
        raise
    finally:
        s.end = time.time()
        _current.reset(token)
        if parent is None:
            _persist(s)


def recent(n: int = 5) -> list[dict]:
    d = settings.home / "traces"
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json"))[-n:]:
        out.append(json.loads(f.read_text()))
    return out
