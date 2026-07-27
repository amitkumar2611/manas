"""Append-only audit log for every tool invocation (see prompts/30_security.md)."""
import hashlib
import json
from datetime import datetime, timezone

from manas.kernel.config import settings


def record(agent: str, tool: str, args: dict, risk: str,
           approved_by: str | None, status: str) -> None:
    settings.ensure_dirs()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "tool": tool,
        "args_hash": hashlib.sha256(
            json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16],
        "risk": risk,
        "approved_by": approved_by,
        "status": status,
    }
    path = settings.home / "audit" / "audit.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
