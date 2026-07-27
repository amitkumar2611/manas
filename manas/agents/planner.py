"""Planner agent: goal -> phased task DAG (prompts/50_planning.md)."""
import json
from datetime import datetime, timezone

from manas.agents.base import BaseAgent
from manas.kernel.config import settings
from manas.kernel.registry import agents


@agents.register("planner")
class PlannerAgent(BaseAgent):
    name = "planner"
    purpose = "decompose goals into phased, risk-labeled task DAGs"
    prompt_layers = ("10_agent_rules.md", "50_planning.md")
    memory_scopes = ("working", "episodic")

    async def plan(self, goal: str) -> str:
        messages = [{"role": "user", "content":
                    f"GOAL: {goal}\n\nProduce a phased plan per Layer 50. "
                    f"Phase 0 must be recon of actual current state."}]
        plan = await self.think(messages)
        settings.ensure_dirs()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = settings.home / "plans" / f"plan-{ts}.md"
        path.write_text(f"# Goal\n{goal}\n\n{plan}\n")
        await self.remember(f"planned: {goal[:200]}", importance=0.7)
        return json.dumps({"plan_file": str(path), "plan": plan})
