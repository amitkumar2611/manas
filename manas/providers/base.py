"""Provider contract. Domain code calls complete(); adapters do the rest."""
import time
from typing import Protocol

from manas.kernel.config import settings
from manas.kernel.metrics import LLM_LAT, LLM_REQS
from manas.kernel.registry import providers
from manas.kernel.trace import span


class Provider(Protocol):
    async def complete(self, system: str, messages: list[dict], model: str) -> str: ...


async def complete(system: str, messages: list[dict],
                   provider: str | None = None, model: str | None = None) -> str:
    """Single entry point for all LLM calls in MANAS. Instrumented."""
    name = provider or settings.provider
    p: Provider = providers.get(name)()
    t0 = time.time()
    with span("llm.complete", provider=name, messages=len(messages)):
        try:
            out = await p.complete(system, messages, model or settings.model)
        except Exception:
            LLM_REQS.inc(provider=name, status="error")
            LLM_LAT.observe(time.time() - t0, provider=name)
            raise
    LLM_REQS.inc(provider=name, status="ok")
    LLM_LAT.observe(time.time() - t0, provider=name)
    return out
