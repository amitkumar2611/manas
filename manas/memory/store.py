"""Phase 1 memory: JSONL-backed tiered store with scored retrieval.

Tiers: working | conversation | episodic | semantic | knowledge
Phase 2 swaps the backend for SQLite+vectors behind the same interface.
"""
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field

from manas.kernel.config import settings
from manas.kernel.registry import memories

TIERS = ("working", "conversation", "episodic", "semantic", "knowledge")


@dataclass
class Record:
    tier: str
    content: str
    source: str = "user"
    importance: float = 0.5
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    links: list[str] = field(default_factory=list)
    version: int = 1


@memories.register("jsonl")
class MemoryStore:
    def __init__(self) -> None:
        settings.ensure_dirs()
        self.path = settings.home / "memory" / "store.jsonl"
        self.path.touch(exist_ok=True)

    def write(self, rec: Record) -> str:
        if rec.tier not in TIERS:
            raise ValueError(f"unknown tier {rec.tier}")
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        return rec.id

    def _all(self) -> list[Record]:
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                out.append(Record(**json.loads(line)))
        return out

    def recall(self, query: str, tier: str | None = None, k: int = 5) -> list[Record]:
        """recency * importance * lexical-similarity (embeddings in Phase 2)."""
        q = set(query.lower().split())
        now = time.time()
        scored = []
        for r in self._all():
            if tier and r.tier != tier:
                continue
            words = set(r.content.lower().split())
            sim = len(q & words) / (len(q | words) or 1)
            recency = math.exp(-(now - r.created) / 86400 / 30)   # ~30d half-life
            scored.append((sim * 0.6 + r.importance * 0.25 + recency * 0.15, r))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [r for s, r in scored[:k] if s > 0]
