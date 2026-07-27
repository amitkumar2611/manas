"""Anthropic Messages API adapter (raw HTTP, no SDK dependency).

Docs: https://docs.claude.com/en/api/overview
"""
import httpx

from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import providers


@providers.register("anthropic")
class AnthropicProvider:
    async def complete(self, system: str, messages: list[dict], model: str) -> str:
        if not settings.anthropic_api_key:
            raise ProviderError("MANAS_ANTHROPIC_API_KEY not set")
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.anthropic_api_key,
                         "anthropic-version": "2023-06-01"},
                json={"model": model or "claude-sonnet-4-5",
                      "max_tokens": 4096, "system": system,
                      "messages": messages},
            )
        if r.status_code != 200:
            raise ProviderError(f"anthropic {r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"])
