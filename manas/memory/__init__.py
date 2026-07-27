"""Memory layer: tiered stores per prompts/40_memory.md.

get_store() is the ONLY way domain code obtains memory — backend is config,
not code (MANAS_MEMORY_BACKEND=sqlite|jsonl). Non-regression: a legacy
Phase 1 JSONL store is auto-migrated into SQLite on first use.
"""
from manas.kernel.config import settings
from manas.kernel.log import get_logger
from manas.kernel.registry import memories
from manas.memory import sqlite_store  # noqa: F401  (registration)
from manas.memory.store import MemoryStore, Record  # noqa: F401

log = get_logger("memory")
_migrated = False


def _migrate_jsonl_once(store) -> None:
    global _migrated
    if _migrated:
        return
    _migrated = True
    legacy = settings.home / "memory" / "store.jsonl"
    marker = settings.home / "memory" / ".migrated"
    if legacy.exists() and not marker.exists() and legacy.stat().st_size:
        n = 0
        for rec in MemoryStore()._all():
            store.write(rec); n += 1
        marker.touch()
        log.info(f"migrated={n} records jsonl->sqlite (jsonl kept as backup)")


def get_store():
    store = memories.get(settings.memory_backend)()
    if settings.memory_backend == "sqlite":
        _migrate_jsonl_once(store)
    return store
