"""Learning agent: the self-improvement loop (prompts/50_planning.md step 6).

After every orchestrated run: compare outcome vs. plan, distill the delta
into an episodic 'lesson', and feed relevant past lessons into the NEXT
plan — so every plan starts smarter than the last. Lessons are honest:
mechanical deltas when no LLM is configured, never invented insight.
"""
import time

from manas.agents.base import BaseAgent
from manas.kernel.config import settings
from manas.kernel.metrics import registry as mreg
from manas.kernel.registry import agents
from manas.kernel.taskgraph import TaskGraph
from manas.memory.store import Record

REFLECTIONS = mreg.counter("manas_reflections_total",
                           "Post-run reflections by outcome")


@agents.register("learning")
class LearningAgent(BaseAgent):
    name = "learning"
    purpose = "reflect on finished runs; turn plan-vs-outcome deltas into lessons"
    prompt_layers = ("50_planning.md",)
    memory_scopes = ("working", "episodic")

    async def reflect(self, graph: TaskGraph) -> str:
        done = [t for t in graph.tasks if t.status == "DONE"]
        failed = [t for t in graph.tasks if t.status == "FAILED"]
        human = [t for t in graph.tasks if t.status == "NEED_HUMAN"]
        retried = [t for t in graph.tasks if t.attempts > 1]
        outcome = ("success" if len(done) == len(graph.tasks)
                   else "partial" if done else "failure")

        delta = (f"outcome={outcome} done={len(done)}/{len(graph.tasks)} "
                 f"failed={[t.name for t in failed]} "
                 f"needed_human={[t.name for t in human]} "
                 f"retried={[f'{t.name}x{t.attempts}' for t in retried]}")
        lesson = ""
        if settings.provider != "echo" and (failed or human or retried):
            try:
                lesson = await self.think([{"role": "user", "content":
                    f"GOAL: {graph.goal}\nRUN DELTA: {delta}\n"
                    "Task feedback:\n" + "\n".join(
                        f"- {t.name}: {t.feedback}" for t in graph.tasks
                        if t.feedback) +
                    "\nState ONE actionable lesson for planning similar goals "
                    "next time (a single sentence)."}])
            except Exception:                       # reflection must never break a run
                lesson = ""
        content = (f"lesson[{outcome}] goal='{graph.goal[:150]}' {delta}"
                   + (f" => {lesson.strip()[:300]}" if lesson.strip() else ""))
        importance = {"success": 0.4, "partial": 0.6, "failure": 0.8}[outcome]
        rid = self.memory.write(Record(
            tier="episodic", content=content, source="learning",
            importance=importance, links=[f"graph:{graph.id}"]))
        REFLECTIONS.inc(outcome=outcome)
        return rid

    def lessons_for(self, goal: str, k: int = 3) -> str:
        """Relevant past lessons, formatted for injection into a new plan."""
        hits = [r for r in self.memory.recall(goal, tier="episodic", k=k * 2)
                if r.source == "learning"][:k]
        if not hits:
            return ""
        def age(r):
            d = int((time.time() - r.created) / 86400)
            return "today" if d == 0 else f"{d}d ago"
        return "\n".join(f"- ({age(r)}) {r.content}" for r in hits)
