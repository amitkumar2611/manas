"""MANAS HTTP API — same kernel, different presentation layer.

Run: uvicorn manas.api:app --port 8420
"""
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from manas import __version__
from manas.agents.assistant import AssistantAgent
from manas.kernel.registry import agents, providers, tools

app = FastAPI(title="MANAS", version=__version__)
_assistant = AssistantAgent()


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


@app.get("/health")
def health() -> dict:
    """Liveness: fast, no side effects."""
    return {"status": "ok", "version": __version__,
            "agents": agents.names(), "tools": tools.names(),
            "providers": providers.names()}


@app.get("/healthz")
def healthz() -> dict:
    """Readiness: deep checks across every layer."""
    from manas.kernel.health import run_checks
    checks = run_checks()
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus text exposition."""
    from manas.kernel.metrics import registry as mreg
    return mreg.render()


@app.get("/traces")
def traces(n: int = 5) -> list:
    from manas.kernel.trace import recent
    return recent(n)


@app.post("/chat")
async def chat(body: ChatIn) -> dict:
    reply = await _assistant.chat(body.message, body.history)
    return {"reply": reply}
