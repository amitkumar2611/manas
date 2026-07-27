"""Phase 2 memory backend: SQLite + embeddings, same interface as JSONL.

Adds over Phase 1: vector similarity recall, version history (semantic
records are never destructively edited), archival instead of deletion
(audited), and access-tracking that feeds retrieval scoring.
"""
import json
import math
import sqlite3
import time

from manas.kernel import audit
from manas.kernel.metrics import MEM_OPS
from manas.kernel.config import settings
from manas.kernel.registry import memories
from manas.memory.embed import cosine, from_blob, get_embedder, to_blob
from manas.memory.store import TIERS, Record

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  tier TEXT NOT NULL, content TEXT NOT NULL, source TEXT,
  importance REAL, created REAL, last_access REAL, access_count INTEGER,
  links TEXT, archived INTEGER NOT NULL DEFAULT 0, embedding BLOB,
  PRIMARY KEY (id, version));
CREATE INDEX IF NOT EXISTS idx_tier ON records(tier, archived);
"""


@memories.register("sqlite")
class SqliteMemoryStore:
    def __init__(self) -> None:
        settings.ensure_dirs()
        self.db = sqlite3.connect(settings.home / "memory" / "manas.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.embedder = get_embedder()

    # -- interface parity with Phase 1 -------------------------------------
    def write(self, rec: Record) -> str:
        if rec.tier not in TIERS:
            raise ValueError(f"unknown tier {rec.tier}")
        self.db.execute(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,0,?)",
            (rec.id, rec.version, rec.tier, rec.content, rec.source,
             rec.importance, rec.created, rec.last_access, rec.access_count,
             json.dumps(rec.links), to_blob(self.embedder.embed(rec.content))))
        self.db.commit()
        MEM_OPS.inc(op="write", tier=rec.tier)
        return rec.id

    def recall(self, query: str, tier: str | None = None, k: int = 5) -> list[Record]:
        """cosine * 0.6 + importance * 0.25 + recency * 0.15 (30d half-life)."""
        qv = self.embedder.embed(query)
        now = time.time()
        sql = ("SELECT * FROM records r WHERE archived=0 AND version="
               "(SELECT MAX(version) FROM records WHERE id=r.id)")
        args: tuple = ()
        if tier:
            sql += " AND tier=?"; args = (tier,)
        scored = []
        for row in self.db.execute(sql, args):
            sim = max(0.0, cosine(qv, from_blob(row["embedding"])))
            recency = math.exp(-(now - row["created"]) / 86400 / 30)
            score = sim * 0.6 + row["importance"] * 0.25 + recency * 0.15
            scored.append((score, sim, row))
        scored.sort(key=lambda t: t[0], reverse=True)
        hits = [t for t in scored[:k] if t[1] > 0.05 or t[0] > 0.2]
        for _, _, row in hits:  # access tracking feeds future scoring
            self.db.execute(
                "UPDATE records SET last_access=?, access_count=access_count+1 "
                "WHERE id=? AND version=?", (now, row["id"], row["version"]))
        self.db.commit()
        MEM_OPS.inc(op="recall", tier=tier or "all")
        return [self._to_rec(row) for _, _, row in hits]

    # -- Phase 2 additions --------------------------------------------------
    def update(self, rec_id: str, content: str, importance: float | None = None) -> int:
        """Semantic edits are versioned, never destructive."""
        row = self.db.execute(
            "SELECT * FROM records WHERE id=? ORDER BY version DESC LIMIT 1",
            (rec_id,)).fetchone()
        if not row:
            raise KeyError(rec_id)
        v = row["version"] + 1
        self.db.execute(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,0,?,0,?)",
            (rec_id, v, row["tier"], content, row["source"],
             importance if importance is not None else row["importance"],
             time.time(), time.time(), json.loads(row["links"] or "[]") and
             row["links"] or row["links"],
             to_blob(self.embedder.embed(content))))
        self.db.commit()
        return v

    def archive(self, rec_id: str, agent: str, reason: str) -> None:
        """Never delete — archive with an audit record (Layer 40 rule)."""
        self.db.execute("UPDATE records SET archived=1 WHERE id=?", (rec_id,))
        self.db.commit()
        audit.record(agent, "memory.archive", {"id": rec_id, "reason": reason},
                     "REVIEW", None, "OK")

    def history(self, rec_id: str) -> list[Record]:
        rows = self.db.execute(
            "SELECT * FROM records WHERE id=? ORDER BY version", (rec_id,))
        return [self._to_rec(r) for r in rows]

    def all_active(self, tier: str | None = None) -> list[Record]:
        sql = ("SELECT * FROM records r WHERE archived=0 AND version="
               "(SELECT MAX(version) FROM records WHERE id=r.id)")
        args: tuple = ()
        if tier:
            sql += " AND tier=?"; args = (tier,)
        return [self._to_rec(r) for r in self.db.execute(sql, args)]

    def decay(self, rec_id: str, version: int, new_importance: float) -> None:
        self.db.execute("UPDATE records SET importance=? WHERE id=? AND version=?",
                        (new_importance, rec_id, version))
        self.db.commit()

    def stats(self) -> dict:
        out = {t: 0 for t in TIERS}
        for row in self.db.execute(
                "SELECT tier, COUNT(DISTINCT id) c FROM records "
                "WHERE archived=0 GROUP BY tier"):
            out[row["tier"]] = row["c"]
        return out

    @staticmethod
    def _to_rec(row: sqlite3.Row) -> Record:
        return Record(id=row["id"], tier=row["tier"], content=row["content"],
                      source=row["source"], importance=row["importance"],
                      created=row["created"], last_access=row["last_access"],
                      access_count=row["access_count"],
                      links=json.loads(row["links"] or "[]"),
                      version=row["version"])
