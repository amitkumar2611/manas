"""Agent contract per prompts/10_agent_rules.md — schema enforced at import."""
from pathlib import Path

from manas.kernel.events import Event, bus
from manas.memory import get_store
from manas.memory.store import Record
from manas.providers.base import complete
from manas.tools.gate import ToolGate

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def load_layers(*names: str) -> str:
    """Hierarchical prompt loading: core identity + only the layers needed."""
    parts = [(PROMPTS / "00_core_identity.md").read_text()]
    parts += [(PROMPTS / n).read_text() for n in names]
    return "\n\n".join(parts)


class BaseAgent:
    name: str = "base"
    purpose: str = ""
    prompt_layers: tuple[str, ...] = ()
    tool_allowlist: tuple[str, ...] = ()
    memory_scopes: tuple[str, ...] = ("working",)
    risk_level: str = "SAFE"

    def __init__(self, gate: ToolGate | None = None) -> None:
        self.gate = gate or ToolGate()
        self.memory = get_store()
        self.system = load_layers(*self.prompt_layers) + (
            f"\n\n## YOUR AGENT IDENTITY\nname: {self.name}\npurpose: {self.purpose}")

    async def think(self, messages: list[dict]) -> str:
        return await complete(self.system, messages)

    async def use_tool(self, tool: str, **kwargs) -> object:
        if tool not in self.tool_allowlist:
            raise PermissionError(f"{self.name} not allowed tool '{tool}'")
        return await self.gate.run(self.name, tool, **kwargs)

    async def remember(self, content: str, tier: str = "episodic",
                       importance: float = 0.5) -> str:
        if tier not in self.memory_scopes:
            raise PermissionError(f"{self.name} cannot write tier '{tier}'")
        rid = self.memory.write(Record(tier=tier, content=content,
                                       source=self.name, importance=importance))
        await bus.publish(Event("memory.written",
                                {"id": rid, "tier": tier}, source=self.name))
        return rid
