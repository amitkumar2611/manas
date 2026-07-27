"""GitHub Copilot chat completions adapter (ATIQ convention: GITHUB_COM_TOKEN).

Token exchange then OpenAI-compatible chat call, mirroring ATIQ v2's approach.
"""
import httpx

from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import providers


@providers.register("copilot")
class CopilotProvider:
    async def _session_token(self, c: httpx.AsyncClient) -> str:
        r = await c.get(
            "https://api.github.com/copilot_internal/v2/token",
            headers={"Authorization": f"token {settings.github_com_token}"})
        if r.status_code != 200:
            raise ProviderError(f"copilot token exchange {r.status_code}")
        return r.json()["token"]

    async def complete(self, system: str, messages: list[dict], model: str) -> str:
        if not settings.github_com_token:
            raise ProviderError("MANAS_GITHUB_COM_TOKEN not set")
        async with httpx.AsyncClient(timeout=120) as c:
            tok = await self._session_token(c)
            r = await c.post(
                "https://api.githubcopilot.com/chat/completions",
                headers={"Authorization": f"Bearer {tok}",
                         "Editor-Version": "vscode/1.90"},
                json={"model": model or "gpt-4o",
                      "messages": [{"role": "system", "content": system}, *messages]},
            )
        if r.status_code != 200:
            raise ProviderError(f"copilot {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]
