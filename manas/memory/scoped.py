"""Split, encrypted memory stores — the Layer 40 rule made real.

Personal and enterprise memories live in SEPARATE SQLite files, each
encrypted at rest (Fernet) with its OWN key. Cross-store recall requires an
explicit scope grant per call — there is no ambient 'search everything'.
Keys auto-generate to ~/.manas/keys/<scope>.key (0600) if unset.
"""
from pathlib import Path

from cryptography.fernet import Fernet

from manas.kernel.auth import SYSTEM_USER, User
from manas.kernel.config import settings
from manas.kernel.errors import ToolDenied
from manas.memory.sqlite_store import SqliteMemoryStore
from manas.memory.store import Record

SCOPES = ("personal", "enterprise")


def _key(scope: str) -> bytes:
    env = getattr(settings, f"{scope}_key", "")
    if env:
        return env.encode()
    kdir = settings.home / "keys"
    kdir.mkdir(parents=True, exist_ok=True)
    kf = kdir / f"{scope}.key"
    if not kf.exists():
        kf.write_bytes(Fernet.generate_key())
        kf.chmod(0o600)
    return kf.read_bytes()


class ScopedStore(SqliteMemoryStore):
    """Same interface as SqliteMemoryStore; content encrypted at rest."""

    def __init__(self, scope: str) -> None:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        self.scope = scope
        self._fernet = Fernet(_key(scope))
        settings.ensure_dirs()
        import sqlite3
        from manas.memory.sqlite_store import _SCHEMA
        from manas.memory.embed import get_embedder
        self.db = sqlite3.connect(settings.home / "memory" / f"{scope}.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.embedder = get_embedder()

    # encrypt content on the way in; embedding is computed BEFORE encryption
    def write(self, rec: Record) -> str:
        plain = rec.content
        emb_rec = Record(**{**rec.__dict__})
        emb_rec.content = self._fernet.encrypt(plain.encode()).decode()
        # super().write embeds rec.content — so embed plain, store cipher:
        from manas.memory.embed import to_blob
        import json
        self.db.execute(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,0,?)",
            (rec.id, rec.version, rec.tier, emb_rec.content, rec.source,
             rec.importance, rec.created, rec.last_access, rec.access_count,
             json.dumps(rec.links), to_blob(self.embedder.embed(plain))))
        self.db.commit()
        return rec.id

    def _to_rec(self, row) -> Record:  # type: ignore[override]
        rec = SqliteMemoryStore._to_rec(row)
        rec.content = self._fernet.decrypt(rec.content.encode()).decode()
        return rec

    # recall() in the parent embeds the QUERY and compares vectors, then calls
    # self._to_rec -> decryption happens transparently for permitted callers.


def recall_across(query: str, grant: tuple[str, ...],
                  user: User = SYSTEM_USER, k: int = 5) -> list[Record]:
    """Cross-store recall. `grant` must EXPLICITLY name every scope searched;
    the user must hold each scope. No grant, no search — by design."""
    if not grant:
        raise ToolDenied("cross-store recall requires an explicit scope grant")
    hits: list[Record] = []
    for scope in grant:
        user.check_memory_scope(scope)
        hits += ScopedStore(scope).recall(query, k=k)
    return hits[:k]
