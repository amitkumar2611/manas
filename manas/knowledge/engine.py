"""Ingestion engine: files/repos/tickets -> deduplicated knowledge records.

Idempotency: record id = blake2(source, chunk index, content). Re-ingesting
unchanged content is a no-op; changed content produces new records and the
stale ones are archived (never deleted) with an audit trail.
"""
import hashlib
import json
from pathlib import Path

from manas.kernel.config import settings
from manas.kernel.errors import ManasError
from manas.kernel.log import get_logger
from manas.knowledge import ingestors
from manas.knowledge.chunk import split
from manas.memory import get_store
from manas.memory.store import Record

log = get_logger("knowledge")


def _rid(source: str, index: int, text: str) -> str:
    return hashlib.blake2b(f"{source}#{index}#{text}".encode(),
                           digest_size=6).hexdigest()


def _store():
    store = get_store()
    if settings.memory_backend != "sqlite":
        raise ManasError("knowledge engine requires MANAS_MEMORY_BACKEND=sqlite")
    return store


def ingest_path(path: str | Path) -> dict:
    """Ingest a file or a whole directory/repo into the knowledge tier."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise ManasError(f"no such path: {root}")
    store = _store()
    known = {r.id for r in store.all_active("knowledge")}
    files = [root] if root.is_file() else list(ingestors.walk(root))
    report = {"files": 0, "chunks_new": 0, "chunks_unchanged": 0, "skipped": 0}
    fresh: set[str] = set()
    touched_sources: set[str] = set()
    for f in files:
        loaded = ingestors.read(f)
        if loaded is None:
            report["skipped"] += 1
            continue
        text, kind = loaded
        src = str(f)
        touched_sources.add(src)
        report["files"] += 1
        for ch in split(text, source=src, kind=kind):
            rid = _rid(ch.source, ch.index, ch.text)
            fresh.add(rid)
            if rid in known:
                report["chunks_unchanged"] += 1
                continue
            store.write(Record(id=rid, tier="knowledge", source=ch.source,
                               importance=0.5, links=[f"kind:{ch.kind}",
                                                      f"chunk:{ch.index}"],
                               content=f"[{ch.kind}] {ch.source}\n{ch.text}"))
            report["chunks_new"] += 1
    # Archive stale chunks of re-ingested sources (content changed/removed).
    stale = [r for r in store.all_active("knowledge")
             if r.source in touched_sources and r.id not in fresh]
    for r in stale:
        store.archive(r.id, "knowledge", "superseded by re-ingest")
    report["chunks_archived"] = len(stale)
    log.info(f"ingest root={root.name} {report}")
    return report


def ingest_ticket(ticket: dict) -> str:
    """Generic ticket ingestion (Jira-shaped dict; live APIs arrive Phase 5).

    Routing-intelligence rule carried over from ATIQ: description + comments
    are the primary signal, so they lead the record content.
    """
    key = ticket.get("key") or ticket.get("id")
    if not key:
        raise ManasError("ticket needs a 'key' or 'id'")
    parts = [f"[ticket] {key}: {ticket.get('summary', '')}".strip(),
             ticket.get("description", "").strip()]
    parts += [f"comment: {c}" for c in ticket.get("comments", [])]
    if ticket.get("status"):
        parts.append(f"status: {ticket['status']}")
    text = "\n".join(p for p in parts if p)
    store = _store()
    rid = _rid(f"ticket:{key}", 0, text)
    if not any(r.id == rid for r in store.all_active("knowledge")):
        store.write(Record(id=rid, tier="knowledge", source=f"ticket:{key}",
                           importance=0.6, links=["kind:ticket"], content=text))
    return rid


def ingest_ticket_file(path: str | Path) -> list[str]:
    """Ingest a JSON file containing one ticket or a list of tickets."""
    data = json.loads(Path(path).read_text())
    return [ingest_ticket(t) for t in (data if isinstance(data, list) else [data])]
