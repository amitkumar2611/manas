"""Provider contract + hardening: retry/backoff, fallback chain, routing,
token & cost accounting, streaming. Instrumented (Phase 7).

Degradation ladder for a flaky provider:
  attempt (retries w/ exponential backoff) -> next provider in
  MANAS_PROVIDER_FALLBACKS -> ProviderError with full failure history.
"""
import asyncio
import time
from typing import AsyncIterator, Protocol

from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.log import get_logger
from manas.kernel.metrics import LLM_LAT, LLM_REQS, registry as mreg
from manas.kernel.registry import providers
from manas.kernel.trace import span

log = get_logger("providers")
LLM_TOKENS = mreg.counter("manas_llm_tokens_total",
                          "Estimated tokens by provider and direction")
LLM_COST = mreg.counter("manas_llm_cost_usd_total",
                        "Estimated cost (USD) by provider")
RETRIES = 3
BACKOFF = 0.5           # seconds, doubles per retry


class Provider(Protocol):
    async def complete(self, system: str, messages: list[dict], model: str) -> str: ...


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)               # honest estimate, labeled as such


def _account(provider: str, prompt: str, output: str) -> None:
    tin, tout = _est_tokens(prompt), _est_tokens(output)
    LLM_TOKENS.inc(tin, provider=provider, direction="in")
    LLM_TOKENS.inc(tout, provider=provider, direction="out")
    # MANAS_COST_PER_MTOK e.g. "anthropic=3:15,ollama=0:0"  (in:out USD/Mtok)
    for part in settings.cost_per_mtok.split(","):
        if "=" in part and part.split("=")[0].strip() == provider:
            cin, cout = (float(x) for x in part.split("=")[1].split(":"))
            LLM_COST.inc(tin / 1e6 * cin + tout / 1e6 * cout, provider=provider)


def _route(purpose: str | None) -> tuple[str | None, str | None]:
    """MANAS_ROUTES e.g. 'critic=ollama:llama3.1,plan=anthropic:claude-x'"""
    if not purpose:
        return None, None
    for part in settings.routes.split(","):
        if "=" in part and part.split("=")[0].strip() == purpose:
            target = part.split("=")[1]
            prov, _, model = target.partition(":")
            return prov.strip() or None, model.strip() or None
    return None, None


async def _attempt(name: str, system: str, messages: list[dict],
                   model: str | None) -> str:
    p: Provider = providers.get(name)()
    last: Exception | None = None
    for i in range(RETRIES):
        t0 = time.time()
        try:
            with span("llm.complete", provider=name, attempt=i + 1,
                      messages=len(messages)):
                out = await p.complete(system, messages,
                                       model or settings.model)
            LLM_REQS.inc(provider=name, status="ok")
            LLM_LAT.observe(time.time() - t0, provider=name)
            _account(name, system + "".join(m["content"] for m in messages), out)
            return out
        except Exception as e:  # noqa: BLE001 — retried, then surfaced
            last = e
            LLM_REQS.inc(provider=name, status="error")
            LLM_LAT.observe(time.time() - t0, provider=name)
            if i < RETRIES - 1:
                await asyncio.sleep(BACKOFF * (2 ** i))
    raise ProviderError(f"{name} failed after {RETRIES} attempts: {last}")


async def complete(system: str, messages: list[dict],
                   provider: str | None = None, model: str | None = None,
                   purpose: str | None = None) -> str:
    """Single entry point for all LLM calls. Routing > explicit > default,
    then the fallback chain."""
    rp, rm = _route(purpose)
    chain = [rp or provider or settings.provider]
    chain += [c.strip() for c in settings.provider_fallbacks.split(",")
              if c.strip() and c.strip() not in chain]
    errors = []
    for name in chain:
        try:
            return await _attempt(name, system, messages, rm or model)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            if name != chain[-1]:
                log.info(f"provider fallback from={name}")
    raise ProviderError(" | ".join(errors))


async def stream(system: str, messages: list[dict],
                 provider: str | None = None) -> AsyncIterator[str]:
    """Streaming when the provider supports it; single-chunk fallback when not
    (honest: no fake token pacing)."""
    name = provider or settings.provider
    p = providers.get(name)()
    if hasattr(p, "stream"):
        async for chunk in p.stream(system, messages, settings.model):
            yield chunk
    else:
        yield await complete(system, messages, provider=name)
