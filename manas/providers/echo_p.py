"""Offline fallback provider — keeps the whole OS runnable with zero keys."""
from manas.kernel.registry import providers


@providers.register("echo")
class EchoProvider:
    async def complete(self, system: str, messages: list[dict], model: str) -> str:
        last = messages[-1]["content"] if messages else ""
        return (f"[echo provider — no LLM configured]\n"
                f"system chars={len(system)} | last user message:\n{last}")

    async def stream(self, system: str, messages: list[dict], model: str):
        for word in (await self.complete(system, messages, model)).split(" "):
            yield word + " "
