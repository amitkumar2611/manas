"""Ollama adapter — the local-first default once a model is pulled."""
import httpx

from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import providers


@providers.register("ollama")
class OllamaProvider:
    async def complete(self, system: str, messages: list[dict], model: str) -> str:
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{settings.ollama_url}/api/chat",
                json={"model": model or "llama3.1", "stream": False,
                      "messages": [{"role": "system", "content": system}, *messages]},
            )
        if r.status_code != 200:
            raise ProviderError(f"ollama {r.status_code}: {r.text[:300]}")
        return r.json()["message"]["content"]
