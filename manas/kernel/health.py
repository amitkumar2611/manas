"""Deep health checks: every layer answers 'am I actually working?'"""
import shutil
import time
from pathlib import Path

from manas.kernel.config import settings


def _check(name: str, fn) -> dict:
    t0 = time.time()
    try:
        detail = fn()
        ok = True
    except Exception as e:  # noqa: BLE001 — a health check reports, never raises
        detail, ok = f"{type(e).__name__}: {e}", False
    return {"name": name, "ok": ok, "detail": str(detail)[:200],
            "ms": round((time.time() - t0) * 1000, 1)}


def run_checks() -> list[dict]:
    checks = []

    def prompts():
        root = Path(__file__).resolve().parents[2] / "prompts"
        n = len(list(root.glob("*.md")))
        assert n >= 7, f"only {n} prompt layers found"
        return f"{n} prompt layers"
    checks.append(_check("prompts", prompts))

    def memory():
        from manas.memory import get_store
        from manas.memory.store import Record
        store = get_store()
        rid = store.write(Record(tier="working", content="healthcheck",
                                 importance=0.05, source="health"))
        hits = store.recall("healthcheck", tier="working", k=1)
        assert hits and hits[0].id == rid
        return f"backend={settings.memory_backend} write+recall ok"
    checks.append(_check("memory", memory))

    def audit():
        from manas.kernel import audit as a
        a.record("health", "healthcheck", {}, "SAFE", None, "OK")
        return "audit append ok"
    checks.append(_check("audit", audit))

    def provider():
        from manas.kernel.registry import providers
        providers.get(settings.provider)
        return f"provider '{settings.provider}' registered"
    checks.append(_check("provider", provider))

    def disk():
        settings.ensure_dirs()
        free_gb = shutil.disk_usage(settings.home).free / 1e9
        assert free_gb > 0.5, f"only {free_gb:.2f} GB free"
        return f"{free_gb:.1f} GB free at {settings.home}"
    checks.append(_check("disk", disk))

    def registries():
        from manas.kernel.registry import agents, tools
        return f"{len(agents.names())} agents, {len(tools.names())} tools"
    checks.append(_check("registries", registries))

    return checks
