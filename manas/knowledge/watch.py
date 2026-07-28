"""Continuous ingestion: watch paths, re-ingest on change automatically.

Zero-dependency polling (mtime+size snapshot); Phase 4's engine already
guarantees the hard parts — idempotent chunks, stale-chunk archival — so
the watcher only needs to detect 'something changed' and call ingest_path.
Watched paths persist to ~/.manas/watch.json so daemons survive restarts.
"""
import json
import time
from pathlib import Path

from manas.kernel.config import settings
from manas.kernel.log import get_logger
from manas.knowledge import ingestors
from manas.knowledge.engine import ingest_path

log = get_logger("watch")


def _registry_file() -> Path:
    settings.ensure_dirs()
    return settings.home / "watch.json"


def add_watch(path: str) -> list[str]:
    paths = set(load_watches())
    paths.add(str(Path(path).expanduser().resolve()))
    _registry_file().write_text(json.dumps(sorted(paths)))
    return sorted(paths)


def load_watches() -> list[str]:
    f = _registry_file()
    return json.loads(f.read_text()) if f.exists() else []


def _snapshot(root: Path) -> dict[str, tuple[float, int]]:
    files = [root] if root.is_file() else list(ingestors.walk(root))
    out = {}
    for f in files:
        try:
            st = f.stat()
            out[str(f)] = (st.st_mtime, st.st_size)
        except FileNotFoundError:
            pass                                # raced a delete; next poll sees it
    return out


class Watcher:
    def __init__(self, paths: list[str] | None = None) -> None:
        self.paths = [Path(p) for p in (paths or load_watches())]
        self._snaps: dict[str, dict] = {}     # empty baseline: first poll
                                              # ingests every root (idempotent
                                              # anyway if already ingested)

    def poll_once(self) -> dict[str, dict]:
        """One cycle: re-ingest every root whose snapshot changed."""
        reports: dict[str, dict] = {}
        for p in self.paths:
            snap = _snapshot(p)
            if snap != self._snaps.get(str(p)):
                reports[str(p)] = ingest_path(p)
                self._snaps[str(p)] = snap
                log.info(f"reingested root={p} {reports[str(p)]}")
        return reports

    def run_forever(self, interval: float = 5.0) -> None:
        log.info(f"watching {len(self.paths)} path(s) every {interval}s")
        while True:
            self.poll_once()
            time.sleep(interval)
