"""Critic agent: reviews REVIEW/APPROVAL task output before it counts as DONE.

LLM verdict when a real provider is configured; honest mechanical checks
otherwise (never fake an LLM judgment with the echo provider).
"""
from manas.agents.base import BaseAgent
from manas.kernel.config import settings
from manas.kernel.registry import agents
from manas.kernel.taskgraph import Task


@agents.register("critic")
class CriticAgent(BaseAgent):
    name = "critic"
    purpose = "verify task output against done-criteria; approve or demand revision"
    prompt_layers = ("10_agent_rules.md",)
    memory_scopes = ("working", "episodic")

    async def review(self, task: Task) -> tuple[bool, str]:
        """Returns (approved, feedback)."""
        if settings.provider == "echo":           # mechanical fallback, labeled
            if not task.result.strip():
                return False, "mechanical check: empty result"
            return True, "mechanical check only (no LLM configured)"
        verdict = await self.think([{"role": "user", "content":
            f"TASK: {task.name}\nINSTRUCTION: {task.instruction}\n"
            f"DONE CRITERIA: {task.done_criteria or 'reasonable completion'}\n"
            f"OUTPUT:\n{task.result[:6000]}\n\n"
            "Reply with exactly 'VERDICT: APPROVE' or 'VERDICT: REVISE' on the "
            "first line, then one short paragraph of feedback."}])
        approved = "VERDICT: APPROVE" in verdict.upper()
        feedback = verdict.split("\n", 1)[-1].strip()
        return approved, feedback
